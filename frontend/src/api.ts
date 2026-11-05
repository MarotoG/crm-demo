// Llamadas a la API: salud del sistema (T06), sesión y usuarios (T10), contactos (T12–T14), servicios (T15) y citas (T16–T19). Las rutas son
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
 * `general` los que no son de un campo concreto.
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

type Opciones = { method?: "GET" | "POST" | "PUT"; cuerpo?: unknown; csrf?: string };

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
  // 401, 403, 409, 410 y 429 traen un mensaje pensado para el usuario (p. ej. «Email o contraseña incorrectos»).
  if ([401, 403, 409, 410, 429].includes(respuesta.status)) {
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
  /** Obligatorio y único (T21b): una persona, un email. Es también con el que entra al portal. */
  email: string;
  phone: string | null;
  source: OrigenContacto;
  status: EstadoContacto;
  created_at: string;
  /** Responsable (T14): quién lo lleva en la clínica; null = sin responsable. */
  owner_id: number | null;
  owner_email: string | null;
};

export type ListaContactos = { total: number; items: Contacto[] };

/** Filtros de la lista (T14). `estados` vacío: todos. */
export type FiltrosContactos = { estados: EstadoContacto[]; responsable: "todos" | "mios" | "sin" };

export const SIN_FILTROS: FiltrosContactos = { estados: [], responsable: "todos" };

export type NuevoContacto = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  source: OrigenContacto;
  note: string;
};

/** Los 20 más recientes que coinciden con `busqueda` (vacía: todos) y los filtros, y el total. */
export function listarContactos(busqueda: string, filtros: FiltrosContactos = SIN_FILTROS): Promise<ListaContactos> {
  const parametros = new URLSearchParams();
  const q = busqueda.trim();
  if (q) parametros.append("q", q);
  for (const estado of filtros.estados) parametros.append("status", estado);
  if (filtros.responsable === "mios") parametros.append("owner", "me");
  if (filtros.responsable === "sin") parametros.append("owner", "none");
  const consulta = parametros.toString();
  return peticion<ListaContactos>(consulta ? `/api/contacts?${consulta}` : "/api/contacts");
}

export function crearContacto(datos: NuevoContacto, csrf: string): Promise<Contacto> {
  return peticion<Contacto>("/api/contacts", { method: "POST", cuerpo: datos, csrf });
}

/** La ficha (T13): `version` es la que hay que devolver al editar (bloqueo optimista). */
export type ContactoDetalle = Contacto & {
  version: number;
  updated_at: string;
  created_by_email: string | null;
  updated_by_email: string | null;
  /** Nota corta (T21b), por ejemplo su usuario de Instagram. */
  note: string | null;
};

export function obtenerContacto(id: number): Promise<ContactoDetalle> {
  return peticion<ContactoDetalle>(`/api/contacts/${id}`);
}

/** PUT con la ficha entera (con el responsable) y la versión leída: 409 si otra persona guardó antes. */
export function actualizarContacto(
  id: number,
  datos: NuevoContacto & { owner_id: number | null; version: number },
  csrf: string,
): Promise<ContactoDetalle> {
  return peticion<ContactoDetalle>(`/api/contacts/${id}`, { method: "PUT", cuerpo: datos, csrf });
}

/** Cambio de estado a mano (T14): solo a Contactado o Perdido; misma versión que la edición. */
export function cambiarEstado(
  id: number,
  datos: { status: EstadoContacto; version: number },
  csrf: string,
): Promise<ContactoDetalle> {
  return peticion<ContactoDetalle>(`/api/contacts/${id}/status`, { method: "PUT", cuerpo: datos, csrf });
}

export type Responsable = { id: number; email: string };

/** Quién puede ser responsable: las cuentas activas de recepción y administración. */
export function listarResponsables(): Promise<Responsable[]> {
  return peticion<Responsable[]>("/api/contacts/owners");
}

// --- Servicios (T15) -----------------------------------------------------------

/** Una persona que realiza servicios: cualquier cuenta interna. `active` false: desactivada después. */
export type PersonaServicio = { id: number; email: string; role: Rol; active: boolean };

export type Servicio = {
  id: number;
  name: string;
  duration_minutes: number;
  active: boolean;
  /** Bloqueo optimista, como en los contactos: hay que devolverla al editar. */
  version: number;
  staff: PersonaServicio[];
};

export type DatosServicio = { name: string; duration_minutes: number; staff_ids: number[] };

/** Admin y recepción: todos (primero los activos). Profesional: solo sus servicios activos. */
export function listarServicios(): Promise<Servicio[]> {
  return peticion<Servicio[]>("/api/services");
}

/** Quién se puede asignar a un servicio: las cuentas internas activas. */
export function listarPersonasAsignables(): Promise<PersonaServicio[]> {
  return peticion<PersonaServicio[]>("/api/services/staff");
}

export function crearServicio(datos: DatosServicio, csrf: string): Promise<Servicio> {
  return peticion<Servicio>("/api/services", { method: "POST", cuerpo: datos, csrf });
}

