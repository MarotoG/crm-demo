// Áreas por rol (T10). Ocultar o mostrar un área no protege nada: quien decide es la API
// (403 en /api/users para quien no es admin). Aquí solo se evita pedir datos sin sentido
// y se explica al usuario dónde está.

import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, Outlet } from "react-router";

import { ErrorApi, listarUsuarios, type Rol, type UsuarioAdmin } from "./api";
import Contactos from "./Contactos";
import Servicios from "./Servicios";
import { AREA_DE, NOMBRE_ROL, useSesion } from "./sesion";

/** Exige sesión: sin ella, al login. Con ella, la cabecera común y el área pedida. */
export function RutaProtegida() {
  const { estado } = useSesion();
  if (estado.tipo === "comprobando") return <p className="pagina">Comprobando la sesión…</p>;
  if (estado.tipo === "fuera") return <Navigate to="/login" replace />;
  return (
    <>
      <Cabecera />
      <main className="pagina">
        <Outlet />
      </main>
    </>
  );
}

/** Solo muestra su contenido al rol indicado; a los demás, un aviso y un enlace a su área. */
export function SoloRol({ rol, children }: { rol: Rol; children: ReactNode }) {
  const { estado } = useSesion();
  if (estado.tipo !== "dentro") return null; // RutaProtegida ya lo ha resuelto
  if (estado.usuario.role !== rol) {
    return (
      <section className="tarjeta">
        <h2>No tienes acceso a esta área</h2>
        <p>
          Esta área es de {NOMBRE_ROL[rol].toLowerCase()}. <Link to={AREA_DE[estado.usuario.role]}>Ir a tu área</Link>
        </p>
      </section>
    );
  }
  return children;
}

/** Al entrar en "/", cada uno a su sitio. */
export function Inicio() {
  const { estado } = useSesion();
  if (estado.tipo === "comprobando") return <p className="pagina">Comprobando la sesión…</p>;
  return <Navigate to={estado.tipo === "dentro" ? AREA_DE[estado.usuario.role] : "/login"} replace />;
}

function Cabecera() {
  const { estado, salir } = useSesion();
  const [saliendo, setSaliendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (estado.tipo !== "dentro") return null;

  async function cerrar() {
    setSaliendo(true);
    setError(null);
    try {
      await salir();
    } catch (e) {
      setError(`No se pudo cerrar la sesión: ${e instanceof ErrorApi ? e.message : "error inesperado"}`);
      setSaliendo(false);
    }
  }

  return (
    <header className="cabecera">
      <span className="cabecera__marca">crm-demo</span>
      <span className="cabecera__usuario">
        {estado.usuario.email} · {NOMBRE_ROL[estado.usuario.role]}
      </span>
      <button type="button" className="secundario" onClick={cerrar} disabled={saliendo}>
        {saliendo ? "Cerrando…" : "Cerrar sesión"}
      </button>
      {error && (
        <p className="error cabecera__error" role="alert">
          {error}
        </p>
      )}
    </header>
  );
}

type EstadoLista =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; usuarios: UsuarioAdmin[] };

/** Área de administración: la lista real de usuarios (GET /api/users, solo admin), los servicios (T15) y los contactos (T12). */
export function AreaAdmin() {
  const { caducada } = useSesion();
  const [lista, setLista] = useState<EstadoLista>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    setLista({ tipo: "cargando" });
    listarUsuarios()
      .then((usuarios) => vigente && setLista({ tipo: "ok", usuarios }))
      .catch((error: unknown) => {
        if (!vigente) return;
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setLista({ tipo: "error", mensaje: error instanceof ErrorApi ? error.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [caducada, intento]);

  return (
    <>
      <section className="tarjeta" aria-labelledby="titulo-usuarios">
        <h2 id="titulo-usuarios">Usuarios</h2>
        {lista.tipo === "cargando" && <p>Cargando usuarios…</p>}
        {lista.tipo === "error" && (
          <>
            <p className="error" role="alert">
              {lista.mensaje}
            </p>
            <button type="button" className="secundario" onClick={() => setIntento((n) => n + 1)}>
              Reintentar
            </button>
          </>
        )}
        {lista.tipo === "ok" && (
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Email</th>
                <th scope="col">Rol</th>
                <th scope="col">Estado</th>
              </tr>
            </thead>
            <tbody>
              {lista.usuarios.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{NOMBRE_ROL[u.role]}</td>
                  <td>{u.active ? "Activa" : "Desactivada"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <Servicios />
      <Contactos />
    </>
  );
}

/** Áreas de profesional y cliente: de momento, solo la bienvenida. */
export function Bienvenida() {
  const { estado } = useSesion();
  if (estado.tipo !== "dentro") return null;
  return (
    <section className="tarjeta">
      <h2>Área de {NOMBRE_ROL[estado.usuario.role].toLowerCase()}</h2>
      <p>
        Hola, {estado.usuario.email}. Las funciones de esta área (contactos, agenda, portal) llegarán en próximas
        tareas.
      </p>
    </section>
  );
}

export function NoEncontrada() {
  return (
    <main className="pagina">
      <section className="tarjeta">
        <h2>Página no encontrada</h2>
        <Link to="/">Volver al inicio</Link>
      </section>
    </main>
  );
}
