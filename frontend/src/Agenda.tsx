// Agenda de recepción (T18): las citas de un día por hora, con el filtro por persona, y el
// formulario para dar una cita. Lo usan recepción y administración en /agenda. La ficha de un
// contacto abre el mismo formulario con el contacto ya elegido (/agenda?nueva=1&contacto=7).
//
// El día, la persona y si el formulario está abierto van en la dirección (?fecha=2027-01-11…):
// se puede recargar o compartir la página sin perderlos. Todas las horas son las de la clínica.
//
// Quién puede hacer qué y los solapamientos de una persona los decide la API (403, 409). El
// aviso de que el contacto ya tiene otra cita a esa hora es solo eso, un aviso (decisión T17):
// una clienta puede recibir dos servicios a la vez con personas distintas.
//
// Reprogramar y cancelar (T19): solo las citas Programadas que no han empezado. Reprogramar abre
// el mismo formulario con el contacto y el servicio fijos (/agenda?reprogramar=12); cancelar pide
// el motivo en la propia fila. Las canceladas siguen en la lista, atenuadas y con su motivo.
//
// Vista del mes (T20, ?vista=mes): todas las citas del mes agrupadas por día, con cuántas
// Programadas hay de cada servicio (para preparar el material) y los mismos botones, sin ir día a
// día. «Mi agenda» del profesional (/mi-agenda) es esta misma agenda en solo lectura: la API le
// devuelve solo sus citas, y aquí no hay formulario, filtro por persona ni reprogramar o cancelar.
//
// Asistencia (T20b): en las citas que ya han empezado, «Realizada» y «No presentado» (también en
// «Mi agenda», para las suyas); durante 7 días desde que se marcó, el botón para corregirla.

import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import {
  cancelarCita,
  crearCita,
  ErrorApi,
  listarCitas,
  listarCitasEntre,
  listarContactos,
  listarPersonasAsignables,
  listarServicios,
  marcarAsistencia,
  obtenerContacto,
  reprogramarCita,
  type Asistencia,
  type CitaAgenda,
  type Contacto,
  type EstadoCita,
  type FiltrosContactos,
  type MotivoCancelacion,
  type PersonaServicio,
  type Servicio,
} from "./api";
import { formatoTelefono, PAUSA_BUSQUEDA_MS, ZONA_CLINICA } from "./Contactos";
import { formatoDuracion } from "./Servicios";
import { NOMBRE_ROL, useSesion } from "./sesion";

export const NOMBRE_ESTADO_CITA: Record<EstadoCita, string> = {
  scheduled: "Programada",
  completed: "Realizada",
  no_show: "No presentado",
  cancelled: "Cancelada",
};

export const NOMBRE_MOTIVO: Record<MotivoCancelacion, string> = {
  client_request: "Lo pidió la clienta",
  clinic: "Lo canceló la clínica",
  other: "Otro motivo",
};

/** Solo se reprograma o cancela una cita Programada que todavía no ha empezado (decisión T19). */
export function sePuedeCambiar(cita: CitaAgenda, ahora: Date = new Date()): boolean {
  return cita.status === "scheduled" && new Date(cita.starts_at).getTime() > ahora.getTime();
}

// Asistencia (T20b): se marca desde la hora de inicio y se corrige durante 7 días desde que se marcó.
const PLAZO_CORRECCION_MS = 7 * 86_400_000;

/** Una Programada que ya ha empezado: se marca Realizada o No presentado. */
export function sePuedeMarcar(cita: CitaAgenda, ahora: Date = new Date()): boolean {
  return cita.status === "scheduled" && new Date(cita.starts_at).getTime() <= ahora.getTime();
}

/** Una ya marcada, dentro del plazo: se cambia a la otra. */
export function sePuedeCorregir(cita: CitaAgenda, ahora: Date = new Date()): boolean {
  if ((cita.status !== "completed" && cita.status !== "no_show") || cita.attended_at === null) return false;
  return ahora.getTime() <= new Date(cita.attended_at).getTime() + PLAZO_CORRECCION_MS;
}

// --- Fechas y horas en la zona de la clínica ---------------------------------------