/** PUT con el servicio entero, si está activo y la versión leída: 409 si otra persona guardó antes. */
export function actualizarServicio(
  id: number,
  datos: DatosServicio & { active: boolean; version: number },
  csrf: string,
): Promise<Servicio> {
  return peticion<Servicio>(`/api/services/${id}`, { method: "PUT", cuerpo: datos, csrf });
}

// --- Citas (T16–T19) -----------------------------------------------------------

export type EstadoCita = "scheduled" | "completed" | "no_show" | "cancelled";

/** Motivo de una cancelación (T19): lista cerrada; el detalle opcional va aparte. */
export type MotivoCancelacion = "client_request" | "clinic" | "other";

/** Una cita de la agenda. Las horas vienen en la de la clínica, con su desfase («…T09:30:00-05:00»). */
export type CitaAgenda = {
  id: number;
  contact_id: number;
  service_id: number;
  staff_id: number;
  starts_at: string;
  ends_at: string;
  duration_minutes: number;
  status: EstadoCita;
  version: number;
  created_at: string;
  /** Solo en las canceladas (T19). */
  cancel_reason: MotivoCancelacion | null;
  cancel_note: string | null;
  /** Cuándo se marcó la asistencia la primera vez (T20b); null si no está marcada. */
  attended_at: string | null;
  /** Nota interna (T21b): el cliente no la ve. */
  note: string | null;
  contact_name: string;
  service_name: string;
  staff_email: string;
};

/** Sin la duración: la API la copia del servicio. `starts_at`: hora local de la clínica, «2027-01-11T09:30». */
export type NuevaCita = { contact_id: number; service_id: number; staff_id: number; starts_at: string; note?: string };

/** Las citas que ocupan parte de un día (AAAA-MM-DD, en la hora de la clínica), por hora. */
export function listarCitas(dia: string, filtros: { persona?: number; contacto?: number } = {}): Promise<CitaAgenda[]> {
  const parametros = new URLSearchParams({ date: dia });
  if (filtros.persona !== undefined) parametros.append("staff_id", String(filtros.persona));
  if (filtros.contacto !== undefined) parametros.append("contact_id", String(filtros.contacto));
  return peticion<CitaAgenda[]>(`/api/appointments?${parametros}`);
}

/** Las citas de un intervalo de días (T20, la vista del mes; 31 como mucho), por hora. Para el
 * profesional, la API pone sola el filtro por su persona. */
export function listarCitasEntre(desde: string, hasta: string, filtros: { persona?: number } = {}): Promise<CitaAgenda[]> {
  const parametros = new URLSearchParams({ from: desde, to: hasta });
  if (filtros.persona !== undefined) parametros.append("staff_id", String(filtros.persona));
  return peticion<CitaAgenda[]>(`/api/appointments?${parametros}`);
}

/** 409 si quien la realiza ya tiene otra cita que se pisa (T17); el mensaje dice cuál. */
export function crearCita(datos: NuevaCita, csrf: string): Promise<Omit<CitaAgenda, "contact_name" | "service_name" | "staff_email">> {
  return peticion("/api/appointments", { method: "POST", cuerpo: datos, csrf });
}

/** Reprogramar (T19): día y hora (locales de la clínica) y persona, con la versión leída. 409 si
 * otra persona la cambió antes o si la persona ya tiene otra cita que se pisa. */
export function reprogramarCita(
  id: number,
  datos: { staff_id: number; starts_at: string; version: number },
  csrf: string,
): Promise<Omit<CitaAgenda, "contact_name" | "service_name" | "staff_email">> {
  return peticion(`/api/appointments/${id}`, { method: "PUT", cuerpo: datos, csrf });
}

/** Cancelar (T19) con el motivo y, si se quiere, un detalle corto; libera la franja. */
export function cancelarCita(
  id: number,
  datos: { version: number; reason: MotivoCancelacion; note: string | null },
  csrf: string,
): Promise<Omit<CitaAgenda, "contact_name" | "service_name" | "staff_email">> {
  return peticion(`/api/appointments/${id}/cancel`, { method: "POST", cuerpo: datos, csrf });
}

export type Asistencia = "completed" | "no_show";

/** Asistencia (T20b): desde la hora de inicio; se corrige durante 7 días desde que se marcó. 409
 * si otra persona la cambió, no ha empezado, está cancelada o pasó el plazo. El profesional, solo
 * las suyas (404 en las demás). */
export function marcarAsistencia(
  id: number,
  datos: { version: number; status: Asistencia },
  csrf: string,
): Promise<Omit<CitaAgenda, "contact_name" | "service_name" | "staff_email">> {
  return peticion(`/api/appointments/${id}/attendance`, { method: "POST", cuerpo: datos, csrf });
}

/** Editar la nota (T21b), sin reprogramar y en cualquier estado; null la quita. 409 si otra persona
 * cambió la cita antes. */
export function editarNotaCita(
  id: number,
  datos: { version: number; note: string | null },
  csrf: string,
): Promise<Omit<CitaAgenda, "contact_name" | "service_name" | "staff_email">> {
  return peticion(`/api/appointments/${id}/note`, { method: "PUT", cuerpo: datos, csrf });
}

