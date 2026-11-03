// Servicios en la interfaz (T15): lista, alta uno a uno, edición, desactivación y la vista del
// profesional, contra una API falsa.

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { PersonaServicio, Servicio } from "./api";
import { AVISO_OTRA_VERSION_SERVICIO, formatoDuracion, SIN_PERSONAS } from "./Servicios";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = { clave: string; headers: Record<string, string>; cuerpo: unknown };

const ADMIN = { id: 1, email: "admin@prueba.example.com", role: "admin", csrf_token: "csrf-admin" };
const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };
const PROFESIONAL = { id: 3, email: "pro@prueba.example.com", role: "professional", csrf_token: "csrf-pro" };

const P_ADMIN: PersonaServicio = { id: 1, email: "admin@prueba.example.com", role: "admin", active: true };
const P_RECEPCION: PersonaServicio = { id: 2, email: "recepcion@prueba.example.com", role: "reception", active: true };
const P_PRO: PersonaServicio = { id: 3, email: "pro@prueba.example.com", role: "professional", active: true };
const P_BAJA: PersonaServicio = { id: 9, email: "baja@prueba.example.com", role: "professional", active: false };

const BOTOX: Servicio = { id: 10, name: "Botox", duration_minutes: 30, active: true, version: 4, staff: [P_ADMIN, P_PRO] };
const FACIAL: Servicio = { id: 11, name: "Facial", duration_minutes: 90, active: false, version: 2, staff: [] };
const PEEL: Servicio = { id: 12, name: "Peel", duration_minutes: 60, active: true, version: 1, staff: [P_BAJA] };

let usuario: typeof ADMIN;
let rutas: Record<string, (cuerpo: unknown) => Respuesta>;
let llamadas: Llamada[];