const PARTES = new Intl.DateTimeFormat("en-CA", {
  timeZone: ZONA_CLINICA,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const HORA = new Intl.DateTimeFormat("es-ES", { timeZone: ZONA_CLINICA, hour: "numeric", minute: "2-digit" });
// El día como fecha de calendario: se formatea a mediodía UTC para que ninguna zona lo mueva de día.
const DIA = new Intl.DateTimeFormat("es-ES", { timeZone: "UTC", weekday: "long", day: "numeric", month: "long", year: "numeric" });

/** Fecha y hora de un instante en la clínica: { dia: "2027-01-11", minutos: 570 } para las 9:30. */
function enLaClinica(momento: Date): { dia: string; minutos: number } {
  const p = Object.fromEntries(PARTES.formatToParts(momento).map(({ type, value }) => [type, value]));
  return { dia: `${p.year}-${p.month}-${p.day}`, minutos: Number(p.hour) * 60 + Number(p.minute) };
}

export function hoyEnLaClinica(ahora: Date = new Date()): string {
  return enLaClinica(ahora).dia;
}

const mediodia = (dia: string) => new Date(`${dia}T12:00:00Z`);

export function diaValido(texto: string | null): texto is string {
  if (!texto || !/^\d{4}-\d{2}-\d{2}$/.test(texto)) return false;
  const fecha = mediodia(texto);
  return !Number.isNaN(fecha.getTime()) && fecha.toISOString().slice(0, 10) === texto; // descarta el 30/02
}

export function sumarDias(dia: string, dias: number): string {
  const fecha = mediodia(dia);
  fecha.setUTCDate(fecha.getUTCDate() + dias);
  return fecha.toISOString().slice(0, 10);
}

/** «2027-01-11» → «lunes, 11 de enero de 2027». */
export function formatoDia(dia: string): string {
  return DIA.format(mediodia(dia));
}

const MES = new Intl.DateTimeFormat("es-ES", { timeZone: "UTC", month: "long", year: "numeric" });

/** «2027-02-17» → «2027-02-01». */
export function primeroDeMes(dia: string): string {
  return `${dia.slice(0, 7)}-01`;
}

/** El día 1 del mes que está `meses` antes o después del de `dia`. */
export function sumarMeses(dia: string, meses: number): string {
  const [anio, mes] = dia.split("-").map(Number);
  return new Date(Date.UTC(anio, mes - 1 + meses, 1, 12)).toISOString().slice(0, 10);
}

/** El último día del mes de `dia` (28, 29, 30 o 31). */
export function ultimoDeMes(dia: string): string {
  return sumarDias(sumarMeses(dia, 1), -1);
}

/** «2027-02-17» → «febrero de 2027». */
export function formatoMes(dia: string): string {
  return MES.format(mediodia(primeroDeMes(dia)));
}

/** Las citas del mes agrupadas por el día (en la clínica) en que empiezan, en orden. La que empieza
 * la víspera del día 1 y acaba ya en el mes (23:30-0:30) sale en el día 1. */
export function porDia(citas: CitaAgenda[], primero: string): [string, CitaAgenda[]][] {
  const grupos = new Map<string, CitaAgenda[]>();
  for (const cita of citas) {
    const suDia = enLaClinica(new Date(cita.starts_at)).dia;
    const clave = suDia < primero ? primero : suDia;
    grupos.set(clave, [...(grupos.get(clave) ?? []), cita]);
  }
  return [...grupos.entries()].sort(([a], [b]) => a.localeCompare(b));
}

/** Cuántas Programadas hay de cada servicio, de más a menos (a igualdad, por nombre). */
export function resumenPorServicio(citas: CitaAgenda[]): { servicio: string; total: number }[] {
  const cuenta = new Map<string, number>();
  for (const c of citas) if (c.status === "scheduled") cuenta.set(c.service_name, (cuenta.get(c.service_name) ?? 0) + 1);
  return [...cuenta.entries()]
    .map(([servicio, total]) => ({ servicio, total }))
    .sort((a, b) => b.total - a.total || a.servicio.localeCompare(b.servicio));
}

/** Minutos desde las 0:00 de `dia` (en la clínica) hasta el instante: negativos si es el día
 * anterior, más de 1440 si es el siguiente. Sirve para comparar con la hora elegida. */
export function minutosDesde(dia: string, iso: string): number {
  const { dia: suDia, minutos } = enLaClinica(new Date(iso));
  const dias = Math.round((mediodia(suDia).getTime() - mediodia(dia).getTime()) / 86_400_000);
  return dias * 1440 + minutos;
}

/** La hora de un instante; si cae en otro día que `dia`, con la fecha: «23:30 (10/01)». */
export function horaEn(dia: string, iso: string): string {
  const hora = HORA.format(new Date(iso));
  const suDia = enLaClinica(new Date(iso)).dia;
  // La fecha corta a mano: el formato de Intl para «12/01» cambia entre versiones de ICU («12/1»).
  return suDia === dia ? hora : `${hora} (${suDia.slice(8, 10)}/${suDia.slice(5, 7)})`;
}

const tramo = (dia: string, cita: CitaAgenda) => `${horaEn(dia, cita.starts_at)}–${horaEn(dia, cita.ends_at)}`;

/** «Cancelada (Lo pidió la clienta: Llamara otro dia)»; el resto de estados, solo su nombre. */
function estadoDe(cita: CitaAgenda): string {
  const nombre = NOMBRE_ESTADO_CITA[cita.status];
  if (cita.status !== "cancelled" || !cita.cancel_reason) return nombre;
  const motivo = NOMBRE_MOTIVO[cita.cancel_reason];
  return `${nombre} (${cita.cancel_note ? `${motivo}: ${cita.cancel_note}` : motivo})`;
}

// --- Agenda ---------------------------------------------------------------------------

type EstadoLista = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; citas: CitaAgenda[] };

function mensajeDe(error: unknown): string {
  return error instanceof ErrorApi ? error.message : "Error inesperado";
}

/** La agenda de la clínica (admin y recepción, /agenda) o, con `propia`, «Mi agenda» del
 * profesional (/mi-agenda, T20): solo sus citas, que filtra la API, sin dar, reprogramar ni cancelar
 * citas; sí marca su asistencia (T20b). */
export default function Agenda({ propia = false }: { propia?: boolean }) {
  const { estado, caducada } = useSesion();
  const [parametros, setParametros] = useSearchParams();
  const fecha = parametros.get("fecha");
  const dia = diaValido(fecha) ? fecha : hoyEnLaClinica();
  const vista = parametros.get("vista") === "mes" ? "mes" : "dia";
  const primero = primeroDeMes(dia);
  // Lo que se pide a la API: el día o, en la vista del mes, el mes (moverse dentro de él no recarga).
  const periodo = vista === "mes" ? primero : dia;
  const persona = propia ? "" : (parametros.get("persona") ?? ""); // "": todas
  const nueva = !propia && parametros.get("nueva") === "1";
  const contactoInicial = Number(parametros.get("contacto")) || null;
  const reprogramar = propia ? null : Number(parametros.get("reprogramar")) || null;
  const [lista, setLista] = useState<EstadoLista>({ tipo: "cargando" });
  const [recarga, setRecarga] = useState(0);
  const [personas, setPersonas] = useState<PersonaServicio[]>([]);
  const [creada, setCreada] = useState<string | null>(null);
  // La cita que se reprograma, tal como llegó en la última lista: se conserva mientras la lista
  // se recarga, y la recarga trae su versión nueva si otra persona la cambió (409).
  const [enEdicion, setEnEdicion] = useState<CitaAgenda | null>(null);
  const [cancelando, setCancelando] = useState<number | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  function cambiar(cambios: Record<string, string | null>) {
    const nuevos = new URLSearchParams(parametros);
    for (const [clave, valor] of Object.entries(cambios)) {
      if (valor === null || valor === "") nuevos.delete(clave);
      else nuevos.set(clave, valor);
    }
    setParametros(nuevos);
  }

  useEffect(() => {
    let vigente = true;
    setLista({ tipo: "cargando" });
    const filtros = persona ? { persona: Number(persona) } : {};
    // El mes entero de una vez (T20): de su día 1 al último.
    const peticion = vista === "mes" ? listarCitasEntre(primero, ultimoDeMes(primero), filtros) : listarCitas(dia, filtros);
    peticion
      .then((citas) => vigente && setLista({ tipo: "ok", citas }))
      .catch((error: unknown) => {
        if (!vigente) return;
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setLista({ tipo: "error", mensaje: mensajeDe(error) });
      });
    return () => {
      vigente = false;
    };
  }, [periodo, vista, persona, recarga, caducada]);

  useEffect(() => {
    // Para el filtro: las cuentas internas activas (las que pueden realizar citas). El profesional
    // no tiene filtro: ve solo las suyas.
    if (propia) return;
    listarPersonasAsignables()
      .then(setPersonas)
      .catch(() => setPersonas([])); // sin la lista, el filtro solo ofrece «Todas»
  }, [propia]);

  useEffect(() => {
    if (lista.tipo !== "ok" || reprogramar === null) return;
    const encontrada = lista.citas.find((c) => c.id === reprogramar);
    if (encontrada) setEnEdicion(encontrada);
  }, [lista, reprogramar]);

  if (estado.tipo !== "dentro") return null;
  const yo = String(estado.usuario.id);

  function alGuardar(diaDeLaCita: string, texto: string) {
    setCreada(texto);
    cambiar({ nueva: null, contacto: null, reprogramar: null, fecha: diaDeLaCita });
    setRecarga((n) => n + 1);
  }

  function limpiarMensajes() {
    setCreada(null);
    setAviso(null);
  }

  const editada = enEdicion && enEdicion.id === reprogramar ? enEdicion : null;

  /** Una cita de la lista; `diaDeLaFila` es el día bajo el que sale (para escribir sus horas). */
  function fila(c: CitaAgenda, diaDeLaFila: string) {
    return (
      <li key={c.id} className={c.status === "cancelled" ? "cita cita--cancelada" : "cita"}>
        <span className="cita__hora">{tramo(diaDeLaFila, c)}</span>
        <Link className="cita__contacto" to={`/contactos/${c.contact_id}`}>
          {c.contact_name}
        </Link>
        <span className="cita__meta">
          {c.service_name}
          {!propia && ` · ${c.staff_email}`}
          {c.status !== "scheduled" && ` · ${estadoDe(c)}`}
        </span>
        {!propia && sePuedeCambiar(c) && cancelando !== c.id && (
          <span className="cita__acciones">
            <button
              type="button"
              className="secundario"
              aria-label={`Reprogramar: ${c.contact_name}, ${tramo(diaDeLaFila, c)}`}
              onClick={() => {
                limpiarMensajes();
                setCancelando(null);
                setEnEdicion(c);
                cambiar({ reprogramar: String(c.id), nueva: null, contacto: null });
              }}
            >
              Reprogramar
            </button>
            <button
              type="button"
              className="secundario"
              aria-label={`Cancelar la cita: ${c.contact_name}, ${tramo(diaDeLaFila, c)}`}
              onClick={() => {
                limpiarMensajes();
                setCancelando(c.id);
              }}
            >
              Cancelar cita
            </button>
          </span>
        )}
        {!propia && sePuedeCambiar(c) && cancelando === c.id && (
          <FormularioCancelar
            cita={c}
            dia={diaDeLaFila}
            alTerminar={(texto) => {
              setCancelando(null);
              setCreada(texto);
              setRecarga((n) => n + 1);
            }}
            alConflicto={(texto) => {
              // Otra persona la cambió: se cierra, se avisa y la lista trae la versión nueva.
              setCancelando(null);
              setAviso(texto);
              setRecarga((n) => n + 1);
            }}
            alVolver={() => setCancelando(null)}
          />
        )}
        {(sePuedeMarcar(c) || sePuedeCorregir(c)) && (
          // También en «Mi agenda»: el profesional marca las suyas (T20b).
          <BotonesAsistencia
            cita={c}
            dia={diaDeLaFila}
            alTerminar={(texto) => {
              limpiarMensajes();
              setCreada(texto);
              setRecarga((n) => n + 1);
            }}
            alConflicto={(texto) => {
              limpiarMensajes();
              setAviso(texto);
              setRecarga((n) => n + 1);
            }}
          />
        )}
      </li>
    );
  }

  const titulo = propia ? "Mi agenda" : "Agenda";
  const vacia = vista === "mes" ? "este mes" : "este día";

  return (
    <section className="tarjeta" aria-labelledby="titulo-agenda">
      <h2 id="titulo-agenda">{titulo}</h2>

      {creada && (
        <p className="exito" role="status">
          {creada}
        </p>
      )}
      {aviso && (
        <p className="error" role="alert">
          {aviso}
        </p>
      )}

      {propia ? null : editada && sePuedeCambiar(editada) ? (
        <FormularioCita
          key={editada.id}
          diaInicial={dia}
          contactoInicial={null}
          cita={editada}
          alGuardar={alGuardar}
          alCancelar={() => cambiar({ reprogramar: null })}
          alConflicto={() => setRecarga((n) => n + 1)}
        />
      ) : nueva ? (
        <FormularioCita
          diaInicial={dia}
          contactoInicial={contactoInicial}
          alGuardar={alGuardar}
          alCancelar={() => cambiar({ nueva: null, contacto: null })}
        />
      ) : (
        <>
          {editada && (
            // Otra persona la canceló (o empezó) mientras se reprogramaba: la recarga lo muestra.
            <p className="error" role="alert">
              Esta cita ya no se puede reprogramar: está «{NOMBRE_ESTADO_CITA[editada.status]}»
              {editada.status === "scheduled" && " y ya ha empezado"}.
            </p>
          )}
          <button
            type="button"
            onClick={() => {
              limpiarMensajes();
              cambiar({ nueva: "1", reprogramar: null });
            }}
          >
            Nueva cita
          </button>
        </>
      )}

      <div className="vistas" role="group" aria-label="Vista">
        <button type="button" className="secundario" aria-pressed={vista === "dia"} onClick={() => cambiar({ vista: null })}>
          Día
        </button>
        <button type="button" className="secundario" aria-pressed={vista === "mes"} onClick={() => cambiar({ vista: "mes" })}>
          Mes
        </button>
      </div>

      {vista === "dia" ? (
        <div className="dia">
          <button type="button" className="secundario" onClick={() => cambiar({ fecha: sumarDias(dia, -1) })}>
            ← Día anterior
          </button>
          <label>
            Día
            <input type="date" value={dia} onChange={(e) => diaValido(e.target.value) && cambiar({ fecha: e.target.value })} />
          </label>
          <button type="button" className="secundario" onClick={() => cambiar({ fecha: sumarDias(dia, 1) })}>
            Día siguiente →
          </button>
          <button type="button" className="secundario" onClick={() => cambiar({ fecha: null })} disabled={dia === hoyEnLaClinica()}>
            Hoy
          </button>
        </div>
      ) : (
        <div className="dia dia--mes">
          <button type="button" className="secundario" onClick={() => cambiar({ fecha: sumarMeses(primero, -1) })}>
            ← Mes anterior
          </button>
          <button type="button" className="secundario" onClick={() => cambiar({ fecha: sumarMeses(primero, 1) })}>
            Mes siguiente →
          </button>
          <button
            type="button"
            className="secundario"
            onClick={() => cambiar({ fecha: null })}
            disabled={primero === primeroDeMes(hoyEnLaClinica())}
          >
            Este mes
          </button>
        </div>
      )}
      {!propia && (
        <div className="filtros">
          <label>
            Persona
            <select value={persona} onChange={(e) => cambiar({ persona: e.target.value })}>
              <option value="">Todas</option>
              {personas.map((p) => (
                <option key={p.id} value={String(p.id)}>
                  {p.email}
                </option>
              ))}
            </select>
          </label>
          {/* Para quien también realiza servicios (T20): el filtro con su propia cuenta. */}
          <button type="button" className="secundario" onClick={() => cambiar({ persona: yo })} disabled={persona === yo}>
            Solo mis citas
          </button>
        </div>
      )}

      <h3 className="dia__titulo">
        {vista === "mes" ? formatoMes(primero) : formatoDia(dia)} <span className="ayuda">(hora de Nueva York)</span>
      </h3>
      {lista.tipo === "cargando" && <p>Cargando la agenda…</p>}
      {lista.tipo === "error" && (
        <>
          <p className="error" role="alert">
            {lista.mensaje}
          </p>
          <button type="button" className="secundario" onClick={() => setRecarga((n) => n + 1)}>
            Reintentar
          </button>
        </>
      )}
      {lista.tipo === "ok" && lista.citas.length === 0 && (
        <p>{propia ? `No tienes citas ${vacia}.` : persona ? `Esta persona no tiene citas ${vacia}.` : `No hay citas ${vacia}.`}</p>
      )}
      {lista.tipo === "ok" && lista.citas.length > 0 && vista === "dia" && (
        <ul className="citas">{lista.citas.map((c) => fila(c, dia))}</ul>
      )}
      {lista.tipo === "ok" && lista.citas.length > 0 && vista === "mes" && (
        <>
          <Resumen citas={lista.citas} />
          {porDia(lista.citas, primero).map(([diaDelGrupo, citas]) => (
            <div key={diaDelGrupo} className="mes__dia">
              <h4>
                {formatoDia(diaDelGrupo)}{" "}
                <button type="button" className="enlace" onClick={() => cambiar({ vista: null, fecha: diaDelGrupo })}>
                  Ver el día
                </button>
              </h4>
              <ul className="citas">{citas.map((c) => fila(c, diaDelGrupo))}</ul>
            </div>
          ))}
        </>
      )}
    </section>
  );
}

/** Cuántas citas Programadas hay de cada servicio en el periodo (T20): para preparar el material.
 * Las canceladas no gastan material y no cuentan. */
function Resumen({ citas }: { citas: CitaAgenda[] }) {
  const resumen = resumenPorServicio(citas);
  if (resumen.length === 0) return <p className="resumen">No hay ninguna cita Programada este mes.</p>;
  return (
    <p className="resumen">
      <strong>Programadas este mes:</strong> {resumen.map(({ servicio, total }) => `${servicio}: ${total}`).join(" · ")}
    </p>
  );
}

// --- Formulario de cita ------------------------------------------------------------------

type Elegido = { id: number; nombre: string };
type Campo = "contact_id" | "service_id" | "staff_id" | "starts_at";
type EstadoServicios = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; lista: Servicio[] };

