// Pruebas de la invitación al portal y de las citas en la ficha (T21), con una API falsa en fetch.

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { CitaAgenda, ContactoDetalle } from "./api";
import { CUENTA_CREADA, ENLACE_NO_VALIDO } from "./Invitacion";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = { metodo: string; ruta: string; headers: Record<string, string>; cuerpo: unknown };

const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };
const PROFESIONAL = { id: 3, email: "profesional@prueba.example.com", role: "professional", csrf_token: "csrf-prof" };
const CADUCA = "2027-01-05T15:00:00Z";
const SIN_INVITACION = { has_account: false, invitation_expires_at: null };
const NO_VALE = { status: 410, cuerpo: { detail: ENLACE_NO_VALIDO } };

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
  owner_id: 2,
  owner_email: "recepcion@prueba.example.com",
};

const CITA: CitaAgenda = {
  id: 1,
  contact_id: 7,
  service_id: 1,
  staff_id: 3,
  starts_at: "2027-01-11T09:30:00-05:00",
  ends_at: "2027-01-11T10:30:00-05:00",
  duration_minutes: 60,
  status: "scheduled",
  version: 1,
  created_at: "2027-01-04T10:00:00-05:00",
  cancel_reason: null,
  cancel_note: null,
  attended_at: null,
  contact_name: "Ana Smith",
  service_name: "Botox",
  staff_email: "profesional@prueba.example.com",
};

let usuario: typeof RECEPCION | null;
let rutas: Record<string, (cuerpo: unknown) => Respuesta>;
let llamadas: Llamada[];

