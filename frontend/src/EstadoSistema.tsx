// Estado de la API y de la base de datos (T06). Desde T10 se muestra en la pantalla de login.

import { useCallback, useEffect, useState } from "react";

import { comprobarSalud, type EstadoSalud } from "./api";

const COMPROBACIONES = [
  { ruta: "/api/health", nombre: "API" },
  { ruta: "/api/health/db", nombre: "Base de datos" },
] as const;

type Ruta = (typeof COMPROBACIONES)[number]["ruta"];

const TODO_CARGANDO: Record<Ruta, EstadoSalud> = {
  "/api/health": { tipo: "cargando" },
  "/api/health/db": { tipo: "cargando" },
};

export default function EstadoSistema() {
  const [estados, setEstados] = useState(TODO_CARGANDO);

  const comprobar = useCallback(() => {
    setEstados(TODO_CARGANDO);
    for (const { ruta } of COMPROBACIONES) {
      comprobarSalud(ruta).then((estado) => {
        setEstados((anteriores) => ({ ...anteriores, [ruta]: estado }));
      });
    }
  }, []);

  useEffect(comprobar, [comprobar]);

  const cargando = Object.values(estados).some((e) => e.tipo === "cargando");

  return (
    <section className="tarjeta" aria-labelledby="titulo-estado">
      <h2 id="titulo-estado">Estado del sistema</h2>
      <ul className="estados" aria-live="polite">
        {COMPROBACIONES.map(({ ruta, nombre }) => (
          <FilaEstado key={ruta} nombre={nombre} estado={estados[ruta]} />
        ))}
      </ul>
      <button type="button" className="secundario" onClick={comprobar} disabled={cargando}>
        {cargando ? "Comprobando…" : "Volver a comprobar"}
      </button>
    </section>
  );
}

function FilaEstado({ nombre, estado }: { nombre: string; estado: EstadoSalud }) {
  const texto =
    estado.tipo === "cargando" ? "Comprobando…" : estado.tipo === "ok" ? "Disponible" : estado.mensaje;

  return (
    <li className={`estado estado--${estado.tipo}`}>
      <span className="estado__nombre">{nombre}</span>
      <span className="estado__valor">{texto}</span>
    </li>
  );
}