// Los Perdidos no pueden recibir cita (T16): no se ofrecen al buscar.
const SIN_PERDIDOS: FiltrosContactos = { estados: ["new", "contacted", "scheduled", "client"], responsable: "todos" };
const HORAS = Array.from({ length: 24 }, (_, h) => String(h));
// Minutos de 5 en 5 (decisión T18): siempre se elige una hora que la API acepta.
const MINUTOS = Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, "0"));

const nombreDe = (c: Pick<Contacto, "first_name" | "last_name">) => `${c.first_name} ${c.last_name}`;

/** Solo los servicios que se pueden reservar: activos y con alguien activo que los realice. */
function reservables(servicios: Servicio[]): Servicio[] {
  return servicios.filter((s) => s.active && s.staff.some((p) => p.active));
}

/** Nueva cita o, con `cita`, reprogramarla (T19): el contacto y el servicio quedan fijos y se
 * cambian el día, la hora y la persona. La versión se lee de `cita` al guardar: tras un 409 la
 * agenda se recarga (`alConflicto`) y llega la nueva. */
function FormularioCita({
  diaInicial,
  contactoInicial,
  cita,
  alGuardar,
  alCancelar,
  alConflicto,
}: {
  diaInicial: string;
  contactoInicial: number | null;
  cita?: CitaAgenda;
  alGuardar: (dia: string, texto: string) => void;
  alCancelar: () => void;
  alConflicto?: () => void;
}) {
  const { estado, caducada } = useSesion();
  const inicial = cita ? enLaClinica(new Date(cita.starts_at)) : null;
  const [contacto, setContacto] = useState<Elegido | null>(cita ? { id: cita.contact_id, nombre: cita.contact_name } : null);
  const [texto, setTexto] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [resultados, setResultados] = useState<Contacto[] | null>(null);
  const [servicios, setServicios] = useState<EstadoServicios>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);
  const [servicioId, setServicioId] = useState(cita ? String(cita.service_id) : "");
  const [personaId, setPersonaId] = useState(cita ? String(cita.staff_id) : "");
  const [dia, setDia] = useState(inicial ? inicial.dia : diaInicial);
  const [hora, setHora] = useState(inicial ? String(Math.floor(inicial.minutos / 60)) : "9");
  const [minuto, setMinuto] = useState(inicial ? String(inicial.minutos % 60).padStart(2, "0") : "00");
  const [ocupadas, setOcupadas] = useState<CitaAgenda[] | null>(null);
  const [delContacto, setDelContacto] = useState<CitaAgenda[]>([]);
  const [recargaOcupadas, setRecargaOcupadas] = useState(0);
  const [errores, setErrores] = useState<Partial<Record<Campo, string>>>({});
  const [general, setGeneral] = useState<string[]>([]);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    listarServicios()
      .then((lista) => setServicios({ tipo: "ok", lista: reservables(lista) }))
      .catch((error: unknown) => {
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setServicios({ tipo: "error", mensaje: mensajeDe(error) });
      });
  }, [caducada, intento]);

  useEffect(() => {
    // Desde la ficha: el contacto ya viene elegido.
    if (contactoInicial === null) return;
    obtenerContacto(contactoInicial)
      .then((c) => setContacto({ id: c.id, nombre: nombreDe(c) }))
      .catch((error: unknown) => {
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setErrores({ contact_id: "No se pudo cargar el contacto: búscalo aquí" });
      });
  }, [contactoInicial, caducada]);

  useEffect(() => {
    const espera = setTimeout(() => setBusqueda(texto.trim()), PAUSA_BUSQUEDA_MS);
    return () => clearTimeout(espera);
  }, [texto]);

  useEffect(() => {
    if (contacto) return;
    let vigente = true;
    listarContactos(busqueda, SIN_PERDIDOS)
      .then((lista) => vigente && setResultados(lista.items))
      .catch((error: unknown) => {
        if (!vigente) return;
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setResultados([]);
      });
    return () => {
      vigente = false;
    };
  }, [busqueda, contacto, caducada]);

  // Lo que ya tiene ese día la persona elegida (ayuda para elegir hueco) y el contacto (aviso).
  useEffect(() => {
    if (!personaId || !diaValido(dia)) return setOcupadas(null);
    let vigente = true;
    listarCitas(dia, { persona: Number(personaId) })
      .then((citas) => vigente && setOcupadas(citas.filter((c) => c.status !== "cancelled")))
      .catch(() => vigente && setOcupadas(null));
    return () => {
      vigente = false;
    };
  }, [personaId, dia, recargaOcupadas]);

  useEffect(() => {
    if (!contacto || !diaValido(dia)) return setDelContacto([]);
    let vigente = true;
    listarCitas(dia, { contacto: contacto.id })
      .then((citas) => vigente && setDelContacto(citas.filter((c) => c.status !== "cancelled")))
      .catch(() => vigente && setDelContacto([]));
    return () => {
      vigente = false;
    };
  }, [contacto, dia]);

  if (estado.tipo !== "dentro") return null;
  const csrf = estado.usuario.csrf_token;
  const lista = servicios.tipo === "ok" ? servicios.lista : [];
  const servicio = lista.find((s) => String(s.id) === servicioId);
  const personasDelServicio = servicio ? servicio.staff.filter((p) => p.active) : [];
  // Al reprogramar, la propia cita no cuenta: ni ocupa a la persona ni da aviso al contacto.
  const otrasOcupadas = ocupadas && ocupadas.filter((c) => c.id !== cita?.id);
  const otrasDelContacto = delContacto.filter((c) => c.id !== cita?.id);
  // Al reprogramar se conserva la duración copiada al crearla (T16), aunque el servicio cambie.
  const duracion = cita ? cita.duration_minutes : servicio?.duration_minutes;

  // Aviso no bloqueante: otra cita del contacto que se pisa con la que se está dando.
  const inicio = Number(hora) * 60 + Number(minuto);
  const coinciden =
    duracion !== undefined
      ? otrasDelContacto.filter(
          (c) => minutosDesde(dia, c.starts_at) < inicio + duracion && inicio < minutosDesde(dia, c.ends_at),
        )
      : [];

  function quitarError(campo: Campo) {
    setErrores(({ [campo]: _anterior, ...resto }) => resto);
    setGeneral([]);
  }

  function elegirServicio(id: string) {
    setServicioId(id);
    quitarError("service_id");
    const elegido = lista.find((s) => String(s.id) === id);
    const activas = elegido ? elegido.staff.filter((p) => p.active) : [];
    // Si solo una persona lo realiza, queda elegida; si la elegida también lo hace, se mantiene.
    if (activas.length === 1) setPersonaId(String(activas[0].id));
    else if (!activas.some((p) => String(p.id) === personaId)) setPersonaId("");
  }

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setGeneral([]);
    const previos: Partial<Record<Campo, string>> = {};
    if (!contacto) previos.contact_id = "Elige el contacto";
    if (!servicio && !cita) previos.service_id = "Elige el servicio";
    if (!personaId) previos.staff_id = "Elige quién la realiza";
    if (!diaValido(dia)) previos.starts_at = "Elige el día";
    setErrores(previos);
    if (!contacto || Object.keys(previos).length) return;
    const startsAt = `${dia}T${hora.padStart(2, "0")}:${minuto}`;
    setGuardando(true);
    try {
      let guardada;
      if (cita) {
        guardada = await reprogramarCita(cita.id, { staff_id: Number(personaId), starts_at: startsAt, version: cita.version }, csrf);
      } else if (servicio) {
        guardada = await crearCita(
          { contact_id: contacto.id, service_id: servicio.id, staff_id: Number(personaId), starts_at: startsAt },
          csrf,
        );
      } else return;
      const horas = `${HORA.format(new Date(guardada.starts_at))}–${HORA.format(new Date(guardada.ends_at))}`;
      const accion = cita ? "Cita reprogramada" : "Cita creada";
      const nombreServicio = cita ? cita.service_name : servicio?.name;
      alGuardar(dia, `${accion}: ${contacto.nombre}, ${formatoDia(dia)}, ${horas} (${nombreServicio})`);
    } catch (error) {
      setGuardando(false);
      if (!(error instanceof ErrorApi)) return setGeneral(["Error inesperado"]);
      if (error.status === 401) return caducada();
      if (error.status === 422) {
        setErrores(error.campos);
        setGeneral(error.general.length || Object.keys(error.campos).length ? error.general : [error.message]);
        return;
      }
      // 409: esa persona ya tiene otra cita que se pisa, o (al reprogramar) otra persona cambió
      // la cita. Se refresca su ocupación y la agenda, que trae la versión nueva de la cita.
      if (error.status === 409) {
        setRecargaOcupadas((n) => n + 1);
        alConflicto?.();
      }
      setGeneral([error.status === 404 ? "Esta cita ya no existe" : error.message]);
    }
  }

  function errorDe(campo: Campo) {
    return (
      errores[campo] && (
        <span className="error" id={`error-${campo}`}>
          {errores[campo]}
        </span>
      )
    );
  }

  const describe = (campo: Campo) => (errores[campo] ? `error-${campo}` : undefined);

  const titulo = cita ? "Reprogramar cita" : "Nueva cita";

  return (
    <form className="formulario" onSubmit={enviar} noValidate aria-label={titulo}>
      <h3>{titulo}</h3>

      <div className="campo">
        {contacto ? (
          <>
            <span className="etiqueta">Contacto</span>
            <p className="elegido">
              <strong>{contacto.nombre}</strong>{" "}
              {!cita && (
                <button
                  type="button"
                  className="secundario"
                  onClick={() => {
                    setContacto(null);
                    quitarError("contact_id");
                  }}
                >
                  Cambiar
                </button>
              )}
            </p>
          </>
        ) : (
          <>
            <label htmlFor="cita-contacto">Contacto: busca por nombre, email o teléfono</label>
            <input
              id="cita-contacto"
              type="search"
              value={texto}
              maxLength={100}
              aria-invalid={errores.contact_id ? true : undefined}
              aria-describedby={describe("contact_id")}
              onChange={(e) => setTexto(e.target.value)}
            />
            {resultados !== null && resultados.length === 0 && (
              <p className="ayuda">No hay contactos que coincidan (los Perdidos no aparecen: reábrelos desde su ficha).</p>
            )}
            {resultados !== null && resultados.length > 0 && (
              <ul className="resultados" aria-label="Contactos encontrados">
                {resultados.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className="secundario"
                      onClick={() => {
                        setContacto({ id: c.id, nombre: nombreDe(c) });
                        quitarError("contact_id");
                      }}
                    >
                      {nombreDe(c)}
                    </button>
                    <span className="contacto__datos">
                      {[c.email, c.phone && formatoTelefono(c.phone)].filter(Boolean).join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        {errorDe("contact_id")}
      </div>

      {servicios.tipo === "cargando" && <p>Cargando los servicios…</p>}
      {servicios.tipo === "error" && (
        <>
          <p className="error" role="alert">
            No se pudieron cargar los servicios: {servicios.mensaje}
          </p>
          <button type="button" className="secundario" onClick={() => setIntento((n) => n + 1)}>
            Reintentar
          </button>
        </>
      )}
      {!cita && servicios.tipo === "ok" && lista.length === 0 && (
        <p className="aviso">No hay servicios que se puedan reservar: añade uno en «Servicios» con alguien que lo realice.</p>
      )}

      {cita ? (
        // Al reprogramar, el servicio no cambia (decisión T19): para otro, se cancela y se da otra.
        <div className="campo">
          <span className="etiqueta">Servicio</span>
          <p className="elegido">
            <strong>
              {cita.service_name} ({formatoDuracion(cita.duration_minutes)})
            </strong>
          </p>
          <p className="ayuda">Para cambiar de servicio, cancela esta cita y da otra.</p>
          {servicios.tipo === "ok" && !servicio && (
            <p className="aviso">El servicio está desactivado o nadie activo lo realiza: cancela la cita y da otra.</p>
          )}
        </div>
      ) : (
        <div className="campo">
          <label htmlFor="cita-servicio">Servicio</label>
          <select
            id="cita-servicio"
            value={servicioId}
            aria-invalid={errores.service_id ? true : undefined}
            aria-describedby={describe("service_id")}
            onChange={(e) => elegirServicio(e.target.value)}
          >
            <option value="">Elige el servicio…</option>
            {lista.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.name} ({formatoDuracion(s.duration_minutes)})
              </option>
            ))}
          </select>
          {errorDe("service_id")}
        </div>
      )}

      <div className="campo">
        <label htmlFor="cita-persona">Quién la realiza</label>
        <select
          id="cita-persona"
          value={personaId}
          disabled={!servicio}
          aria-invalid={errores.staff_id ? true : undefined}
          aria-describedby={describe("staff_id")}
          onChange={(e) => {
            setPersonaId(e.target.value);
            quitarError("staff_id");
          }}
        >
          <option value="">{servicio ? "Elige quién la realiza…" : "Elige antes el servicio"}</option>
          {personasDelServicio.map((p) => (
            <option key={p.id} value={String(p.id)}>
              {p.email} · {NOMBRE_ROL[p.role]}
            </option>
          ))}
        </select>
        {errorDe("staff_id")}
      </div>

      <div className="campo">
        <label htmlFor="cita-dia">Día</label>
        <input
          id="cita-dia"
          type="date"
          value={dia}
          aria-invalid={errores.starts_at ? true : undefined}
          aria-describedby={describe("starts_at")}
          onChange={(e) => {
            setDia(e.target.value);
            quitarError("starts_at");
          }}
        />
      </div>
      <div className="hora">
        <div className="campo">
          <label htmlFor="cita-hora">Hora</label>
          <select id="cita-hora" value={hora} onChange={(e) => {
              setHora(e.target.value);
              quitarError("starts_at");
            }}>
            {HORAS.map((h) => (
              <option key={h} value={h}>
                {h.padStart(2, "0")}
              </option>
            ))}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="cita-minutos">Minutos</label>
          <select id="cita-minutos" value={minuto} onChange={(e) => {
              setMinuto(e.target.value);
              quitarError("starts_at");
            }}>
            {MINUTOS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="ayuda">Hora de Nueva York.</p>
      {errorDe("starts_at")}

      {otrasOcupadas !== null && (
        <p className="ayuda" aria-live="polite">
          {otrasOcupadas.length
            ? `Ya tiene ese día: ${otrasOcupadas.map((c) => tramo(dia, c)).join(", ")}`
            : "No tiene otras citas ese día."}
        </p>
      )}
      {coinciden.length > 0 && (
        <p className="aviso" role="status">
          {contacto?.nombre} ya tiene otra cita a esa hora:{" "}
          {coinciden.map((c) => `${tramo(dia, c)} (${c.service_name} · ${c.staff_email})`).join("; ")}. Puedes guardar
          igualmente si es a propósito, por ejemplo dos servicios a la vez con personas distintas.
        </p>
      )}

      {general.map((mensaje) => (
        <p key={mensaje} className="error" role="alert">
          {mensaje}
        </p>
      ))}
      <div className="acciones">
        <button type="submit" disabled={guardando}>
          {guardando ? "Guardando…" : cita ? "Guardar cambios" : "Guardar cita"}
        </button>
        <button type="button" className="secundario" onClick={alCancelar} disabled={guardando}>
          {/* Al reprogramar, «Cancelar» se confundiría con cancelar la cita. */}
          {cita ? "Volver" : "Cancelar"}
        </button>
      </div>
    </form>
  );
}

// --- Asistencia (T20b) ---------------------------------------------------------------------------

/** «Realizada» y «No presentado» en una cita que ha empezado; en una ya marcada y dentro del
 * plazo, el botón para cambiarla a la otra. Sin confirmación: un error se corrige así. */
function BotonesAsistencia({
  cita,
  dia,
  alTerminar,
  alConflicto,
}: {
  cita: CitaAgenda;
  dia: string;
  alTerminar: (texto: string) => void;
  alConflicto: (texto: string) => void;
}) {
  const { estado, caducada } = useSesion();
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (estado.tipo !== "dentro") return null;
  const csrf = estado.usuario.csrf_token;

  async function marcar(destino: Asistencia) {
    setGuardando(true);
    setError(null);
    try {
      await marcarAsistencia(cita.id, { version: cita.version, status: destino }, csrf);
      alTerminar(`Asistencia: ${cita.contact_name}, ${tramo(dia, cita)}, «${NOMBRE_ESTADO_CITA[destino]}»`);
    } catch (e) {
      setGuardando(false);
      if (!(e instanceof ErrorApi)) return setError("Error inesperado");
      if (e.status === 401) return caducada();
      // Otra persona la cambió, pasó el plazo o ya no es suya: se avisa y la lista se recarga.
      if (e.status === 409) return alConflicto(e.message);
      if (e.status === 404) return alConflicto("Esta cita ya no existe");
      setError(e.message);
    }
  }

  const quien = `${cita.contact_name}, ${tramo(dia, cita)}`;
  const opciones: { destino: Asistencia; texto: string }[] =
    cita.status === "scheduled"
      ? [
          { destino: "completed", texto: "Realizada" },
          { destino: "no_show", texto: "No presentado" },
        ]
      : [cita.status === "completed" ? { destino: "no_show", texto: "Cambiar a No presentado" } : { destino: "completed", texto: "Cambiar a Realizada" }];

  return (
    <span className="cita__acciones">
      {opciones.map(({ destino, texto }) => (
        <button
          key={destino}
          type="button"
          className="secundario"
          aria-label={`${texto}: ${quien}`}
          disabled={guardando}
          onClick={() => marcar(destino)}
        >
          {texto}
        </button>
      ))}
      {error && (
        <span className="error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}

// --- Cancelar una cita (T19) ------------------------------------------------------------------

const MAX_DETALLE = 200;

/** En la propia fila: motivo de la lista (obligatorio) y un detalle corto opcional. */
function FormularioCancelar({
  cita,
  dia,
  alTerminar,
  alConflicto,
  alVolver,
}: {
  cita: CitaAgenda;
  dia: string;
  alTerminar: (texto: string) => void;
  alConflicto: (texto: string) => void;
  alVolver: () => void;
}) {
  const { estado, caducada } = useSesion();
  const [motivo, setMotivo] = useState<MotivoCancelacion | "">("");
  const [detalle, setDetalle] = useState("");
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string[]>([]);
  const [guardando, setGuardando] = useState(false);

  if (estado.tipo !== "dentro") return null;
  const csrf = estado.usuario.csrf_token;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setGeneral([]);
    if (!motivo) return setErrores({ reason: "Elige el motivo" });
    setErrores({});
    setGuardando(true);
    try {
      await cancelarCita(cita.id, { version: cita.version, reason: motivo, note: detalle.trim() || null }, csrf);
      alTerminar(`Cita cancelada: ${cita.contact_name}, ${tramo(dia, cita)} (${cita.service_name})`);
    } catch (error) {
      setGuardando(false);
      if (!(error instanceof ErrorApi)) return setGeneral(["Error inesperado"]);
      if (error.status === 401) return caducada();
      if (error.status === 409) return alConflicto(error.message);
      if (error.status === 404) return alConflicto("Esta cita ya no existe");
      if (error.status === 422) {
        setErrores(error.campos);
        return setGeneral(error.general.length || Object.keys(error.campos).length ? error.general : [error.message]);
      }
      setGeneral([error.message]);
    }
  }

  return (
    <form className="formulario cancelar" onSubmit={enviar} noValidate aria-label="Cancelar la cita">
      <p className="cancelar__pregunta">
        ¿Cancelar la cita de {cita.contact_name} ({tramo(dia, cita)})? La franja quedará libre.
      </p>
      <div className="campo">
        <label htmlFor={`motivo-${cita.id}`}>Motivo</label>
        <select
          id={`motivo-${cita.id}`}
          value={motivo}
          aria-invalid={errores.reason ? true : undefined}
          aria-describedby={errores.reason ? `error-motivo-${cita.id}` : undefined}
          onChange={(e) => {
            setMotivo(e.target.value as MotivoCancelacion | "");
            setErrores(({ reason: _anterior, ...resto }) => resto);
          }}
        >
          <option value="">Elige el motivo…</option>
          {Object.entries(NOMBRE_MOTIVO).map(([valor, nombre]) => (
            <option key={valor} value={valor}>
              {nombre}
            </option>
          ))}
        </select>
        {errores.reason && (
          <span className="error" id={`error-motivo-${cita.id}`}>
            {errores.reason}
          </span>
        )}
      </div>
      <div className="campo">
        <label htmlFor={`detalle-${cita.id}`}>Detalle (opcional)</label>
        <input
          id={`detalle-${cita.id}`}
          type="text"
          value={detalle}
          maxLength={MAX_DETALLE}
          aria-invalid={errores.note ? true : undefined}
          aria-describedby={`ayuda-detalle-${cita.id}`}
          onChange={(e) => {
            setDetalle(e.target.value);
            setErrores(({ note: _anterior, ...resto }) => resto);
          }}
        />
        <span className="ayuda" id={`ayuda-detalle-${cita.id}`}>
          Una línea, sin tildes. No escribas datos clínicos (síntomas, diagnósticos ni tratamientos).
        </span>
        {errores.note && <span className="error">{errores.note}</span>}
      </div>
      {general.map((mensaje) => (
        <p key={mensaje} className="error" role="alert">
          {mensaje}
        </p>
      ))}
      <div className="acciones">
        <button type="submit" disabled={guardando}>
          {guardando ? "Cancelando…" : "Confirmar cancelación"}
        </button>
        <button type="button" className="secundario" onClick={alVolver} disabled={guardando}>
          Volver
        </button>
      </div>
    </form>
  );
}
