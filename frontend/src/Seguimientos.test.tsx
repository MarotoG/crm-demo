// Pruebas de las tareas de seguimiento en la ficha (T24), con una API falsa en fetch.

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { hoyEnLaClinica } from "./Agenda";
import App from "./App";
import type { ContactoDetalle, TareaSeguimiento } from "./api";
import { AVISO_TILDES } from "./Contactos";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = { metodo: string; ruta: string; headers: Record<string, string>; cuerpo: unknown };

const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };
const PROFESIONAL = { id: 3, email: "prof@prueba.example.com", role: "professional", csrf_token: "csrf-prof" };

const ANA: ContactoDetalle = {
  id: 7,
  first_name: "Ana",
  last_name: "Smith",
  email: "ana@clinica.example.com",
  phone: null,
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

const TAREA: TareaSeguimiento = {
  id: 40,
  contact_id: 7,
  contact_name: "Ana Smith",
  contact_status: "new",
  description: "Llamar para confirmar",
  due_on: "2027-01-11",
  assigned_to_id: 3,
  assigned_to_email: "prof@prueba.example.com",
  created_by_email: "recepcion@prueba.example.com",
  created_at: "2026-11-04T15:00:00Z",
  completed_at: null,
  completed_by_email: null,
  version: 1,
};

const HOY = "2026-11-04";

const ASIGNABLES = [
  { id: 2, email: "recepcion@prueba.example.com" },
  { id: 3, email: "prof@prueba.example.com" },
];

const RUTA_TAREAS = "/api/contacts/7/follow-ups";

let usuario: typeof RECEPCION;
let rutas: Record<string, (cuerpo: unknown) => Respuesta>;
let llamadas: Llamada[];

beforeEach(() => {
  llamadas = [];
  usuario = RECEPCION;
  rutas = {
    "GET /api/auth/me": () => ({ status: 200, cuerpo: usuario }),
    "GET /api/contacts/7": () => ({ status: 200, cuerpo: ANA }),
    "GET /api/appointments/by-contact/7": () => ({ status: 200, cuerpo: { total: 0, items: [] } }),
    "GET /api/contacts/7/portal": () => ({ status: 200, cuerpo: { has_account: true, invitation_expires_at: null } }),
    [`GET ${RUTA_TAREAS}`]: () => ({ status: 200, cuerpo: { today: HOY, total: 1, items: [TAREA] } }),
    "GET /api/contacts/7/follow-up-assignees": () => ({ status: 200, cuerpo: ASIGNABLES }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (ruta: string, init: RequestInit = {}) => {
      const metodo = init.method ?? "GET";
      const cuerpo = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      const ruta_ = new URL(ruta, "http://localhost").pathname;
      llamadas.push({ metodo, ruta: ruta_, headers: (init.headers ?? {}) as Record<string, string>, cuerpo });
      const r = rutas[`${metodo} ${ruta_}`]?.(cuerpo) ?? { status: 404, cuerpo: { detail: "No encontrado" } };
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

function abrir() {
  render(
    <MemoryRouter initialEntries={["/contactos/7"]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const posts = () => llamadas.filter((l) => l.metodo === "POST");

async function seccion() {
  const titulo = await screen.findByRole("heading", { name: /seguimientos/i });
  return within(titulo.closest("section") as HTMLElement);
}

async function abrirFormulario() {
  const usuarioReal = abrir();
  await usuarioReal.click(await screen.findByRole("button", { name: "Nueva tarea" }));
  await screen.findByLabelText("Quién se encarga");
  return usuarioReal;
}

async function rellenar(u: ReturnType<typeof userEvent.setup>, descripcion = "Llamar a Ana") {
  await u.type(screen.getByLabelText("Qué hay que hacer"), descripcion);
  await u.type(screen.getByLabelText("Fecha prevista"), "2027-01-11");
  await u.selectOptions(screen.getByLabelText("Quién se encarga"), "3");
}

describe("lista de tareas", () => {
  it("muestra la fecha, la descripción y el responsable", async () => {
    abrir();
    const s = await seccion();
    expect(await s.findByText("Llamar para confirmar")).toBeTruthy();
    expect(s.getByText("Responsable: prof@prueba.example.com")).toBeTruthy();
    expect(s.getByText(/11 de enero|11 ene/)).toBeTruthy();
  });

  it("sin tareas lo dice", async () => {
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 200, cuerpo: { today: HOY, total: 0, items: [] } });
    abrir();
    const s = await seccion();
    expect(await s.findByText("Todavía no tiene tareas.")).toBeTruthy();
  });

  it("avisa si hay más de las que se muestran", async () => {
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 200, cuerpo: { today: HOY, total: 25, items: [TAREA] } });
    abrir();
    const s = await seccion();
    expect(await s.findByText("Mostrando 1 de 25; el resto, en «Pendientes».")).toBeTruthy();
  });

  it("si la sesión caducó vuelve al login", async () => {
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 401, cuerpo: { detail: "Sesión no válida" } });
    abrir();
    expect(await screen.findByRole("button", { name: /entrar/i })).toBeTruthy();
  });

  it("un error se puede reintentar", async () => {
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 503 });
    const u = abrir();
    const s = await seccion();
    await s.findByRole("alert");
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 200, cuerpo: { today: HOY, total: 1, items: [TAREA] } });
    await u.click(s.getByRole("button", { name: "Reintentar" }));
    expect(await s.findByText("Llamar para confirmar")).toBeTruthy();
  });
});

