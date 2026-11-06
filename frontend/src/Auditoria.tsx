// Eventos de auditoría (T26), solo lectura y solo para administración (la API da 403 a los demás).
// Quién hizo qué, sobre qué registro y cuándo: los nombres de los campos que cambiaron, nunca sus
// valores. La persona, la acción y la página van en la dirección, para poder recargar.

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { ErrorApi, listarEventos, listarUsuarios, type AccionAuditoria, type EventoAuditoria, type UsuarioAdmin } from "./api";
import { formatoFecha, NOMBRE_ESTADO } from "./Contactos";
import { useSesion } from "./sesion";

export const NOMBRE_ACCION: Record<AccionAuditoria, string> = {
  login_succeeded: "Entró en el CRM",
  login_failed: "Intento de entrada fallido",
  logout: "Cerró sesión",
  contact_viewed: "Abrió una ficha",
  contact_created: "Creó un contacto",
  contact_updated: "Editó un contacto",
  contact_status_changed: "Cambio de estado del contacto",
  service_created: "Creó un servicio",
  service_updated: "Editó un servicio",
  appointment_created: "Creó una cita",
  appointment_rescheduled: "Reprogramó una cita",
  appointment_cancelled: "Canceló una cita",
  appointment_attendance_marked: "Marcó la asistencia",
  appointment_note_edited: "Editó la nota de una cita",
  invitation_created: "Generó una invitación al portal",
  invitation_accepted: "Aceptó la invitación al portal",
  follow_up_created: "Creó una tarea",
  follow_up_updated: "Editó una tarea",
  follow_up_completed: "Completó una tarea",
  follow_up_reopened: "Reabrió una tarea",
};

const NOMBRE_OBJETIVO: Record<NonNullable<EventoAuditoria["target_type"]>, string> = {
  contact: "Contacto",
  service: "Servicio",
  appointment: "Cita",
  follow_up: "Tarea",
  user: "Cuenta",
};

const ESTADO_CONTACTO: Record<string, string> = { ...NOMBRE_ESTADO };
const ESTADO_CITA: Record<string, string> = {
  scheduled: "Programada",
  completed: "Realizada",
  no_show: "No presentado",
  cancelled: "Cancelada",
};

/** Sobre qué registro, los estados y los campos; vacío si el evento no tiene nada de eso, como un login. */
function detalle(evento: EventoAuditoria): string {
  const partes: string[] = [];
  if (evento.target_type !== null) {
    partes.push(`Sobre: ${evento.target_email ?? `${NOMBRE_OBJETIVO[evento.target_type]} ${evento.target_id}`}`);
  }
  if (evento.from_status && evento.to_status) {
    const nombres = evento.target_type === "appointment" ? ESTADO_CITA : ESTADO_CONTACTO;
    const estado = (s: string) => nombres[s] ?? s;
    partes.push(`${estado(evento.from_status)} → ${estado(evento.to_status)}`);
  }
  if (evento.changed_fields.length > 0) partes.push(`Campos: ${evento.changed_fields.join(", ")}`);
  return partes.join(" · ");
}

type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; total: number; tamano: number; eventos: EventoAuditoria[] };

export default function Auditoria() {
  const { caducada } = useSesion();
  const [parametros, setParametros] = useSearchParams();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [personas, setPersonas] = useState<UsuarioAdmin[]>([]);
  const [recarga, setRecarga] = useState(0);

  const persona = parametros.get("persona") ?? "";
  const accion = parametros.get("accion") ?? "";
  const pagina = Math.max(1, Number(parametros.get("pagina")) || 1);

  useEffect(() => {
    let vigente = true;
    setEstado({ tipo: "cargando" });
    listarEventos({ persona: persona ? Number(persona) : undefined, accion: accion || undefined, pagina })
      .then(({ total, page_size, items }) => vigente && setEstado({ tipo: "ok", total, tamano: page_size, eventos: items }))
      .catch((e: unknown) => {
        if (!vigente) return;
        if (e instanceof ErrorApi && e.status === 401) return caducada();
        setEstado({ tipo: "error", mensaje: e instanceof ErrorApi ? e.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [persona, accion, pagina, recarga, caducada]);

  useEffect(() => {
    let vigente = true;
    // Si falla, el filtro solo ofrece «Todas»: los eventos se siguen viendo.
    listarUsuarios()
      .then((lista) => vigente && setPersonas(lista))
      .catch(() => {});
    return () => {
      vigente = false;
    };
  }, []);

  function cambiar(cambios: { persona?: string; accion?: string; pagina?: string }) {
    const siguientes = new URLSearchParams(parametros);
    // Otro filtro cambia los resultados: se vuelve a la primera página.
    if (cambios.pagina === undefined) siguientes.delete("pagina");
    for (const [nombre, valor] of Object.entries(cambios)) {
      if (valor) siguientes.set(nombre, valor);
      else siguientes.delete(nombre);
    }
    setParametros(siguientes);
  }

  return (
    <section className="tarjeta auditoria" aria-labelledby="titulo-auditoria">
      <h2 id="titulo-auditoria">Auditoría</h2>
      <p className="ayuda">
        Quién hizo qué y cuándo: accesos, fichas abiertas y cambios de datos. Muestra qué campos cambiaron, no su contenido. Es una
        ayuda para revisar, no un registro inalterable: quien administre la base de datos podría modificarlo.
      </p>
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
        <label>
          Acción
          <select value={accion} onChange={(e) => cambiar({ accion: e.target.value })}>
            <option value="">Todas</option>
            {(Object.keys(NOMBRE_ACCION) as AccionAuditoria[]).map((a) => (
              <option key={a} value={a}>
                {NOMBRE_ACCION[a]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {estado.tipo === "cargando" && <p>Cargando los eventos…</p>}
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
      {estado.tipo === "ok" && estado.eventos.length === 0 && <p>No hay eventos con estos filtros.</p>}
      {estado.tipo === "ok" && estado.eventos.length > 0 && (
        <>
          <ul className="citas">
            {estado.eventos.map((evento) => (
              <li key={evento.id} className="cita">
                <span className="cita__contacto">{NOMBRE_ACCION[evento.action]}</span>
                <span className="cita__meta">
                  {formatoFecha(evento.occurred_at)} · {evento.actor_email ?? "Sin identificar"}
                </span>
                {detalle(evento) && <span className="cita__meta">{detalle(evento)}</span>}
              </li>
            ))}
          </ul>
          <div className="acciones">
            <button type="button" className="secundario" disabled={pagina <= 1} onClick={() => cambiar({ pagina: String(pagina - 1) })}>
              Más recientes
            </button>
            <button
              type="button"
              className="secundario"
              disabled={pagina * estado.tamano >= estado.total}
              onClick={() => cambiar({ pagina: String(pagina + 1) })}
            >
              Más antiguos
            </button>
          </div>
          <p className="ayuda">
            Página {pagina} de {Math.ceil(estado.total / estado.tamano)} · {estado.total} {estado.total === 1 ? "evento" : "eventos"} en total.
          </p>
        </>
      )}
      {estado.tipo === "ok" && estado.eventos.length === 0 && pagina > 1 && (
        <button type="button" className="secundario" onClick={() => cambiar({ pagina: "" })}>
          Volver a la primera página
        </button>
      )}
    </section>
  );
}
