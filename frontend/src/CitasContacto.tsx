// Las citas de un contacto en su ficha (T21), de la fecha más reciente a la más antigua y en solo
// lectura: reprogramar, cancelar y marcar la asistencia se hacen desde la agenda, adonde lleva cada
// una. El profesional solo ve las suyas (lo decide la API), y por eso no se le dice quién la realiza.

import { useEffect, useState } from "react";
import { Link } from "react-router";

import { ErrorApi, listarCitasDeContacto, type CitaAgenda } from "./api";
import { formatoDia, horaEn, NOMBRE_ESTADO_CITA } from "./Agenda";
import { useSesion } from "./sesion";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; total: number; citas: CitaAgenda[] };

export default function CitasContacto({ contacto }: { contacto: number }) {
  const { estado: sesion, caducada } = useSesion();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    setEstado({ tipo: "cargando" });
    listarCitasDeContacto(contacto)
      .then(({ total, items }) => vigente && setEstado({ tipo: "ok", total, citas: items }))
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
  const agenda = profesional ? "/mi-agenda" : "/agenda";

  return (
    <section className="seccion-ficha" aria-labelledby="titulo-citas-contacto">
      <h3 id="titulo-citas-contacto">{profesional ? "Citas contigo" : "Citas"}</h3>
      {estado.tipo === "cargando" && <p>Cargando las citas…</p>}
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
      {estado.tipo === "ok" && estado.citas.length === 0 && <p className="ayuda">Todavía no tiene citas.</p>}
      {estado.tipo === "ok" && estado.citas.length > 0 && (
        <>
          <p className="ayuda">Horas de Nueva York.</p>
          <ul className="citas">
            {estado.citas.map((cita) => {
              const dia = cita.starts_at.slice(0, 10); // ya viene en la hora de la clínica
              return (
                <li key={cita.id} className={cita.status === "cancelled" ? "cita cita--cancelada" : "cita"}>
                  <span className="cita__hora">
                    <Link to={`${agenda}?fecha=${dia}`}>{formatoDia(dia)}</Link> · {horaEn(dia, cita.starts_at)}–{horaEn(dia, cita.ends_at)}
                  </span>
                  <span className="cita__meta">
                    {cita.service_name}
                    {!profesional && ` · ${cita.staff_email}`} · {NOMBRE_ESTADO_CITA[cita.status]}
                  </span>
                </li>
              );
            })}
          </ul>
          {estado.total > estado.citas.length && (
            <p className="ayuda">
              Mostrando las {estado.citas.length} más recientes de {estado.total}.
            </p>
          )}
        </>
      )}
    </section>
  );
}
