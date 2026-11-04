// Pruebas de la ficha y la edición de contactos (T13), con estado y responsable (T14), con una API falsa en fetch.

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
  note: null,
  owner_id: 2,
  owner_email: "recepcion@prueba.example.com",
};

const RESPONSABLES = [
  { id: 1, email: "admin@prueba.example.com" },
  { id: 2, email: "recepcion@prueba.example.com" },
];

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
    "GET /api/contacts/owners": () => ({ status: 200, cuerpo: RESPONSABLES }),
    // Citas e invitación (T21) tienen sus pruebas en Invitacion.test.tsx; aquí, sin botones de más.
    "GET /api/appointments/by-contact/7": () => ({ status: 200, cuerpo: { total: 0, items: [] } }),
    "GET /api/contacts/7/portal": () => ({ status: 200, cuerpo: { has_account: true, invitation_expires_at: null } }),
    // Tareas de seguimiento (T24): sus pruebas, en Seguimientos.test.tsx.
    "GET /api/contacts/7/follow-ups": () => ({ status: 200, cuerpo: { total: 0, items: [] } }),
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
    const u = abrir("/contactos");

    await u.click(await screen.findByRole("link", { name: "Ana Smith" }));

    expect(await screen.findByRole("heading", { name: "Ana Smith" })).toBeTruthy();
    expect(dato("Email")).toBe("ana@clinica.example.com");
    expect(dato("Teléfono")).toBe("(212) 555-0123");
    expect(dato("Origen")).toBe("Instagram");
    expect(dato("Estado")).toBe("Nuevo");
    expect(dato("Creado")).toBe(`${formatoFecha(ANA.created_at)} · recepcion@prueba.example.com`);
    expect(screen.queryByText("Último cambio")).toBeNull(); // versión 1: nadie la ha cambiado
  });

  it("la dirección de la ficha se puede abrir directamente (recargar), también el admin", async () => {
    usuario = ADMIN;
    abrir("/contactos/7");

    expect(await screen.findByRole("heading", { name: "Ana Smith" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "← Volver a contactos" }).getAttribute("href")).toBe("/contactos");
  });

  it.each(["/admin/contactos/7", "/recepcion/contactos/7"])("la dirección de antes de T18 (%s) lleva a la ficha", async (ruta) => {
    abrir(ruta);

    expect(await screen.findByRole("heading", { name: "Ana Smith" })).toBeTruthy();
    expect(llamadas.some((l) => l.ruta === "/api/contacts/7")).toBe(true);
  });

  it("una cuenta de cliente no ve la ficha ni la pide", async () => {
    usuario = { ...RECEPCION, role: "client" };
    abrir("/contactos/7");

    expect(await screen.findByText("No tienes acceso a esta área")).toBeTruthy();
    expect(llamadas.some((l) => l.ruta === "/api/contacts/7")).toBe(false);
  });

  it("el profesional la ve en solo lectura, sin editar, cambiar el estado ni dar cita (T20)", async () => {
    usuario = { ...RECEPCION, role: "professional" };
    abrir("/contactos/7");

    expect(await screen.findByRole("heading", { name: "Ana Smith" })).toBeTruthy();
    expect(dato("Teléfono")).toBe("(212) 555-0123");
    expect(dato("Estado")).toBe("Nuevo");
    expect(screen.queryAllByRole("button")).toEqual([screen.getByRole("button", { name: "Cerrar sesión" })]);
    expect(screen.getByRole("link", { name: "← Volver a mi agenda" }).getAttribute("href")).toBe("/mi-agenda");
    expect(screen.queryByText(/Al darle una cita/)).toBeNull();
    // No pide la lista de responsables (403 para él).
    expect(llamadas.some((l) => l.ruta === "/api/contacts/owners")).toBe(false);
  });

  it("al profesional, un contacto sin citas con él (404) no le dice si existe", async () => {
    usuario = { ...RECEPCION, role: "professional" };
    abrir("/contactos/8");

    expect(await screen.findByRole("heading", { name: "Este contacto no existe o no tiene citas contigo" })).toBeTruthy();
  });

  it("un contacto que no existe (404) lo dice", async () => {
    abrir("/contactos/8");

    expect(await screen.findByRole("heading", { name: "Este contacto no existe" })).toBeTruthy();
  });

  it("un id que no es un número ni se pregunta a la API", async () => {
    abrir("/contactos/abc");

    expect(await screen.findByRole("heading", { name: "Este contacto no existe" })).toBeTruthy();
    expect(llamadas.some((l) => l.ruta.startsWith("/api/contacts/"))).toBe(false);
  });

  it("si la sesión caduca al abrir la ficha, vuelve al login con un aviso", async () => {
    rutas["GET /api/contacts/7"] = () => ({ status: 401, cuerpo: { detail: "No autenticado" } });
    abrir("/contactos/7");

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
    const u = abrir("/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));

    expect((await screen.findByLabelText("Nombre") as HTMLInputElement).value).toBe("Ana");
    expect((screen.getByLabelText("Teléfono (opcional)") as HTMLInputElement).value).toBe("(212) 555-0123");
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
      owner_id: 2,
      note: "",
      version: 1,
    });
  });

  it("la nota se ve en la ficha, sale en el formulario y se envía al guardar (T21b)", async () => {
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, note: "Instagram: @ana" } });
    rutas["PUT /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, note: "Instagram: @ana2", version: 2 } });
    const u = abrir("/contactos/7");

    await screen.findByRole("heading", { name: "Ana Smith" });
    expect(dato("Nota")).toBe("Instagram: @ana");

    await u.click(screen.getByRole("button", { name: "Editar" }));
    const nota = (await screen.findByLabelText("Nota (opcional)")) as HTMLInputElement;
    expect(nota.value).toBe("Instagram: @ana");
    expect(screen.getByText(/No escribas datos clínicos/)).toBeTruthy();
    await u.clear(nota);
    await u.type(nota, "Instagram: @ana2");
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await screen.findByText("Cambios guardados");
    expect((puts()[0].cuerpo as { note: string }).note).toBe("Instagram: @ana2");
    expect(dato("Nota")).toBe("Instagram: @ana2");
  });

  it("sin nota no aparece esa fila", async () => {
    abrir("/contactos/7");

    await screen.findByRole("heading", { name: "Ana Smith" });
    expect(screen.queryByText("Nota", { selector: "dt" })).toBeNull();
  });

  it("una nota con tilde se avisa sin llamar a la API", async () => {
    const u = abrir("/contactos/7");

    await u.click(await screen.findByRole("button", { name: "Editar" }));
    await u.type(await screen.findByLabelText("Nota (opcional)"), "niño");

    expect(screen.getByLabelText("Nota (opcional)").getAttribute("aria-invalid")).toBe("true");
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));
    expect(puts()).toHaveLength(0);
  });

  it("si otra persona guardó antes (409 y versión nueva), muestra la ficha actual con un aviso", async () => {
    const deOtraPersona = { ...ANA, last_name: "Brown", version: 2, updated_by_email: "admin@prueba.example.com" };
    rutas["PUT /api/contacts/7"] = () => ({ status: 409, cuerpo: { detail: "Otra persona ha cambiado esta ficha mientras la editabas" } });
    const u = abrir("/contactos/7");
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
    const u = abrir("/contactos/7");
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
    const u = abrir("/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));

    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Ya existe un contacto con ese nombre, apellidos y email");
    expect(screen.getByRole("button", { name: "Guardar cambios" })).toBeTruthy();
  });

  it("con tildes no se envía y sale el aviso", async () => {
    const u = abrir("/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));
    await u.clear(screen.getByLabelText("Nombre"));
    await u.type(screen.getByLabelText("Nombre"), "Ánna");

    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(screen.getByText(AVISO_TILDES)).toBeTruthy());
    expect(puts()).toHaveLength(0);
  });

  it("cancelar vuelve a la ficha sin enviar nada", async () => {
    const u = abrir("/contactos/7");
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

describe("estado comercial y responsable (T14)", () => {
  const cambiosDeEstado = () => llamadas.filter((l) => l.metodo === "PUT" && l.ruta === "/api/contacts/7/status");
  const botones = () =>
    screen
      .getAllByRole("button")
      .map((b) => b.textContent)
      .filter((t) => t !== "Cerrar sesión" && t !== "Nueva tarea"); // esta no depende del estado

  it("muestra el responsable, o «Sin responsable»", async () => {
    abrir("/contactos/7");
    expect(await screen.findByRole("heading", { name: "Ana Smith" })).toBeTruthy();
    expect(dato("Responsable")).toBe("recepcion@prueba.example.com");

    cleanup();
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, owner_id: null, owner_email: null } });
    abrir("/contactos/7");
    await screen.findByRole("heading", { name: "Ana Smith" });
    expect(dato("Responsable")).toBe("Sin responsable");
  });

  it.each([
    ["new", ["Dar cita", "Editar", "Marcar como contactado", "Marcar como perdido"]],
    ["contacted", ["Dar cita", "Editar", "Marcar como perdido"]],
    ["scheduled", ["Dar cita", "Editar", "Marcar como perdido"]],
    ["client", ["Dar cita", "Editar", "Marcar como perdido"]],
    ["lost", ["Editar", "Reabrir (pasa a Contactado)"]],
  ] as const)("en «%s» solo ofrece los cambios permitidos", async (estado, esperados) => {
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, status: estado } });
    abrir("/contactos/7");
    await screen.findByRole("heading", { name: "Ana Smith" });

    expect(botones()).toEqual(esperados);
  });

  it("cambiar el estado envía la versión y el token, y muestra el nuevo estado", async () => {
    rutas["PUT /api/contacts/7/status"] = (cuerpo) => ({
      status: 200,
      cuerpo: { ...ANA, ...(cuerpo as object), version: 4, updated_by_email: "recepcion@prueba.example.com" },
    });
    // Versión 3: la que se leyó, no la primera.
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, version: 3 } });
    const u = abrir("/contactos/7");

    await u.click(await screen.findByRole("button", { name: "Marcar como contactado" }));

    expect((await screen.findByRole("status")).textContent).toBe("Estado cambiado a «Contactado»");
    expect(dato("Estado")).toBe("Contactado");
    expect(cambiosDeEstado()).toHaveLength(1);
    expect(cambiosDeEstado()[0].cuerpo).toEqual({ status: "contacted", version: 3 });
    expect(cambiosDeEstado()[0].headers["X-CSRF-Token"]).toBe("csrf-recepcion");
    expect(botones()).toEqual(["Dar cita", "Editar", "Marcar como perdido"]);
  });

  it("si otra persona cambió la ficha antes (409), muestra la actual con el aviso", async () => {
    rutas["PUT /api/contacts/7/status"] = () => ({ status: 409, cuerpo: { detail: "Otra persona ha cambiado esta ficha mientras la editabas" } });
    const u = abrir("/contactos/7");
    const boton = await screen.findByRole("button", { name: "Marcar como perdido" });
    // Mientras se miraba la ficha, otra persona la pasó a Contactado.
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, status: "contacted", version: 2 } });
    await u.click(boton);

    expect((await screen.findByRole("alert")).textContent).toBe(AVISO_OTRA_VERSION);
    expect(dato("Estado")).toBe("Contactado");
  });

  it("un cambio no permitido (422) se explica", async () => {
    rutas["PUT /api/contacts/7/status"] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body", "status"], msg: "No se puede pasar de «Perdido» a «Perdido»" }] },
    });
    const u = abrir("/contactos/7");

    await u.click(await screen.findByRole("button", { name: "Marcar como perdido" }));

    expect((await screen.findByRole("alert")).textContent).toBe("No se puede pasar de «Perdido» a «Perdido»");
    expect(dato("Estado")).toBe("Nuevo");
  });

  it("al editar se elige el responsable entre recepción y admin, o ninguno", async () => {
    rutas["PUT /api/contacts/7"] = (cuerpo) => ({
      status: 200,
      cuerpo: { ...ANA, ...(cuerpo as object), owner_email: "admin@prueba.example.com", version: 2 },
    });
    const u = abrir("/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));

    const selector = (await screen.findByLabelText("Responsable")) as HTMLSelectElement;
    expect(selector.value).toBe("2");
    expect([...selector.options].map((o) => o.textContent)).toEqual([
      "Sin responsable",
      "admin@prueba.example.com",
      "recepcion@prueba.example.com",
    ]);
    await u.selectOptions(selector, "1");
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await screen.findByText("Cambios guardados");
    expect(puts()[0].cuerpo).toMatchObject({ owner_id: 1, version: 1 });
    expect(dato("Responsable")).toBe("admin@prueba.example.com");
  });

  it("«Sin responsable» envía null", async () => {
    rutas["PUT /api/contacts/7"] = (cuerpo) => ({ status: 200, cuerpo: { ...ANA, ...(cuerpo as object), owner_email: null, version: 2 } });
    const u = abrir("/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));

    await u.selectOptions(await screen.findByLabelText("Responsable"), "");
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await screen.findByText("Cambios guardados");
    expect(puts()[0].cuerpo).toMatchObject({ owner_id: null });
  });

  it("un responsable que ya no puede serlo sigue en la lista para no cambiarlo sin querer", async () => {
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, owner_id: 5, owner_email: "baja@prueba.example.com" } });
    const u = abrir("/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));

    const selector = (await screen.findByLabelText("Responsable")) as HTMLSelectElement;

    expect(selector.value).toBe("5");
    expect(selector.selectedOptions[0].textContent).toBe("baja@prueba.example.com (ya no disponible)");
  });

  it("un 422 del responsable sale junto al desplegable", async () => {
    rutas["PUT /api/contacts/7"] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body", "owner_id"], msg: "El responsable debe ser una cuenta activa de recepción o administración" }] },
    });
    const u = abrir("/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));
    await u.selectOptions(await screen.findByLabelText("Responsable"), "1");

    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("El responsable debe ser una cuenta activa de recepción o administración")).toBeTruthy();
    expect(screen.getByLabelText("Responsable").getAttribute("aria-invalid")).toBe("true");
  });

  it("si no se puede cargar la lista de responsables, se explica y se puede reintentar", async () => {
    rutas["GET /api/contacts/owners"] = () => ({ status: 503 });
    const u = abrir("/contactos/7");
    await u.click(await screen.findByRole("button", { name: "Editar" }));

    expect((await screen.findByRole("alert")).textContent).toMatch(/No se pudo cargar la lista de responsables/);
    rutas["GET /api/contacts/owners"] = () => ({ status: 200, cuerpo: RESPONSABLES });
    await u.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByLabelText("Responsable")).toBeTruthy();
  });
});
