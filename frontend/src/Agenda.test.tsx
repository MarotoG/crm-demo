// Pruebas de la agenda y del formulario de cita (T18), de reprogramar y cancelar (T19), de la vista del mes y
// «Mi agenda» del profesional (T20) y de la asistencia (T20b), con una API falsa en fetch.

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  diaValido,
  formatoDia,
  formatoMes,
  horaEn,
  hoyEnLaClinica,
  minutosDesde,
  porDia,
  primeroDeMes,
  resumenPorServicio,
  sePuedeCambiar,
  sePuedeCorregir,
  sePuedeMarcar,
  sumarDias,
  sumarMeses,
  ultimoDeMes,
} from "./Agenda";
import App from "./App";
import type { CitaAgenda, Contacto, ContactoDetalle, PersonaServicio, Servicio } from "./api";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = { metodo: string; ruta: string; consulta: URLSearchParams; headers: Record<string, string>; cuerpo: unknown };

const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };

const P_ADMIN: PersonaServicio = { id: 1, email: "admin@prueba.example.com", role: "admin", active: true };
const P_PRO: PersonaServicio = { id: 3, email: "pro@prueba.example.com", role: "professional", active: true };
const P_BAJA: PersonaServicio = { id: 9, email: "baja@prueba.example.com", role: "professional", active: false };

const BOTOX: Servicio = { id: 10, name: "Botox", duration_minutes: 60, active: true, version: 1, staff: [P_PRO] };
// La persona de baja sigue asignada al Peel, pero no se ofrece.
const PEEL: Servicio = { id: 12, name: "Peel", duration_minutes: 30, active: true, version: 1, staff: [P_ADMIN, P_PRO, P_BAJA] };
const FACIAL: Servicio = { id: 11, name: "Facial", duration_minutes: 90, active: false, version: 1, staff: [P_PRO] };
const SIN_NADIE: Servicio = { id: 13, name: "Laser", duration_minutes: 45, active: true, version: 1, staff: [P_BAJA] };

const ANA: Contacto = {
  id: 7,
  first_name: "Ana",
  last_name: "Lopez",
  email: "ana@clinica.example.com",
  phone: "+12125550123",
  source: "instagram",
  status: "new",
  created_at: "2026-11-02T23:05:00Z",
  owner_id: 2,
  owner_email: RECEPCION.email,
};
const BEA: Contacto = { ...ANA, id: 8, first_name: "Bea", last_name: "Ruiz", email: "bea@clinica.example.com", phone: null };
const ANA_FICHA: ContactoDetalle = { ...ANA, version: 1, updated_at: ANA.created_at, created_by_email: RECEPCION.email, updated_by_email: null };

function cita(id: number, inicio: string, fin: string, cambios: Partial<CitaAgenda> = {}): CitaAgenda {
  return {
    id,
    contact_id: 7,
    service_id: 10,
    staff_id: 3,
    starts_at: inicio,
    ends_at: fin,
    duration_minutes: 60,
    status: "scheduled",
    version: 1,
    created_at: "2027-01-04T15:00:00-05:00",
    cancel_reason: null,
    cancel_note: null,
    attended_at: null,
    contact_name: "Ana Lopez",
    service_name: "Botox",
    staff_email: P_PRO.email,
    ...cambios,
  };
}

// Lunes 11/01/2027: Ana a las 9:30 con el profesional; Bea de 23:30 a 0:30 con la admin.
const DE_ANA = cita(1, "2027-01-11T09:30:00-05:00", "2027-01-11T10:30:00-05:00");
const DE_BEA = cita(2, "2027-01-11T23:30:00-05:00", "2027-01-12T00:30:00-05:00", {
  contact_id: 8,
  contact_name: "Bea Ruiz",
  service_id: 12,
  service_name: "Peel",
  staff_id: 1,
  staff_email: P_ADMIN.email,
});

let rutas: Record<string, (llamada: Llamada) => Respuesta>;
let llamadas: Llamada[];

/** La agenda falsa: filtra por día (o intervalo, T20), persona y contacto como la API. */
function agendaFalsa(citas: CitaAgenda[]) {
  return ({ consulta }: Llamada): Respuesta => {
    const dia = consulta.get("date");
    const [desde, hasta] = dia ? [dia, dia] : [consulta.get("from") ?? "", consulta.get("to") ?? ""];
    const dentro = (iso: string) => iso.slice(0, 10) >= desde && iso.slice(0, 10) <= hasta;
    const persona = consulta.get("staff_id");
    const contacto = consulta.get("contact_id");
    const delDia = citas.filter(
      (c) =>
        (dentro(c.starts_at) || dentro(c.ends_at)) &&
        (!persona || String(c.staff_id) === persona) &&
        (!contacto || String(c.contact_id) === contacto),
    );
    return { status: 200, cuerpo: delDia };
  };
}

