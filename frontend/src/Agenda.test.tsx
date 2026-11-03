// Pruebas de la agenda y del formulario de cita (T18), con una API falsa en fetch.

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { diaValido, formatoDia, horaEn, hoyEnLaClinica, minutosDesde, sumarDias } from "./Agenda";
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

/** La agenda falsa: filtra por día, persona y contacto como la API. */
function agendaFalsa(citas: CitaAgenda[]) {
  return ({ consulta }: Llamada): Respuesta => {
    const dia = consulta.get("date");
    const persona = consulta.get("staff_id");
    const contacto = consulta.get("contact_id");
    const delDia = citas.filter(
      (c) =>
        (c.starts_at.startsWith(dia ?? "") || c.ends_at.startsWith(dia ?? "")) &&
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
  return within(ul).getAllByRole("listitem").map((li) => li.textContent);
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
