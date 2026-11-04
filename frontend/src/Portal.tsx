// Portal del cliente (T23): sus citas, en solo lectura. Las próximas y, debajo, las anteriores con su
// estado real (decisión T22). Quién ve qué lo decide la API a partir de la sesión: aquí no se envía
// ningún dato que diga de quién son las citas.

import { useEffect, useState } from "react";

import { ErrorApi, listarMisCitas, type CitaPortal, type MisCitas } from "./api";
import { formatoDia, horaEn, NOMBRE_ESTADO_CITA } from "./Agenda";
import { useSesion } from "./sesion";

export const SIN_CITAS = "Aún no tienes citas. Escribe a la clínica para reservar.";
export const SIN_PROXIMAS = "No tienes citas próximas. Escribe a la clínica para reservar.";

type Estado = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; citas: MisCitas };

/** Una Programada ya pasada que la clínica aún no ha marcado: «Programada» se leería como futura. */
function estadoDe(cita: CitaPortal, pasada: boolean): string {
  return pasada && cita.status === "scheduled" ? "Sin confirmar" : NOMBRE_ESTADO_CITA[cita.status];
}

function ListaCitas({ citas, pasadas }: { citas: CitaPortal[]; pasadas: boolean }) {
  return (
    <ul className="citas">
      {citas.map((cita) => {
        const dia = cita.starts_at.slice(0, 10); // ya viene en la hora de la clínica
        return (
          <li key={cita.id} className={cita.status === "cancelled" ? "cita cita--cancelada" : "cita"}>
            <span className="cita__hora">
              {formatoDia(dia)} · {horaEn(dia, cita.starts_at)}–{horaEn(dia, cita.ends_at)}
            </span>
            <span className="cita__meta">
              {cita.service_name} · {estadoDe(cita, pasadas)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default function Portal() {
  const { caducada } = useSesion();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    setEstado({ tipo: "cargando" });
    listarMisCitas()
      .then((citas) => vigente && setEstado({ tipo: "ok", citas }))
      .catch((e: unknown) => {
        if (!vigente) return;
        if (e instanceof ErrorApi && e.status === 401) return caducada();
        setEstado({ tipo: "error", mensaje: e instanceof ErrorApi ? e.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [intento, caducada]);

  const citas = estado.tipo === "ok" ? estado.citas : null;

  return (
    <section className="tarjeta portal" aria-labelledby="titulo-portal">
      <h2 id="titulo-portal">Mis citas</h2>
      {estado.tipo === "cargando" && <p>Cargando tus citas…</p>}
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
      {citas && citas.upcoming.length === 0 && citas.past.length === 0 && <p>{SIN_CITAS}</p>}
      {citas && (citas.upcoming.length > 0 || citas.past.length > 0) && (
        <>
          <p className="ayuda">Horas de Nueva York.</p>
          <h3>Próximas</h3>
          {citas.upcoming.length > 0 ? <ListaCitas citas={citas.upcoming} pasadas={false} /> : <p>{SIN_PROXIMAS}</p>}
          {citas.past.length > 0 && (
            <>
              <h3>Anteriores</h3>
              <ListaCitas citas={citas.past} pasadas />
              {citas.past_total > citas.past.length && (
                <p className="ayuda">
                  Mostrando las {citas.past.length} más recientes de {citas.past_total}.
                </p>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
