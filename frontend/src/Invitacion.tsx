// Página pública de la invitación al portal (T21): /invitacion#<token>. El cliente ve con qué email
// entrará (el de su ficha, T21b), elige su contraseña y después entra por el login como cualquiera.
// Es el único dato de la ficha que se muestra: si está mal, el cliente avisa a la clínica antes.

import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { aceptarInvitacion, comprobarInvitacion, ErrorApi } from "./api";
import { useSesion } from "./sesion";

export const ENLACE_NO_VALIDO = "Este enlace no es válido o ha caducado. Pide uno nuevo a la clínica.";
export const CUENTA_CREADA = "Cuenta creada. Entra con tu email y tu contraseña.";

type Estado =
  | { tipo: "comprobando" }
  | { tipo: "no-valido" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "valido"; email: string };

export default function Invitacion() {
  const { estado: sesion, salir } = useSesion();
  const { hash } = useLocation();
  const token = hash.slice(1);
  const [estado, setEstado] = useState<Estado>({ tipo: "comprobando" });
  const [intento, setIntento] = useState(0);
  const [errorSalir, setErrorSalir] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return setEstado({ tipo: "no-valido" });
    let vigente = true;
    setEstado({ tipo: "comprobando" });
    comprobarInvitacion(token)
      .then(({ email }) => vigente && setEstado({ tipo: "valido", email }))
      .catch((e: unknown) => {
        if (!vigente) return;
        // Un token mal formado (422) tampoco es un enlace válido.
        if (e instanceof ErrorApi && (e.status === 410 || e.status === 422)) return setEstado({ tipo: "no-valido" });
        setEstado({ tipo: "error", mensaje: e instanceof ErrorApi ? e.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [token, intento]);

  async function cerrar() {
    setErrorSalir(null);
    try {
      await salir();
    } catch (e) {
      setErrorSalir(`No se pudo cerrar la sesión: ${e instanceof ErrorApi ? e.message : "error inesperado"}`);
    }
  }

  return (
    <main className="pagina">
      <h1>crm-demo</h1>
      <p className="subtitulo">Portal del cliente · demo con datos ficticios</p>
      <section className="tarjeta" aria-labelledby="titulo-invitacion">
        <h2 id="titulo-invitacion">Crea tu cuenta</h2>
        {(estado.tipo === "comprobando" || sesion.tipo === "comprobando") && <p>Comprobando el enlace…</p>}
        {estado.tipo === "no-valido" && (
          <p className="error" role="alert">
            {ENLACE_NO_VALIDO}
          </p>
        )}
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
        {estado.tipo === "valido" && sesion.tipo === "dentro" && (
          // Si recepción abre el enlace para probarlo, no debe gastarlo con su sesión abierta.
          <>
            <p className="aviso">
              Este enlace es para que el cliente cree su cuenta y tienes una sesión abierta como {sesion.usuario.email}. Si es
              tu invitación, cierra antes la sesión.
            </p>
            {errorSalir && (
              <p className="error" role="alert">
                {errorSalir}
              </p>
            )}
            <button type="button" className="secundario" onClick={cerrar}>
              Cerrar sesión
            </button>
          </>
        )}
        {estado.tipo === "valido" && sesion.tipo === "fuera" && (
          <Formulario token={token} email={estado.email} alCaducar={() => setEstado({ tipo: "no-valido" })} />
        )}
      </section>
    </main>
  );
}

function Formulario({ token, email, alCaducar }: { token: string; email: string; alCaducar: () => void }) {
  const navegar = useNavigate();
  const [password, setPassword] = useState("");
  const [repetida, setRepetida] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [campos, setCampos] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setError(null);
    if (password !== repetida) return setCampos({ repetida: "Las contraseñas no coinciden" });
    setCampos({});
    setEnviando(true);
    try {
      await aceptarInvitacion({ token, password });
      navegar("/login", { replace: true, state: { aviso: CUENTA_CREADA } });
    } catch (e) {
      setEnviando(false);
      if (e instanceof ErrorApi && e.status === 410) return alCaducar();
      if (e instanceof ErrorApi && e.status === 422 && Object.keys(e.campos).length > 0) return setCampos(e.campos);
      setError(e instanceof ErrorApi ? e.message : "Error inesperado");
    }
  }

  return (
    <form className="formulario" onSubmit={enviar}>
      <p className="ayuda">
        Con esta cuenta podrás consultar tus citas. Si ya la creaste, <Link to="/login">entra aquí</Link>.
      </p>
      <p>
        Entrarás con <strong>{email}</strong>. Si no es tu email, avisa a la clínica antes de continuar.
      </p>
      {/* Para que el gestor de contraseñas guarde la nueva junto a este email. */}
      <input type="hidden" autoComplete="username" value={email} />
      <Campo id="invitacion-password" etiqueta="Contraseña (al menos 12 caracteres)" error={campos.password}>
        <input
          id="invitacion-password"
          type="password"
          autoComplete="new-password"
          required
          maxLength={1024}
          value={password}
          aria-invalid={campos.password ? true : undefined}
          aria-describedby={campos.password ? "invitacion-password-error" : undefined}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Campo>
      <Campo id="invitacion-repetida" etiqueta="Repite la contraseña" error={campos.repetida}>
        <input
          id="invitacion-repetida"
          type="password"
          autoComplete="new-password"
          required
          maxLength={1024}
          value={repetida}
          aria-invalid={campos.repetida ? true : undefined}
          aria-describedby={campos.repetida ? "invitacion-repetida-error" : undefined}
          onChange={(e) => setRepetida(e.target.value)}
        />
      </Campo>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" disabled={enviando}>
        {enviando ? "Creando…" : "Crear cuenta"}
      </button>
    </form>
  );
}

function Campo({ id, etiqueta, error, children }: { id: string; etiqueta: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="campo">
      <label htmlFor={id}>{etiqueta}</label>
      {children}
      {error && (
        <p className="error" id={`${id}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
