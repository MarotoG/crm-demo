// Pruebas de la ficha y la edición de contactos (T13) con una API falsa en fetch.

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { ContactoDetalle } from "./api";
import { AVISO_TILDES, formatoFecha } from "./Contactos";
import { AVISO_OTRA_VERSION } from "./FichaContacto";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = { metodo: string; ruta: string; headers: Record<string, string>; cuerpo: unknown };

const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };
const ADMIN = { id: 1, email: "admin@prueba.example.com", role: "admin", csrf_token: "csrf-admin" };

const ANA: ContactoDetalle = {
  id: 7,
  first_name: "Ana",
  last_name: "Smith",
  email: "ana@clinica.example.com",
  phone: "+12125550123",
  source: "instagram",
  status: "new",
  created_at: "2026-11-02T23:05:00Z",
  updated_at: "2026-11-02T23:05:00Z",
  version: 1,
  created_by_email: "recepcion@prueba.example.com",
  updated_by_email: null,
};

let usuario: typeof RECEPCION;
let rutas: Record<string, (cuerpo: unknown) => Respuesta>;
let llamadas: Llamada[];

beforeEach(() => {
  llamadas = [];
  usuario = RECEPCION;
  rutas = {
    "GET /api/auth/me": () => ({ status: 200, cuerpo: usuario }),
    "GET /api/users": () => ({ status: 200, cuerpo: [] }),
    "GET /api/contacts": () => ({ status: 200, cuerpo: { total: 1, items: [ANA] } }),
    "GET /api/contacts/7": () => ({ status: 200, cuerpo: ANA }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (ruta: string, init: RequestInit = {}) => {
      const metodo = init.method ?? "GET";
      const cuerpo = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      const ruta_ = new URL(ruta, "http://localhost").pathname;
      llamadas.push({ metodo, ruta: ruta_, headers: (init.headers ?? {}) as Record<string, string>, cuerpo });
      const r = rutas[`${metodo} ${ruta_}`]?.(cuerpo) ?? { status: 404, cuerpo: { detail: "Contacto no encontrado" } };
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

function abrir(ruta: string) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const puts = () => llamadas.filter((l) => l.metodo === "PUT");
const dato = (nombre: string) => screen.getByText(nombre, { selector: "dt" }).nextElementSibling?.textContent;

describe("ver la ficha", () => {
  it("desde la lista, el nombre lleva a su ficha con los datos legibles", async () => {
    const u = abrir("/recepcion");

    await u.click(await screen.findByRole("link", { name: "Ana Smith" }));

    expect(await screen.findByRole("heading", { name: "Ana Smith" })).toBeTruthy();
    expect(dato("Email")).toBe("ana@clinica.example.com");
    expect(dato("Teléfono")).toBe("(212) 555-0123");
    expect(dato("Origen")).toBe("Instagram");
    expect(dato("Estado")).toBe("Nuevo");
    expect(dato("Creado")).toBe(`${formatoFecha(ANA.created_at)} · recepcion@prueba.example.com`);
    expect(screen.queryByText("Último cambio")).toBeNull(); // versión 1: nadie la ha cambiado
  });

  it("la dirección de la ficha se puede abrir directamente (recargar) y el admin tiene la suya", async () => {
    usuario = ADMIN;
    abrir("/admin/contactos/7");

    expect(await screen.findByRole("heading", { name: "Ana Smith" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "← Volver a contactos" }).getAttribute("href")).toBe("/admin");
  });

  it("recepción no entra en la ficha del área de admin", async () => {
    abrir("/admin/contactos/7");

    expect(await screen.findByText("No tienes acceso a esta área")).toBeTruthy();
  });

  it("un contacto que no existe (404) lo dice", async () => {
    abrir("/recepcion/contactos/8");

    expect(await screen.findByRole("heading", { name: "Este contacto no existe" })).toBeTruthy();
  });

  it("un id que no es un número ni se pregunta a la API", async () => {
    abrir("/recepcion/contactos/abc");

    expect(await screen.findByRole("heading", { name: "Este contacto no existe" })).toBeTruthy();
    expect(llamadas.some((l) => l.ruta.startsWith("/api/contacts/"))).toBe(false);
  });

  it("si la sesión caduca al abrir la ficha, vuelve al login con un aviso", async () => {
    rutas["GET /api/contacts/7"] = () => ({ status: 401, cuerpo: { detail: "No autenticado" } });
    abrir("/recepcion/contactos/7");

    expect(await screen.findByText("Tu sesión ha caducado. Vuelve a entrar.")).toBeTruthy();
  });
});

describe("editar", () => {
  it("el formulario sale relleno; guardar envía la ficha entera con la versión y el token", async () => {
    rutas["PUT /api/contacts/7"] = (cuerpo) => ({
      status: 200,
      cuerpo: {
        ...ANA,
        ...(cuerpo as object),
        phone: "+12125550123",
        version: 2,
        updated_at: "2026-11-03T15:00:00Z",
        updated_by_email: "recepcion@prueba.example.com",
      },
    });
    const u = abrir("/recepcion/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));

    expect((screen.getByLabelText("Nombre") as HTMLInputElement).value).toBe("Ana");
    expect((screen.getByLabelText("Teléfono") as HTMLInputElement).value).toBe("(212) 555-0123");
    expect((screen.getByLabelText("Origen") as HTMLSelectElement).value).toBe("instagram");
    await u.clear(screen.getByLabelText("Apellidos"));
    await u.type(screen.getByLabelText("Apellidos"), "Smyth");
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect((await screen.findByRole("status")).textContent).toBe("Cambios guardados");
    expect(screen.getByRole("heading", { name: "Ana Smyth" })).toBeTruthy();
    expect(dato("Último cambio")).toBe(`${formatoFecha("2026-11-03T15:00:00Z")} · recepcion@prueba.example.com`);
    expect(puts()).toHaveLength(1);
    expect(puts()[0].headers["X-CSRF-Token"]).toBe("csrf-recepcion");
    expect(puts()[0].cuerpo).toEqual({
      first_name: "Ana",
      last_name: "Smyth",
      email: "ana@clinica.example.com",
      phone: "(212) 555-0123",
      source: "instagram",
      version: 1,
    });
  });

  it("si otra persona guardó antes (409 y versión nueva), muestra la ficha actual con un aviso", async () => {
    const deOtraPersona = { ...ANA, last_name: "Brown", version: 2, updated_by_email: "admin@prueba.example.com" };
    rutas["PUT /api/contacts/7"] = () => ({ status: 409, cuerpo: { detail: "Otra persona ha cambiado esta ficha mientras la editabas" } });
    const u = abrir("/recepcion/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));
    await u.type(screen.getByLabelText("Nombre"), "bel");
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: deOtraPersona });

    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect((await screen.findByRole("alert")).textContent).toBe(AVISO_OTRA_VERSION);
    expect(screen.getByRole("heading", { name: "Ana Brown" })).toBeTruthy(); // lo de la otra persona, sin pisar
    expect(screen.queryByLabelText("Nombre")).toBeNull(); // formulario cerrado
    expect(puts()).toHaveLength(1);
  });

  it("al volver a editar tras el aviso, se envía la versión nueva", async () => {
    let version = 1;
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, version } });
    rutas["PUT /api/contacts/7"] = (cuerpo) =>
      (cuerpo as { version: number }).version === version
        ? { status: 200, cuerpo: { ...ANA, version: version + 1 } }
        : { status: 409, cuerpo: { detail: "Otra persona ha cambiado esta ficha mientras la editabas" } };
    const u = abrir("/recepcion/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));
    version = 2; // alguien guarda mientras tanto
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await screen.findByText(AVISO_OTRA_VERSION);

    await u.click(screen.getByRole("button", { name: "Editar" }));
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect((await screen.findByRole("status")).textContent).toBe("Cambios guardados");
    expect(puts().map((p) => (p.cuerpo as { version: number }).version)).toEqual([1, 2]);
  });

  it("un duplicado (409 con la misma versión) se explica en el formulario, que sigue abierto", async () => {
    rutas["PUT /api/contacts/7"] = () => ({ status: 409, cuerpo: { detail: "Ya existe un contacto con ese nombre, apellidos y email" } });
    const u = abrir("/recepcion/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));

    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Ya existe un contacto con ese nombre, apellidos y email");
    expect(screen.getByRole("button", { name: "Guardar cambios" })).toBeTruthy();
  });

  it("con tildes no se envía y sale el aviso", async () => {
    const u = abrir("/recepcion/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));
    await u.clear(screen.getByLabelText("Nombre"));
    await u.type(screen.getByLabelText("Nombre"), "Ánna");

    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(screen.getByText(AVISO_TILDES)).toBeTruthy());
    expect(puts()).toHaveLength(0);
  });

  it("cancelar vuelve a la ficha sin enviar nada", async () => {
    const u = abrir("/recepcion/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));
    await u.type(screen.getByLabelText("Nombre"), "bel");

    await u.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.getByRole("heading", { name: "Ana Smith" })).toBeTruthy();
    expect(puts()).toHaveLength(0);
  });
});

describe("formatoFecha", () => {
  it("muestra la hora de Nueva York, también con el horario de verano", () => {
    expect(formatoFecha("2026-11-02T23:05:00Z")).toMatch(/18:05 \(hora de Nueva York\)$/); // EST, UTC−5
    expect(formatoFecha("2026-07-01T16:00:00Z")).toMatch(/12:00 \(hora de Nueva York\)$/); // EDT, UTC−4
  });
});
