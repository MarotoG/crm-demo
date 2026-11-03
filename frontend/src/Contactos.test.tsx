// Pruebas de la pantalla de contactos (T12) con una API falsa en fetch, como en App.test.tsx.
// Aquí la API falsa puede responder tarde (promesa) para probar búsquedas que se cruzan.

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { Contacto } from "./api";
import { AVISO_TILDES, formatoTelefono, tieneTildes } from "./Contactos";

type Respuesta = { status: number; cuerpo?: unknown };
type Llamada = {
  metodo: string;
  ruta: string;
  q: string | null;
  consulta: string; // todos los parámetros (?q=…&status=…), para los filtros (T14)
  headers: Record<string, string>;
  cuerpo: unknown;
};

const RECEPCION = { id: 2, email: "recepcion@prueba.example.com", role: "reception", csrf_token: "csrf-recepcion" };
const ADMIN = { id: 1, email: "admin@prueba.example.com", role: "admin", csrf_token: "csrf-admin" };

function contacto(id: number, datos: Partial<Contacto> = {}): Contacto {
  return {
    id,
    first_name: "Ana",
    last_name: "Smith",
    email: "ana@clinica.example.com",
    phone: null,
    source: "instagram",
    status: "new",
    created_at: "2026-11-02T10:00:00Z",
    owner_id: 2,
    owner_email: "recepcion@prueba.example.com",
    ...datos,
  };
}

let usuario: typeof RECEPCION;
let contactos: (q: string | null) => Respuesta | Promise<Respuesta>;
let alta: (cuerpo: unknown) => Respuesta;
let llamadas: Llamada[];

