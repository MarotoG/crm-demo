// Pantalla de login (T10). Los mensajes de error vienen de la API (401, 429) o de api.ts (503, red).

import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router";

import { ErrorApi } from "./api";
import EstadoSistema from "./EstadoSistema";
import { inicioDe } from "./permisos";
import { useSesion } from "./sesion";

export default function Login() {
  const { estado, entrar } = useSesion();
  // Al llegar desde la invitación (T21), «Cuenta creada».
  const exito = (useLocation().state as { aviso?: string } | null)?.aviso;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (estado.tipo === "comprobando") return <p className="pagina">Comprobando la sesión…</p>;
  // Con sesión, cada rol va a su página de inicio (T18: la agenda para admin y recepción).
  if (estado.tipo === "dentro") return <Navigate to={inicioDe(estado.usuario.role)} replace />;

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await entrar(email, password);
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "Error inesperado");
      setEnviando(false);
    }
  }

  return (
    <main className="pagina">
      <h1>crm-demo</h1>
      <p className="subtitulo">CRM para clínicas estéticas · demo con datos ficticios</p>

      <form className="tarjeta formulario" onSubmit={enviar} aria-labelledby="titulo-login">
        <h2 id="titulo-login">Entrar</h2>
        {exito && (
          <p className="exito" role="status">
            {exito}
          </p>
        )}
        {estado.aviso && <p className="aviso">{estado.aviso}</p>}
        <label>
          Email
          <input
            type="email"
            autoComplete="username"
            required
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Contraseña
          <input
            type="password"
            autoComplete="current-password"
            required
            maxLength={1024}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>

      <EstadoSistema />
    </main>
  );
}
