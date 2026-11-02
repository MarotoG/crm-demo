// Llamadas a la API: salud del sistema (T06), sesión y usuarios (T10) y contactos (T12). Las rutas son
// relativas (/api/...): en desarrollo las reenvía el proxy de Vite y en producción nginx.

export type EstadoSalud =
  | { tipo: "cargando" }
  | { tipo: "ok" }
  | { tipo: "error"; mensaje: string };

// Holgado respecto a los 3 s que la API espera a PostgreSQL (connect_timeout),
// para mostrar su 503 real y no un "sin respuesta" engañoso.
const TIEMPO_MAXIMO_MS = 10000;

export async function comprobarSalud(ruta: string): Promise<EstadoSalud> {
  let respuesta: Response;
  try {
    respuesta = await fetch(ruta, {
      headers: { Accept: "application/json" },
      // Un estado de salud nunca debe salir de la caché. Además evita que el navegador
      // ponga en fila peticiones idénticas simultáneas esperando poder reutilizarlas.
      cache: "no-store",
      signal: AbortSignal.timeout(TIEMPO_MAXIMO_MS),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      return { tipo: "error", mensaje: `Sin respuesta en ${TIEMPO_MAXIMO_MS / 1000} s` };
    }
    return { tipo: "error", mensaje: "No se pudo contactar con el servidor" };
  }

  if (!respuesta.ok) {
    return { tipo: "error", mensaje: mensajeDeError(respuesta.status) };
  }

  try {
    const cuerpo: unknown = await respuesta.json();
    if (typeof cuerpo === "object" && cuerpo !== null && "status" in cuerpo && cuerpo.status === "ok") {
      return { tipo: "ok" };
    }
  } catch {
    // Cuerpo que no es JSON: se trata como respuesta inesperada.
  }
  return { tipo: "error", mensaje: "Respuesta inesperada del servidor" };
}

function mensajeDeError(status: number): string {
  // 502/504 los genera el proxy (Vite o nginx) cuando la API no contesta;
  // 503 lo devuelve la propia API cuando no llega a la base de datos.
  if (status === 502 || status === 504) return `La API no responde (HTTP ${status})`;
  if (status === 503) return `No disponible (HTTP ${status})`;
  return `Error del servidor (HTTP ${status})`;
}

// --- Sesión y datos (T10) ----------------------------------------------------

export type Rol = "admin" | "reception" | "professional" | "client";

/** Usuario de la sesión; csrf_token solo se guarda en memoria, nunca en localStorage. */
export type Usuario = { id: number; email: string; role: Rol; csrf_token: string };

export type UsuarioAdmin = { id: number; email: string; role: Rol; active: boolean };

/**
 * Error de una llamada: status es null si ni siquiera hubo respuesta (red, tiempo agotado).
 * En un 422, `campos` trae el mensaje de cada campo no válido (p. ej. { email: "…" }) y
 * `general` los que no son de un campo concreto («Indica al menos un email o un teléfono»).
 */
export class ErrorApi extends Error {
  readonly status: number | null;
  readonly campos: Record<string, string>;
  readonly general: string[];

  constructor(status: number | null, mensaje: string, campos: Record<string, string> = {}, general: string[] = []) {
    super(mensaje);
    this.name = "ErrorApi";
    this.status = status;
    this.campos = campos;
    this.general = general;
  }
}

type Opciones = { method?: "GET" | "POST"; cuerpo?: unknown; csrf?: string };

// Única puerta de salida hacia la API: añade X-CSRF-Token a lo que cambia datos y
// convierte cualquier fallo en un ErrorApi con un mensaje comprensible.
async function peticion<T>(ruta: string, { method = "GET", cuerpo, csrf }: Opciones = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (cuerpo !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;

  let respuesta: Response;
  try {
    respuesta = await fetch(ruta, {
      method,
      headers,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      credentials: "same-origin", // la cookie de sesión viaja sola; JavaScript no la ve (HttpOnly)
      cache: "no-store",
      signal: AbortSignal.timeout(TIEMPO_MAXIMO_MS),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ErrorApi(null, `Sin respuesta en ${TIEMPO_MAXIMO_MS / 1000} s`);
    }
    throw new ErrorApi(null, "No se pudo contactar con el servidor");
  }

  if (!respuesta.ok) throw await errorDeRespuesta(respuesta);
  if (respuesta.status === 204) return undefined as T;
  return (await respuesta.json()) as T;
}

async function errorDeRespuesta(respuesta: Response): Promise<ErrorApi> {
  if (respuesta.status !== 422) return new ErrorApi(respuesta.status, await mensajeDeRespuesta(respuesta));
  // 422 de FastAPI: detail = [{ loc: ["body", "email"], msg: "…" }, …]
  const campos: Record<string, string> = {};
  const general: string[] = [];
  try {
    const cuerpo: unknown = await respuesta.json();
    const detalle = typeof cuerpo === "object" && cuerpo !== null && "detail" in cuerpo ? cuerpo.detail : null;
    if (Array.isArray(detalle)) {
      for (const error of detalle as { loc?: unknown[]; msg?: unknown }[]) {
        if (typeof error.msg !== "string") continue;
        const campo = error.loc?.length === 2 && typeof error.loc[1] === "string" ? error.loc[1] : null;
        if (campo && !(campo in campos)) campos[campo] = error.msg;
        else if (!campo) general.push(error.msg);
      }
    }
  } catch {
    // Sin cuerpo JSON: solo el mensaje genérico.
  }
  return new ErrorApi(422, "Revisa los datos introducidos", campos, general);
}

async function mensajeDeRespuesta(respuesta: Response): Promise<string> {
  if (respuesta.status === 503) return "Servicio no disponible. Inténtalo de nuevo en unos minutos";
  // 401, 403, 409 y 429 traen un mensaje pensado para el usuario (p. ej. «Email o contraseña incorrectos»).
  if ([401, 403, 409, 429].includes(respuesta.status)) {
    try {
      const cuerpo: unknown = await respuesta.json();
      if (typeof cuerpo === "object" && cuerpo !== null && "detail" in cuerpo && typeof cuerpo.detail === "string") {
        return cuerpo.detail;
      }
    } catch {
      // Sin cuerpo JSON: mensaje genérico.
    }
  }
  return mensajeDeError(respuesta.status);
}

export function iniciarSesion(email: string, password: string): Promise<Usuario> {
  return peticion<Usuario>("/api/auth/login", { method: "POST", cuerpo: { email, password } });
}

/** El usuario de la cookie actual, o null si no hay sesión válida (401). */
export async function obtenerSesion(): Promise<Usuario | null> {
  try {
    return await peticion<Usuario>("/api/auth/me");
  } catch (error) {
    if (error instanceof ErrorApi && error.status === 401) return null;
    throw error;
  }
}

export function cerrarSesion(csrf: string): Promise<void> {
  return peticion<void>("/api/auth/logout", { method: "POST", csrf });
}

export function listarUsuarios(): Promise<UsuarioAdmin[]> {
  return peticion<UsuarioAdmin[]>("/api/users");
}

// --- Contactos (T12) -----------------------------------------------------------

export type OrigenContacto = "instagram" | "facebook" | "google" | "website" | "referral" | "walk_in" | "other";
export type EstadoContacto = "new" | "contacted" | "scheduled" | "client" | "lost";

export type Contacto = {
  id: number;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  source: OrigenContacto;
  status: EstadoContacto;
  created_at: string;
};

export type ListaContactos = { total: number; items: Contacto[] };

export type NuevoContacto = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  source: OrigenContacto;
};

/** Los 20 más recientes que coinciden con `busqueda` (vacía: todos) y el total. */
export function listarContactos(busqueda: string): Promise<ListaContactos> {
  const q = busqueda.trim();
  return peticion<ListaContactos>(q ? `/api/contacts?${new URLSearchParams({ q })}` : "/api/contacts");
}

export function crearContacto(datos: NuevoContacto, csrf: string): Promise<Contacto> {
  return peticion<Contacto>("/api/contacts", { method: "POST", cuerpo: datos, csrf });
}
