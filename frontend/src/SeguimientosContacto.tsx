// Las tareas de seguimiento de un contacto en su ficha (T24): primero las pendientes y, desde T25,
// las hechas, con «Hecha», «Reabrir» y «Editar» (Tareas.tsx). Para administración y recepción,
// «Nueva tarea». El profesional solo ve las suyas (lo decide la API) y no crea ni edita.

import { useEffect, useState } from "react";

import { crearTarea, ErrorApi, listarTareas, type TareaSeguimiento } from "./api";
import { useSesion } from "./sesion";
import { avisarTareasCambiadas, FilaTarea, FormularioTarea, MensajeAviso, type Aviso } from "./Tareas";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; hoy: string; total: number; tareas: TareaSeguimiento[] };

export default function SeguimientosContacto({ contacto }: { contacto: number }) {
  const { estado: sesion, caducada } = useSesion();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);
  const [creando, setCreando] = useState(false);
  const [aviso, setAviso] = useState<Aviso | null>(null);

  useEffect(() => {
    let vigente = true;
    setEstado({ tipo: "cargando" });
    listarTareas(contacto)
      .then(({ today, total, items }) => vigente && setEstado({ tipo: "ok", hoy: today, total, tareas: items }))
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

  /** La lista la ordena y la recorta la API: tras cualquier cambio, se vuelve a pedir. */
  function trasCambio(nuevo: Aviso) {
    setAviso(nuevo);
    setIntento((n) => n + 1);
    avisarTareasCambiadas();
  }

  return (
    <section className="seccion-ficha seguimientos" aria-labelledby="titulo-seguimientos">
      <h3 id="titulo-seguimientos">{profesional ? "Tus seguimientos" : "Seguimientos"}</h3>
      <MensajeAviso aviso={aviso} />
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
              <FilaTarea key={tarea.id} tarea={tarea} hoy={estado.hoy} alCambiar={trasCambio} />
            ))}
          </ul>
          {estado.total > estado.tareas.length && (
            <p className="ayuda">
              Mostrando {estado.tareas.length} de {estado.total}; el resto, en «Pendientes».
            </p>
          )}
        </>
      )}
      {!profesional &&
        (creando ? (
          <FormularioTarea
            contacto={contacto}
            textoGuardar="Crear tarea"
            guardar={(datos, csrf) => crearTarea(contacto, datos, csrf)}
            alCancelar={() => setCreando(false)}
            alGuardar={() => {
              setCreando(false);
              trasCambio({ tipo: "exito", texto: "Tarea creada" });
            }}
          />
        ) : (
          <button
            type="button"
            className="secundario"
            onClick={() => {
              setAviso(null);
              setCreando(true);
            }}
          >
            Nueva tarea
          </button>
        ))}
    </section>
  );
}