beforeEach(() => {
  llamadas = [];
  usuario = RECEPCION;
  rutas = {
    "GET /api/auth/me": () => (usuario ? { status: 200, cuerpo: usuario } : { status: 401, cuerpo: { detail: "No autenticado" } }),
    "POST /api/auth/logout": () => {
      usuario = null;
      return { status: 204 };
    },
    "GET /api/contacts/7": () => ({ status: 200, cuerpo: ANA }),
    "GET /api/contacts/7/portal": () => ({ status: 200, cuerpo: SIN_INVITACION }),
    "GET /api/appointments/by-contact/7": () => ({ status: 200, cuerpo: { total: 0, items: [] } }),
    "POST /api/contacts/7/portal-invitation": () => ({ status: 201, cuerpo: { token: "token-secreto", expires_at: CADUCA } }),
    "POST /api/portal-invitations/check": () => ({ status: 204 }),
    "POST /api/portal-invitations/accept": () => ({ status: 204 }),
    "GET /api/health": () => ({ status: 200, cuerpo: { status: "ok" } }),
    "GET /api/health/db": () => ({ status: 200, cuerpo: { status: "ok" } }),
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

function abrir(ruta: string) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const de = (metodo: string, ruta: string) => llamadas.filter((l) => l.metodo === metodo && l.ruta === ruta);

describe("invitar desde la ficha", () => {
  it("genera el enlace con el token CSRF, lo muestra y lo copia", async () => {
    const u = abrir("/contactos/7");
    const copiar = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText: copiar }, configurable: true });

    await u.click(await screen.findByRole("button", { name: "Invitar al portal" }));

    const enlace = (await screen.findByLabelText("Enlace de invitación")) as HTMLInputElement;
    expect(enlace.value).toBe(`${window.location.origin}/invitacion#token-secreto`);
    expect(de("POST", "/api/contacts/7/portal-invitation")[0].headers["X-CSRF-Token"]).toBe("csrf-recepcion");

    await u.click(screen.getByRole("button", { name: "Copiar enlace" }));

    expect(copiar).toHaveBeenCalledWith(`${window.location.origin}/invitacion#token-secreto`);
    expect((await screen.findByRole("status")).textContent).toBe("Enlace copiado");
  });

  it("si el navegador no deja copiar, avisa para hacerlo a mano", async () => {
    const u = abrir("/contactos/7");
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });

    await u.click(await screen.findByRole("button", { name: "Invitar al portal" }));
    await u.click(await screen.findByRole("button", { name: "Copiar enlace" }));

    expect((await screen.findByRole("alert")).textContent).toContain("cópialo a mano");
  });

  it("con un enlace sin usar no lo muestra y ofrece generar otro, que lo sustituye", async () => {
    rutas["GET /api/contacts/7/portal"] = () => ({ status: 200, cuerpo: { has_account: false, invitation_expires_at: CADUCA } });
    const u = abrir("/contactos/7");

    await u.click(await screen.findByRole("button", { name: "Generar otro enlace" }));

    expect(de("POST", "/api/contacts/7/portal-invitation")).toHaveLength(1);
    expect(await screen.findByLabelText("Enlace de invitación")).toBeTruthy();
  });

  it("si ya tiene cuenta no ofrece invitar", async () => {
    rutas["GET /api/contacts/7/portal"] = () => ({ status: 200, cuerpo: { has_account: true, invitation_expires_at: null } });
    abrir("/contactos/7");

    expect(await screen.findByText("Ya tiene cuenta en el portal.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Invitar al portal" })).toBeNull();
  });

  it("a un Perdido no se le ofrece invitar", async () => {
    rutas["GET /api/contacts/7"] = () => ({ status: 200, cuerpo: { ...ANA, status: "lost" } });
    abrir("/contactos/7");

    expect(await screen.findByText("Para invitarlo al portal, reábrelo primero.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Invitar al portal" })).toBeNull();
  });

  it("un 409 muestra el mensaje de la API y vuelve a leer el estado", async () => {
    rutas["POST /api/contacts/7/portal-invitation"] = () => ({ status: 409, cuerpo: { detail: "Este contacto ya tiene cuenta en el portal" } });
    const u = abrir("/contactos/7");
    const boton = await screen.findByRole("button", { name: "Invitar al portal" });
    rutas["GET /api/contacts/7/portal"] = () => ({ status: 200, cuerpo: { has_account: true, invitation_expires_at: null } });

    await u.click(boton);

    expect((await screen.findByRole("alert")).textContent).toBe("Este contacto ya tiene cuenta en el portal");
    expect(await screen.findByText("Ya tiene cuenta en el portal.")).toBeTruthy();
  });

  it("marcar Perdido retira el enlace que se estaba mostrando", async () => {
    rutas["PUT /api/contacts/7/status"] = () => ({ status: 200, cuerpo: { ...ANA, status: "lost", version: 2 } });
    const u = abrir("/contactos/7");

    await u.click(await screen.findByRole("button", { name: "Invitar al portal" }));
    await screen.findByLabelText("Enlace de invitación");
    await u.click(screen.getByRole("button", { name: "Marcar como perdido" }));

    expect(await screen.findByText("Para invitarlo al portal, reábrelo primero.")).toBeTruthy();
    expect(screen.queryByLabelText("Enlace de invitación")).toBeNull();
  });

  it("editar la ficha no pierde el enlace generado", async () => {
    rutas["GET /api/contacts/owners"] = () => ({ status: 200, cuerpo: [] });
    const u = abrir("/contactos/7");

    await u.click(await screen.findByRole("button", { name: "Invitar al portal" }));
    await screen.findByLabelText("Enlace de invitación");
    await u.click(screen.getByRole("button", { name: "Editar" }));

    expect(screen.getByLabelText("Enlace de invitación")).toBeTruthy();
  });

  it("el profesional no ve la sección ni pregunta por ella", async () => {
    usuario = PROFESIONAL;
    abrir("/contactos/7");

    await screen.findByRole("heading", { name: "Ana Smith" });
    await screen.findByRole("heading", { name: "Citas contigo" });
    expect(screen.queryByRole("heading", { name: "Portal del cliente" })).toBeNull();
    expect(de("GET", "/api/contacts/7/portal")).toHaveLength(0);
  });
});

