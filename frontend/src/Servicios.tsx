// Servicios de la clínica (T15): administración y recepción los añaden uno a uno, con nombre,
// duración y quién los realiza; los editan, desactivan y reactivan. Nunca se borran. El
// profesional ve solo los suyos (MisServicios). Quién puede hacer qué lo decide la API.
//
// Bloqueo optimista, como en los contactos (T13): al guardar se envía la versión leída. Si otra
// persona guardó antes (409), se recarga la lista y se avisa en vez de pisar su cambio.

import { useEffect, useState, type FormEvent } from "react";

import {
  actualizarServicio,
  crearServicio,
  ErrorApi,
  listarPersonasAsignables,
  listarServicios,
  type DatosServicio,
  type PersonaServicio,
  type Servicio,
} from "./api";
import { AVISO_TILDES, tieneTildes } from "./Contactos";
import { NOMBRE_ROL, useSesion } from "./sesion";

export const AVISO_OTRA_VERSION_SERVICIO =
  "Otra persona ha cambiado este servicio. Se muestran los datos actuales; si hace falta, vuelve a aplicar tu cambio.";

// El mismo texto que da la API (422).
export const SIN_PERSONAS = "Un servicio activo necesita al menos una persona que lo realice";

/** 45 → «45 min»; 60 → «1 h»; 90 → «1 h 30 min». */
export function formatoDuracion(minutos: number): string {
  const horas = Math.floor(minutos / 60);
  const resto = minutos % 60;
  if (!horas) return `${resto} min`;
  return resto ? `${horas} h ${resto} min` : `${horas} h`;
}

/** «ana@clinica.com», con la marca si la cuenta se desactivó después de asignarla. */
function nombrePersona(persona: PersonaServicio): string {
  return persona.active ? persona.email : `${persona.email} (desactivada)`;
}

type EstadoLista = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; servicios: Servicio[] };
type EstadoPersonas = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; lista: PersonaServicio[] };
type Aviso = { tipo: "exito" | "conflicto" | "error"; texto: string };
/** null: formulario cerrado; servicio null: alta. */
type Formulario = { servicio: Servicio | null } | null;

function mensajeDe(error: unknown): string {
  return error instanceof ErrorApi ? error.message : "Error inesperado";
}

