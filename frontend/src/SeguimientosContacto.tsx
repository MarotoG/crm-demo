// Las tareas de seguimiento de un contacto en su ficha (T24): las más cercanas primero y, para
// administración y recepción, «Nueva tarea». El profesional solo ve las suyas (lo decide la API) y
// no crea tareas. Marcarlas como hechas llega con el panel de pendientes (T25).

import { useEffect, useState, type FormEvent } from "react";

import { crearTarea, ErrorApi, listarAsignables, listarTareas, type Responsable, type TareaSeguimiento } from "./api";
import { formatoDia, hoyEnLaClinica } from "./Agenda";
import { AVISO_NOTA, AVISO_TILDES, tieneTildes } from "./Contactos";
import { useSesion } from "./sesion";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; total: number; tareas: TareaSeguimiento[] };

export default function SeguimientosContacto({ contacto }: { contacto: number }) {
  const { estado: sesion, caducada } = useSesion();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);
  const [creando, setCreando] = useState(false);
  const [creada, setCreada] = useState(false);

  useEffect(() => {
    let vigente = true;
    setEstado({ tipo: "cargando" });
    listarTareas(contacto)
      .then(({ total, items }) => vigente && setEstado({ tipo: "ok", total, tareas: items }))
      .catch((e: unknown) => {
        if (!vigente) return;
        if (e instanceof ErrorApi && e.status === 401) return caducada();
        setEstado({ tipo: "error", mensaje: e instanceof ErrorApi ? e.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [contacto, intento, caducada]);

  if (sesion.tipo !== "dentro") return null;
  const profesional = sesion.usuario.role === "professional";

  return (
    <section className="seccion-ficha seguimientos" aria-labelledby="titulo-seguimientos">
      <h3 id="titulo-seguimientos">{profesional ? "Tus seguimientos" : "Seguimientos"}</h3>
      {creada && (
        <p className="exito" role="status">
          Tarea creada
        </p>
      )}
      {estado.tipo === "cargando" && <p>Cargando las tareas…</p>}
      {estado.tipo === "error" && (
        <>
          <p className="error" role="alert">
            {estado.mensaje}
          </p>
          <button type="button" className="secundario" onClick={() => setIntento((n) => n + 1)}>
            Reintentar
          </button>
        </>
      )}
      {estado.tipo === "ok" && estado.tareas.length === 0 && (
        <p className="ayuda">{profesional ? "No tienes tareas de este contacto." : "Todavía no tiene tareas."}</p>
      )}
      {estado.tipo === "ok" && estado.tareas.length > 0 && (
        <>
          <ul className="citas">
            {estado.tareas.map((tarea) => (
              <li key={tarea.id} className="cita">
                <span className="cita__hora">{formatoDia(tarea.due_on)}</span>
                <span>{tarea.description}</span>
                {!profesional && <span className="cita__meta">Responsable: {tarea.assigned_to_email}</span>}
              </li>
            ))}
          </ul>
          {estado.total > estado.tareas.length && (
            <p className="ayuda">
              Mostrando las {estado.tareas.length} más cercanas de {estado.total}.
            </p>
          )}
        </>
      )}
      {!profesional &&
        (creando ? (
          <FormularioTarea
            contacto={contacto}
            csrf={sesion.usuario.csrf_token}
            alCancelar={() => setCreando(false)}
            alCrear={() => {
              setCreando(false);
              setCreada(true);
              setIntento((n) => n + 1); // la lista la ordena y la recorta la API
            }}
          />
        ) : (
          <button
            type="button"
            className="secundario"
            onClick={() => {
              setCreada(false);
              setCreando(true);
            }}
          >
            Nueva tarea
          </button>
        ))}
    </section>
  );
}

type Asignables = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; lista: Responsable[] };
type CampoTarea = "description" | "due_on" | "assigned_to_id";

function FormularioTarea({
  contacto,
  csrf,
  alCancelar,
  alCrear,
}: {
  contacto: number;
  csrf: string;
  alCancelar: () => void;
  alCrear: () => void;
}) {
  const { caducada } = useSesion();
  const [asignables, setAsignables] = useState<Asignables>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);
  const [descripcion, setDescripcion] = useState("");
  const [fecha, setFecha] = useState("");
  const [responsable, setResponsable] = useState("");
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
      await crearTarea(contacto, { description: descripcion, due_on: fecha, assigned_to_id: Number(responsable) }, csrf);
      alCrear();
    } catch (e) {
      setGuardando(false);
      if (!(e instanceof ErrorApi)) return setGeneral("Error inesperado");
      if (e.status === 401) return caducada();
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
          {asignables.lista.map((persona) => (
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
          Crear tarea
        </button>
        <button type="button" className="secundario" disabled={guardando} onClick={alCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
