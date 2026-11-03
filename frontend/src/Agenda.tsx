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

import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import {
  crearCita,
  ErrorApi,
  listarCitas,
  listarContactos,
  listarPersonasAsignables,
  listarServicios,
  obtenerContacto,
  type CitaAgenda,
  type Contacto,
  type EstadoCita,
  type FiltrosContactos,
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

// --- Agenda ---------------------------------------------------------------------------

type EstadoLista = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; citas: CitaAgenda[] };

function mensajeDe(error: unknown): string {
  return error instanceof ErrorApi ? error.message : "Error inesperado";
}

export default function Agenda() {
  const { caducada } = useSesion();
  const [parametros, setParametros] = useSearchParams();
  const fecha = parametros.get("fecha");
  const dia = diaValido(fecha) ? fecha : hoyEnLaClinica();
  const persona = parametros.get("persona") ?? ""; // "": todas
  const nueva = parametros.get("nueva") === "1";
  const contactoInicial = Number(parametros.get("contacto")) || null;
  const [lista, setLista] = useState<EstadoLista>({ tipo: "cargando" });
  const [recarga, setRecarga] = useState(0);
  const [personas, setPersonas] = useState<PersonaServicio[]>([]);
  const [creada, setCreada] = useState<string | null>(null);

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
    listarCitas(dia, persona ? { persona: Number(persona) } : {})
      .then((citas) => vigente && setLista({ tipo: "ok", citas }))
      .catch((error: unknown) => {
        if (!vigente) return;
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setLista({ tipo: "error", mensaje: mensajeDe(error) });
      });
    return () => {
      vigente = false;
    };
  }, [dia, persona, recarga, caducada]);

  useEffect(() => {
    // Para el filtro: las cuentas internas activas (las que pueden realizar citas).
    listarPersonasAsignables()
      .then(setPersonas)
      .catch(() => setPersonas([])); // sin la lista, el filtro solo ofrece «Todas»
  }, []);

  function alGuardar(diaDeLaCita: string, texto: string) {
    setCreada(texto);
    cambiar({ nueva: null, contacto: null, fecha: diaDeLaCita });
    setRecarga((n) => n + 1);
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-agenda">
      <h2 id="titulo-agenda">Agenda</h2>

      {creada && (
        <p className="exito" role="status">
          {creada}
        </p>
      )}

      {nueva ? (
        <FormularioCita
          diaInicial={dia}
          contactoInicial={contactoInicial}
          alGuardar={alGuardar}
          alCancelar={() => cambiar({ nueva: null, contacto: null })}
        />
      ) : (
        <button
          type="button"
          onClick={() => {
            setCreada(null);
            cambiar({ nueva: "1" });
          }}
        >
          Nueva cita
        </button>
      )}

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
      </div>

      <h3 className="dia__titulo">
        {formatoDia(dia)} <span className="ayuda">(hora de Nueva York)</span>
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
        <p>{persona ? "Esta persona no tiene citas este día." : "No hay citas este día."}</p>
      )}
      {lista.tipo === "ok" && lista.citas.length > 0 && (
        <ul className="citas">
          {lista.citas.map((c) => (
            <li key={c.id} className={c.status === "cancelled" ? "cita cita--cancelada" : "cita"}>
              <span className="cita__hora">{tramo(dia, c)}</span>
              <Link className="cita__contacto" to={`/contactos/${c.contact_id}`}>
                {c.contact_name}
              </Link>
              <span className="cita__meta">
                {c.service_name} · {c.staff_email}
                {c.status !== "scheduled" && ` · ${NOMBRE_ESTADO_CITA[c.status]}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
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

function FormularioCita({
  diaInicial,
  contactoInicial,
  alGuardar,
  alCancelar,
}: {
  diaInicial: string;
  contactoInicial: number | null;
  alGuardar: (dia: string, texto: string) => void;
  alCancelar: () => void;
}) {
  const { estado, caducada } = useSesion();
  const [contacto, setContacto] = useState<Elegido | null>(null);
  const [texto, setTexto] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [resultados, setResultados] = useState<Contacto[] | null>(null);
  const [servicios, setServicios] = useState<EstadoServicios>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);
  const [servicioId, setServicioId] = useState("");
  const [personaId, setPersonaId] = useState("");
  const [dia, setDia] = useState(diaInicial);
  const [hora, setHora] = useState("9");
  const [minuto, setMinuto] = useState("00");
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

  // Aviso no bloqueante: otra cita del contacto que se pisa con la que se está dando.
  const inicio = Number(hora) * 60 + Number(minuto);
  const coinciden = servicio
    ? delContacto.filter(
        (c) => minutosDesde(dia, c.starts_at) < inicio + servicio.duration_minutes && inicio < minutosDesde(dia, c.ends_at),
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
    if (!servicio) previos.service_id = "Elige el servicio";
    if (!personaId) previos.staff_id = "Elige quién la realiza";
    if (!diaValido(dia)) previos.starts_at = "Elige el día";
    setErrores(previos);
    if (!contacto || !servicio || Object.keys(previos).length) return;
    setGuardando(true);
    try {
      const cita = await crearCita(
        {
          contact_id: contacto.id,
          service_id: servicio.id,
          staff_id: Number(personaId),
          starts_at: `${dia}T${hora.padStart(2, "0")}:${minuto}`,
        },
        csrf,
      );
      const horas = `${HORA.format(new Date(cita.starts_at))}–${HORA.format(new Date(cita.ends_at))}`;
      alGuardar(dia, `Cita creada: ${contacto.nombre}, ${formatoDia(dia)}, ${horas} (${servicio.name})`);
    } catch (error) {
      setGuardando(false);
      if (!(error instanceof ErrorApi)) return setGeneral(["Error inesperado"]);
      if (error.status === 401) return caducada();
      if (error.status === 422) {
        setErrores(error.campos);
        setGeneral(error.general.length || Object.keys(error.campos).length ? error.general : [error.message]);
        return;
      }
      // 409: esa persona ya tiene otra cita que se pisa. Se refresca su ocupación para verla.
      if (error.status === 409) setRecargaOcupadas((n) => n + 1);
      setGeneral([error.message]);
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

  return (
    <form className="formulario" onSubmit={enviar} noValidate aria-label="Nueva cita">
      <h3>Nueva cita</h3>

      <div className="campo">
        {contacto ? (
          <>
            <span className="etiqueta">Contacto</span>
            <p className="elegido">
              <strong>{contacto.nombre}</strong>{" "}
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
      {servicios.tipo === "ok" && lista.length === 0 && (
        <p className="aviso">No hay servicios que se puedan reservar: añade uno en «Servicios» con alguien que lo realice.</p>
      )}

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

      {ocupadas !== null && (
        <p className="ayuda" aria-live="polite">
          {ocupadas.length
            ? `Ya tiene ese día: ${ocupadas.map((c) => tramo(dia, c)).join(", ")}`
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
          {guardando ? "Guardando…" : "Guardar cita"}
        </button>
        <button type="button" className="secundario" onClick={alCancelar} disabled={guardando}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
