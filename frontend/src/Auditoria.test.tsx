// Pruebas de la sección de auditoría (T26), con una API falsa en fetch.

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { EventoAuditoria } from "./api";

type Respuesta = { status: number; cuerpo?: unknown };

const ADMIN = { id: 1, email: "admin@prueba.example.com", role: "admin", csrf_token: "csrf-admin" };
const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };

const BASE: EventoAuditoria = {
  id: 1,
  occurred_at: "2027-01-11T15:00:00Z",
  actor_email: "recepcion@prueba.example.com",
  action: "contact_viewed",
  target_type: "contact",
  target_id: 7,
  target_email: null,
  changed_fields: [],
  from_status: null,
  to_status: null,
};

const lista = (items: EventoAuditoria[], total = items.length) => ({ status: 200, cuerpo: { total, page_size: 50, items } });

let usuario: typeof ADMIN;
let rutas: Record<string, (url: URL) => Respuesta>;
let lecturas: string[];

beforeEach(() => {
  lecturas = [];
  usuario = ADMIN;
  rutas = {
    "GET /api/auth/me": () => ({ status: 200, cuerpo: usuario }),
    "GET /api/follow-ups/summary": () => ({ status: 200, cuerpo: { overdue: 0, due_today: 0 } }),
    "GET /api/users": () => ({
      status: 200,
      cuerpo: [
        { id: 1, email: "admin@prueba.example.com", role: "admin", active: true },
        { id: 2, email: "recepcion@prueba.example.com", role: "reception", active: true },
      ],
    }),
    "GET /api/audit-events": () => lista([BASE]),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (ruta: string, init: RequestInit = {}) => {
      const metodo = init.method ?? "GET";
      const url = new URL(ruta, "http://localhost");
      if (url.pathname === "/api/audit-events") lecturas.push(url.search);
      const r = rutas[`${metodo} ${url.pathname}`]?.(url) ?? { status: 404, cuerpo: { detail: "No encontrado" } };
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

function abrir(ruta = "/auditoria") {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

// El nombre de la acción sale también en el filtro: se busca el de la lista.
const evento = (nombre: string) => screen.findByText(nombre, { selector: ".cita__contacto" });

describe("lista", () => {
  it("enseña la acción, quién, cuándo en hora de la clínica y sobre qué", async () => {
    abrir();
    const fila = (await evento("Abrió una ficha")).closest("li") as HTMLElement;
    expect(within(fila).getByText(/recepcion@prueba\.example\.com/)).toBeTruthy();
    // 15:00 UTC son las 10:00 en Nueva York.
    expect(within(fila).getByText(/11\/1\/27, 10:00/)).toBeTruthy();
    expect(within(fila).getByText(/Sobre: Contacto 7/)).toBeTruthy();
    expect(lecturas[0]).toBe("?page=1");
  });

  it("nombra los campos que cambiaron", async () => {
    rutas["GET /api/audit-events"] = () => lista([{ ...BASE, action: "contact_updated", changed_fields: ["note", "phone"] }]);
    abrir();
    expect(await screen.findByText(/Campos: note, phone/)).toBeTruthy();
  });

  it("traduce el cambio de estado de un contacto", async () => {
    rutas["GET /api/audit-events"] = () =>
      lista([{ ...BASE, action: "contact_status_changed", from_status: "new", to_status: "scheduled" }]);
    abrir();
    expect(await screen.findByText(/Nuevo → Cita agendada/)).toBeTruthy();
  });

  it("traduce el cambio de estado de una cita con sus propios nombres", async () => {
    rutas["GET /api/audit-events"] = () =>
      lista([{ ...BASE, action: "appointment_cancelled", target_type: "appointment", from_status: "scheduled", to_status: "cancelled" }]);
    abrir();
    expect(await screen.findByText(/Programada → Cancelada/)).toBeTruthy();
  });

  it("un login fallido sale sin identificar y con la cuenta intentada", async () => {
    rutas["GET /api/audit-events"] = () =>
      lista([{ ...BASE, action: "login_failed", actor_email: null, target_type: "user", target_id: 3, target_email: "ana@prueba.example.com" }]);
    abrir();
    const fila = (await evento("Intento de entrada fallido")).closest("li") as HTMLElement;
    expect(within(fila).getByText(/Sin identificar/)).toBeTruthy();
    expect(within(fila).getByText(/Sobre: ana@prueba\.example\.com/)).toBeTruthy();
    expect(within(fila).queryByText(/Cuenta 3/)).toBeNull();
  });

  it("un evento sin objetivo ni cambios no enseña una línea vacía", async () => {
    rutas["GET /api/audit-events"] = () => lista([{ ...BASE, action: "login_succeeded", target_type: null, target_id: null }]);
    abrir();
    const fila = (await evento("Entró en el CRM")).closest("li") as HTMLElement;
    expect(within(fila).queryByText(/Sobre/)).toBeNull();
    expect(fila.querySelectorAll(".cita__meta").length).toBe(1);
  });

  it("avisa de que no es un registro inalterable", async () => {
    abrir();
    expect(await screen.findByText(/no un registro inalterable/)).toBeTruthy();
  });

  it("sin eventos lo dice", async () => {
    rutas["GET /api/audit-events"] = () => lista([]);
    abrir();
    expect(await screen.findByText("No hay eventos con estos filtros.")).toBeTruthy();
  });
});

describe("filtros", () => {
  it("filtra por persona desde la lista de cuentas", async () => {
    const u = abrir();
    await evento("Abrió una ficha");
    await screen.findByRole("option", { name: "recepcion@prueba.example.com" });
    await u.selectOptions(screen.getByLabelText("Persona"), "2");
    await evento("Abrió una ficha");
    expect(lecturas.at(-1)).toBe("?page=1&actor_id=2");
  });

  it("filtra por acción", async () => {
    const u = abrir();
    await evento("Abrió una ficha");
    await u.selectOptions(screen.getByLabelText("Acción"), "login_failed");
    await evento("Abrió una ficha");
    expect(lecturas.at(-1)).toBe("?page=1&action=login_failed");
  });

  it("los filtros y la página salen de la dirección", async () => {
    abrir("/auditoria?persona=2&accion=logout&pagina=3");
    await evento("Abrió una ficha");
    expect(lecturas[0]).toBe("?page=3&actor_id=2&action=logout");
  });

  it("cambiar un filtro vuelve a la primera página", async () => {
    rutas["GET /api/audit-events"] = () => lista([BASE], 200);
    const u = abrir("/auditoria?pagina=3");
    await evento("Abrió una ficha");
    await u.selectOptions(screen.getByLabelText("Acción"), "logout");
    await evento("Abrió una ficha");
    expect(lecturas.at(-1)).toBe("?page=1&action=logout");
  });

  it("si la lista de personas falla, los eventos se ven igual", async () => {
    rutas["GET /api/users"] = () => ({ status: 500, cuerpo: { detail: "Error" } });
    abrir();
    expect(await evento("Abrió una ficha")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("páginas", () => {
  it("pasa a los más antiguos y vuelve", async () => {
    rutas["GET /api/audit-events"] = () => lista([BASE], 120);
    const u = abrir();
    await screen.findByText(/Página 1 de 3 · 120 eventos/);
    expect((screen.getByRole("button", { name: "Más recientes" }) as HTMLButtonElement).disabled).toBe(true);
    await u.click(screen.getByRole("button", { name: "Más antiguos" }));
    await screen.findByText(/Página 2 de 3/);
    expect(lecturas.at(-1)).toBe("?page=2");
    await u.click(screen.getByRole("button", { name: "Más recientes" }));
    await screen.findByText(/Página 1 de 3/);
    expect(lecturas.at(-1)).toBe("?page=1");
  });

  it("con un solo evento no habla en plural", async () => {
    abrir();
    expect(await screen.findByText(/Página 1 de 1 · 1 evento en total/)).toBeTruthy();
  });

  it("en la última página no deja seguir", async () => {
    rutas["GET /api/audit-events"] = () => lista([BASE], 100);
    abrir("/auditoria?pagina=2");
    await screen.findByText(/Página 2 de 2/);
    expect((screen.getByRole("button", { name: "Más antiguos" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("una página que ya no existe ofrece volver a la primera", async () => {
    rutas["GET /api/audit-events"] = () => lista([], 3);
    const u = abrir("/auditoria?pagina=9");
    await u.click(await screen.findByRole("button", { name: "Volver a la primera página" }));
    await screen.findByText("No hay eventos con estos filtros.");
    expect(lecturas.at(-1)).toBe("?page=1");
  });
});

describe("errores y permisos", () => {
  it("un error se enseña y se puede reintentar", async () => {
    rutas["GET /api/audit-events"] = () => ({ status: 503, cuerpo: { detail: "Servicio no disponible" } });
    const u = abrir();
    expect((await screen.findByRole("alert")).textContent).toContain("Servicio no disponible");
    rutas["GET /api/audit-events"] = () => lista([BASE]);
    await u.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await evento("Abrió una ficha")).toBeTruthy();
  });

  it("si la sesión caduca vuelve al login con el aviso", async () => {
    rutas["GET /api/audit-events"] = () => ({ status: 401, cuerpo: { detail: "No autenticado" } });
    abrir();
    expect(await screen.findByText(/Tu sesión ha caducado/)).toBeTruthy();
  });

  it("el admin tiene la sección en la barra", async () => {
    abrir();
    await evento("Abrió una ficha");
    const barra = screen.getByRole("navigation", { name: "Secciones" });
    expect(within(barra).getByRole("link", { name: "Auditoría" })).toBeTruthy();
  });

  it("recepción no la ve en la barra ni pide los eventos al escribir la dirección", async () => {
    usuario = RECEPCION;
    abrir();
    expect(await screen.findByRole("heading", { name: "No tienes acceso a esta área" })).toBeTruthy();
    const barra = screen.getByRole("navigation", { name: "Secciones" });
    expect(within(barra).queryByRole("link", { name: "Auditoría" })).toBeNull();
    expect(lecturas).toEqual([]);
  });
});