beforeEach(() => {
  llamadas = [];
  rutas = {
    "GET /api/auth/me": () => ({ status: 200, cuerpo: RECEPCION }),
    "GET /api/appointments": agendaFalsa([DE_ANA, DE_BEA]),
    "GET /api/services/staff": () => ({ status: 200, cuerpo: [P_ADMIN, P_PRO] }),
    "GET /api/services": () => ({ status: 200, cuerpo: [BOTOX, PEEL, FACIAL, SIN_NADIE] }),
    "GET /api/contacts": () => ({ status: 200, cuerpo: { total: 2, items: [ANA, BEA] } }),
    "GET /api/contacts/7": () => ({ status: 200, cuerpo: ANA_FICHA }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (ruta: string, init: RequestInit = {}) => {
      const url = new URL(ruta, "http://localhost");
      const llamada: Llamada = {
        metodo: init.method ?? "GET",
        ruta: url.pathname,
        consulta: url.searchParams,
        headers: (init.headers ?? {}) as Record<string, string>,
        cuerpo: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
      };
      llamadas.push(llamada);
      const r = rutas[`${llamada.metodo} ${llamada.ruta}`]?.(llamada) ?? { status: 404, cuerpo: { detail: "Not Found" } };
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

function abrir(ruta = "/agenda?fecha=2027-01-11") {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const diasPedidos = () =>
  llamadas.filter((l) => l.ruta === "/api/appointments" && !l.consulta.has("contact_id") && !l.consulta.has("staff_id")).map((l) => l.consulta.get("date"));
const posts = () => llamadas.filter((l) => l.metodo === "POST" && l.ruta === "/api/appointments");

async function filas() {
  const ul = await waitFor(() => {
    const encontrada = document.querySelector("ul.citas");
    if (!encontrada) throw new Error("sin lista de citas");
    return encontrada as HTMLElement;
  });
  // Solo los datos de la cita, sin los botones ni el recuadro de cancelar (T19).
  return within(ul)
    .getAllByRole("listitem")
    .map((li) => [...li.querySelectorAll(".cita__hora, .cita__contacto, .cita__meta")].map((e) => e.textContent).join(""));
}

// --- La agenda del día -------------------------------------------------------------------

describe("agenda del día", () => {
  it("muestra las citas por hora con contacto, servicio y persona, y el día en palabras", async () => {
    abrir();

    expect(await filas()).toEqual([
      `9:30–10:30Ana LopezBotox · ${P_PRO.email}`,
      `23:30–0:30 (12/01)Bea RuizPeel · ${P_ADMIN.email}`,
    ]);
    expect(screen.getByRole("heading", { name: /lunes, 11 de enero de 2027/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ana Lopez" }).getAttribute("href")).toBe("/contactos/7");
    expect(diasPedidos()).toEqual(["2027-01-11"]);
  });

  it("sin citas lo dice", async () => {
    rutas["GET /api/appointments"] = () => ({ status: 200, cuerpo: [] });
    abrir();

    expect(await screen.findByText("No hay citas este día.")).toBeTruthy();
  });

  it("una cita que no está programada dice su estado", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([{ ...DE_ANA, status: "cancelled" }]);
    abrir();

    expect((await filas())[0]).toBe(`9:30–10:30Ana LopezBotox · ${P_PRO.email} · Cancelada`);
  });

  it("día anterior, siguiente y hoy cambian el día que se pide", async () => {
    const u = abrir();
    await filas();

    await u.click(screen.getByRole("button", { name: "Día siguiente →" }));
    await screen.findByRole("heading", { name: /martes, 12 de enero de 2027/ });
    await u.click(screen.getByRole("button", { name: "← Día anterior" }));
    await u.click(screen.getByRole("button", { name: "← Día anterior" }));
    await screen.findByRole("heading", { name: /domingo, 10 de enero de 2027/ });
    await u.click(screen.getByRole("button", { name: "Hoy" }));

    await waitFor(() => expect(diasPedidos().at(-1)).toBe(hoyEnLaClinica()));
    expect(diasPedidos().slice(0, 4)).toEqual(["2027-01-11", "2027-01-12", "2027-01-11", "2027-01-10"]);
    expect(screen.getByRole("button", { name: "Hoy" }).hasAttribute("disabled")).toBe(true);
  });

  it("sin fecha en la dirección, abre el día de hoy en la clínica", async () => {
    abrir("/agenda");

    await waitFor(() => expect(diasPedidos()).toEqual([hoyEnLaClinica()]));
  });

  it("el filtro de persona pide solo sus citas", async () => {
    const u = abrir();
    await filas();

    await u.selectOptions(screen.getByLabelText("Persona"), P_ADMIN.email);

    await waitFor(async () => expect(await filas()).toEqual([`23:30–0:30 (12/01)Bea RuizPeel · ${P_ADMIN.email}`]));
    expect(llamadas.filter((l) => l.ruta === "/api/appointments").at(-1)?.consulta.get("staff_id")).toBe("1");
  });

  it("si la API falla se puede reintentar", async () => {
    rutas["GET /api/appointments"] = () => ({ status: 503, cuerpo: { detail: "Servicio no disponible" } });
    const u = abrir();

    expect((await screen.findByRole("alert")).textContent).toBe("Servicio no disponible. Inténtalo de nuevo en unos minutos");
    rutas["GET /api/appointments"] = agendaFalsa([DE_ANA]);
    await u.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await filas()).toHaveLength(1);
  });

  it("si la sesión caduca, vuelve al login con un aviso", async () => {
    rutas["GET /api/appointments"] = () => ({ status: 401, cuerpo: { detail: "No autenticado" } });
    abrir();

    expect(await screen.findByText("Tu sesión ha caducado. Vuelve a entrar.")).toBeTruthy();
  });
});

// --- Dar una cita ------------------------------------------------------------------------

async function abrirFormulario(ruta?: string) {
  const u = abrir(ruta);
  await u.click(await screen.findByRole("button", { name: "Nueva cita" }));
  const formulario = within(await screen.findByRole("form", { name: "Nueva cita" }));
  return { u, formulario };
}

async function elegirContacto(u: ReturnType<typeof userEvent.setup>, nombre = "Ana Lopez") {
  const resultados = within(await screen.findByRole("list", { name: "Contactos encontrados" }));
  await u.click(resultados.getByRole("button", { name: nombre }));
}

describe("dar una cita", () => {
  it("contacto, servicio, persona (sola si es la única) y hora → envía la cita y la anuncia", async () => {
    const { u, formulario } = await abrirFormulario();
    rutas["POST /api/appointments"] = () => ({
      status: 201,
      cuerpo: cita(5, "2027-01-11T11:15:00-05:00", "2027-01-11T12:15:00-05:00"),
    });

    await elegirContacto(u);
    await u.selectOptions(formulario.getByLabelText("Servicio"), "Botox (1 h)");
    // Solo el profesional realiza el Botox: queda elegido.
    expect((formulario.getByLabelText("Quién la realiza") as HTMLSelectElement).value).toBe("3");
    await u.selectOptions(formulario.getByLabelText("Hora"), "11");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "15");
    await u.click(formulario.getByRole("button", { name: "Guardar cita" }));

    expect((await screen.findByRole("status")).textContent).toBe(
      "Cita creada: Ana Lopez, lunes, 11 de enero de 2027, 11:15–12:15 (Botox)",
    );
    expect(posts()).toHaveLength(1);
    expect(posts()[0].cuerpo).toEqual({ contact_id: 7, service_id: 10, staff_id: 3, starts_at: "2027-01-11T11:15" });
    expect(posts()[0].headers["X-CSRF-Token"]).toBe("csrf-recepcion");
    await waitFor(() => expect(screen.queryByRole("form", { name: "Nueva cita" })).toBeNull());
    // La agenda se vuelve a pedir para que aparezca.
    await waitFor(() => expect(diasPedidos().filter((d) => d === "2027-01-11").length).toBeGreaterThan(1));
  });

  it("solo ofrece servicios activos con alguien activo; con varias personas, hay que elegir", async () => {
    const { u, formulario } = await abrirFormulario();
    const servicios = formulario.getByLabelText("Servicio") as HTMLSelectElement;
    await waitFor(() => expect(servicios.options).toHaveLength(3));

    expect([...servicios.options].map((o) => o.textContent)).toEqual(["Elige el servicio…", "Botox (1 h)", "Peel (30 min)"]);
    await u.selectOptions(servicios, "Peel (30 min)");
    const personas = formulario.getByLabelText("Quién la realiza") as HTMLSelectElement;
    expect(personas.value).toBe("");
    expect([...personas.options].map((o) => o.textContent)).toEqual([
      "Elige quién la realiza…",
      `${P_ADMIN.email} · Administración`,
      `${P_PRO.email} · Profesional`,
    ]);
  });

  it("la búsqueda de contactos no ofrece los Perdidos", async () => {
    await abrirFormulario();
    await screen.findByRole("list", { name: "Contactos encontrados" });

    const pedida = llamadas.find((l) => l.ruta === "/api/contacts");
    expect(pedida?.consulta.getAll("status")).toEqual(["new", "contacted", "scheduled", "client"]);
  });

  it("sin datos no se envía y se dice qué falta", async () => {
    const { u, formulario } = await abrirFormulario();

    await u.click(formulario.getByRole("button", { name: "Guardar cita" }));

    expect(formulario.getByText("Elige el contacto")).toBeTruthy();
    expect(formulario.getByText("Elige el servicio")).toBeTruthy();
    expect(formulario.getByText("Elige quién la realiza")).toBeTruthy();
    expect(posts()).toHaveLength(0);
  });

  it("muestra lo que ya tiene ese día la persona elegida", async () => {
    const { u, formulario } = await abrirFormulario();

    await u.selectOptions(formulario.getByLabelText("Servicio"), "Botox (1 h)");

    expect(await formulario.findByText("Ya tiene ese día: 9:30–10:30")).toBeTruthy();
    fireEvent.change(formulario.getByLabelText("Día"), { target: { value: "2027-01-13" } });
    expect(await formulario.findByText("No tiene otras citas ese día.")).toBeTruthy();
  });

  it("si la persona ya tiene una cita que se pisa (409), lo dice junto al formulario", async () => {
    const { u, formulario } = await abrirFormulario();
    rutas["POST /api/appointments"] = () => ({ status: 409, cuerpo: { detail: "Esa persona ya tiene una cita de 9:30 a 10:30" } });
    await elegirContacto(u, "Bea Ruiz");
    await u.selectOptions(formulario.getByLabelText("Servicio"), "Botox (1 h)");
    await u.selectOptions(formulario.getByLabelText("Hora"), "10");

    await u.click(formulario.getByRole("button", { name: "Guardar cita" }));

    expect((await formulario.findByRole("alert")).textContent).toBe("Esa persona ya tiene una cita de 9:30 a 10:30");
    expect(screen.getByRole("form", { name: "Nueva cita" })).toBeTruthy(); // conserva lo elegido
  });

  it("un 422 de la API sale junto a su campo", async () => {
    const { u, formulario } = await abrirFormulario();
    rutas["POST /api/appointments"] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body", "starts_at"], msg: "La cita no puede empezar en el pasado" }] },
    });
    await elegirContacto(u);
    await u.selectOptions(formulario.getByLabelText("Servicio"), "Botox (1 h)");

    await u.click(formulario.getByRole("button", { name: "Guardar cita" }));

    expect(await formulario.findByText("La cita no puede empezar en el pasado")).toBeTruthy();
  });

  it("avisa, sin impedirlo, si el contacto ya tiene otra cita a esa hora", async () => {
    const { u, formulario } = await abrirFormulario();
    rutas["POST /api/appointments"] = () => ({ status: 201, cuerpo: cita(6, "2027-01-11T09:45:00-05:00", "2027-01-11T10:15:00-05:00") });
    await elegirContacto(u);
    // Peel con la admin a las 9:45, mientras Ana está en el Botox de 9:30 a 10:30 (tinte y pedicura, T17).
    await u.selectOptions(formulario.getByLabelText("Servicio"), "Peel (30 min)");
    await u.selectOptions(formulario.getByLabelText("Quién la realiza"), `${P_ADMIN.email} · Administración`);
    await u.selectOptions(formulario.getByLabelText("Hora"), "9");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "45");

    expect((await formulario.findByRole("status")).textContent).toMatch(
      new RegExp(`^Ana Lopez ya tiene otra cita a esa hora: 9:30–10:30 \\(Botox · ${P_PRO.email}\\)\\. Puedes guardar`),
    );
    await u.selectOptions(formulario.getByLabelText("Hora"), "10");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "30");
    expect(formulario.queryByRole("status")).toBeNull(); // a las 10:30 ya ha terminado
    await u.selectOptions(formulario.getByLabelText("Minutos"), "00");
    await u.selectOptions(formulario.getByLabelText("Hora"), "9");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "15");
    expect(await formulario.findByRole("status")).toBeTruthy(); // de 9:15 a 9:45: pisa el comienzo de la otra
    await u.selectOptions(formulario.getByLabelText("Hora"), "8");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "45");
    expect(formulario.queryByRole("status")).toBeNull(); // de 8:45 a 9:15: acaba antes
    await u.selectOptions(formulario.getByLabelText("Hora"), "9");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "45");
    await formulario.findByRole("status");

    await u.click(formulario.getByRole("button", { name: "Guardar cita" }));

    await screen.findByText(/^Cita creada: Ana Lopez/);
    expect(posts()[0].cuerpo).toEqual({ contact_id: 7, service_id: 12, staff_id: 1, starts_at: "2027-01-11T09:45" });
  });

  it("una cita cancelada del contacto no da aviso", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([{ ...DE_ANA, status: "cancelled" }]);
    const { u, formulario } = await abrirFormulario();
    await elegirContacto(u);
    await u.selectOptions(formulario.getByLabelText("Servicio"), "Peel (30 min)");
    await u.selectOptions(formulario.getByLabelText("Hora"), "9");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "45");

    await waitFor(() => expect(llamadas.some((l) => l.consulta.get("contact_id") === "7")).toBe(true));
    expect(formulario.queryByRole("status")).toBeNull();
  });

  it("al guardar una cita de otro día, la agenda pasa a ese día", async () => {
    const { u, formulario } = await abrirFormulario();
    rutas["POST /api/appointments"] = () => ({ status: 201, cuerpo: cita(7, "2027-01-13T09:00:00-05:00", "2027-01-13T10:00:00-05:00") });
    await elegirContacto(u);
    await u.selectOptions(formulario.getByLabelText("Servicio"), "Botox (1 h)");
    fireEvent.change(formulario.getByLabelText("Día"), { target: { value: "2027-01-13" } });

    await u.click(formulario.getByRole("button", { name: "Guardar cita" }));

    expect(await screen.findByRole("heading", { name: /miércoles, 13 de enero de 2027/ })).toBeTruthy();
    expect(posts()[0].cuerpo).toMatchObject({ starts_at: "2027-01-13T09:00" });
    expect(diasPedidos().at(-1)).toBe("2027-01-13");
  });

  it("cancelar cierra el formulario sin enviar nada", async () => {
    const { u, formulario } = await abrirFormulario();

    await u.click(formulario.getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByRole("form", { name: "Nueva cita" })).toBeNull());
    expect(posts()).toHaveLength(0);
  });

  it("desde la ficha, «Dar cita» abre el formulario con el contacto ya elegido", async () => {
    const u = abrir("/contactos/7");

    await u.click(await screen.findByRole("button", { name: "Dar cita" }));

    const formulario = within(await screen.findByRole("form", { name: "Nueva cita" }));
    expect(await formulario.findByText("Ana Lopez", { selector: "strong" })).toBeTruthy();
    expect(formulario.queryByLabelText(/Contacto: busca/)).toBeNull();
    // «Cambiar» vuelve a la búsqueda.
    await u.click(formulario.getByRole("button", { name: "Cambiar" }));
    expect(formulario.getByLabelText(/Contacto: busca/)).toBeTruthy();
  });
});

