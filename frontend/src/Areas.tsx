// Estructura común de las páginas con sesión (T10): cabecera, barra de secciones (T18) y la
// protección de cada sección. Qué ve cada rol lo decide permisos.ts. Ocultar o mostrar una
// sección no protege nada: quien decide es la API (403). Aquí solo se evita pedir datos sin
// sentido y se explica al usuario dónde está lo suyo.

import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, NavLink, Outlet, useParams } from "react-router";

import { ErrorApi, listarUsuarios, type UsuarioAdmin } from "./api";
import { inicioDe, puede, SECCIONES, seccionesDe, type Seccion } from "./permisos";
import { NOMBRE_ROL, useSesion } from "./sesion";

/** Exige sesión: sin ella, al login. Con ella, la cabecera común y la sección pedida. */
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

/** Solo muestra la sección a quien puede verla; a los demás, un aviso y un enlace a su inicio. */
export function ConPermiso({ seccion, children }: { seccion: Seccion; children: ReactNode }) {
  const { estado } = useSesion();
  if (estado.tipo !== "dentro") return null; // RutaProtegida ya lo ha resuelto
  const rol = estado.usuario.role;
  if (!puede(rol, seccion)) {
    return (
      <section className="tarjeta">
        <h2>No tienes acceso a esta área</h2>
        <p>
          Tu cuenta ({NOMBRE_ROL[rol].toLowerCase()}) no puede ver «{SECCIONES[seccion].nombre}».{" "}
          <Link to={inicioDe(rol)}>Ir a tu área</Link>
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
  return <Navigate to={estado.tipo === "dentro" ? inicioDe(estado.usuario.role) : "/login"} replace />;
}

/** Direcciones de antes de T18 (/admin, /recepcion/contactos/7…): llevan a la nueva, para que
 * no se rompa un enlace guardado. */
export function RedirigirFicha() {
  const { id } = useParams();
  return <Navigate to={`/contactos/${id}`} replace />;
}

function Cabecera() {
  const { estado, salir } = useSesion();
  const [saliendo, setSaliendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (estado.tipo !== "dentro") return null;
  const secciones = seccionesDe(estado.usuario.role);

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
      {/* Con una sola sección (el cliente, de momento) la barra no aporta nada. */}
      {secciones.length > 1 && (
        <nav className="secciones" aria-label="Secciones">
          {secciones.map((s) => (
            <NavLink key={s} to={SECCIONES[s].ruta}>
              {SECCIONES[s].nombre}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}

type EstadoLista =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; usuarios: UsuarioAdmin[] };

/** Usuarios (solo admin): la lista real de GET /api/users. Su propia sección desde T18. */
export function Usuarios() {
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
  );
}

/** Área del cliente: de momento, solo la bienvenida (el portal llega en T21-T23). */
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
