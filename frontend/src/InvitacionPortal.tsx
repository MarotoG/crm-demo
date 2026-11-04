// La invitación al portal en la ficha del contacto (T21), para administración y recepción.
//
// El enlace solo se ve al generarlo, porque en la BD queda su hash. El token va tras «#»: esa parte
// de la dirección no se envía al servidor, así que no acaba en los logs de ningún proxy.

import { useEffect, useState } from "react";

import { ErrorApi, generarInvitacion, obtenerEstadoPortal, type ContactoDetalle, type EstadoPortal } from "./api";
import { formatoFecha } from "./Contactos";
import { useSesion } from "./sesion";

type Estado = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; portal: EstadoPortal };

export default function InvitacionPortal({ ficha }: { ficha: ContactoDetalle }) {
  const { estado: sesion, caducada } = useSesion();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [enlace, setEnlace] = useState<{ url: string; caduca: string } | null>(null);
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copia, setCopia] = useState<"copiado" | "fallo" | null>(null);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    setEstado({ tipo: "cargando" });
    setEnlace(null);
    obtenerEstadoPortal(ficha.id)
      .then((portal) => vigente && setEstado({ tipo: "ok", portal }))
      .catch((e: unknown) => {
        if (!vigente) return;
        if (e instanceof ErrorApi && e.status === 401) return caducada();
        setEstado({ tipo: "error", mensaje: e instanceof ErrorApi ? e.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [ficha.id, intento, caducada]);

  if (sesion.tipo !== "dentro") return null;
  const csrf = sesion.usuario.csrf_token;

  async function generar(portal: EstadoPortal) {
    setGenerando(true);
    setError(null);
    setCopia(null);
    try {
      const nueva = await generarInvitacion(ficha.id, csrf);
      setEnlace({ url: `${window.location.origin}/invitacion#${nueva.token}`, caduca: nueva.expires_at });
      setEstado({ tipo: "ok", portal: { ...portal, invitation_expires_at: nueva.expires_at } });
    } catch (e) {
      if (e instanceof ErrorApi && e.status === 401) return caducada();
      setEnlace(null);
      setError(e instanceof ErrorApi ? e.message : "Error inesperado");
      if (e instanceof ErrorApi && e.status === 409) setIntento((n) => n + 1); // otra persona u otra pestaña
    } finally {
      setGenerando(false);
    }
  }

  async function copiar(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopia("copiado");
    } catch {
      setCopia("fallo");
    }
  }

  return (
    <section className="seccion-ficha" aria-labelledby="titulo-portal">
      <h3 id="titulo-portal">Portal del cliente</h3>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {estado.tipo === "cargando" && <p>Cargando…</p>}
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
      {estado.tipo === "ok" && estado.portal.has_account && <p>Ya tiene cuenta en el portal.</p>}
      {estado.tipo === "ok" && !estado.portal.has_account && ficha.status === "lost" && (
        <p className="ayuda">Para invitarlo al portal, reábrelo primero.</p>
      )}
      {estado.tipo === "ok" && !estado.portal.has_account && ficha.status !== "lost" && (
        <>
          {enlace ? (
            <>
              <div className="campo">
                <label htmlFor="enlace-invitacion">Enlace de invitación</label>
                <input id="enlace-invitacion" readOnly value={enlace.url} onFocus={(e) => e.target.select()} />
              </div>
              <p className="ayuda">
                Envíaselo por WhatsApp. Vale una sola vez, hasta el {formatoFecha(enlace.caduca)}. Después de salir de esta
                ficha ya no se puede volver a ver.
              </p>
              <div className="acciones">
                <button type="button" onClick={() => copiar(enlace.url)}>
                  Copiar enlace
                </button>
                <button type="button" className="secundario" disabled={generando} onClick={() => generar(estado.portal)}>
                  Generar otro enlace
                </button>
              </div>
              {copia === "copiado" && (
                <p className="exito" role="status">
                  Enlace copiado
                </p>
              )}
              {copia === "fallo" && (
                <p className="aviso" role="alert">
                  No se pudo copiar: selecciona el enlace y cópialo a mano.
                </p>
              )}
            </>
          ) : estado.portal.invitation_expires_at ? (
            <>
              <p className="ayuda">
                Hay un enlace sin usar, válido hasta el {formatoFecha(estado.portal.invitation_expires_at)}. Por seguridad no
                se puede volver a mostrar: generar otro anula el anterior.
              </p>
              <button type="button" className="secundario" disabled={generando} onClick={() => generar(estado.portal)}>
                Generar otro enlace
              </button>
            </>
          ) : (
            <>
              <p className="ayuda">Genera un enlace para que cree su cuenta con su email y su contraseña. Caduca a las 24 horas.</p>
              <button type="button" disabled={generando} onClick={() => generar(estado.portal)}>
                Invitar al portal
              </button>
            </>
          )}
        </>
      )}
    </section>
  );
}