// --- Reprogramar y cancelar (T19) --------------------------------------------------------------

const puts = () => llamadas.filter((l) => l.metodo === "PUT" && l.ruta.startsWith("/api/appointments/"));
const cancelaciones = () => llamadas.filter((l) => l.metodo === "POST" && l.ruta.endsWith("/cancel"));

/** La fila de una cita por el nombre del contacto. */
async function fila(nombre: string) {
  const enlace = await screen.findByRole("link", { name: nombre });
  return within(enlace.closest("li") as HTMLElement);
}

async function abrirReprogramar(nombre = "Ana Lopez", ruta?: string) {
  const u = abrir(ruta);
  await u.click((await fila(nombre)).getByRole("button", { name: /^Reprogramar/ }));
  const formulario = within(await screen.findByRole("form", { name: "Reprogramar cita" }));
  return { u, formulario };
}

describe("reprogramar y cancelar", () => {
  it("solo las programadas que no han empezado tienen «Reprogramar» y «Cancelar cita»", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([
      DE_ANA,
      { ...DE_BEA, status: "cancelled", cancel_reason: "client_request", cancel_note: "Llamara otro dia" },
    ]);
    abrir();

    const ana = await fila("Ana Lopez");
    expect(ana.getByRole("button", { name: `Reprogramar: Ana Lopez, 9:30–10:30` })).toBeTruthy();
    expect(ana.getByRole("button", { name: `Cancelar la cita: Ana Lopez, 9:30–10:30` })).toBeTruthy();
    const bea = await fila("Bea Ruiz");
    expect(bea.queryByRole("button")).toBeNull();
    // Cancelada: atenuada (tachada por CSS) y con su motivo.
    expect((await filas())[1]).toBe(`23:30–0:30 (12/01)Bea RuizPeel · ${P_ADMIN.email} · Cancelada (Lo pidió la clienta: Llamara otro dia)`);
    expect(document.querySelectorAll("li.cita--cancelada")).toHaveLength(1);
  });

  it("una cita que ya ha empezado, realizada o no presentada no se puede cambiar", () => {
    const ahora = new Date("2027-01-11T14:30:00Z"); // las 9:30 en Nueva York
    expect(sePuedeCambiar(DE_ANA, ahora)).toBe(false); // empieza justo ahora
    expect(sePuedeCambiar(DE_ANA, new Date("2027-01-11T14:29:00Z"))).toBe(true);
    expect(sePuedeCambiar({ ...DE_ANA, status: "completed" }, new Date("2027-01-01T00:00:00Z"))).toBe(false);
    expect(sePuedeCambiar({ ...DE_ANA, status: "no_show" }, new Date("2027-01-01T00:00:00Z"))).toBe(false);
    expect(sePuedeCambiar({ ...DE_ANA, status: "cancelled" }, new Date("2027-01-01T00:00:00Z"))).toBe(false);
  });

  it("reprogramar abre el formulario con la cita: contacto y servicio fijos, lo demás elegido", async () => {
    const { formulario } = await abrirReprogramar();

    expect(formulario.getByText("Ana Lopez", { selector: "strong" })).toBeTruthy();
    expect(formulario.queryByRole("button", { name: "Cambiar" })).toBeNull();
    expect(formulario.getByText("Botox (1 h)", { selector: "strong" })).toBeTruthy();
    expect(formulario.queryByLabelText("Servicio")).toBeNull();
    expect((formulario.getByLabelText("Quién la realiza") as HTMLSelectElement).value).toBe("3");
    expect((formulario.getByLabelText("Día") as HTMLInputElement).value).toBe("2027-01-11");
    expect((formulario.getByLabelText("Hora") as HTMLSelectElement).value).toBe("9");
    expect((formulario.getByLabelText("Minutos") as HTMLSelectElement).value).toBe("30");
    // Su propia cita no ocupa a la persona ni da aviso al contacto.
    expect(await formulario.findByText("No tiene otras citas ese día.")).toBeTruthy();
    expect(formulario.queryByRole("status")).toBeNull();
  });

  it("guardar envía la hora, la persona y la versión, y lo anuncia", async () => {
    const { u, formulario } = await abrirReprogramar();
    rutas["PUT /api/appointments/1"] = () => ({
      status: 200,
      cuerpo: cita(1, "2027-01-12T11:15:00-05:00", "2027-01-12T12:15:00-05:00", { version: 2 }),
    });

    fireEvent.change(formulario.getByLabelText("Día"), { target: { value: "2027-01-12" } });
    await u.selectOptions(formulario.getByLabelText("Hora"), "11");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "15");
    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect((await screen.findByRole("status")).textContent).toBe(
      "Cita reprogramada: Ana Lopez, martes, 12 de enero de 2027, 11:15–12:15 (Botox)",
    );
    expect(puts()).toHaveLength(1);
    expect(puts()[0].cuerpo).toEqual({ staff_id: 3, starts_at: "2027-01-12T11:15", version: 1 });
    expect(puts()[0].headers["X-CSRF-Token"]).toBe("csrf-recepcion");
    await waitFor(() => expect(screen.queryByRole("form", { name: "Reprogramar cita" })).toBeNull());
    expect(diasPedidos().at(-1)).toBe("2027-01-12");
  });

  it("se puede cambiar a otra persona del servicio", async () => {
    const { u, formulario } = await abrirReprogramar("Bea Ruiz");
    rutas["PUT /api/appointments/2"] = () => ({ status: 200, cuerpo: { ...DE_BEA, staff_id: 3, version: 2 } });

    await u.selectOptions(formulario.getByLabelText("Quién la realiza"), `${P_PRO.email} · Profesional`);
    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    await screen.findByText(/^Cita reprogramada: Bea Ruiz/);
    expect(puts()[0].cuerpo).toEqual({ staff_id: 3, starts_at: "2027-01-11T23:30", version: 1 });
  });

  it("con un 409 lo dice, sigue abierto y el siguiente intento lleva la versión nueva", async () => {
    const { u, formulario } = await abrirReprogramar();
    rutas["PUT /api/appointments/1"] = () => ({
      status: 409,
      cuerpo: { detail: "Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo." },
    });
    // Otra persona la movió a las 9:45: la agenda recargada trae la versión 2.
    rutas["GET /api/appointments"] = agendaFalsa([
      { ...DE_ANA, starts_at: "2027-01-11T09:45:00-05:00", ends_at: "2027-01-11T10:45:00-05:00", version: 2 },
    ]);

    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect((await formulario.findByRole("alert")).textContent).toBe(
      "Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo.",
    );
    expect(screen.getByRole("form", { name: "Reprogramar cita" })).toBeTruthy();
    await screen.findByText(/9:45–10:45/);
    rutas["PUT /api/appointments/1"] = () => ({ status: 200, cuerpo: { ...DE_ANA, version: 3 } });
    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));
    await screen.findByText(/^Cita reprogramada/);
    expect(puts().map((p) => (p.cuerpo as { version: number }).version)).toEqual([1, 2]);
  });

  it("si otra persona la canceló mientras tanto, se cierra y lo explica", async () => {
    const { u, formulario } = await abrirReprogramar();
    rutas["PUT /api/appointments/1"] = () => ({ status: 409, cuerpo: { detail: "La cita está «Cancelada»: ya no se puede cambiar" } });
    rutas["GET /api/appointments"] = agendaFalsa([{ ...DE_ANA, status: "cancelled", cancel_reason: "clinic", version: 2 }]);

    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("Esta cita ya no se puede reprogramar: está «Cancelada».")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Reprogramar cita" })).toBeNull();
  });

  it("avisa si el contacto tiene otra cita a esa hora, con la duración de la cita y no la del servicio", async () => {
    // El Botox dura ahora 30 min, pero la cita de Ana conserva sus 60. Ana tiene además un Peel a las 11:00.
    rutas["GET /api/services"] = () => ({ status: 200, cuerpo: [{ ...BOTOX, duration_minutes: 30 }, PEEL] });
    const peel = cita(4, "2027-01-11T11:00:00-05:00", "2027-01-11T11:30:00-05:00", { service_id: 12, service_name: "Peel", staff_id: 1, staff_email: P_ADMIN.email });
    rutas["GET /api/appointments"] = agendaFalsa([DE_ANA, peel]);
    // Ana sale dos veces en la lista: se abre por la dirección.
    const u = abrir("/agenda?fecha=2027-01-11&reprogramar=1");
    const formulario = within(await screen.findByRole("form", { name: "Reprogramar cita" }));

    await u.selectOptions(formulario.getByLabelText("Hora"), "10");
    await u.selectOptions(formulario.getByLabelText("Minutos"), "15");

    // De 10:15 a 11:15 pisa el Peel de las 11:00 (con 30 min acabaría a las 10:45).
    expect((await formulario.findByRole("status")).textContent).toMatch(/^Ana Lopez ya tiene otra cita a esa hora: 11:00–11:30 \(Peel/);
  });

  it("si el servicio se desactivó, lo avisa: hay que cancelarla y dar otra", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([{ ...DE_ANA, service_id: 11, service_name: "Facial", duration_minutes: 90, ends_at: "2027-01-11T11:00:00-05:00" }]);
    const { formulario } = await abrirReprogramar();

    expect(await formulario.findByText("El servicio está desactivado o nadie activo lo realiza: cancela la cita y da otra.")).toBeTruthy();
  });

  it("un 422 general de la API sale sobre el formulario", async () => {
    const { u, formulario } = await abrirReprogramar();
    rutas["PUT /api/appointments/1"] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body"], msg: "El contacto está «Perdido»: reábrelo antes de cambiar la cita, o cancélala" }] },
    });

    await u.click(formulario.getByRole("button", { name: "Guardar cambios" }));

    expect((await formulario.findByRole("alert")).textContent).toBe(
      "El contacto está «Perdido»: reábrelo antes de cambiar la cita, o cancélala",
    );
  });

  it("la dirección guarda la cita que se reprograma; «Volver» cierra sin enviar", async () => {
    const u = abrir("/agenda?fecha=2027-01-11&reprogramar=1");
    const formulario = within(await screen.findByRole("form", { name: "Reprogramar cita" }));
    expect((formulario.getByLabelText("Minutos") as HTMLSelectElement).value).toBe("30");

    await u.click(formulario.getByRole("button", { name: "Volver" }));

    await waitFor(() => expect(screen.queryByRole("form", { name: "Reprogramar cita" })).toBeNull());
    expect(puts()).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Nueva cita" })).toBeTruthy();
  });

  it("cancelar pide el motivo y, con él, envía motivo, detalle y versión", async () => {
    const u = abrir();
    rutas["POST /api/appointments/1/cancel"] = () => ({
      status: 200,
      cuerpo: { ...DE_ANA, status: "cancelled", cancel_reason: "clinic", version: 2 },
    });
    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^Cancelar la cita/ }));
    const recuadro = within(await screen.findByRole("form", { name: "Cancelar la cita" }));
    expect(recuadro.getByText(/No escribas datos clínicos/)).toBeTruthy();

    await u.click(recuadro.getByRole("button", { name: "Confirmar cancelación" }));
    expect(recuadro.getByText("Elige el motivo")).toBeTruthy();
    expect(cancelaciones()).toHaveLength(0);

    await u.selectOptions(recuadro.getByLabelText("Motivo"), "Lo canceló la clínica");
    await u.type(recuadro.getByLabelText("Detalle (opcional)"), "  Cierre por nieve ");
    await u.click(recuadro.getByRole("button", { name: "Confirmar cancelación" }));

    expect((await screen.findByRole("status")).textContent).toBe("Cita cancelada: Ana Lopez, 9:30–10:30 (Botox)");
    expect(cancelaciones()[0].cuerpo).toEqual({ version: 1, reason: "clinic", note: "Cierre por nieve" });
    expect(cancelaciones()[0].headers["X-CSRF-Token"]).toBe("csrf-recepcion");
    await waitFor(() => expect(diasPedidos().filter((d) => d === "2027-01-11").length).toBeGreaterThan(1));
  });

  it("sin detalle, envía note null; «Volver» cierra el recuadro", async () => {
    const u = abrir();
    rutas["POST /api/appointments/1/cancel"] = () => ({ status: 200, cuerpo: { ...DE_ANA, status: "cancelled" } });
    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^Cancelar la cita/ }));
    let recuadro = within(await screen.findByRole("form", { name: "Cancelar la cita" }));
    await u.click(recuadro.getByRole("button", { name: "Volver" }));
    expect(screen.queryByRole("form", { name: "Cancelar la cita" })).toBeNull();

    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^Cancelar la cita/ }));
    recuadro = within(await screen.findByRole("form", { name: "Cancelar la cita" }));
    await u.selectOptions(recuadro.getByLabelText("Motivo"), "Lo pidió la clienta");
    await u.click(recuadro.getByRole("button", { name: "Confirmar cancelación" }));

    await screen.findByText(/^Cita cancelada/);
    expect(cancelaciones()[0].cuerpo).toEqual({ version: 1, reason: "client_request", note: null });
  });

  it("si otra persona la cambió (409), cierra el recuadro, avisa y recarga", async () => {
    const u = abrir();
    rutas["POST /api/appointments/1/cancel"] = () => ({
      status: 409,
      cuerpo: { detail: "Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo." },
    });
    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^Cancelar la cita/ }));
    const recuadro = within(await screen.findByRole("form", { name: "Cancelar la cita" }));
    await u.selectOptions(recuadro.getByLabelText("Motivo"), "Otro motivo");
    const pedidasAntes = diasPedidos().length;

    await u.click(recuadro.getByRole("button", { name: "Confirmar cancelación" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo.",
    );
    expect(screen.queryByRole("form", { name: "Cancelar la cita" })).toBeNull();
    await waitFor(() => expect(diasPedidos().length).toBeGreaterThan(pedidasAntes));
  });

  it("un detalle no válido (422) sale junto al campo", async () => {
    const u = abrir();
    rutas["POST /api/appointments/1/cancel"] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body", "note"], msg: "No se permiten tildes ni caracteres especiales (á, ñ, ü…)" }] },
    });
    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^Cancelar la cita/ }));
    const recuadro = within(await screen.findByRole("form", { name: "Cancelar la cita" }));
    await u.selectOptions(recuadro.getByLabelText("Motivo"), "Otro motivo");
    await u.type(recuadro.getByLabelText("Detalle (opcional)"), "Llamará");

    await u.click(recuadro.getByRole("button", { name: "Confirmar cancelación" }));

    expect(await recuadro.findByText("No se permiten tildes ni caracteres especiales (á, ñ, ü…)")).toBeTruthy();
    expect(screen.getByRole("form", { name: "Cancelar la cita" })).toBeTruthy();
  });
});

