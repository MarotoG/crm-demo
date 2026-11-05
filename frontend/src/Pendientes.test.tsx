// Pruebas del panel de pendientes y del contador de la barra (T25), con una API falsa en fetch.

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { TareaSeguimiento } from "./api";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = { metodo: string; url: string; ruta: string; cuerpo: unknown };

const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };
const PROFESIONAL = { id: 3, email: "prof@prueba.example.com", role: "professional", csrf_token: "csrf-prof" };
const CLIENTE = { id: 9, email: "ana@clinica.example.com", role: "client", csrf_token: "csrf-cliente" };

const HOY = "2027-01-11";

const BASE: TareaSeguimiento = {
  id: 1,
  contact_id: 7,
  contact_name: "Ana Smith",
  contact_status: "new",
  description: "Tarea",
  due_on: HOY,
  assigned_to_id: 3,
  assigned_to_email: "prof@prueba.example.com",
  created_by_email: "recepcion@prueba.example.com",
  created_at: "2026-11-04T15:00:00Z",
  completed_at: null,
  completed_by_email: null,
  version: 1,
};

const VENCIDA = { ...BASE, id: 1, due_on: "2027-01-10", description: "Llamar ayer" };
const DE_HOY = { ...BASE, id: 2, description: "Llamar hoy", contact_name: "Lara Lost", contact_status: "lost" as const };
const PROXIMA = { ...BASE, id: 3, due_on: "2027-01-20", description: "Llamar luego" };
const HECHA = { ...BASE, id: 4, description: "Ya llamada", completed_at: "2027-01-10T16:00:00Z", completed_by_email: "prof@prueba.example.com", version: 2 };

const lista = (items: TareaSeguimiento[], total = items.length) => ({ status: 200, cuerpo: { today: HOY, total, items } });

let usuario: typeof RECEPCION;
let rutas: Record<string, (cuerpo: unknown, url: URL) => Respuesta>;
let llamadas: Llamada[];