/** Las citas de la ficha (T21): las 20 de fecha más reciente, también canceladas, y el total. El
 * profesional, solo las suyas. */
export function listarCitasDeContacto(contacto: number): Promise<{ total: number; items: CitaAgenda[] }> {
  return peticion(`/api/appointments/by-contact/${contacto}`);
}

// --- Tareas de seguimiento (T24) -------------------------------------------------

export type TareaSeguimiento = {
  id: number;
  contact_id: number;
  contact_name: string;
  contact_status: EstadoContacto;
  description: string;
  due_on: string; // día de la clínica, AAAA-MM-DD
  assigned_to_id: number;
  assigned_to_email: string;
  created_by_email: string | null;
  created_at: string;
  completed_at: string | null; // null: pendiente (T25)
  completed_by_email: string | null;
  version: number;
};

export type NuevaTarea = { description: string; due_on: string; assigned_to_id: number };

/** `today` es el día de la clínica según la API: con él se ve cuáles están vencidas. */
export type ListaTareas = { today: string; total: number; items: TareaSeguimiento[] };

/** Las de un contacto: pendientes y después hechas, por fecha; las 20 primeras y el total. El
 * profesional, solo las suyas. */
export function listarTareas(contacto: number): Promise<ListaTareas> {
  return peticion(`/api/contacts/${contacto}/follow-ups`);
}

/** El panel (T25): las 50 pendientes más cercanas o las 50 hechas más recientes. El profesional,
 * solo las suyas; pedir las de otra persona es 403. */
export function listarPanelTareas(estado: "pending" | "done", persona?: number): Promise<ListaTareas> {
  const parametros = new URLSearchParams({ state: estado });
  if (persona !== undefined) parametros.set("assigned_to_id", String(persona));
  return peticion(`/api/follow-ups?${parametros}`);
}

/** Para el contador de la barra: las pendientes vencidas y las de hoy. */
export function resumenTareas(): Promise<{ overdue: number; due_today: number }> {
  return peticion("/api/follow-ups/summary");
}

export function completarTarea(id: number, version: number, csrf: string): Promise<TareaSeguimiento> {
  return peticion(`/api/follow-ups/${id}/complete`, { method: "POST", cuerpo: { version }, csrf });
}

export function reabrirTarea(id: number, version: number, csrf: string): Promise<TareaSeguimiento> {
  return peticion(`/api/follow-ups/${id}/reopen`, { method: "POST", cuerpo: { version }, csrf });
}

export function editarTarea(id: number, datos: NuevaTarea & { version: number }, csrf: string): Promise<TareaSeguimiento> {
  return peticion(`/api/follow-ups/${id}`, { method: "PUT", cuerpo: datos, csrf });
}

/** A quién se puede asignar: administración, recepción y los profesionales con cita con el contacto. */
export function listarAsignables(contacto: number): Promise<Responsable[]> {
  return peticion<Responsable[]>(`/api/contacts/${contacto}/follow-up-assignees`);
}

export function crearTarea(contacto: number, datos: NuevaTarea, csrf: string): Promise<TareaSeguimiento> {
  return peticion(`/api/contacts/${contacto}/follow-ups`, { method: "POST", cuerpo: datos, csrf });
}

// --- Portal del cliente (T22) ----------------------------------------------------

/** Lo que el cliente sabe de una cita: sin notas, motivo ni quién la realiza. */
export type CitaPortal = { id: number; service_name: string; starts_at: string; ends_at: string; status: EstadoCita };

export type MisCitas = { upcoming: CitaPortal[]; past: CitaPortal[]; past_total: number };

/** Las citas de quien tiene la sesión: no se envía ningún dato que diga de quién son. */
export function listarMisCitas(): Promise<MisCitas> {
  return peticion<MisCitas>("/api/portal/appointments");
}

// --- Invitación al portal (T21) ------------------------------------------------

export type EstadoPortal = { has_account: boolean; invitation_expires_at: string | null };

export function obtenerEstadoPortal(contacto: number): Promise<EstadoPortal> {
  return peticion<EstadoPortal>(`/api/contacts/${contacto}/portal`);
}

/** El token solo viene en esta respuesta: en la BD queda su hash. Generar otro anula el anterior. */
export function generarInvitacion(contacto: number, csrf: string): Promise<{ token: string; expires_at: string }> {
  return peticion(`/api/contacts/${contacto}/portal-invitation`, { method: "POST", csrf });
}

/** Sin sesión: lo que autoriza es el token del enlace. Devuelve con qué email se entrará; 410 si no vale. */
export function comprobarInvitacion(token: string): Promise<{ email: string }> {
  return peticion("/api/portal-invitations/check", { method: "POST", cuerpo: { token } });
}

/** Crea la cuenta con el email de la ficha y gasta el enlace; no inicia sesión. 409 si ya hay otra
 * cuenta con ese email; 410 si no vale. */
export function aceptarInvitacion(datos: { token: string; password: string }): Promise<void> {
  return peticion<void>("/api/portal-invitations/accept", { method: "POST", cuerpo: datos });
}