describe("profesional", () => {
  beforeEach(() => {
    usuario = PROFESIONAL;
  });

  it("ve sus tareas sin el botón de crear ni el responsable", async () => {
    abrir();
    const s = await screen.findByRole("heading", { name: "Tus seguimientos" });
    const seccionTareas = within(s.closest("section") as HTMLElement);
    expect(await seccionTareas.findByText("Llamar para confirmar")).toBeTruthy();
    expect(seccionTareas.queryByText(/Responsable:/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Nueva tarea" })).toBeNull();
    expect(llamadas.some((l) => l.ruta.endsWith("follow-up-assignees"))).toBe(false);
  });

  it("sin tareas lo dice en su lenguaje", async () => {
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 200, cuerpo: { today: HOY, total: 0, items: [] } });
    abrir();
    expect(await screen.findByText("No tienes tareas de este contacto.")).toBeTruthy();
  });
});

describe("completar, reabrir y editar en la ficha (T25)", () => {
  const RUTA_HECHA = "/api/follow-ups/40/complete";

  it("«Hecha» envía la versión con el CSRF, avisa y recarga la lista", async () => {
    const hecha = { ...TAREA, completed_at: "2026-11-04T16:00:00Z", completed_by_email: "recepcion@prueba.example.com", version: 2 };
    let marcada = false;
    rutas[`POST ${RUTA_HECHA}`] = () => {
      marcada = true;
      return { status: 200, cuerpo: hecha };
    };
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 200, cuerpo: { today: HOY, total: 1, items: [marcada ? hecha : TAREA] } });
    const u = abrir();
    await u.click(await screen.findByRole("button", { name: "Hecha" }));

    expect(await screen.findByText("Tarea marcada como hecha")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Reabrir" })).toBeTruthy();
    expect(screen.getByText(/Hecha el .* · recepcion@prueba.example.com/)).toBeTruthy();
    const [post] = posts();
    expect(post.cuerpo).toEqual({ version: 1 });
    expect(post.headers["X-CSRF-Token"]).toBe("csrf-recepcion");
  });

  it("una hecha ofrece «Reabrir», sin «Hecha» ni editar la tarea", async () => {
    const hecha = { ...TAREA, completed_at: "2026-11-04T16:00:00Z", completed_by_email: null, version: 5 };
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 200, cuerpo: { today: HOY, total: 1, items: [hecha] } });
    rutas["POST /api/follow-ups/40/reopen"] = () => ({ status: 200, cuerpo: TAREA });
    const u = abrir();
    const s = await seccion();
    const boton = await s.findByRole("button", { name: "Reabrir" });
    expect(s.queryByRole("button", { name: "Hecha" })).toBeNull();
    expect(s.queryByRole("button", { name: "Editar" })).toBeNull();
    expect(s.getByText(/cuenta ya no disponible/)).toBeTruthy();
    await u.click(boton);

    expect(await screen.findByText("Tarea reabierta")).toBeTruthy();
    expect(posts()[0].ruta).toBe("/api/follow-ups/40/reopen");
    expect(posts()[0].cuerpo).toEqual({ version: 5 });
  });

  it("marca como vencida solo a la pendiente de antes de hoy según la API", async () => {
    rutas[`GET ${RUTA_TAREAS}`] = () => ({
      status: 200,
      cuerpo: {
        today: "2027-01-11",
        total: 3,
        items: [
          { ...TAREA, id: 1, due_on: "2027-01-10", description: "Antes" },
          { ...TAREA, id: 2, due_on: "2027-01-11", description: "Hoy" },
          { ...TAREA, id: 3, due_on: "2027-01-10", description: "Hecha antes", completed_at: "2027-01-10T16:00:00Z" },
        ],
      },
    });
    abrir();
    const s = await seccion();
    const vencidas = await s.findAllByText("Vencida");
    expect(vencidas).toHaveLength(1);
    expect(vencidas[0].closest("li")?.textContent).toContain("Antes");
  });

  it("si otra persona la cambió (409), avisa y recarga en vez de pisarla", async () => {
    rutas[`POST ${RUTA_HECHA}`] = () => ({ status: 409, cuerpo: { detail: "Esta tarea ya está hecha" } });
    const u = abrir();
    await u.click(await screen.findByRole("button", { name: "Hecha" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Esta tarea ya está hecha");
    const lecturas = llamadas.filter((l) => l.metodo === "GET" && l.ruta === RUTA_TAREAS);
    expect(lecturas.length).toBeGreaterThanOrEqual(2);
  });

  it("si la sesión caducó al marcarla vuelve al login", async () => {
    rutas[`POST ${RUTA_HECHA}`] = () => ({ status: 401, cuerpo: { detail: "Sesión no válida" } });
    const u = abrir();
    await u.click(await screen.findByRole("button", { name: "Hecha" }));

    expect(await screen.findByRole("button", { name: /entrar/i })).toBeTruthy();
  });

  it("el profesional marca, pero no edita", async () => {
    usuario = PROFESIONAL;
    abrir();
    const s = await seccion();
    expect(await s.findByRole("button", { name: "Hecha" })).toBeTruthy();
    expect(s.queryByRole("button", { name: "Editar" })).toBeNull();
  });

  async function abrirEdicion() {
    const u = abrir();
    const s = await seccion();
    await u.click(await s.findByRole("button", { name: "Editar" }));
    await screen.findByLabelText("Quién se encarga");
    return u;
  }

  it("editar abre el formulario con los datos y envía también la versión", async () => {
    rutas["PUT /api/follow-ups/40"] = () => ({ status: 200, cuerpo: { ...TAREA, version: 2 } });
    const u = await abrirEdicion();
    const texto = screen.getByLabelText("Qué hay que hacer") as HTMLInputElement;
    expect(texto.value).toBe("Llamar para confirmar");
    expect((screen.getByLabelText("Fecha prevista") as HTMLInputElement).value).toBe("2027-01-11");
    expect((screen.getByLabelText("Quién se encarga") as HTMLSelectElement).value).toBe("3");

    await u.selectOptions(screen.getByLabelText("Quién se encarga"), "2");
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("Tarea guardada")).toBeTruthy();
    const put = llamadas.find((l) => l.metodo === "PUT");
    expect(put?.cuerpo).toEqual({ description: "Llamar para confirmar", due_on: "2027-01-11", assigned_to_id: 2, version: 1 });
    expect(put?.headers["X-CSRF-Token"]).toBe("csrf-recepcion");
  });

  it("al editar, un responsable que ya no se podría asignar sigue en el desplegable", async () => {
    rutas["GET /api/contacts/7/follow-up-assignees"] = () => ({ status: 200, cuerpo: [ASIGNABLES[0]] });
    await abrirEdicion();
    const opciones = within(screen.getByLabelText("Quién se encarga")).getAllByRole("option");
    expect(opciones.map((o) => o.textContent)).toContain("prof@prueba.example.com (ya no disponible)");
    expect((screen.getByLabelText("Quién se encarga") as HTMLSelectElement).value).toBe("3");
  });

  it("al editar, un 409 cierra el formulario, avisa y recarga", async () => {
    rutas["PUT /api/follow-ups/40"] = () => ({ status: 409, cuerpo: { detail: "Otra persona ha cambiado esta tarea." } });
    const u = await abrirEdicion();
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Otra persona ha cambiado esta tarea.");
    expect(screen.queryByRole("button", { name: "Guardar cambios" })).toBeNull();
  });

  it("al editar, un 422 sale junto al campo y el formulario sigue abierto", async () => {
    const mensaje = "La fecha prevista no puede ser anterior a hoy";
    rutas["PUT /api/follow-ups/40"] = () => ({ status: 422, cuerpo: { detail: [{ loc: ["body", "due_on"], msg: mensaje }] } });
    const u = await abrirEdicion();
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect((await screen.findByText(mensaje)).id).toBe("error-tarea-due_on");
    expect(screen.getByRole("button", { name: "Guardar cambios" })).toBeTruthy();
  });

  it("al editar envía la versión que se leyó, no otra", async () => {
    rutas[`GET ${RUTA_TAREAS}`] = () => ({ status: 200, cuerpo: { today: HOY, total: 1, items: [{ ...TAREA, version: 7 }] } });
    rutas["PUT /api/follow-ups/40"] = () => ({ status: 200, cuerpo: { ...TAREA, version: 8 } });
    const u = await abrirEdicion();
    await u.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await screen.findByText("Tarea guardada");
    expect((llamadas.find((l) => l.metodo === "PUT")?.cuerpo as { version: number }).version).toBe(7);
  });

  it("cambiar una tarea desde la ficha actualiza el contador de la barra", async () => {
    rutas[`POST ${RUTA_HECHA}`] = () => ({ status: 200, cuerpo: TAREA });
    rutas["GET /api/follow-ups/summary"] = () => ({ status: 200, cuerpo: { overdue: 0, due_today: 0 } });
    const u = abrir();
    const boton = await screen.findByRole("button", { name: "Hecha" });
    const pedidos = () => llamadas.filter((l) => l.ruta === "/api/follow-ups/summary").length;
    await waitFor(() => expect(pedidos()).toBeGreaterThan(0));
    const antes = pedidos();

    await u.click(boton);

    await waitFor(() => expect(pedidos()).toBeGreaterThan(antes));
  });

  it("cancelar la edición vuelve a la fila sin llamar a la API", async () => {
    const u = await abrirEdicion();
    await u.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByLabelText("Qué hay que hacer")).toBeNull();
    expect(llamadas.some((l) => l.metodo === "PUT")).toBe(false);
  });
});

