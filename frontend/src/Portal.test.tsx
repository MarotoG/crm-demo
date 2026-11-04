// Pruebas del portal del cliente (T23), con una API falsa en fetch.

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { CitaPortal, MisCitas } from "./api";
import { SIN_CITAS, SIN_PROXIMAS } from "./Portal";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = { metodo: string; url: string };

const CLIENTE = { id: 9, email: "ana@example.com", role: "client", csrf_token: "csrf-cliente" };

function cita(id: number, inicio: string, fin: string, cambios: Partial<CitaPortal> = {}): CitaPortal {
  return { id, service_name: "Botox", starts_at: inicio, ends_at: fin, status: "scheduled", ...cambios };
}

const PROXIMA = cita(1, "2027-01-11T09:30:00-05:00", "2027-01-11T10:30:00-05:00");
const VACIO: MisCitas = { upcoming: [], past: [], past_total: 0 };

let usuario: typeof CLIENTE;
let misCitas: () => Respuesta;
let llamadas: Llamada[];

beforeEach(() => {
  llamadas = [];
  usuario = CLIENTE;
  misCitas = () => ({ status: 200, cuerpo: VACIO });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      llamadas.push({ metodo: init.method ?? "GET", url });
      const r: Respuesta =
        url === "/api/auth/me"
          ? { status: 200, cuerpo: usuario }
          : url === "/api/portal/appointments"
            ? misCitas()
            : { status: 404, cuerpo: { detail: "No encontrado" } };
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

function abrir(ruta = "/portal") {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const responder = (citas: Partial<MisCitas>) => {
  misCitas = () => ({ status: 200, cuerpo: { ...VACIO, ...citas } });
};

describe("portal del cliente", () => {
  it("al entrar, el cliente llega a «Mis citas» y no pide nada más que las suyas", async () => {
    abrir("/");

    expect(await screen.findByRole("heading", { name: "Mis citas" })).toBeTruthy();
    await screen.findByText(SIN_CITAS);
    expect(llamadas.map((l) => l.url).sort()).toEqual(["/api/auth/me", "/api/portal/appointments"]);
    expect(llamadas.every((l) => l.metodo === "GET")).toBe(true);
  });

  it("sin citas, lo dice y explica qué hacer", async () => {
    abrir();

    expect(await screen.findByText(SIN_CITAS)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Próximas" })).toBeNull();
  });

  it("muestra día, hora y servicio de la próxima, en la hora de la clínica", async () => {
    responder({ upcoming: [PROXIMA] });
    abrir();

    expect(await screen.findByText(/lunes, 11 de enero de 2027 · 9:30–10:30/)).toBeTruthy();
    expect(screen.getByText("Botox · Programada")).toBeTruthy();
    expect(screen.getByText("Horas de Nueva York.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Anteriores" })).toBeNull();
  });

  it("separa próximas y anteriores, cada una con su estado real", async () => {
    responder({
      upcoming: [PROXIMA, cita(2, "2027-01-12T09:00:00-05:00", "2027-01-12T10:00:00-05:00", { status: "cancelled", service_name: "Peel" })],
      past: [
        cita(3, "2027-01-02T09:00:00-05:00", "2027-01-02T10:00:00-05:00", { status: "no_show", service_name: "Laser" }),
        cita(4, "2027-01-01T09:00:00-05:00", "2027-01-01T10:00:00-05:00", { status: "completed", service_name: "Facial" }),
      ],
      past_total: 2,
    });
    abrir();

    const proximas = within((await screen.findByRole("heading", { name: "Próximas" })).nextElementSibling as HTMLElement);
    const anteriores = within(screen.getByRole("heading", { name: "Anteriores" }).nextElementSibling as HTMLElement);
    expect(proximas.getByText("Botox · Programada")).toBeTruthy();
    expect(proximas.getByText("Peel · Cancelada").closest("li")?.className).toContain("cita--cancelada");
    expect(anteriores.getByText("Laser · No presentado")).toBeTruthy();
    expect(anteriores.getByText("Facial · Realizada")).toBeTruthy();
  });

  it("una Programada ya pasada no se lee como futura", async () => {
    responder({ past: [cita(3, "2027-01-02T09:00:00-05:00", "2027-01-02T10:00:00-05:00")], past_total: 1 });
    abrir();

    expect(await screen.findByText("Botox · Sin confirmar")).toBeTruthy();
    expect(screen.getByText(SIN_PROXIMAS)).toBeTruthy();
  });

  it("avisa si hay más anteriores de las que muestra", async () => {
    responder({ past: [cita(3, "2027-01-02T09:00:00-05:00", "2027-01-02T10:00:00-05:00", { status: "completed" })], past_total: 22 });
    abrir();

    expect(await screen.findByText("Mostrando las 1 más recientes de 22.")).toBeTruthy();
  });

  it("es de solo lectura: sin botones en las citas", async () => {
    responder({ upcoming: [PROXIMA] });
    abrir();

    const lista = (await screen.findByText("Botox · Programada")).closest("ul") as HTMLElement;
    expect(within(lista).queryAllByRole("button")).toEqual([]);
    expect(within(lista).queryAllByRole("link")).toEqual([]);
  });

  it("si falla, muestra el error y deja reintentar, sin decir que no tiene citas", async () => {
    misCitas = () => ({ status: 503 });
    const u = abrir();

    expect((await screen.findByRole("alert")).textContent).toContain("Servicio no disponible");
    expect(screen.queryByText(SIN_CITAS)).toBeNull();
    misCitas = () => ({ status: 200, cuerpo: VACIO });
    await u.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText(SIN_CITAS)).toBeTruthy();
  });

  it("si la sesión caduca, vuelve al login con el aviso", async () => {
    misCitas = () => ({ status: 401, cuerpo: { detail: "No autenticado" } });
    abrir();

    expect(await screen.findByText("Tu sesión ha caducado. Vuelve a entrar.")).toBeTruthy();
  });

  it("el personal no entra en el portal ni pide sus citas", async () => {
    usuario = { ...CLIENTE, role: "reception" };
    abrir();

    expect(await screen.findByText("No tienes acceso a esta área")).toBeTruthy();
    expect(llamadas.some((l) => l.url === "/api/portal/appointments")).toBe(false);
  });
});
