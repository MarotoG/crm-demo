// Panel de tareas de seguimiento (T25): pendientes agrupadas en Vencidas, Hoy y Próximas, y hechas.
// Administración y recepción ven las de toda la clínica, con filtro por persona (decisión T25); el
// profesional, solo las suyas (el filtro lo pone la API). Sin push: el aviso es este panel y el
// contador de la barra. La vista y la persona van en la dirección (?vista=hechas), para poder recargar.

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { ErrorApi, listarPanelTareas, listarPersonasAsignables, type PersonaServicio, type TareaSeguimiento } from "./api";
import { useSesion } from "./sesion";
import { avisarTareasCambiadas, FilaTarea, MensajeAviso, type Aviso } from "./Tareas";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; hoy: string; total: number; tareas: TareaSeguimiento[] };

export default function Pendientes() {
  const { estado: sesion, caducada } = useSesion();
  const [parametros, setParametros] = useSearchParams();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [recarga, setRecarga] = useState(0);
  const [personas, setPersonas] = useState<PersonaServicio[]>([]);
  const [aviso, setAviso] = useState<Aviso | null>(null);

  const hechas = parametros.get("vista") === "hechas";
  const profesional = sesion.tipo === "dentro" && sesion.usuario.role === "professional";
  const persona = profesional ? "" : (parametros.get("persona") ?? ""); // "": todas

  useEffect(() => {
    let vigente = true;
    setEstado({ tipo: "cargando" });
    listarPanelTareas(hechas ? "done" : "pending", persona ? Number(persona) : undefined)
      .then(({ today, total, items }) => vigente && setEstado({ tipo: "ok", hoy: today, total, tareas: items }))
      .catch((e: unknown) => {
        if (!vigente) return;
        if (e instanceof ErrorApi && e.status === 401) return caducada();
        setEstado({ tipo: "error", mensaje: e instanceof ErrorApi ? e.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [hechas, persona, recarga, caducada]);

  useEffect(() => {
    if (profesional) return;
    let vigente = true;
    // Si falla, el filtro solo ofrece «Todas» y «Solo mías»: el panel sigue sirviendo.
    listarPersonasAsignables()
      .then((lista) => vigente && setPersonas(lista))
      .catch(() => {});
    return () => {
      vigente = false;
    };
  }, [profesional]);

  if (sesion.tipo !== "dentro") return null;
  const yo = String(sesion.usuario.id);

  function cambiar(cambios: { vista?: string; persona?: string }) {
    setAviso(null);
    const siguientes = new URLSearchParams(parametros);
    for (const [nombre, valor] of Object.entries(cambios)) {
      if (valor) siguientes.set(nombre, valor);
      else siguientes.delete(nombre);
    }
    setParametros(siguientes);
  }

  function trasCambio(nuevo: Aviso) {
    setAviso(nuevo);
    setRecarga((n) => n + 1);
    avisarTareasCambiadas();
  }

  function grupo(titulo: string, tareas: TareaSeguimiento[], hoy: string) {
    if (tareas.length === 0) return null;
    return (
      <>
        <h3 className="dia__titulo">
          {titulo} ({tareas.length})
        </h3>
        <ul className="citas">
          {tareas.map((tarea) => (
            <FilaTarea key={tarea.id} tarea={tarea} hoy={hoy} conContacto alCambiar={trasCambio} />
          ))}
        </ul>
      </>
    );
  }

  return (
    <section className="tarjeta pendientes" aria-labelledby="titulo-pendientes">
      <h2 id="titulo-pendientes">Pendientes</h2>
      <div className="acciones">
        <button type="button" className={hechas ? "secundario" : undefined} aria-pressed={!hechas} onClick={() => cambiar({ vista: "" })}>
          Pendientes
        </button>
        <button type="button" className={hechas ? undefined : "secundario"} aria-pressed={hechas} onClick={() => cambiar({ vista: "hechas" })}>
          Hechas
        </button>
      </div>
      {!profesional && (
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
          <button type="button" className="secundario" onClick={() => cambiar({ persona: yo })} disabled={persona === yo}>
            Solo mías
          </button>
        </div>
      )}
      <MensajeAviso aviso={aviso} />
      {estado.tipo === "cargando" && <p>Cargando las tareas…</p>}
      {estado.tipo === "error" && (
        <>
          <p className="error" role="alert">
            {estado.mensaje}
          </p>
          <button type="button" className="secundario" onClick={() => setRecarga((n) => n + 1)}>
            Reintentar
          </button>
        </>
      )}
      {estado.tipo === "ok" && estado.tareas.length === 0 && <p>{hechas ? "No hay tareas hechas." : "No hay tareas pendientes."}</p>}
      {estado.tipo === "ok" && hechas && grupo("Hechas", estado.tareas, estado.hoy)}
      {estado.tipo === "ok" && !hechas && (
        <>
          {grupo("Vencidas", estado.tareas.filter((t) => t.due_on < estado.hoy), estado.hoy)}
          {grupo("Hoy", estado.tareas.filter((t) => t.due_on === estado.hoy), estado.hoy)}
          {grupo("Próximas", estado.tareas.filter((t) => t.due_on > estado.hoy), estado.hoy)}
        </>
      )}
      {estado.tipo === "ok" && estado.total > estado.tareas.length && (
        <p className="ayuda">
          Mostrando {hechas ? "las más recientes" : "las más cercanas"}: {estado.tareas.length} de {estado.total}.
        </p>
      )}
    </section>
  );
}