describe("citas en la ficha", () => {
  it("lista cada cita con su día, hora, servicio, persona y estado, y lleva a la agenda de ese día", async () => {
    rutas["GET /api/appointments/by-contact/7"] = () => ({
      status: 200,
      cuerpo: { total: 2, items: [CITA, { ...CITA, id: 2, status: "cancelled", cancel_reason: "clinic", service_name: "Peel" }] },
    });
    abrir("/contactos/7");

    const enlaces = await screen.findAllByRole("link", { name: /2027|enero/ });
    expect(enlaces[0].getAttribute("href")).toBe("/agenda?fecha=2027-01-11");
    expect(enlaces[0].closest("span")?.textContent).toContain("9:30–10:30");
    expect(screen.getByText("Botox · profesional@prueba.example.com · Programada")).toBeTruthy();
    const cancelada = screen.getByText("Peel · profesional@prueba.example.com · Cancelada");
    expect(cancelada.closest("li")?.className).toContain("cita--cancelada");
  });

  it("sin citas lo dice", async () => {
    abrir("/contactos/7");

    expect(await screen.findByText("Todavía no tiene citas.")).toBeTruthy();
  });

  it("avisa si hay más de las que muestra", async () => {
    rutas["GET /api/appointments/by-contact/7"] = () => ({ status: 200, cuerpo: { total: 22, items: [CITA] } });
    abrir("/contactos/7");

    expect(await screen.findByText("Mostrando las 1 más recientes de 22.")).toBeTruthy();
  });

  it("al profesional lo lleva a su agenda y no le dice quién la realiza", async () => {
    usuario = PROFESIONAL;
    rutas["GET /api/appointments/by-contact/7"] = () => ({ status: 200, cuerpo: { total: 1, items: [CITA] } });
    abrir("/contactos/7");

    const enlace = await screen.findByRole("link", { name: /2027|enero/ });
    expect(enlace.getAttribute("href")).toBe("/mi-agenda?fecha=2027-01-11");
    expect(screen.getByText("Botox · Programada")).toBeTruthy();
  });

  it("si falla, muestra el error y deja reintentar", async () => {
    rutas["GET /api/appointments/by-contact/7"] = () => ({ status: 503 });
    const u = abrir("/contactos/7");

    await screen.findByText(/Servicio no disponible/);
    rutas["GET /api/appointments/by-contact/7"] = () => ({ status: 200, cuerpo: { total: 0, items: [] } });
    await u.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Todavía no tiene citas.")).toBeTruthy();
  });
});