// --- Fechas en la zona de la clínica -------------------------------------------------------

describe("fechas de la agenda", () => {
  it("suma días cruzando meses y años, y el día en palabras", () => {
    expect(sumarDias("2027-01-31", 1)).toBe("2027-02-01");
    expect(sumarDias("2027-01-01", -1)).toBe("2026-12-31");
    expect(sumarDias("2027-03-14", 1)).toBe("2027-03-15"); // el día del cambio de horario
    expect(formatoDia("2027-03-14")).toBe("domingo, 14 de marzo de 2027");
  });

  it("solo valen fechas reales AAAA-MM-DD", () => {
    expect(["2027-01-11", "2028-02-29"].map(diaValido)).toEqual([true, true]);
    expect(["2027-02-30", "2027-1-11", "11/01/2027", "", null].map(diaValido)).toEqual([false, false, false, false, false]);
  });

  it("las horas en la de Nueva York, también con el cambio de horario", () => {
    // 14/03/2027 a las 3:00 (ya en verano) son 2 horas reales desde la 1:00, pero el reloj marca 180 min.
    expect(minutosDesde("2027-03-14", "2027-03-14T07:00:00Z")).toBe(180);
    expect(minutosDesde("2027-01-11", "2027-01-12T05:30:00Z")).toBe(1470); // 0:30 del día siguiente
    expect(minutosDesde("2027-01-12", "2027-01-12T04:30:00Z")).toBe(-30); // 23:30 del día anterior
    expect(horaEn("2027-01-11", "2027-01-11T14:30:00Z")).toBe("9:30");
    expect(horaEn("2027-01-11", "2027-01-12T05:30:00Z")).toBe("0:30 (12/01)");
  });

  it("«hoy» es el día de Nueva York, no el del navegador", () => {
    // 03:30 UTC del 12/01 son las 22:30 del 11/01 en Nueva York.
    expect(hoyEnLaClinica(new Date("2027-01-12T03:30:00Z"))).toBe("2027-01-11");
  });
});

