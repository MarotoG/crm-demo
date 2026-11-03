// Pruebas de la interfaz (T10) con Vitest + Testing Library.
// fetch se sustituye por una API falsa: cada prueba decide qué responde cada ruta y
// después se comprueba lo que vería el usuario y qué peticiones salieron.

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = { clave: string; headers: Record<string, string>; cuerpo: unknown };

const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };
const ADMIN = { id: 1, email: "admin@prueba.example.com", role: "admin", csrf_token: "csrf-admin" };

let rutas: Record<string, () => Respuesta>;
let llamadas: Llamada[];

beforeEach(() => {
  llamadas = [];
  rutas = {
    "GET /api/health": () => ({ status: 200, cuerpo: { status: "ok" } }),
    "GET /api/health/db": () => ({ status: 200, cuerpo: { status: "ok", database: "ok" } }),
    "GET /api/auth/me": () => ({ status: 401, cuerpo: { detail: "No autenticado" } }),
    "GET /api/contacts": () => ({ status: 200, cuerpo: { total: 0, items: [] } }), // T12: recepción y admin la piden
    "GET /api/services": () => ({ status: 200, cuerpo: [] }), // T15: recepción, admin y profesional la piden
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (ruta: string, init: RequestInit = {}) => {
      // Sin la consulta (?status=…): los filtros de contactos (T14) no cambian la ruta.
      const clave = `${init.method ?? "GET"} ${new URL(ruta, "http://localhost").pathname}`;
      llamadas.push({
        clave,
        headers: (init.headers ?? {}) as Record<string, string>,
        cuerpo: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
      });
      const r = rutas[clave]?.() ?? { status: 404, cuerpo: { detail: "Not Found" } };
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
}

function conSesion(usuario: typeof RECEPCION) {
  rutas["GET /api/auth/me"] = () => ({ status: 200, cuerpo: usuario });
}

async function rellenarLogin(email = RECEPCION.email, password = "contraseña-larga") {
  const usuario = userEvent.setup();
  await usuario.type(await screen.findByLabelText("Email"), email);
  await usuario.type(screen.getByLabelText("Contraseña"), password);
  await usuario.click(screen.getByRole("button", { name: "Entrar" }));
  return usuario;
}

const pidio = (clave: string) => llamadas.some((l) => l.clave === clave);

describe("login", () => {
  it("sin sesión, entrar directamente en un área lleva al login", async () => {
    abrir("/admin");

    expect(await screen.findByRole("heading", { name: "Entrar" })).toBeTruthy();
    expect(pidio("GET /api/users")).toBe(false);
    expect(screen.queryByText(/No se pudo comprobar la sesión/)).toBeNull(); // un 401 aquí es lo normal
  });

  it("si la API no responde al abrir la página, avisa en el login", async () => {
    rutas["GET /api/auth/me"] = () => ({ status: 503, cuerpo: { detail: "Servicio no disponible" } });
    abrir("/");

    expect(
      await screen.findByText("No se pudo comprobar la sesión: Servicio no disponible. Inténtalo de nuevo en unos minutos"),
    ).toBeTruthy();
  });

  it("un login correcto lleva al área del rol y envía email y contraseña", async () => {
    rutas["POST /api/auth/login"] = () => ({ status: 200, cuerpo: RECEPCION });
    abrir("/login");

    await rellenarLogin();

    expect(await screen.findByRole("heading", { name: "Contactos" })).toBeTruthy();
    const login = llamadas.find((l) => l.clave === "POST /api/auth/login");
    expect(login?.cuerpo).toEqual({ email: RECEPCION.email, password: "contraseña-larga" });
    expect(login?.headers["X-CSRF-Token"]).toBeUndefined(); // el login no lleva token
  });

  it.each([
    [401, { detail: "Email o contraseña incorrectos" }, "Email o contraseña incorrectos"],
    [429, { detail: "Demasiados intentos. Espera unos minutos." }, "Demasiados intentos. Espera unos minutos."],
    [503, { detail: "Servicio no disponible" }, "Servicio no disponible. Inténtalo de nuevo en unos minutos"],
  ])("un login fallido (%i) muestra el error y sigue en el login", async (status, cuerpo, mensaje) => {
    rutas["POST /api/auth/login"] = () => ({ status, cuerpo });
    abrir("/login");

    await rellenarLogin();

    expect((await screen.findByRole("alert")).textContent).toBe(mensaje);
    expect(screen.getByRole("button", { name: "Entrar" })).toBeTruthy(); // se puede reintentar
  });

  it("sin conexión con el servidor, lo dice", async () => {
    abrir("/login");
    await screen.findByLabelText("Email");
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await rellenarLogin();

    expect((await screen.findByRole("alert")).textContent).toBe("No se pudo contactar con el servidor");
  });

  it("al recargar con sesión válida, entra directamente en su área", async () => {
    conSesion(RECEPCION);
    abrir("/");

    expect(await screen.findByRole("heading", { name: "Contactos" })).toBeTruthy();
    expect(screen.getByText(/recepcion@prueba\.example\.com · Recepción/)).toBeTruthy();
  });
});

describe("áreas por rol", () => {
  it("recepción en /admin ve «sin acceso» y no se piden los usuarios", async () => {
    conSesion(RECEPCION);
    abrir("/admin");

    expect(await screen.findByRole("heading", { name: "No tienes acceso a esta área" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ir a tu área" }).getAttribute("href")).toBe("/recepcion");
    expect(pidio("GET /api/users")).toBe(false);
  });

  it("el admin ve la lista real de usuarios", async () => {
    conSesion(ADMIN);
    rutas["GET /api/users"] = () => ({
      status: 200,
      cuerpo: [
        { id: 1, email: ADMIN.email, role: "admin", active: true },
        { id: 2, email: RECEPCION.email, role: "reception", active: false },
      ],
    });
    abrir("/admin");

    const tabla = await screen.findByRole("table");
    const filas = within(tabla).getAllByRole("row");
    expect(filas).toHaveLength(3); // cabecera + 2
    expect(filas[2].textContent).toBe(`${RECEPCION.email}RecepciónDesactivada`);
  });

  it("si la API dice 403 en /api/users, se muestra el mensaje y se puede reintentar", async () => {
    conSesion(ADMIN);
    rutas["GET /api/users"] = () => ({ status: 403, cuerpo: { detail: "Permiso denegado" } });
    abrir("/admin");

    expect((await screen.findByRole("alert")).textContent).toBe("Permiso denegado");
    rutas["GET /api/users"] = () => ({ status: 200, cuerpo: [] });
    await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("table")).toBeTruthy();
  });

  it("si la sesión caduca en mitad del uso, vuelve al login con un aviso", async () => {
    conSesion(ADMIN);
    rutas["GET /api/users"] = () => ({ status: 401, cuerpo: { detail: "No autenticado" } });
    abrir("/admin");

    expect(await screen.findByText("Tu sesión ha caducado. Vuelve a entrar.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Entrar" })).toBeTruthy();
  });

  it("una dirección que no existe muestra «página no encontrada»", async () => {
    abrir("/no-existe");

    expect(await screen.findByRole("heading", { name: "Página no encontrada" })).toBeTruthy();
  });
});

describe("cerrar sesión", () => {
  it("envía el token CSRF y vuelve al login", async () => {
    conSesion(RECEPCION);
    rutas["POST /api/auth/logout"] = () => ({ status: 204 });
    abrir("/recepcion");

    await userEvent.setup().click(await screen.findByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { name: "Entrar" })).toBeTruthy();
    const logout = llamadas.find((l) => l.clave === "POST /api/auth/logout");
    expect(logout?.headers["X-CSRF-Token"]).toBe("csrf-recepcion");
  });

  it("si el servidor no confirma el cierre, sigue dentro y lo avisa", async () => {
    conSesion(RECEPCION);
    rutas["POST /api/auth/logout"] = () => ({ status: 503, cuerpo: { detail: "Servicio no disponible" } });
    abrir("/recepcion");

    await userEvent.setup().click(await screen.findByRole("button", { name: "Cerrar sesión" }));

    expect((await screen.findByRole("alert")).textContent).toMatch(/^No se pudo cerrar la sesión/);
    expect(screen.getByRole("heading", { name: "Contactos" })).toBeTruthy();
  });

  it("con un token CSRF desfasado (403), pide uno nuevo y reintenta una vez", async () => {
    conSesion(RECEPCION);
    let intentos = 0;
    rutas["POST /api/auth/logout"] = () =>
      ++intentos === 1 ? { status: 403, cuerpo: { detail: "Token CSRF ausente o no válido" } } : { status: 204 };
    abrir("/recepcion");
    await screen.findByRole("button", { name: "Cerrar sesión" });
    conSesion({ ...RECEPCION, csrf_token: "csrf-nuevo" });

    await userEvent.setup().click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { name: "Entrar" })).toBeTruthy();
    const tokens = llamadas.filter((l) => l.clave === "POST /api/auth/logout").map((l) => l.headers["X-CSRF-Token"]);
    expect(tokens).toEqual(["csrf-recepcion", "csrf-nuevo"]);
  });
});