describe("la página de la invitación", () => {
  beforeEach(() => {
    usuario = null;
  });

  async function rellenar(u: ReturnType<typeof userEvent.setup>, password = "una-frase-bastante-larga", repetida = password) {
    await u.type(await screen.findByLabelText("Email"), "ana@example.com");
    await u.type(screen.getByLabelText("Contraseña (al menos 12 caracteres)"), password);
    await u.type(screen.getByLabelText("Repite la contraseña"), repetida);
    await u.click(screen.getByRole("button", { name: "Crear cuenta" }));
  }

  it("se abre sin sesión y envía el token sin datos de rol ni contacto; después va al login con el aviso", async () => {
    const u = abrir("/invitacion#token-secreto");

    await rellenar(u);

    expect((await screen.findByRole("status")).textContent).toBe(CUENTA_CREADA);
    expect(await screen.findByRole("heading", { name: "Entrar" })).toBeTruthy();
    expect(de("POST", "/api/portal-invitations/check")[0].cuerpo).toEqual({ token: "token-secreto" });
    expect(de("POST", "/api/portal-invitations/accept")[0].cuerpo).toEqual({
      token: "token-secreto",
      email: "ana@example.com",
      password: "una-frase-bastante-larga",
    });
  });

  it("no muestra ningún dato del contacto ni pide datos internos", async () => {
    abrir("/invitacion#token-secreto");

    await screen.findByLabelText("Email");
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("");
    expect(screen.queryByText(/Ana/)).toBeNull();
    expect(de("GET", "/api/contacts/7")).toHaveLength(0);
  });

  it("sin token no pregunta a la API y dice que no vale", async () => {
    abrir("/invitacion");

    expect((await screen.findByRole("alert")).textContent).toBe(ENLACE_NO_VALIDO);
    expect(de("POST", "/api/portal-invitations/check")).toHaveLength(0);
  });

  it("con un enlace caducado o gastado dice que no vale y no muestra el formulario", async () => {
    rutas["POST /api/portal-invitations/check"] = () => NO_VALE;
    abrir("/invitacion#viejo");

    expect((await screen.findByRole("alert")).textContent).toBe(ENLACE_NO_VALIDO);
    expect(screen.queryByLabelText("Email")).toBeNull();
  });

  it("si la API no responde no dice que el enlace no vale, y deja reintentar", async () => {
    rutas["POST /api/portal-invitations/check"] = () => ({ status: 503 });
    const u = abrir("/invitacion#token-secreto");

    expect((await screen.findByRole("alert")).textContent).toContain("Servicio no disponible");
    rutas["POST /api/portal-invitations/check"] = () => ({ status: 204 });
    await u.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByLabelText("Email")).toBeTruthy();
  });

  it("si las contraseñas no coinciden no llama a la API", async () => {
    const u = abrir("/invitacion#token-secreto");

    await rellenar(u, "una-frase-bastante-larga", "otra-frase-bastante-larga");

    expect((await screen.findByRole("alert")).textContent).toBe("Las contraseñas no coinciden");
    expect(screen.getByLabelText("Repite la contraseña").getAttribute("aria-invalid")).toBe("true");
    expect(de("POST", "/api/portal-invitations/accept")).toHaveLength(0);
  });

  it("un 422 se muestra junto a su campo", async () => {
    rutas["POST /api/portal-invitations/accept"] = () => ({
      status: 422,
      cuerpo: { detail: [{ loc: ["body", "password"], msg: "La contraseña debe tener entre 12 y 1024 caracteres" }] },
    });
    const u = abrir("/invitacion#token-secreto");

    await rellenar(u, "corta");

    const error = await screen.findByText("La contraseña debe tener entre 12 y 1024 caracteres");
    expect(screen.getByLabelText(/^Contraseña/).getAttribute("aria-describedby")).toBe(error.id);
  });

  it("un email en uso se explica junto al campo y se puede volver a intentar", async () => {
    rutas["POST /api/portal-invitations/accept"] = () => ({ status: 409, cuerpo: { detail: "Ese email ya está en uso: escribe otro" } });
    const u = abrir("/invitacion#token-secreto");

    await rellenar(u);

    const error = await screen.findByText("Ese email ya está en uso: escribe otro");
    expect(screen.getByLabelText("Email").getAttribute("aria-describedby")).toBe(error.id);
    expect((screen.getByRole("button", { name: "Crear cuenta" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("si el enlace deja de valer al enviar, retira el formulario", async () => {
    rutas["POST /api/portal-invitations/accept"] = () => NO_VALE;
    const u = abrir("/invitacion#token-secreto");

    await rellenar(u);

    expect((await screen.findByRole("alert")).textContent).toBe(ENLACE_NO_VALIDO);
    expect(screen.queryByLabelText("Email")).toBeNull();
  });

  it("con una sesión abierta no deja gastar el enlace hasta cerrarla", async () => {
    usuario = RECEPCION;
    const u = abrir("/invitacion#token-secreto");

    await screen.findByText(/sesión abierta como recepcion@prueba\.example\.com/);
    expect(screen.queryByLabelText("Email")).toBeNull();

    await u.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByLabelText("Email")).toBeTruthy();
    await waitFor(() => expect(de("POST", "/api/auth/logout")[0].headers["X-CSRF-Token"]).toBe("csrf-recepcion"));
  });
});