beforeEach(() => {
  llamadas = [];
  usuario = ADMIN;
  rutas = {
    "GET /api/users": () => ({ status: 200, cuerpo: [] }),
    "GET /api/contacts": () => ({ status: 200, cuerpo: { total: 0, items: [] } }),
    "GET /api/services": () => ({ status: 200, cuerpo: [BOTOX, PEEL, FACIAL] }),
    "GET /api/services/staff": () => ({ status: 200, cuerpo: [P_ADMIN, P_PRO, P_RECEPCION] }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (ruta: string, init: RequestInit = {}) => {
      const clave = `${init.method ?? "GET"} ${new URL(ruta, "http://localhost").pathname}`;
      const cuerpo = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      llamadas.push({ clave, headers: (init.headers ?? {}) as Record<string, string>, cuerpo });
      const r =
        clave === "GET /api/auth/me"
          ? { status: 200, cuerpo: usuario }
          : (rutas[clave]?.(cuerpo) ?? { status: 404, cuerpo: { detail: "Not Found" } });
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

function abrir(ruta = "/servicios") {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

async function seccion() {
  return within((await screen.findByRole("heading", { name: "Servicios" })).closest("section") as HTMLElement);
}

const enviadas = (clave: string) => llamadas.filter((l) => l.clave === clave);

describe("lista de servicios", () => {
  it("muestra duración, estado y quién lo realiza; avisa si nadie disponible lo realiza", async () => {
    abrir();
    const s = await seccion();

    expect(await s.findByText("Botox")).toBeTruthy();
    expect(s.getByText("30 min · Activo")).toBeTruthy();
    expect(s.getByText("Lo realizan: admin@prueba.example.com, pro@prueba.example.com")).toBeTruthy();
    expect(s.getByText("1 h 30 min · Desactivado")).toBeTruthy();
    expect(s.getByText("Sin nadie asignado")).toBeTruthy();
    expect(s.getByText("Lo realizan: baja@prueba.example.com (desactivada)")).toBeTruthy();
    // Solo el Peel: activo y con su única persona desactivada. El Facial está desactivado.
    expect(s.getAllByText("Nadie disponible lo realiza: no se podrán dar citas de este servicio.")).toHaveLength(1);
    expect(s.getByRole("button", { name: "Reactivar Facial" })).toBeTruthy();
  });

  it("sin servicios, invita a añadir el primero", async () => {
    rutas["GET /api/services"] = () => ({ status: 200, cuerpo: [] });
    usuario = RECEPCION;
    abrir("/servicios");

    expect(await (await seccion()).findByText("Todavía no hay servicios. Añade el primero con «Añadir servicio».")).toBeTruthy();
  });

  it("formato de la duración", () => {
    expect([5, 45, 60, 90, 240].map(formatoDuracion)).toEqual(["5 min", "45 min", "1 h", "1 h 30 min", "4 h"]);
  });
});

describe("añadir servicio", () => {
  it("envía nombre, duración y las personas marcadas con el token, y lo anuncia", async () => {
    let creado = false;
    rutas["POST /api/services"] = (cuerpo) => {
      creado = true;
      return { status: 201, cuerpo: { ...BOTOX, id: 20, ...(cuerpo as object), staff: [P_PRO, P_RECEPCION], version: 1 } };
    };
    const original = rutas["GET /api/services"];
    rutas["GET /api/services"] = (c) => (creado ? { status: 200, cuerpo: [{ ...BOTOX, id: 20, name: "Lips" }] } : original(c));
    usuario = RECEPCION;
    const u = abrir("/servicios");
    const s = await seccion();

    await u.click(s.getByRole("button", { name: "Añadir servicio" }));
    const formulario = within(await s.findByRole("form", { name: "Añadir servicio" }));
    expect(formulario.getByLabelText("admin@prueba.example.com · Administración")).toBeTruthy();
    await u.type(formulario.getByLabelText("Nombre"), "Lips");
    await u.type(formulario.getByLabelText("Duración (minutos)"), "45");
    await u.click(formulario.getByLabelText("recepcion@prueba.example.com · Recepción"));
    await u.click(formulario.getByLabelText("pro@prueba.example.com · Profesional"));
    await u.click(formulario.getByRole("button", { name: "Guardar servicio" }));

    expect(await s.findByText("Servicio añadido: Lips")).toBeTruthy();
    const [alta] = enviadas("POST /api/services");
    expect(alta.cuerpo).toEqual({ name: "Lips", duration_minutes: 45, staff_ids: [2, 3] });
    expect(alta.headers["X-CSRF-Token"]).toBe("csrf-recepcion");
    expect(s.queryByRole("form")).toBeNull();
    expect(enviadas("GET /api/services").length).toBeGreaterThanOrEqual(2); // la lista se recarga
  });

  it("los 422 de la API salen junto a cada campo", async () => {
    rutas["POST /api/services"] = () => ({
      status: 422,
      cuerpo: {
        detail: [
          { loc: ["body", "duration_minutes"], msg: "La duración debe ser un múltiplo de 5 minutos, entre 5 y 240 (4 horas)" },
          { loc: ["body", "staff_ids"], msg: "Solo se pueden asignar cuentas internas activas (administración, recepción o profesional)" },
        ],
      },
    });
    const u = abrir();
    const s = await seccion();

    await u.click(s.getByRole("button", { name: "Añadir servicio" }));
    const formulario = within(await s.findByRole("form", { name: "Añadir servicio" }));
    await u.type(formulario.getByLabelText("Nombre"), "Lips");
    await u.type(formulario.getByLabelText("Duración (minutos)"), "62");
    await u.click(formulario.getByLabelText("admin@prueba.example.com · Administración"));
    await u.click(formulario.getByRole("button", { name: "Guardar servicio" }));

    const duracion = formulario.getByLabelText("Duración (minutos)");
    expect(await formulario.findByText("La duración debe ser un múltiplo de 5 minutos, entre 5 y 240 (4 horas)")).toBeTruthy();
    expect(duracion.getAttribute("aria-invalid")).toBe("true");
    expect(formulario.getByText("Solo se pueden asignar cuentas internas activas (administración, recepción o profesional)")).toBeTruthy();
    expect(enviadas("POST /api/services")[0].cuerpo).toEqual({ name: "Lips", duration_minutes: 62, staff_ids: [1] });
  });

  it("sin duración, sin personas o con tildes no se envía, y se avisa de todo a la vez", async () => {
    const u = abrir();
    const s = await seccion();

    await u.click(s.getByRole("button", { name: "Añadir servicio" }));
    const formulario = within(await s.findByRole("form", { name: "Añadir servicio" }));
    await u.type(formulario.getByLabelText("Nombre"), "Depilación");
    expect(formulario.getByText("No se permiten tildes ni caracteres especiales (á, ñ, ü…)")).toBeTruthy();
    await u.click(formulario.getByRole("button", { name: "Guardar servicio" }));

    expect(formulario.getByText("Indica la duración en minutos")).toBeTruthy();
    expect(formulario.getByText(SIN_PERSONAS)).toBeTruthy();
    expect(enviadas("POST /api/services")).toHaveLength(0);
  });

  it("un servicio desactivado se puede guardar sin nadie asignado", async () => {
    rutas["PUT /api/services/11"] = (cuerpo) => ({ status: 200, cuerpo: { ...FACIAL, ...(cuerpo as object), version: 3 } });
    const u = abrir();
    const s = await seccion();

    await u.click(await s.findByRole("button", { name: "Editar Facial" }));
    const formulario = within(await s.findByRole("form", { name: "Editar Facial" }));
    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect(await s.findByText("Servicio guardado: Facial")).toBeTruthy();
    expect(enviadas("PUT /api/services/11")[0].cuerpo).toMatchObject({ staff_ids: [], active: false, version: 2 });
  });

  it("un nombre repetido (409) se avisa y el formulario conserva los datos", async () => {
    rutas["POST /api/services"] = () => ({ status: 409, cuerpo: { detail: "Ya existe un servicio con ese nombre (puede estar desactivado: edítalo y reactívalo)" } });
    const u = abrir();
    const s = await seccion();

    await u.click(s.getByRole("button", { name: "Añadir servicio" }));
    const formulario = within(await s.findByRole("form", { name: "Añadir servicio" }));
    await u.type(formulario.getByLabelText("Nombre"), "botox");
    await u.type(formulario.getByLabelText("Duración (minutos)"), "30");
    await u.click(formulario.getByLabelText("admin@prueba.example.com · Administración"));
    await u.click(formulario.getByRole("button", { name: "Guardar servicio" }));

    expect(await formulario.findByText("Ya existe un servicio con ese nombre (puede estar desactivado: edítalo y reactívalo)")).toBeTruthy();
    expect((formulario.getByLabelText("Nombre") as HTMLInputElement).value).toBe("botox");
  });

  it("si fallan las personas asignables se puede reintentar", async () => {
    let fallos = 1;
    rutas["GET /api/services/staff"] = () => (fallos-- > 0 ? { status: 503 } : { status: 200, cuerpo: [P_ADMIN] });
    const u = abrir();
    const s = await seccion();

    await u.click(s.getByRole("button", { name: "Añadir servicio" }));
    expect(await s.findByText("Servicio no disponible. Inténtalo de nuevo en unos minutos")).toBeTruthy();
    await u.click(s.getByRole("button", { name: "Reintentar" }));

    expect(await s.findByRole("form", { name: "Añadir servicio" })).toBeTruthy();
  });
});

describe("editar, desactivar y reactivar", () => {
  it("el formulario parte de lo guardado y el PUT lleva activo y la versión leída", async () => {
    rutas["PUT /api/services/10"] = (cuerpo) => ({ status: 200, cuerpo: { ...BOTOX, ...(cuerpo as object), version: 5 } });
    const u = abrir();
    const s = await seccion();

    await u.click(await s.findByRole("button", { name: "Editar Botox" }));
    const formulario = within(await s.findByRole("form", { name: "Editar Botox" }));
    expect((formulario.getByLabelText("Duración (minutos)") as HTMLInputElement).value).toBe("30");
    expect((formulario.getByLabelText("pro@prueba.example.com · Profesional") as HTMLInputElement).checked).toBe(true);
    expect((formulario.getByLabelText("recepcion@prueba.example.com · Recepción") as HTMLInputElement).checked).toBe(false);
    await u.clear(formulario.getByLabelText("Duración (minutos)"));
    await u.type(formulario.getByLabelText("Duración (minutos)"), "60");
    await u.click(formulario.getByLabelText("admin@prueba.example.com · Administración"));
    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect(await s.findByText("Servicio guardado: Botox")).toBeTruthy();
    expect(enviadas("PUT /api/services/10")[0].cuerpo).toEqual({
      name: "Botox", duration_minutes: 60, staff_ids: [3], active: true, version: 4,
    });
  });

  it("una persona ya asignada y desactivada sigue marcada para no quitarla sin querer", async () => {
    rutas["PUT /api/services/12"] = (cuerpo) => ({ status: 200, cuerpo: { ...PEEL, ...(cuerpo as object), version: 2 } });
    const u = abrir();
    const s = await seccion();

    await u.click(await s.findByRole("button", { name: "Editar Peel" }));
    const formulario = within(await s.findByRole("form", { name: "Editar Peel" }));
    expect((formulario.getByLabelText("baja@prueba.example.com (ya no disponible)") as HTMLInputElement).checked).toBe(true);
    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect(await s.findByText("Servicio guardado: Peel")).toBeTruthy();
    expect(enviadas("PUT /api/services/12")[0].cuerpo).toMatchObject({ staff_ids: [9], version: 1 });
  });

  it("si otra persona guardó antes (409), se muestra su versión con un aviso", async () => {
    rutas["PUT /api/services/10"] = () => ({ status: 409, cuerpo: { detail: "Otra persona ha cambiado este servicio antes de que guardaras" } });
    const u = abrir();
    const s = await seccion();

    await u.click(await s.findByRole("button", { name: "Editar Botox" }));
    const formulario = within(await s.findByRole("form", { name: "Editar Botox" }));
    rutas["GET /api/services"] = () => ({ status: 200, cuerpo: [{ ...BOTOX, duration_minutes: 45, version: 5 }] });
    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect(await s.findByText(AVISO_OTRA_VERSION_SERVICIO)).toBeTruthy();
    expect(s.getByText("45 min · Activo")).toBeTruthy();
    expect(s.queryByRole("form")).toBeNull();
  });

  it("un 409 sin cambio de versión es un nombre repetido: sale en el formulario", async () => {
    rutas["PUT /api/services/10"] = () => ({ status: 409, cuerpo: { detail: "Ya existe un servicio con ese nombre (puede estar desactivado: edítalo y reactívalo)" } });
    const u = abrir();
    const s = await seccion();

    await u.click(await s.findByRole("button", { name: "Editar Botox" }));
    const formulario = within(await s.findByRole("form", { name: "Editar Botox" }));
    await u.clear(formulario.getByLabelText("Nombre"));
    await u.type(formulario.getByLabelText("Nombre"), "Peel");
    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect(await formulario.findByText("Ya existe un servicio con ese nombre (puede estar desactivado: edítalo y reactívalo)")).toBeTruthy();
  });

  it("desactivar envía el servicio entero con active false y la versión", async () => {
    rutas["PUT /api/services/10"] = (cuerpo) => ({ status: 200, cuerpo: { ...BOTOX, ...(cuerpo as object), version: 5 } });
    const u = abrir();
    const s = await seccion();

    await u.click(await s.findByRole("button", { name: "Desactivar Botox" }));

    expect(await s.findByText("Servicio desactivado: Botox")).toBeTruthy();
    expect(enviadas("PUT /api/services/10")[0]).toMatchObject({
      cuerpo: { name: "Botox", duration_minutes: 30, staff_ids: [1, 3], active: false, version: 4 },
      headers: { "X-CSRF-Token": "csrf-admin" },
    });
  });

  it("reactivar sin nadie asignado explica qué hacer", async () => {
    rutas["PUT /api/services/11"] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body", "staff_ids"], msg: "Un servicio activo necesita al menos una persona que lo realice" }] },
    });
    const u = abrir();
    const s = await seccion();

    await u.click(await s.findByRole("button", { name: "Reactivar Facial" }));

    expect(
      await s.findByText("Un servicio activo necesita al menos una persona que lo realice. Edítalo para asignar a alguien."),
    ).toBeTruthy();
  });
});

describe("profesional", () => {
  it("ve sus servicios, sin gestión ni personas asignables", async () => {
    usuario = PROFESIONAL;
    rutas["GET /api/services"] = () => ({ status: 200, cuerpo: [BOTOX] });
    abrir("/profesional");

    const s = within((await screen.findByRole("heading", { name: "Mis servicios" })).closest("section") as HTMLElement);
    expect(await s.findByText("Botox")).toBeTruthy();
    expect(s.getByText("30 min")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Añadir servicio" })).toBeNull();
    expect(enviadas("GET /api/services/staff")).toHaveLength(0);
  });

  it("sin servicios asignados, lo dice", async () => {
    usuario = PROFESIONAL;
    rutas["GET /api/services"] = () => ({ status: 200, cuerpo: [] });
    abrir("/profesional");

    expect(await screen.findByText("Todavía no tienes servicios asignados. Pídelo en recepción o administración.")).toBeTruthy();
  });
});