/** Para administración y recepción: lista completa y gestión. */
export default function Servicios() {
  const { estado, caducada } = useSesion();
  const [lista, setLista] = useState<EstadoLista>({ tipo: "cargando" });
  const [recarga, setRecarga] = useState(0);
  const [formulario, setFormulario] = useState<Formulario>(null);
  const [personas, setPersonas] = useState<EstadoPersonas>({ tipo: "cargando" });
  const [intentoPersonas, setIntentoPersonas] = useState(0);
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const [cambiando, setCambiando] = useState<number | null>(null); // id del que se activa o desactiva

  useEffect(() => {
    let vigente = true;
    listarServicios()
      .then((servicios) => vigente && setLista({ tipo: "ok", servicios }))
      .catch((error: unknown) => {
        if (!vigente) return;
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setLista({ tipo: "error", mensaje: mensajeDe(error) });
      });
    return () => {
      vigente = false;
    };
  }, [recarga, caducada]);

  // Las personas asignables se piden al abrir el formulario: así están al día.
  const abierto = formulario !== null;
  useEffect(() => {
    if (!abierto) return;
    let vigente = true;
    setPersonas({ tipo: "cargando" });
    listarPersonasAsignables()
      .then((lista) => vigente && setPersonas({ tipo: "ok", lista }))
      .catch((error: unknown) => {
        if (!vigente) return;
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setPersonas({ tipo: "error", mensaje: mensajeDe(error) });
      });
    return () => {
      vigente = false;
    };
  }, [abierto, intentoPersonas, caducada]);

  if (estado.tipo !== "dentro") return null;
  const csrf = estado.usuario.csrf_token;

  function abrir(servicio: Servicio | null) {
    setAviso(null);
    setFormulario({ servicio });
  }

  function alGuardar(servicio: Servicio, nuevo: boolean) {
    setFormulario(null);
    setAviso({ tipo: "exito", texto: `${nuevo ? "Servicio añadido" : "Servicio guardado"}: ${servicio.name}` });
    setRecarga((n) => n + 1);
  }

  /** Tras un 409: ¿cambió la versión de ese servicio? Si es así, se muestra la actual con un aviso. */
  async function otraVersion(servicio: Servicio): Promise<boolean> {
    try {
      const actuales = await listarServicios();
      const actual = actuales.find((s) => s.id === servicio.id);
      if (actual && actual.version === servicio.version) return false; // era un nombre repetido
      setLista({ tipo: "ok", servicios: actuales });
      setFormulario(null);
      setAviso({ tipo: "conflicto", texto: actual ? AVISO_OTRA_VERSION_SERVICIO : "Este servicio ya no existe." });
      return true;
    } catch {
      return false;
    }
  }

  async function cambiarActivo(servicio: Servicio) {
    setAviso(null);
    setCambiando(servicio.id);
    try {
      const guardado = await actualizarServicio(
        servicio.id,
        {
          name: servicio.name,
          duration_minutes: servicio.duration_minutes,
          staff_ids: servicio.staff.map((p) => p.id),
          active: !servicio.active,
          version: servicio.version,
        },
        csrf,
      );
      setAviso({ tipo: "exito", texto: `${guardado.active ? "Servicio reactivado" : "Servicio desactivado"}: ${guardado.name}` });
      setRecarga((n) => n + 1);
    } catch (error) {
      if (error instanceof ErrorApi && error.status === 401) return caducada();
      if (error instanceof ErrorApi && error.status === 409 && (await otraVersion(servicio))) return;
      // 422 al reactivar sin nadie asignado: el mensaje de la API lo explica.
      const texto = error instanceof ErrorApi && error.campos.staff_ids ? `${error.campos.staff_ids}. Edítalo para asignar a alguien.` : mensajeDe(error);
      setAviso({ tipo: "error", texto });
    } finally {
      setCambiando(null);
    }
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-servicios">
      <h2 id="titulo-servicios">Servicios</h2>

      {aviso && (
        <p className={aviso.tipo === "exito" ? "exito" : aviso.tipo === "conflicto" ? "aviso" : "error"} role={aviso.tipo === "exito" ? "status" : "alert"}>
          {aviso.texto}
        </p>
      )}

      {formulario === null && (
        <button type="button" onClick={() => abrir(null)}>
          Añadir servicio
        </button>
      )}
      {formulario !== null && personas.tipo === "cargando" && <p>Cargando las personas que pueden realizarlo…</p>}
      {formulario !== null && personas.tipo === "error" && (
        <>
          <p className="error" role="alert">
            {personas.mensaje}
          </p>
          <div className="acciones">
            <button type="button" className="secundario" onClick={() => setIntentoPersonas((n) => n + 1)}>
              Reintentar
            </button>
            <button type="button" className="secundario" onClick={() => setFormulario(null)}>
              Cancelar
            </button>
          </div>
        </>
      )}
      {formulario !== null && personas.tipo === "ok" && (
        <FormularioServicio
          // Una clave por servicio: al pasar de uno a otro, el formulario empieza de cero.
          key={formulario.servicio?.id ?? "nuevo"}
          servicio={formulario.servicio}
          personas={personas.lista}
          guardar={(datos) => {
            const { servicio } = formulario;
            return servicio
              ? actualizarServicio(servicio.id, { ...datos, active: servicio.active, version: servicio.version }, csrf)
              : crearServicio(datos, csrf);
          }}
          alGuardar={(servicio) => alGuardar(servicio, formulario.servicio === null)}
          alCancelar={() => setFormulario(null)}
          alConflicto={formulario.servicio ? () => otraVersion(formulario.servicio as Servicio) : undefined}
        />
      )}

      {lista.tipo === "cargando" && <p>Cargando servicios…</p>}
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
      {lista.tipo === "ok" && lista.servicios.length === 0 && (
        <p>Todavía no hay servicios. Añade el primero con «Añadir servicio».</p>
      )}
      {lista.tipo === "ok" && lista.servicios.length > 0 && (
        <ul className="contactos">
          {lista.servicios.map((s) => (
            <li key={s.id} className="contacto">
              <span className="contacto__nombre">{s.name}</span>
              <span className="contacto__datos">
                {formatoDuracion(s.duration_minutes)} · {s.active ? "Activo" : "Desactivado"}
              </span>
              <span className="contacto__meta">
                {s.staff.length ? `Lo realizan: ${s.staff.map(nombrePersona).join(", ")}` : "Sin nadie asignado"}
              </span>
              {s.active && !s.staff.some((p) => p.active) && (
                <span className="aviso-campo">Nadie disponible lo realiza: no se podrán dar citas de este servicio.</span>
              )}
              <div className="acciones">
                <button type="button" className="secundario" onClick={() => abrir(s)} disabled={cambiando !== null} aria-label={`Editar ${s.name}`}>
                  Editar
                </button>
                <button
                  type="button"
                  className="secundario"
                  onClick={() => cambiarActivo(s)}
                  disabled={cambiando !== null}
                  aria-label={`${s.active ? "Desactivar" : "Reactivar"} ${s.name}`}
                >
                  {cambiando === s.id ? "Guardando…" : s.active ? "Desactivar" : "Reactivar"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Errores = Partial<Record<"name" | "duration_minutes" | "staff_ids", string>>;

/** Alta (servicio null) y edición: nombre, duración y quién lo realiza. */
export function FormularioServicio({
  servicio,
  personas,
  guardar,
  alGuardar,
  alCancelar,
  alConflicto,
}: {
  servicio: Servicio | null;
  personas: PersonaServicio[];
  guardar: (datos: DatosServicio) => Promise<Servicio>;
  alGuardar: (servicio: Servicio) => void;
  alCancelar: () => void;
  /** Ante un 409, true si quien usa el formulario lo ha resuelto (otra versión). */
  alConflicto?: () => Promise<boolean>;
}) {
  const { caducada } = useSesion();
  const [nombre, setNombre] = useState(servicio?.name ?? "");
  const [duracion, setDuracion] = useState(servicio ? String(servicio.duration_minutes) : "");
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set(servicio?.staff.map((p) => p.id) ?? []));
  const [errores, setErrores] = useState<Errores>({});
  const [general, setGeneral] = useState<string[]>([]);
  const [guardando, setGuardando] = useState(false);
  const titulo = servicio ? `Editar ${servicio.name}` : "Añadir servicio";

  // Quien ya estaba asignado y ya no puede asignarse (cuenta desactivada) sigue en la lista para
  // que guardar sin tocarlo no lo quite; se puede desmarcar.
  const opciones = [
    ...personas,
    ...(servicio?.staff.filter((p) => !personas.some((o) => o.id === p.id)) ?? []).map((p) => ({ ...p, active: false })),
  ];

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErrores({});
    setGeneral([]);
    const minutos = Number(duracion);
    const previos: Errores = {};
    if (tieneTildes(nombre)) previos.name = AVISO_TILDES;
    // Se avisa aquí para que salga junto con los demás errores; lo demás (múltiplos de 5, máximo)
    // lo comprueba la API, que repite también esto.
    if (!duracion.trim() || !Number.isInteger(minutos)) previos.duration_minutes = "Indica la duración en minutos";
    if ((servicio?.active ?? true) && marcadas.size === 0) previos.staff_ids = SIN_PERSONAS;
    if (Object.keys(previos).length) return setErrores(previos);
    setGuardando(true);
    try {
      alGuardar(await guardar({ name: nombre, duration_minutes: minutos, staff_ids: [...marcadas].sort((a, b) => a - b) }));
    } catch (error) {
      setGuardando(false);
      if (!(error instanceof ErrorApi)) return setGeneral(["Error inesperado"]);
      if (error.status === 401) return caducada();
      if (error.status === 422) {
        setErrores(error.campos);
        setGeneral(error.general.length || Object.keys(error.campos).length ? error.general : [error.message]);
        return;
      }
      if (error.status === 409 && alConflicto && (await alConflicto())) return;
      setGeneral([error.message]); // nombre repetido, 403, 503, sin conexión…
    }
  }

  function alternar(id: number) {
    const nuevas = new Set(marcadas);
    if (nuevas.has(id)) nuevas.delete(id);
    else nuevas.add(id);
    setMarcadas(nuevas);
    setErrores(({ staff_ids: _anterior, ...resto }) => resto);
  }

  const errorNombre = errores.name ?? (tieneTildes(nombre) ? AVISO_TILDES : undefined);

  return (
    <form className="formulario" onSubmit={enviar} noValidate aria-label={titulo}>
      <h3>{titulo}</h3>
      <div className="campo">
        <label htmlFor="servicio-name">Nombre</label>
        <input
          id="servicio-name"
          type="text"
          autoComplete="off"
          value={nombre}
          maxLength={120}
          aria-invalid={errorNombre ? true : undefined}
          aria-describedby={errorNombre ? "error-servicio-name" : undefined}
          onChange={(e) => {
            setNombre(e.target.value);
            setErrores(({ name: _anterior, ...resto }) => resto);
          }}
        />
        {errorNombre && (
          <span className="error" id="error-servicio-name">
            {errorNombre}
          </span>
        )}
      </div>
      <div className="campo">
        <label htmlFor="servicio-duration_minutes">Duración (minutos)</label>
        <input
          id="servicio-duration_minutes"
          type="number"
          inputMode="numeric"
          min={5}
          max={240}
          step={5}
          value={duracion}
          aria-invalid={errores.duration_minutes ? true : undefined}
          aria-describedby={errores.duration_minutes ? "ayuda-duracion error-servicio-duration_minutes" : "ayuda-duracion"}
          onChange={(e) => {
            setDuracion(e.target.value);
            setErrores(({ duration_minutes: _anterior, ...resto }) => resto);
          }}
        />
        <span className="ayuda" id="ayuda-duracion">
          Múltiplos de 5, hasta 240 (4 horas).
        </span>
        {errores.duration_minutes && (
          <span className="error" id="error-servicio-duration_minutes">
            {errores.duration_minutes}
          </span>
        )}
      </div>
      <fieldset className="personas" aria-describedby={errores.staff_ids ? "error-servicio-staff_ids" : undefined}>
        <legend>Quién lo realiza</legend>
        {opciones.map((p) => (
          <label key={p.id} className="casilla">
            <input type="checkbox" checked={marcadas.has(p.id)} onChange={() => alternar(p.id)} />
            {p.active ? `${p.email} · ${NOMBRE_ROL[p.role]}` : `${p.email} (ya no disponible)`}
          </label>
        ))}
        {errores.staff_ids && (
          <span className="error" id="error-servicio-staff_ids">
            {errores.staff_ids}
          </span>
        )}
      </fieldset>
      {general.map((mensaje) => (
        <p key={mensaje} className="error" role="alert">
          {mensaje}
        </p>
      ))}
      <div className="acciones">
        <button type="submit" disabled={guardando}>
          {guardando ? "Guardando…" : servicio ? "Guardar cambios" : "Guardar servicio"}
        </button>
        <button type="button" className="secundario" onClick={alCancelar} disabled={guardando}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

/** Para el profesional: los servicios activos que tiene asignados, solo para consultar. */
export function MisServicios() {
  const { caducada } = useSesion();
  const [lista, setLista] = useState<EstadoLista>({ tipo: "cargando" });
  const [recarga, setRecarga] = useState(0);

  useEffect(() => {
    let vigente = true;
    listarServicios()
      .then((servicios) => vigente && setLista({ tipo: "ok", servicios }))
      .catch((error: unknown) => {
        if (!vigente) return;
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setLista({ tipo: "error", mensaje: mensajeDe(error) });
      });
    return () => {
      vigente = false;
    };
  }, [recarga, caducada]);

  return (
    <section className="tarjeta" aria-labelledby="titulo-mis-servicios">
      <h2 id="titulo-mis-servicios">Mis servicios</h2>
      {lista.tipo === "cargando" && <p>Cargando servicios…</p>}
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
      {lista.tipo === "ok" && lista.servicios.length === 0 && (
        <p>Todavía no tienes servicios asignados. Pídelo en recepción o administración.</p>
      )}
      {lista.tipo === "ok" && lista.servicios.length > 0 && (
        <ul className="contactos">
          {lista.servicios.map((s) => (
            <li key={s.id} className="contacto">
              <span className="contacto__nombre">{s.name}</span>
              <span className="contacto__datos">{formatoDuracion(s.duration_minutes)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
