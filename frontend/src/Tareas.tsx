// Lo común de las tareas de seguimiento (T25), en la ficha (SeguimientosContacto) y en el panel
// (Pendientes): cada fila con «Hecha», «Reabrir» y «Editar», y el formulario de crear y editar.
//
// Lo que decide es la API: al profesional solo le llegan las suyas y editar le da 403. Aquí solo se
// le quita el botón. Si otra persona cambió la tarea (409), se avisa y la lista se vuelve a pedir.

import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";

import {
  completarTarea,
  editarTarea,
  ErrorApi,
  listarAsignables,
  reabrirTarea,
  type NuevaTarea,
  type Responsable,
  type TareaSeguimiento,
} from "./api";
import { formatoDia, hoyEnLaClinica } from "./Agenda";
import { AVISO_NOTA, AVISO_TILDES, formatoFecha, tieneTildes } from "./Contactos";
import { useSesion } from "./sesion";

// El contador de la barra se vuelve a pedir al cambiar de página y al oír este aviso.
const TAREAS_CAMBIADAS = "tareas-cambiadas";

export function avisarTareasCambiadas() {
  window.dispatchEvent(new Event(TAREAS_CAMBIADAS));
}

export function alCambiarTareas(oyente: () => void): () => void {
  window.addEventListener(TAREAS_CAMBIADAS, oyente);
  return () => window.removeEventListener(TAREAS_CAMBIADAS, oyente);
}

export type Aviso = { tipo: "exito" | "conflicto"; texto: string };

export function MensajeAviso({ aviso }: { aviso: Aviso | null }) {
  if (!aviso) return null;
  return aviso.tipo === "exito" ? (
    <p className="exito" role="status">
      {aviso.texto}
    </p>
  ) : (
    <p className="aviso" role="alert">
      {aviso.texto}
    </p>
  );
}

export function FilaTarea({
  tarea,
  hoy,
  conContacto = false,
  alCambiar,
}: {
  tarea: TareaSeguimiento;
  hoy: string;
  /** En el panel hay que decir de quién es; en la ficha ya se sabe. */
  conContacto?: boolean;
  /** Tras cualquier cambio, o tras un conflicto: quien lista avisa y vuelve a pedir la lista. */
  alCambiar: (aviso: Aviso) => void;
}) {
  const { estado: sesion, caducada } = useSesion();
  const [editando, setEditando] = useState(false);
  const [ocupada, setOcupada] = useState(false);
  if (sesion.tipo !== "dentro") return null;
  const csrf = sesion.usuario.csrf_token;
  const profesional = sesion.usuario.role === "professional";
  const hecha = tarea.completed_at !== null;
  const vencida = !hecha && tarea.due_on < hoy;

  async function ejecutar(accion: () => Promise<unknown>, exito: string) {
    setOcupada(true);
    try {
      await accion();
      alCambiar({ tipo: "exito", texto: exito });
    } catch (e) {
      setOcupada(false);
      if (e instanceof ErrorApi && e.status === 401) return caducada();
      alCambiar({ tipo: "conflicto", texto: e instanceof ErrorApi ? e.message : "Error inesperado" });
    }
  }

  if (editando) {
    return (
      <li className="cita">
        <FormularioTarea
          contacto={tarea.contact_id}
          inicial={tarea}
          textoGuardar="Guardar cambios"
          guardar={(datos, token) => editarTarea(tarea.id, { ...datos, version: tarea.version }, token)}
          alCancelar={() => setEditando(false)}
          alGuardar={() => alCambiar({ tipo: "exito", texto: "Tarea guardada" })}
          alConflicto={(texto) => {
            setEditando(false);
            alCambiar({ tipo: "conflicto", texto });
          }}
        />
      </li>
    );
  }

  return (
    <li className={hecha ? "cita tarea--hecha" : "cita"}>
      <span className="cita__hora">
        {formatoDia(tarea.due_on)}
        {vencida && <span className="etiqueta etiqueta--vencida">Vencida</span>}
      </span>
      {conContacto && (
        <span className="cita__contacto">
          <Link to={`/contactos/${tarea.contact_id}`}>{tarea.contact_name}</Link>
          {tarea.contact_status === "lost" && <span className="etiqueta">Perdido</span>}
        </span>
      )}
      <span className="tarea__texto">{tarea.description}</span>
      {!profesional && <span className="cita__meta">Responsable: {tarea.assigned_to_email}</span>}
      {tarea.completed_at !== null && (
        <span className="cita__meta">
          Hecha el {formatoFecha(tarea.completed_at)} · {tarea.completed_by_email ?? "cuenta ya no disponible"}
        </span>
      )}
      <span className="cita__acciones tarea__acciones">
        {hecha ? (
          <button
            type="button"
            className="secundario"
            disabled={ocupada}
            onClick={() => ejecutar(() => reabrirTarea(tarea.id, tarea.version, csrf), "Tarea reabierta")}
          >
            Reabrir
          </button>
        ) : (
          <>
            <button
              type="button"
              disabled={ocupada}
              onClick={() => ejecutar(() => completarTarea(tarea.id, tarea.version, csrf), "Tarea marcada como hecha")}
            >
              Hecha
            </button>
            {!profesional && (
              <button type="button" className="secundario" disabled={ocupada} onClick={() => setEditando(true)}>
                Editar
              </button>
            )}
          </>
        )}
      </span>
    </li>
  );
}