// --- La vista del mes (T20) ------------------------------------------------------------------------

// Enero de 2027: Ana el 11 (Botox), Bea el 11 por la noche (Peel), Carla el 20 (Botox) y una
// cancelada el 25 (Botox); la de Dani empieza el 31/12 a las 23:30 y acaba ya en enero.
const DE_CARLA = cita(3, "2027-01-20T12:00:00-05:00", "2027-01-20T13:00:00-05:00", { contact_id: 9, contact_name: "Carla Diaz" });
const CANCELADA = cita(4, "2027-01-25T10:00:00-05:00", "2027-01-25T11:00:00-05:00", {
  contact_id: 10,
  contact_name: "Eva Gil",
  status: "cancelled",
  cancel_reason: "client_request",
});
const DE_DANI = cita(5, "2026-12-31T23:30:00-05:00", "2027-01-01T00:30:00-05:00", { contact_id: 11, contact_name: "Dani Mora" });
const DEL_MES = [DE_DANI, DE_ANA, DE_BEA, DE_CARLA, CANCELADA];

const mesesPedidos = () =>
  llamadas.filter((l) => l.ruta === "/api/appointments" && l.consulta.has("from")).map((l) => `${l.consulta.get("from")}/${l.consulta.get("to")}`);

/** Los días del mes y, en cada uno, sus citas (contacto). */
function diasDelMes() {
  return [...document.querySelectorAll(".mes__dia")].map((d) => [
    d.querySelector("h4")?.firstChild?.textContent,
    [...d.querySelectorAll(".cita__contacto")].map((e) => e.textContent),
  ]);
}