beforeEach(() => {
  llamadas = [];
  usuario = RECEPCION;
  contactos = () => ({ status: 200, cuerpo: { total: 0, items: [] } });
  alta = () => ({ status: 500 });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (ruta: string, init: RequestInit = {}) => {
      const url = new URL(ruta, "http://localhost");
      const metodo = init.method ?? "GET";
      const cuerpo = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      llamadas.push({
        metodo,
        ruta: url.pathname,
        q: url.searchParams.get("q"),
        consulta: url.searchParams.toString(),
        headers: (init.headers ?? {}) as Record<string, string>,
        cuerpo,
      });
      let r: Respuesta = { status: 404, cuerpo: { detail: "Not Found" } };
      const clave = `${metodo} ${url.pathname}`;
      if (clave === "GET /api/auth/me") r = { status: 200, cuerpo: usuario };
      if (clave === "GET /api/users") r = { status: 200, cuerpo: [] };
      if (clave === "GET /api/services") r = { status: 200, cuerpo: [] }; // T15: la sección de servicios
      if (clave === "GET /api/contacts") r = await contactos(url.searchParams.get("q"));
      if (clave === "POST /api/contacts") r = alta(cuerpo);
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

function abrir(ruta = "/recepcion") {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const busquedas = () => llamadas.filter((l) => l.metodo === "GET" && l.ruta === "/api/contacts").map((l) => l.q);

async function rellenar(u: ReturnType<typeof userEvent.setup>, datos: Record<string, string>) {
  await u.click(await screen.findByRole("button", { name: "Nuevo contacto" }));
  for (const [etiqueta, valor] of Object.entries(datos)) {
    if (etiqueta === "Origen") await u.selectOptions(screen.getByLabelText("Origen"), valor);
    else await u.type(screen.getByLabelText(etiqueta), valor);
  }
}

describe("lista de contactos", () => {
  it("recepción ve sus contactos con teléfono, estado y origen legibles", async () => {
    contactos = () => ({
      status: 200,
      cuerpo: {
        total: 2,
        items: [
          contacto(2, {
            first_name: "Luis",
            last_name: "Perez",
            email: null,
            phone: "+12125550123",
            source: "walk_in",
            owner_id: null,
            owner_email: null,
          }),
          contacto(1),
        ],
      },
    });
    abrir();

    const lista = await screen.findByRole("list");
    const filas = within(lista).getAllByRole("listitem");
    expect(filas.map((f) => f.textContent)).toEqual([
      "Luis Perez(212) 555-0123Nuevo · En persona · Sin responsable",
      "Ana Smithana@clinica.example.comNuevo · Instagram · recepcion@prueba.example.com",
    ]);
    expect(screen.getByText("2 contactos")).toBeTruthy();
  });

  it("sin contactos, invita a crear el primero", async () => {
    abrir();

    expect(await screen.findByText("No hay contactos activos. Crea uno con «Nuevo contacto».")).toBeTruthy();
  });

  it("si hay más de 20, dice cuántos hay en total", async () => {
    const items = Array.from({ length: 20 }, (_, i) => contacto(25 - i, { first_name: `Ana${i}` }));
    contactos = () => ({ status: 200, cuerpo: { total: 25, items } });
    abrir();

    expect(
      await screen.findByText("Mostrando los 20 más recientes de 25. Busca para encontrar los demás."),
    ).toBeTruthy();
  });

  it("el admin también ve los contactos en su área", async () => {
    usuario = ADMIN;
    contactos = () => ({ status: 200, cuerpo: { total: 1, items: [contacto(1)] } });
    abrir("/admin");

    expect(await screen.findByRole("heading", { name: "Usuarios" })).toBeTruthy();
    expect(await screen.findByText("Ana Smith")).toBeTruthy();
  });

  it("si la API falla se puede reintentar", async () => {
    let fallar = true;
    contactos = () => (fallar ? { status: 503 } : { status: 200, cuerpo: { total: 1, items: [contacto(1)] } });
    const u = abrir();

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Servicio no disponible. Inténtalo de nuevo en unos minutos",
    );
    fallar = false;
    await u.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Ana Smith")).toBeTruthy();
  });

  it("si la sesión caduca al pedir la lista, vuelve al login con un aviso", async () => {
    contactos = () => ({ status: 401, cuerpo: { detail: "No autenticado" } });
    abrir();

    expect(await screen.findByText("Tu sesión ha caducado. Vuelve a entrar.")).toBeTruthy();
  });
});

describe("búsqueda", () => {
  it("busca al dejar de escribir, con una sola petición para toda la palabra", async () => {
    contactos = (q) =>
      q === "jose"
        ? { status: 200, cuerpo: { total: 1, items: [contacto(7, { first_name: "Jose", last_name: "Perez" })] } }
        : { status: 200, cuerpo: { total: 0, items: [] } };
    const u = abrir();
    await screen.findByText(/No hay contactos activos/);

    await u.type(screen.getByLabelText("Buscar por nombre, apellidos, email o teléfono"), "jose");

    expect(await screen.findByText("Jose Perez")).toBeTruthy();
    expect(busquedas()).toEqual([null, "jose"]); // ni «j», ni «jo», ni «jos»
  });

  it("sin resultados, lo dice con lo que se buscó", async () => {
    const u = abrir();
    await screen.findByText(/No hay contactos activos/);

    await u.type(screen.getByLabelText("Buscar por nombre, apellidos, email o teléfono"), "nadie");

    expect(await screen.findByText("No hay contactos que coincidan con «nadie».")).toBeTruthy();
  });

  it("si la respuesta de una búsqueda anterior llega tarde, se descarta", async () => {
    let soltarAna: (r: Respuesta) => void = () => {};
    contactos = (q) => {
      if (q === "ana") return new Promise<Respuesta>((resolver) => (soltarAna = resolver));
      if (q === "ana s") return { status: 200, cuerpo: { total: 1, items: [contacto(1)] } };
      return { status: 200, cuerpo: { total: 0, items: [] } };
    };
    const u = abrir();
    await screen.findByText(/No hay contactos activos/);
    const buscador = screen.getByLabelText("Buscar por nombre, apellidos, email o teléfono");

    await u.type(buscador, "ana");
    await waitFor(() => expect(busquedas()).toContain("ana"));
    await u.type(buscador, " s");
    expect(await screen.findByText("Ana Smith")).toBeTruthy();

    // Ahora llega, tarde, la respuesta de «ana» con otra persona: no debe pisar la de «ana s».
    soltarAna({ status: 200, cuerpo: { total: 1, items: [contacto(9, { first_name: "Anabel", last_name: "Ruiz" })] } });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("Anabel Ruiz")).toBeNull();
    expect(screen.getByText("Ana Smith")).toBeTruthy();
  });
});

describe("alta de contactos", () => {
  it("guarda con el token CSRF, avisa y el nuevo aparece en la lista", async () => {
    let guardados: Contacto[] = [];
    contactos = () => ({ status: 200, cuerpo: { total: guardados.length, items: guardados } });
    alta = (cuerpo) => {
      guardados = [contacto(1, { ...(cuerpo as Partial<Contacto>), email: "ana@clinica.example.com", phone: "+12125550123" })];
      return { status: 201, cuerpo: guardados[0] };
    };
    const u = abrir();
    await screen.findByText(/No hay contactos activos/);
    await u.type(screen.getByLabelText("Buscar por nombre, apellidos, email o teléfono"), "algo");

    await rellenar(u, {
      Nombre: "Ana",
      Apellidos: "Smith",
      Email: "Ana@Clinica.Example.com",
      Teléfono: "(212) 555-0123",
      Origen: "instagram",
    });
    await u.click(screen.getByRole("button", { name: "Guardar contacto" }));

    expect((await screen.findByRole("status")).textContent).toBe("Contacto creado: Ana Smith");
    const post = llamadas.find((l) => l.metodo === "POST")!;
    expect(post.headers["X-CSRF-Token"]).toBe("csrf-recepcion");
    expect(post.cuerpo).toEqual({
      first_name: "Ana",
      last_name: "Smith",
      email: "Ana@Clinica.Example.com",
      phone: "(212) 555-0123",
      source: "instagram",
    });
    expect(await screen.findByText("ana@clinica.example.com · (212) 555-0123")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Nuevo contacto" })).toBeNull(); // formulario cerrado
    expect((screen.getByLabelText("Buscar por nombre, apellidos, email o teléfono") as HTMLInputElement).value).toBe("");
  });

  it("sin origen no se envía y lo explica", async () => {
    const u = abrir();
    await rellenar(u, { Nombre: "Ana", Apellidos: "Smith", Email: "ana@x.com" });

    await u.click(screen.getByRole("button", { name: "Guardar contacto" }));

    expect(await screen.findByText("Elige de dónde llegó el contacto")).toBeTruthy();
    expect(llamadas.some((l) => l.metodo === "POST")).toBe(false);
  });

  it("un 422 muestra cada mensaje junto a su campo y los generales aparte", async () => {
    alta = () => ({
      status: 422,
      cuerpo: {
        detail: [
          { loc: ["body", "email"], msg: "El dominio del email no es válido (por ejemplo: nombre@clinica.com)" },
          { loc: ["body"], msg: "Indica al menos un email o un teléfono" },
        ],
      },
    });
    const u = abrir();
    await rellenar(u, { Nombre: "Ana", Apellidos: "Smith", Email: "ana@clinica", Origen: "google" });

    await u.click(screen.getByRole("button", { name: "Guardar contacto" }));

    const email = await screen.findByLabelText("Email");
    await waitFor(() => expect(email.getAttribute("aria-invalid")).toBe("true"));
    expect(document.getElementById(email.getAttribute("aria-describedby")!)!.textContent).toBe(
      "El dominio del email no es válido (por ejemplo: nombre@clinica.com)",
    );
    expect(screen.getByRole("alert").textContent).toBe("Indica al menos un email o un teléfono");
  });

  it("un duplicado (409) se avisa y el formulario conserva los datos", async () => {
    alta = () => ({ status: 409, cuerpo: { detail: "Ya existe un contacto con ese nombre, apellidos y email" } });
    const u = abrir();
    await rellenar(u, { Nombre: "Ana", Apellidos: "Smith", Email: "ana@x.com", Origen: "google" });

    await u.click(screen.getByRole("button", { name: "Guardar contacto" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Ya existe un contacto con ese nombre, apellidos y email");
    expect((screen.getByLabelText("Nombre") as HTMLInputElement).value).toBe("Ana");
    expect(screen.getByRole("button", { name: "Guardar contacto" })).toBeTruthy();
  });

  it("cancelar cierra el formulario sin enviar nada", async () => {
    const u = abrir();
    await rellenar(u, { Nombre: "Ana" });

    await u.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByLabelText("Nombre")).toBeNull();
    expect(llamadas.some((l) => l.metodo === "POST")).toBe(false);
  });
});

describe("sin tildes (T12b)", () => {
  it("el aviso sale bajo el campo mientras se escribe y desaparece al quitar la tilde", async () => {
    const u = abrir();
    await rellenar(u, { Nombre: "Jos\u00e9" });

    const nombre = screen.getByLabelText("Nombre");
    expect(nombre.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(nombre.getAttribute("aria-describedby")!)!.textContent).toBe(AVISO_TILDES);

    await u.clear(nombre);
    await u.type(nombre, "Jose");
    expect(nombre.getAttribute("aria-invalid")).toBeNull();
    expect(screen.queryByText(AVISO_TILDES)).toBeNull();
  });

  it("tras pulsar Guardar con tilde, corregir el campo quita el aviso antes de volver a guardar", async () => {
    const u = abrir();
    await rellenar(u, { Nombre: "José", Apellidos: "Smith", Email: "jose@x.com", Origen: "google" });
    await u.click(screen.getByRole("button", { name: "Guardar contacto" }));
    expect(screen.getByText(AVISO_TILDES)).toBeTruthy();

    await u.clear(screen.getByLabelText("Nombre"));
    await u.type(screen.getByLabelText("Nombre"), "Jose");

    expect(screen.queryByText(AVISO_TILDES)).toBeNull();
    expect(screen.getByLabelText("Nombre").getAttribute("aria-invalid")).toBeNull();
  });

  it("con tildes en apellidos o email no se envía nada", async () => {
    const u = abrir();
    await rellenar(u, { Nombre: "Ana", Apellidos: "Mu\u00f1oz", Email: "jos\u00e9@x.com", Origen: "google" });

    await u.click(screen.getByRole("button", { name: "Guardar contacto" }));

    expect(screen.getAllByText(AVISO_TILDES)).toHaveLength(2);
    expect(llamadas.some((l) => l.metodo === "POST")).toBe(false);
  });

  it("buscar con tilde muestra el aviso bajo el buscador", async () => {
    const u = abrir();
    await screen.findByText(/No hay contactos activos/);
    const buscador = screen.getByLabelText("Buscar por nombre, apellidos, email o teléfono");

    await u.type(buscador, "Jos\u00e9");

    expect(await screen.findByText("No hay contactos que coincidan con «Jos\u00e9».")).toBeTruthy();
    expect(document.getElementById(buscador.getAttribute("aria-describedby")!)!.textContent).toBe(AVISO_TILDES);
  });

  it("tieneTildes detecta cualquier carácter fuera de ASCII", () => {
    expect(tieneTildes("O'Connor-Smith Jr.")).toBe(false);
    expect(["Jos\u00e9", "Mu\u00f1oz", "Zo\u00eb", "\u0410na", "Ana\u200bMaria"].map(tieneTildes)).toEqual([true, true, true, true, true]);
  });
});

describe("formatoTelefono", () => {
  it("muestra los de EE. UU. con su formato y los demás tal cual", () => {
    expect(formatoTelefono("+12125550123")).toBe("(212) 555-0123");
    expect(formatoTelefono("+34612345678")).toBe("+34612345678");
  });
});

describe("filtros de estado y responsable (T14)", () => {
  const consultas = () => llamadas.filter((l) => l.metodo === "GET" && l.ruta === "/api/contacts").map((l) => l.consulta);
  const ACTIVOS = "status=new&status=contacted&status=scheduled&status=client";

  it("por defecto pide los activos (todos menos Perdido) de cualquier responsable", async () => {
    abrir();

    await screen.findByText("No hay contactos activos. Crea uno con «Nuevo contacto».");
    expect(consultas()).toEqual([ACTIVOS]);
    expect((screen.getByLabelText("Estado") as HTMLSelectElement).value).toBe("activos");
    expect((screen.getByLabelText("Responsable") as HTMLSelectElement).value).toBe("todos");
  });

  it("cada filtro cambia lo que se pide a la API y se combina con la búsqueda", async () => {
    const u = abrir();
    await screen.findByText(/No hay contactos activos/);

    await u.selectOptions(screen.getByLabelText("Estado"), "lost");
    await waitFor(() => expect(consultas().at(-1)).toBe("status=lost"));
    await u.selectOptions(screen.getByLabelText("Estado"), "todos");
    await waitFor(() => expect(consultas().at(-1)).toBe(""));
    await u.selectOptions(screen.getByLabelText("Responsable"), "mios");
    await waitFor(() => expect(consultas().at(-1)).toBe("owner=me"));
    await u.selectOptions(screen.getByLabelText("Responsable"), "sin");
    await waitFor(() => expect(consultas().at(-1)).toBe("owner=none"));
    await u.type(screen.getByLabelText(/^Buscar/), "ana");
    await waitFor(() => expect(consultas().at(-1)).toBe("q=ana&owner=none"));
  });

  it("sin resultados con otros filtros, lo dice sin invitar a crear", async () => {
    const u = abrir();
    await screen.findByText(/No hay contactos activos/);

    await u.selectOptions(screen.getByLabelText("Responsable"), "mios");

    expect(await screen.findByText("No hay contactos con estos filtros.")).toBeTruthy();
    await u.type(screen.getByLabelText(/^Buscar/), "nadie");
    expect(await screen.findByText("No hay contactos que coincidan con «nadie» y estos filtros.")).toBeTruthy();
  });

  it("al crear un contacto se quitan los filtros para que aparezca el primero", async () => {
    alta = (cuerpo) => ({ status: 201, cuerpo: contacto(9, cuerpo as Partial<Contacto>) });
    const u = abrir();
    await screen.findByText(/No hay contactos activos/);
    await u.selectOptions(screen.getByLabelText("Estado"), "lost");
    await waitFor(() => expect(consultas().at(-1)).toBe("status=lost"));

    await rellenar(u, { Nombre: "Eva", Apellidos: "Stone", Email: "eva@x.com", Origen: "google" });
    expect(screen.queryByLabelText("Responsable", { selector: "select#contacto-owner_id" })).toBeNull();
    await u.click(screen.getByRole("button", { name: "Guardar contacto" }));

    await screen.findByText("Contacto creado: Eva Stone");
    await waitFor(() => expect(consultas().at(-1)).toBe(ACTIVOS));
    expect((screen.getByLabelText("Estado") as HTMLSelectElement).value).toBe("activos");
    // El alta no envía responsable: lo pone la API (quien lo crea).
    const post = llamadas.find((l) => l.metodo === "POST");
    expect(post?.cuerpo).not.toHaveProperty("owner_id");
  });
});