describe("crear una tarea", () => {
  it("el desplegable ofrece a quien da la API", async () => {
    await abrirFormulario();
    const opciones = within(screen.getByLabelText("Quién se encarga")).getAllByRole("option");
    expect(opciones.map((o) => o.textContent)).toEqual(["Elige una persona…", ...ASIGNABLES.map((a) => a.email)]);
  });

  it("el calendario no deja elegir antes de hoy en la clínica", async () => {
    await abrirFormulario();
    expect(screen.getByLabelText("Fecha prevista").getAttribute("min")).toBe(hoyEnLaClinica());
  });

  it("envía los datos con el CSRF, recarga la lista y cierra el formulario", async () => {
    let pedida = false;
    rutas[`POST ${RUTA_TAREAS}`] = () => {
      pedida = true;
      return { status: 201, cuerpo: TAREA };
    };
    const nueva = { ...TAREA, id: 41, description: "Llamar a Ana" };
    rutas[`GET ${RUTA_TAREAS}`] = () => ({
      status: 200,
      cuerpo: pedida ? { today: HOY, total: 2, items: [TAREA, nueva] } : { today: HOY, total: 1, items: [TAREA] },
    });
    const u = await abrirFormulario();
    await rellenar(u);
    await u.click(screen.getByRole("button", { name: "Crear tarea" }));

    expect(await screen.findByText("Tarea creada")).toBeTruthy();
    expect(await screen.findByText("Llamar a Ana")).toBeTruthy();
    expect(screen.queryByLabelText("Qué hay que hacer")).toBeNull();
    const [post] = posts();
    expect(post.ruta).toBe(RUTA_TAREAS);
    expect(post.cuerpo).toEqual({ description: "Llamar a Ana", due_on: "2027-01-11", assigned_to_id: 3 });
    expect(post.headers["X-CSRF-Token"]).toBe("csrf-recepcion");
  });

  it("sin fecha ni responsable no llama a la API y lo explica junto a cada campo", async () => {
    const u = await abrirFormulario();
    await u.type(screen.getByLabelText("Qué hay que hacer"), "Llamar");
    await u.click(screen.getByRole("button", { name: "Crear tarea" }));

    expect(screen.getByText("Indica la fecha prevista")).toBeTruthy();
    expect(screen.getByText("Elige quién se encarga")).toBeTruthy();
    expect(posts()).toEqual([]);
  });

  it("con una tilde avisa al escribir y no envía", async () => {
    const u = await abrirFormulario();
    await rellenar(u, "Llamar mañana");

    expect(screen.getByText(AVISO_TILDES)).toBeTruthy();
    await u.click(screen.getByRole("button", { name: "Crear tarea" }));
    expect(posts()).toEqual([]);
  });

  it("muestra junto al campo el rechazo de la API", async () => {
    const mensaje = "Este profesional no tiene citas con este contacto: asígnala a recepción o administración";
    rutas[`POST ${RUTA_TAREAS}`] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body", "assigned_to_id"], msg: mensaje }] },
    });
    const u = await abrirFormulario();
    await rellenar(u);
    await u.click(screen.getByRole("button", { name: "Crear tarea" }));

    const error = await screen.findByText(mensaje);
    expect(error.id).toBe("error-tarea-assigned_to_id");
    expect(screen.getByLabelText("Quién se encarga").getAttribute("aria-invalid")).toBe("true");
    // Sin perder lo escrito.
    expect((screen.getByLabelText("Qué hay que hacer") as HTMLInputElement).value).toBe("Llamar a Ana");
  });

  it("corregir el campo quita su error", async () => {
    rutas[`POST ${RUTA_TAREAS}`] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body", "due_on"], msg: "La fecha prevista no puede ser anterior a hoy" }] },
    });
    const u = await abrirFormulario();
    await rellenar(u);
    await u.click(screen.getByRole("button", { name: "Crear tarea" }));
    await screen.findByText("La fecha prevista no puede ser anterior a hoy");

    await u.clear(screen.getByLabelText("Fecha prevista"));

    expect(screen.queryByText("La fecha prevista no puede ser anterior a hoy")).toBeNull();
  });

  it("un 403 se muestra encima de los botones y se puede volver a intentar", async () => {
    rutas[`POST ${RUTA_TAREAS}`] = () => ({ status: 403, cuerpo: { detail: "Token CSRF ausente o no válido" } });
    const u = await abrirFormulario();
    await rellenar(u);
    await u.click(screen.getByRole("button", { name: "Crear tarea" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Token CSRF ausente o no válido");
    expect((screen.getByRole("button", { name: "Crear tarea" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("si la sesión caducó vuelve al login", async () => {
    rutas[`POST ${RUTA_TAREAS}`] = () => ({ status: 401, cuerpo: { detail: "Sesión no válida" } });
    const u = await abrirFormulario();
    await rellenar(u);
    await u.click(screen.getByRole("button", { name: "Crear tarea" }));

    expect(await screen.findByRole("button", { name: /entrar/i })).toBeTruthy();
  });

  it("cancelar cierra el formulario sin llamar a la API", async () => {
    const u = await abrirFormulario();
    await u.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByLabelText("Qué hay que hacer")).toBeNull();
    expect(screen.getByRole("button", { name: "Nueva tarea" })).toBeTruthy();
    expect(posts()).toEqual([]);
  });

  it("si no carga la lista de personas se puede reintentar o cancelar", async () => {
    rutas["GET /api/contacts/7/follow-up-assignees"] = () => ({ status: 503 });
    const u = abrir();
    await u.click(await screen.findByRole("button", { name: "Nueva tarea" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/No se pudo cargar quién puede encargarse/);

    rutas["GET /api/contacts/7/follow-up-assignees"] = () => ({ status: 200, cuerpo: ASIGNABLES });
    await u.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByLabelText("Quién se encarga")).toBeTruthy();
  });
});