describe("vista del mes", () => {
  beforeEach(() => {
    rutas["GET /api/appointments"] = agendaFalsa(DEL_MES);
  });

  it("«Mes» pide el mes entero de una vez y agrupa las citas por día", async () => {
    const u = abrir();
    await filas();

    await u.click(screen.getByRole("button", { name: "Mes" }));

    expect(await screen.findByRole("heading", { name: /^enero de 2027/ })).toBeTruthy();
    await waitFor(() => expect(diasDelMes()).toHaveLength(4));
    expect(diasDelMes()).toEqual([
      ["viernes, 1 de enero de 2027", ["Dani Mora"]], // empezó la víspera
      ["lunes, 11 de enero de 2027", ["Ana Lopez", "Bea Ruiz"]],
      ["miércoles, 20 de enero de 2027", ["Carla Diaz"]],
      ["lunes, 25 de enero de 2027", ["Eva Gil"]],
    ]);
    expect(mesesPedidos()).toEqual(["2027-01-01/2027-01-31"]);
    expect(screen.getByRole("button", { name: "Mes" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Día" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("arriba, cuántas Programadas hay de cada servicio, sin las canceladas", async () => {
    abrir("/agenda?vista=mes&fecha=2027-01-11");

    const resumen = await screen.findByText(/Programadas este mes/);
    // Botox: Dani, Ana y Carla (la de Eva está cancelada); Peel: Bea.
    expect(resumen.closest("p")?.textContent).toBe("Programadas este mes: Botox: 3 · Peel: 1");
  });

  it("la dirección guarda la vista: al recargar sigue en el mes", async () => {
    abrir("/agenda?vista=mes&fecha=2027-01-20");

    await waitFor(() => expect(diasDelMes()).toHaveLength(4));
    expect(mesesPedidos()).toEqual(["2027-01-01/2027-01-31"]);
    expect(diasPedidos().filter(Boolean)).toEqual([]); // ningún día suelto
  });

  it("mes anterior, siguiente y este mes", async () => {
    const u = abrir("/agenda?vista=mes&fecha=2027-01-11");
    await screen.findByRole("heading", { name: /^enero de 2027/ });

    await u.click(screen.getByRole("button", { name: "Mes siguiente →" }));
    await screen.findByRole("heading", { name: /^febrero de 2027/ });
    expect(await screen.findByText("No hay citas este mes.")).toBeTruthy();
    await u.click(screen.getByRole("button", { name: "← Mes anterior" }));
    await u.click(screen.getByRole("button", { name: "← Mes anterior" }));
    await screen.findByRole("heading", { name: /^diciembre de 2026/ });
    await u.click(screen.getByRole("button", { name: "Este mes" }));

    const hoy = hoyEnLaClinica();
    await waitFor(() => expect(mesesPedidos().at(-1)).toBe(`${primeroDeMes(hoy)}/${ultimoDeMes(hoy)}`));
    expect(mesesPedidos().slice(0, 4)).toEqual([
      "2027-01-01/2027-01-31",
      "2027-02-01/2027-02-28",
      "2027-01-01/2027-01-31",
      "2026-12-01/2026-12-31",
    ]);
    expect(screen.getByRole("button", { name: "Este mes" }).hasAttribute("disabled")).toBe(true);
  });

  it("«Ver el día» abre ese día en la vista del día", async () => {
    const u = abrir("/agenda?vista=mes&fecha=2027-01-11");
    await waitFor(() => expect(diasDelMes()).toHaveLength(4));
    const veinte = [...document.querySelectorAll(".mes__dia")][2] as HTMLElement;

    await u.click(within(veinte).getByRole("button", { name: "Ver el día" }));

    expect(await screen.findByRole("heading", { name: /miércoles, 20 de enero de 2027/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Día" }).getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(diasPedidos().at(-1)).toBe("2027-01-20"));
  });

  it("recepción cancela desde el mes, sin ir día a día, y el mes se recarga", async () => {
    rutas["POST /api/appointments/3/cancel"] = () => ({ status: 200, cuerpo: { ...DE_CARLA, status: "cancelled" } });
    const u = abrir("/agenda?vista=mes&fecha=2027-01-11");

    await u.click((await fila("Carla Diaz")).getByRole("button", { name: /^Cancelar la cita/ }));
    const recuadro = within(await screen.findByRole("form", { name: "Cancelar la cita" }));
    await u.selectOptions(recuadro.getByLabelText("Motivo"), "Lo pidió la clienta");
    await u.click(recuadro.getByRole("button", { name: "Confirmar cancelación" }));

    expect((await screen.findByRole("status")).textContent).toBe("Cita cancelada: Carla Diaz, 12:00–13:00 (Botox)");
    await waitFor(() => expect(mesesPedidos()).toHaveLength(2));
    expect(screen.getByRole("heading", { name: /^enero de 2027/ })).toBeTruthy();
  });

  it("y reprograma desde el mes con el mismo formulario", async () => {
    const u = abrir("/agenda?vista=mes&fecha=2027-01-11");

    await u.click((await fila("Carla Diaz")).getByRole("button", { name: /^Reprogramar/ }));

    const formulario = within(await screen.findByRole("form", { name: "Reprogramar cita" }));
    expect((formulario.getByLabelText("Día") as HTMLInputElement).value).toBe("2027-01-20");
  });

  it("la cancelada sale tachada con su motivo, como en el día", async () => {
    abrir("/agenda?vista=mes&fecha=2027-01-11");

    const eva = (await fila("Eva Gil")).getByText(/Cancelada/);
    expect(eva.textContent).toContain("Cancelada (Lo pidió la clienta)");
    expect(eva.closest("li")?.className).toBe("cita cita--cancelada");
  });

  it("si en el mes todo está cancelado, el resumen lo dice", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([CANCELADA]);
    abrir("/agenda?vista=mes&fecha=2027-01-11");

    expect(await screen.findByText("No hay ninguna cita Programada este mes.")).toBeTruthy();
  });

  it("el filtro por persona también vale en el mes", async () => {
    const u = abrir("/agenda?vista=mes&fecha=2027-01-11");
    await waitFor(() => expect(diasDelMes()).toHaveLength(4));

    await u.selectOptions(screen.getByLabelText("Persona"), P_ADMIN.email);

    await waitFor(() => expect(diasDelMes()).toEqual([["lunes, 11 de enero de 2027", ["Bea Ruiz"]]]));
    expect(llamadas.at(-1)?.consulta.get("staff_id")).toBe(String(P_ADMIN.id));
  });
});

describe("«Solo mis citas» (T20)", () => {
  it("aplica el filtro por persona con la propia cuenta", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([DE_ANA, { ...DE_BEA, staff_id: RECEPCION.id }]);
    const u = abrir();
    await filas();

    await u.click(screen.getByRole("button", { name: "Solo mis citas" }));

    await waitFor(async () => expect(await filas()).toHaveLength(1));
    expect(llamadas.at(-1)?.consulta.get("staff_id")).toBe(String(RECEPCION.id));
    expect(screen.getByRole("button", { name: "Solo mis citas" }).hasAttribute("disabled")).toBe(true);
  });
});

// --- «Mi agenda» del profesional (T20) -------------------------------------------------------------

const PROFESIONAL = { id: 3, email: P_PRO.email, role: "professional", csrf_token: "csrf-pro" };

describe("«Mi agenda» del profesional", () => {
  beforeEach(() => {
    rutas["GET /api/auth/me"] = () => ({ status: 200, cuerpo: PROFESIONAL });
    // La API ya le devuelve solo las suyas.
    rutas["GET /api/appointments"] = agendaFalsa([DE_ANA, DE_CARLA, CANCELADA]);
  });

  it("solo lectura: sus citas, sin dar cita, sin filtro de persona y sin botones", async () => {
    abrir("/mi-agenda?fecha=2027-01-11");

    expect(await screen.findByRole("heading", { name: "Mi agenda" })).toBeTruthy();
    expect(await filas()).toEqual(["9:30–10:30Ana LopezBotox"]); // sin su propio email
    expect(screen.queryByRole("button", { name: "Nueva cita" })).toBeNull();
    expect(screen.queryByLabelText("Persona")).toBeNull();
    expect(screen.queryByRole("button", { name: "Solo mis citas" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Reprogramar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Cancelar la cita/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Ana Lopez" }).getAttribute("href")).toBe("/contactos/7");
  });

  it("no envía filtro de persona (lo pone la API), ni aunque la dirección lo lleve, ni pide las personas asignables", async () => {
    abrir("/mi-agenda?fecha=2027-01-11&persona=1");
    await filas();

    const citas = llamadas.filter((l) => l.ruta === "/api/appointments");
    expect(citas.length).toBeGreaterThan(0);
    expect(citas.every((l) => !l.consulta.has("staff_id"))).toBe(true);
    expect(llamadas.some((l) => l.ruta === "/api/services/staff")).toBe(false);
  });

  it("la vista del mes, con su resumen y la cancelada tachada", async () => {
    const u = abrir("/mi-agenda?fecha=2027-01-11");
    await filas();

    await u.click(screen.getByRole("button", { name: "Mes" }));

    await waitFor(() => expect(diasDelMes()).toHaveLength(3));
    expect((await screen.findByText(/Programadas este mes/)).closest("p")?.textContent).toBe("Programadas este mes: Botox: 2");
    expect((await fila("Eva Gil")).getByText(/Cancelada/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Cancelar la cita/ })).toBeNull();
  });

  it("sin citas, se lo dice a ella", async () => {
    rutas["GET /api/appointments"] = () => ({ status: 200, cuerpo: [] });
    abrir("/mi-agenda?fecha=2027-01-11");

    expect(await screen.findByText("No tienes citas este día.")).toBeTruthy();
  });

  it.each(["/mi-agenda?nueva=1&contacto=7", "/mi-agenda?fecha=2027-01-11&reprogramar=1"])(
    "una dirección con el formulario (%s) no lo abre",
    async (ruta) => {
      abrir(ruta);
      await screen.findByRole("heading", { name: "Mi agenda" });
      await waitFor(() => expect(llamadas.some((l) => l.ruta === "/api/appointments")).toBe(true));

      expect(screen.queryByRole("form")).toBeNull();
      expect(llamadas.some((l) => l.ruta === "/api/services" || l.ruta === "/api/contacts/7")).toBe(false);
    },
  );
});

describe("fechas del mes", () => {
  it("primer y último día, y meses que cruzan el año", () => {
    expect(primeroDeMes("2027-02-17")).toBe("2027-02-01");
    expect(ultimoDeMes("2027-02-17")).toBe("2027-02-28");
    expect(ultimoDeMes("2028-02-01")).toBe("2028-02-29"); // bisiesto
    expect(ultimoDeMes("2027-12-31")).toBe("2027-12-31");
    expect(sumarMeses("2027-01-31", 1)).toBe("2027-02-01");
    expect(sumarMeses("2027-01-15", -1)).toBe("2026-12-01");
    expect(sumarMeses("2026-12-01", 1)).toBe("2027-01-01");
    expect(formatoMes("2027-03-14")).toBe("marzo de 2027");
  });

  it("agrupa por el día en Nueva York, no por el UTC", () => {
    // 04:30 UTC del 12/01 son las 23:30 del 11/01 en Nueva York.
    const tarde = cita(1, "2027-01-12T04:30:00Z", "2027-01-12T05:30:00Z");
    expect(porDia([tarde], "2027-01-01").map(([dia]) => dia)).toEqual(["2027-01-11"]);
  });

  it("el resumen cuenta solo las Programadas, de más a menos y a igualdad por nombre", () => {
    const peel = { service_name: "Peel" };
    const resumen = resumenPorServicio([
      cita(1, "", "", peel),
      cita(2, "", ""),
      cita(3, "", "", { service_name: "Acne" }),
      cita(4, "", "", peel),
      cita(5, "", "", { status: "cancelled" }),
      cita(6, "", "", { status: "cancelled" }),
      cita(7, "", "", { status: "completed" }),
    ]);
    expect(resumen).toEqual([
      { servicio: "Peel", total: 2 },
      { servicio: "Acne", total: 1 },
      { servicio: "Botox", total: 1 },
    ]);
  });
});

// --- Asistencia (T20b) -----------------------------------------------------------------------------

// «Ahora» en el navegador: 11/01/2027 a las 12:00 de Nueva York. La de Ana (9:30) ya empezó; la de
// Bea (23:30), no. Solo se finge la fecha: los temporizadores siguen siendo los reales.
const MEDIODIA = new Date("2027-01-11T17:00:00Z");
const asistencias = () => llamadas.filter((l) => l.metodo === "POST" && l.ruta.endsWith("/attendance"));

describe("asistencia", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"], shouldAdvanceTime: true });
    vi.setSystemTime(MEDIODIA);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("la que ya empezó tiene «Realizada» y «No presentado»; la que no, reprogramar y cancelar", async () => {
    abrir();

    const ana = await fila("Ana Lopez");
    expect(ana.getAllByRole("button").map((b) => b.textContent)).toEqual(["Realizada", "No presentado"]);
    const bea = await fila("Bea Ruiz");
    expect(bea.getAllByRole("button").map((b) => b.textContent)).toEqual(["Reprogramar", "Cancelar cita"]);
  });

  it("«Realizada» envía el estado y la versión, avisa y recarga la agenda", async () => {
    rutas["POST /api/appointments/1/attendance"] = () => ({
      status: 200,
      cuerpo: { ...DE_ANA, status: "completed", attended_at: "2027-01-11T12:00:00-05:00", version: 2 },
    });
    const u = abrir();

    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^Realizada/ }));

    expect((await screen.findByRole("status")).textContent).toBe("Asistencia: Ana Lopez, 9:30–10:30, «Realizada»");
    expect(asistencias()[0].cuerpo).toEqual({ version: 1, status: "completed" });
    expect(asistencias()[0].headers["X-CSRF-Token"]).toBe("csrf-recepcion");
    await waitFor(() => expect(diasPedidos().filter((d) => d === "2027-01-11").length).toBeGreaterThan(1));
  });

  it("«No presentado» envía no_show", async () => {
    rutas["POST /api/appointments/1/attendance"] = () => ({ status: 200, cuerpo: { ...DE_ANA, status: "no_show" } });
    const u = abrir();

    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^No presentado/ }));

    await screen.findByText(/«No presentado»/);
    expect(asistencias()[0].cuerpo).toEqual({ version: 1, status: "no_show" });
  });

  it("una marcada dice su estado y, dentro del plazo, se puede cambiar a la otra", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([
      { ...DE_ANA, status: "completed", version: 2, attended_at: "2027-01-10T12:00:00-05:00" },
      { ...DE_BEA, starts_at: "2027-01-11T08:00:00-05:00", ends_at: "2027-01-11T09:00:00-05:00", status: "no_show", attended_at: "2027-01-11T09:00:00-05:00" },
    ]);
    rutas["POST /api/appointments/1/attendance"] = () => ({ status: 200, cuerpo: { ...DE_ANA, status: "no_show" } });
    const u = abrir();

    const ana = await fila("Ana Lopez");
    expect(ana.getByText(/Realizada$/)).toBeTruthy();
    expect(ana.getAllByRole("button").map((b) => b.textContent)).toEqual(["Cambiar a No presentado"]);
    expect((await fila("Bea Ruiz")).getAllByRole("button").map((b) => b.textContent)).toEqual(["Cambiar a Realizada"]);

    await u.click(ana.getByRole("button", { name: /^Cambiar a No presentado/ }));

    await screen.findByText(/«No presentado»/);
    expect(asistencias()[0].cuerpo).toEqual({ version: 2, status: "no_show" });
  });

  it("pasado el plazo de 7 días desde que se marcó, ya no hay botón", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([{ ...DE_ANA, status: "completed", attended_at: "2027-01-04T11:59:00-05:00" }]);
    abrir();

    expect((await fila("Ana Lopez")).queryAllByRole("button")).toEqual([]);
  });

  it("una cancelada que ya pasó no tiene botones", async () => {
    rutas["GET /api/appointments"] = agendaFalsa([{ ...DE_ANA, status: "cancelled", cancel_reason: "clinic" }]);
    abrir();

    expect((await fila("Ana Lopez")).queryAllByRole("button")).toEqual([]);
  });

  it("si otra persona la marcó antes (409), avisa y recarga", async () => {
    rutas["POST /api/appointments/1/attendance"] = () => ({
      status: 409,
      cuerpo: { detail: "Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo." },
    });
    const u = abrir();
    await filas();
    const pedidasAntes = diasPedidos().length;

    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^Realizada/ }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo.",
    );
    await waitFor(() => expect(diasPedidos().length).toBeGreaterThan(pedidasAntes));
  });

  it("también desde la vista del mes", async () => {
    abrir("/agenda?vista=mes&fecha=2027-01-11");

    expect((await fila("Ana Lopez")).getAllByRole("button").map((b) => b.textContent)).toEqual(["Realizada", "No presentado"]);
  });

  it("la profesional marca las suyas en «Mi agenda», sin reprogramar ni cancelar", async () => {
    rutas["GET /api/auth/me"] = () => ({ status: 200, cuerpo: PROFESIONAL });
    rutas["GET /api/appointments"] = agendaFalsa([DE_ANA, { ...DE_BEA, staff_id: 3 }]);
    rutas["POST /api/appointments/1/attendance"] = () => ({ status: 200, cuerpo: { ...DE_ANA, status: "completed" } });
    const u = abrir("/mi-agenda?fecha=2027-01-11");

    expect((await fila("Ana Lopez")).getAllByRole("button").map((b) => b.textContent)).toEqual(["Realizada", "No presentado"]);
    expect((await fila("Bea Ruiz")).queryAllByRole("button")).toEqual([]); // aún no ha empezado

    await u.click((await fila("Ana Lopez")).getByRole("button", { name: /^Realizada/ }));

    await screen.findByText(/«Realizada»/);
    expect(asistencias()[0].headers["X-CSRF-Token"]).toBe("csrf-pro");
  });
});