beforeEach(() => {
  llamadas = [];
  usuario = RECEPCION;
  rutas = {
    "GET /api/auth/me": () => ({ status: 200, cuerpo: usuario }),
    "GET /api/services/staff": () => ({ status: 200, cuerpo: [{ id: 3, email: "prof@prueba.example.com", role: "professional", active: true }] }),
    "GET /api/follow-ups/summary": () => ({ status: 200, cuerpo: { overdue: 1, due_today: 1 } }),
    "GET /api/follow-ups": (_c, url) => (url.searchParams.get("state") === "done" ? lista([HECHA]) : lista([VENCIDA, DE_HOY, PROXIMA])),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (ruta: string, init: RequestInit = {}) => {
      const metodo = init.method ?? "GET";
      const cuerpo = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      const url = new URL(ruta, "http://localhost");
      llamadas.push({ metodo, url: url.pathname + url.search, ruta: url.pathname, cuerpo });
      const r = rutas[`${metodo} ${url.pathname}`]?.(cuerpo, url) ?? { status: 404, cuerpo: { detail: "No encontrado" } };
      return new Response(r.cuerpo === undefined ? null : JSON.stringify(r.cuerpo), {
        status: r.status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function abrir(ruta = "/pendientes") {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const titulo = (nombre: string) => screen.findByRole("heading", { name: nombre });
const lecturas = () => llamadas.filter((l) => l.metodo === "GET" && l.ruta === "/api/follow-ups").map((l) => l.url);
const lecturasResumen = () => llamadas.filter((l) => l.ruta === "/api/follow-ups/summary").length;

describe("panel", () => {
  it("agrupa las pendientes en vencidas, hoy y próximas según el día de la API", async () => {
    abrir();
    const vencidas = (await titulo("Vencidas (1)")).nextElementSibling as HTMLElement;
    expect(within(vencidas).getByText("Llamar ayer")).toBeTruthy();
    expect(within(vencidas).getByText("Vencida")).toBeTruthy();
    const hoy = screen.getByRole("heading", { name: "Hoy (1)" }).nextElementSibling as HTMLElement;
    expect(within(hoy).getByText("Llamar hoy")).toBeTruthy();
    expect(within(hoy).queryByText("Vencida")).toBeNull();
    const proximas = screen.getByRole("heading", { name: "Próximas (1)" }).nextElementSibling as HTMLElement;
    expect(within(proximas).getByText("Llamar luego")).toBeTruthy();
    expect(lecturas()[0]).toBe("/api/follow-ups?state=pending");
  });

  it("no enseña un grupo vacío", async () => {
    rutas["GET /api/follow-ups"] = () => lista([DE_HOY]);
    abrir();
    await titulo("Hoy (1)");
    expect(screen.queryByRole("heading", { name: /Vencidas/ })).toBeNull();
    expect(screen.queryByRole("heading", { name: /Próximas/ })).toBeNull();
  });

  it("cada tarea enlaza a la ficha, dice de quién es y avisa si el contacto está Perdido", async () => {
    abrir();
    const fila = (await screen.findByText("Llamar hoy")).closest("li") as HTMLElement;
    expect(within(fila).getByRole("link", { name: "Lara Lost" }).getAttribute("href")).toBe("/contactos/7");
    expect(within(fila).getByText("Perdido")).toBeTruthy();
    expect(within(fila).getByText("Responsable: prof@prueba.example.com")).toBeTruthy();
    const otra = screen.getByText("Llamar ayer").closest("li") as HTMLElement;
    expect(within(otra).queryByText("Perdido")).toBeNull();
  });

  it("sin pendientes lo dice", async () => {
    rutas["GET /api/follow-ups"] = () => lista([]);
    abrir();
    expect(await screen.findByText("No hay tareas pendientes.")).toBeTruthy();
  });

  it("«Hechas» pide las hechas, las muestra con «Reabrir» y queda en la dirección", async () => {
    const u = abrir();
    await titulo("Vencidas (1)");
    await u.click(screen.getByRole("button", { name: "Hechas" }));

    const fila = (await screen.findByText("Ya llamada")).closest("li") as HTMLElement;
    expect(within(fila).getByRole("button", { name: "Reabrir" })).toBeTruthy();
    expect(within(fila).queryByRole("button", { name: "Hecha" })).toBeNull();
    expect(lecturas()).toContain("/api/follow-ups?state=done");
    expect(screen.getByRole("button", { name: "Hechas" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("recargar con ?vista=hechas mantiene la vista y ?persona= el filtro", async () => {
    abrir("/pendientes?vista=hechas&persona=3");
    await screen.findByText("Ya llamada");
    expect(lecturas()[0]).toBe("/api/follow-ups?state=done&assigned_to_id=3");
  });

  it("sin hechas lo dice", async () => {
    rutas["GET /api/follow-ups"] = () => lista([]);
    abrir("/pendientes?vista=hechas");
    expect(await screen.findByText("No hay tareas hechas.")).toBeTruthy();
  });

  it("avisa si hay más de las que caben", async () => {
    rutas["GET /api/follow-ups"] = () => lista([DE_HOY], 80);
    abrir();
    expect(await screen.findByText("Mostrando las más cercanas: 1 de 80.")).toBeTruthy();
  });

  it("un error se puede reintentar", async () => {
    const buena = rutas["GET /api/follow-ups"];
    rutas["GET /api/follow-ups"] = () => ({ status: 503 });
    const u = abrir();
    await screen.findByRole("alert");
    rutas["GET /api/follow-ups"] = buena;
    await u.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await titulo("Vencidas (1)")).toBeTruthy();
  });

  it("si la sesión caducó vuelve al login", async () => {
    rutas["GET /api/follow-ups"] = () => ({ status: 401, cuerpo: { detail: "Sesión no válida" } });
    abrir();
    expect(await screen.findByRole("button", { name: /entrar/i })).toBeTruthy();
  });
});

describe("filtro por persona", () => {
  it("por defecto pide todas; elegir a alguien filtra y «Solo mías» usa la propia cuenta", async () => {
    const u = abrir();
    await titulo("Vencidas (1)");
    expect(lecturas()[0]).not.toContain("assigned_to_id");

    await u.selectOptions(await screen.findByLabelText("Persona"), "3");
    await waitFor(() => expect(lecturas()).toContain("/api/follow-ups?state=pending&assigned_to_id=3"));

    await u.click(screen.getByRole("button", { name: "Solo mías" }));
    await waitFor(() => expect(lecturas()).toContain("/api/follow-ups?state=pending&assigned_to_id=2"));
    expect((screen.getByRole("button", { name: "Solo mías" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("si no carga la lista de personas, el panel sigue funcionando", async () => {
    rutas["GET /api/services/staff"] = () => ({ status: 503 });
    abrir();
    expect(await titulo("Vencidas (1)")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("profesional", () => {
  beforeEach(() => {
    usuario = PROFESIONAL;
  });

  it("ve el panel sin filtro, sin el responsable y sin editar, y no pide la lista de personas", async () => {
    abrir();
    await titulo("Vencidas (1)");
    expect(screen.queryByLabelText("Persona")).toBeNull();
    expect(screen.queryByRole("button", { name: "Solo mías" })).toBeNull();
    expect(screen.queryByText(/Responsable:/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
    expect(screen.getAllByRole("button", { name: "Hecha" })).toHaveLength(3);
    expect(llamadas.some((l) => l.ruta === "/api/services/staff")).toBe(false);
  });

  it("aunque la dirección lleve ?persona= no pide las de otra persona", async () => {
    abrir("/pendientes?persona=2");
    await titulo("Vencidas (1)");
    expect(lecturas().every((u) => !u.includes("assigned_to_id"))).toBe(true);
  });
});

describe("acciones en el panel", () => {
  it("«Hecha» envía la versión de esa tarea, avisa, recarga la lista y el contador", async () => {
    rutas["POST /api/follow-ups/1/complete"] = () => ({ status: 200, cuerpo: { ...VENCIDA, completed_at: "2027-01-11T15:00:00Z" } });
    const u = abrir();
    const fila = (await screen.findByText("Llamar ayer")).closest("li") as HTMLElement;
    await titulo("Hoy (1)");
    await waitFor(() => expect(lecturasResumen()).toBeGreaterThan(0));
    const panelAntes = lecturas().length;
    const resumenAntes = lecturasResumen();

    await u.click(within(fila).getByRole("button", { name: "Hecha" }));

    expect(await screen.findByText("Tarea marcada como hecha")).toBeTruthy();
    expect(llamadas.find((l) => l.metodo === "POST")?.cuerpo).toEqual({ version: 1 });
    await waitFor(() => expect(lecturas().length).toBeGreaterThan(panelAntes));
    await waitFor(() => expect(lecturasResumen()).toBeGreaterThan(resumenAntes));
  });

  it("un 409 avisa y recarga", async () => {
    rutas["POST /api/follow-ups/1/complete"] = () => ({ status: 409, cuerpo: { detail: "Esta tarea ya está hecha" } });
    const u = abrir();
    const fila = (await screen.findByText("Llamar ayer")).closest("li") as HTMLElement;
    const antes = lecturas().length;
    await u.click(within(fila).getByRole("button", { name: "Hecha" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Esta tarea ya está hecha");
    await waitFor(() => expect(lecturas().length).toBeGreaterThan(antes));
  });
});

describe("contador de la barra", () => {
  const enlace = async () => within(await screen.findByRole("navigation", { name: "Secciones" })).getByRole("link", { name: /Pendientes/ });

  it("suma las vencidas y las de hoy", async () => {
    rutas["GET /api/follow-ups/summary"] = () => ({ status: 200, cuerpo: { overdue: 2, due_today: 3 } });
    abrir();
    const a = await enlace();
    await waitFor(() => expect(a.textContent?.replace(/\s+/g, " ").trim()).toBe("Pendientes 5"));
  });

  it("con cero no enseña número", async () => {
    rutas["GET /api/follow-ups/summary"] = () => ({ status: 200, cuerpo: { overdue: 0, due_today: 0 } });
    abrir();
    const a = await enlace();
    await waitFor(() => expect(lecturasResumen()).toBeGreaterThan(0));
    expect(a.querySelector(".contador")).toBeNull();
  });

  it("si falla no estorba", async () => {
    rutas["GET /api/follow-ups/summary"] = () => ({ status: 503 });
    abrir();
    const a = await enlace();
    await waitFor(() => expect(lecturasResumen()).toBeGreaterThan(0));
    expect(a.querySelector(".contador")).toBeNull();
    expect(screen.queryByText(/Servicio no disponible/)).toBeNull();
  });

  it("se vuelve a pedir al cambiar de página", async () => {
    rutas["GET /api/contacts"] = () => ({ status: 200, cuerpo: { total: 0, items: [] } });
    const u = abrir();
    const barra = await screen.findByRole("navigation", { name: "Secciones" });
    await waitFor(() => expect(lecturasResumen()).toBe(1));

    await u.click(within(barra).getByRole("link", { name: "Contactos" }));

    await waitFor(() => expect(lecturasResumen()).toBe(2));
  });

  it("el cliente no tiene la sección ni pide el contador, y la dirección le dice que no", async () => {
    usuario = CLIENTE;
    rutas["GET /api/portal/appointments"] = () => ({ status: 200, cuerpo: { upcoming: [], past: [], past_total: 0 } });
    abrir();
    expect(await screen.findByText("No tienes acceso a esta área")).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Secciones" })).toBeNull();
    expect(lecturasResumen()).toBe(0);
    expect(lecturas()).toEqual([]);
  });
});