type Asignables = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; lista: Responsable[] };
type CampoTarea = "description" | "due_on" | "assigned_to_id";

export function FormularioTarea({
  contacto,
  inicial,
  textoGuardar,
  guardar,
  alCancelar,
  alGuardar,
  alConflicto,
}: {
  contacto: number;
  inicial?: TareaSeguimiento;
  textoGuardar: string;
  guardar: (datos: NuevaTarea, csrf: string) => Promise<unknown>;
  alCancelar: () => void;
  alGuardar: () => void;
  /** Ante un 409: otra persona la cambió. Sin esta función, el mensaje sale en el formulario. */
  alConflicto?: (texto: string) => void;
}) {
  const { estado: sesion, caducada } = useSesion();
  const [asignables, setAsignables] = useState<Asignables>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);
  const [descripcion, setDescripcion] = useState(inicial?.description ?? "");
  const [fecha, setFecha] = useState(inicial?.due_on ?? "");
  const [responsable, setResponsable] = useState(inicial ? String(inicial.assigned_to_id) : "");
  const [errores, setErrores] = useState<Partial<Record<CampoTarea, string>>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    let vigente = true;
    setAsignables({ tipo: "cargando" });
    listarAsignables(contacto)
      .then((lista) => vigente && setAsignables({ tipo: "ok", lista }))
      .catch((e: unknown) => {
        if (!vigente) return;
        if (e instanceof ErrorApi && e.status === 401) return caducada();
        setAsignables({ tipo: "error", mensaje: e instanceof ErrorApi ? e.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [contacto, intento, caducada]);

  if (sesion.tipo !== "dentro") return null;
  const csrf = sesion.usuario.csrf_token;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setGeneral(null);
    // Lo que se puede decir sin esperar a la API, que repite estas reglas.
    const previos: Partial<Record<CampoTarea, string>> = {};
    if (tieneTildes(descripcion)) previos.description = AVISO_TILDES;
    if (!fecha) previos.due_on = "Indica la fecha prevista";
    if (!responsable) previos.assigned_to_id = "Elige quién se encarga";
    setErrores(previos);
    if (Object.keys(previos).length) return;
    setGuardando(true);
    try {
      await guardar({ description: descripcion, due_on: fecha, assigned_to_id: Number(responsable) }, csrf);
      alGuardar();
    } catch (e) {
      setGuardando(false);
      if (!(e instanceof ErrorApi)) return setGeneral("Error inesperado");
      if (e.status === 401) return caducada();
      if (e.status === 409 && alConflicto) return alConflicto(e.message);
      if (e.status === 422) {
        setErrores(e.campos);
        if (!Object.keys(e.campos).length) setGeneral(e.general[0] ?? e.message);
        return;
      }
      setGeneral(e.message);
    }
  }

  if (asignables.tipo === "cargando") return <p>Cargando el formulario…</p>;
  if (asignables.tipo === "error") {
    return (
      <>
        <p className="error" role="alert">
          No se pudo cargar quién puede encargarse: {asignables.mensaje}
        </p>
        <div className="acciones">
          <button type="button" className="secundario" onClick={() => setIntento((n) => n + 1)}>
            Reintentar
          </button>
          <button type="button" className="secundario" onClick={alCancelar}>
            Cancelar
          </button>
        </div>
      </>
    );
  }

  // Si quien la lleva ya no se podría asignar, se añade: guardar sin tocarlo no debe cambiarlo.
  const personas =
    inicial && !asignables.lista.some((p) => p.id === inicial.assigned_to_id)
      ? [...asignables.lista, { id: inicial.assigned_to_id, email: `${inicial.assigned_to_email} (ya no disponible)` }]
      : asignables.lista;
  const errorDescripcion = errores.description ?? (tieneTildes(descripcion) ? AVISO_TILDES : undefined);
  return (
    <form onSubmit={enviar} noValidate>
      <div className="campo">
        <label htmlFor="tarea-description">Qué hay que hacer</label>
        <input
          id="tarea-description"
          value={descripcion}
          maxLength={200}
          aria-invalid={errorDescripcion ? true : undefined}
          aria-describedby={errorDescripcion ? "error-tarea-description" : undefined}
          onChange={(e) => {
            setDescripcion(e.target.value);
            setErrores(({ description: _anterior, ...resto }) => resto);
          }}
        />
        {errorDescripcion && (
          <span className="error" id="error-tarea-description">
            {errorDescripcion}
          </span>
        )}
        <p className="ayuda">{AVISO_NOTA}</p>
      </div>
      <div className="campo">
        <label htmlFor="tarea-due_on">Fecha prevista</label>
        <input
          id="tarea-due_on"
          type="date"
          value={fecha}
          min={hoyEnLaClinica()}
          aria-invalid={errores.due_on ? true : undefined}
          aria-describedby={errores.due_on ? "error-tarea-due_on" : undefined}
          onChange={(e) => {
            setFecha(e.target.value);
            setErrores(({ due_on: _anterior, ...resto }) => resto);
          }}
        />
        {errores.due_on && (
          <span className="error" id="error-tarea-due_on">
            {errores.due_on}
          </span>
        )}
      </div>
      <div className="campo">
        <label htmlFor="tarea-assigned_to_id">Quién se encarga</label>
        <select
          id="tarea-assigned_to_id"
          value={responsable}
          aria-invalid={errores.assigned_to_id ? true : undefined}
          aria-describedby={errores.assigned_to_id ? "error-tarea-assigned_to_id" : undefined}
          onChange={(e) => {
            setResponsable(e.target.value);
            setErrores(({ assigned_to_id: _anterior, ...resto }) => resto);
          }}
        >
          <option value="">Elige una persona…</option>
          {personas.map((persona) => (
            <option key={persona.id} value={persona.id}>
              {persona.email}
            </option>
          ))}
        </select>
        {errores.assigned_to_id && (
          <span className="error" id="error-tarea-assigned_to_id">
            {errores.assigned_to_id}
          </span>
        )}
        <p className="ayuda">Un profesional solo aparece si este contacto tiene alguna cita con él.</p>
      </div>
      {general && (
        <p className="error" role="alert">
          {general}
        </p>
      )}
      <div className="acciones">
        <button type="submit" disabled={guardando}>
          {textoGuardar}
        </button>
        <button type="button" className="secundario" disabled={guardando} onClick={alCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