describe("cuándo se marca y se corrige", () => {
  const ana = (cambios: Partial<CitaAgenda>) => ({ ...DE_ANA, ...cambios });

  it("se marca desde la hora de inicio, no antes", () => {
    expect(sePuedeMarcar(DE_ANA, new Date("2027-01-11T14:30:00Z"))).toBe(true); // justo a las 9:30
    expect(sePuedeMarcar(DE_ANA, new Date("2027-01-11T14:29:59Z"))).toBe(false);
    expect(sePuedeMarcar(ana({ status: "cancelled" }), MEDIODIA)).toBe(false);
    expect(sePuedeMarcar(ana({ status: "completed" }), MEDIODIA)).toBe(false);
  });

  it("se corrige hasta 7 días después de marcarla, contados desde la marca", () => {
    const marcada = ana({ status: "no_show", attended_at: "2027-01-11T15:00:00Z" });
    expect(sePuedeCorregir(marcada, new Date("2027-01-18T15:00:00Z"))).toBe(true);
    expect(sePuedeCorregir(marcada, new Date("2027-01-18T15:00:01Z"))).toBe(false);
    expect(sePuedeCorregir(ana({ status: "completed", attended_at: null }), MEDIODIA)).toBe(false);
    expect(sePuedeCorregir(ana({ status: "scheduled", attended_at: "2027-01-11T15:00:00Z" }), MEDIODIA)).toBe(false);
  });
});
