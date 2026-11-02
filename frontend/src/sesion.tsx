// Estado de la sesión compartido por toda la app (T10).
// Al abrir la página se pregunta a la API (/api/auth/me) si la cookie sigue valiendo:
// la cookie es HttpOnly, así que JavaScript no puede mirarla directamente.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { cerrarSesion, ErrorApi, iniciarSesion, obtenerSesion, type Rol, type Usuario } from "./api";

export type EstadoSesion =
  | { tipo: "comprobando" }
  | { tipo: "fuera"; aviso?: string }
  | { tipo: "dentro"; usuario: Usuario };

type Sesion = {
  estado: EstadoSesion;
  entrar: (email: string, password: string) => Promise<void>;
  salir: () => Promise<void>;
  /** Para cuando la API responde 401 en mitad del uso: vuelve al login con un aviso. */
  caducada: () => void;
};

export const AREA_DE: Record<Rol, string> = {
  admin: "/admin",
  reception: "/recepcion",
  professional: "/profesional",
  client: "/portal",
};

export const NOMBRE_ROL: Record<Rol, string> = {
  admin: "Administración",
  reception: "Recepción",
  professional: "Profesional",
  client: "Cliente",
};

const ContextoSesion = createContext<Sesion | null>(null);

export function SesionProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoSesion>({ tipo: "comprobando" });

  useEffect(() => {
    let vigente = true; // evita actualizar el estado si el componente ya se desmontó
    obtenerSesion()
      .then((usuario) => vigente && setEstado(usuario ? { tipo: "dentro", usuario } : { tipo: "fuera" }))
      .catch((error: unknown) => {
        const mensaje = error instanceof ErrorApi ? error.message : "Error inesperado";
        if (vigente) setEstado({ tipo: "fuera", aviso: `No se pudo comprobar la sesión: ${mensaje}` });
      });
    return () => {
      vigente = false;
    };
  }, []);

  const entrar = useCallback(async (email: string, password: string) => {
    const usuario = await iniciarSesion(email, password); // si falla, el formulario muestra el error
    setEstado({ tipo: "dentro", usuario });
  }, []);

  const salir = useCallback(async () => {
    if (estado.tipo !== "dentro") return;
    try {
      await cerrarSesion(estado.usuario.csrf_token);
    } catch (error) {
      // 403: token CSRF desfasado (p. ej. cambió CRM_SECRET_KEY). Se pide uno nuevo y se reintenta una vez.
      if (!(error instanceof ErrorApi && error.status === 403)) throw error;
      const actual = await obtenerSesion();
      if (actual) await cerrarSesion(actual.csrf_token);
    }
    // Solo se da por cerrada si la API lo confirmó: en un PC compartido de la clínica,
    // decir «has salido» con la sesión aún abierta sería peor que mostrar un error.
    setEstado({ tipo: "fuera" });
  }, [estado]);

  const caducada = useCallback(() => {
    setEstado({ tipo: "fuera", aviso: "Tu sesión ha caducado. Vuelve a entrar." });
  }, []);

  const valor = useMemo(() => ({ estado, entrar, salir, caducada }), [estado, entrar, salir, caducada]);
  return <ContextoSesion.Provider value={valor}>{children}</ContextoSesion.Provider>;
}

export function useSesion(): Sesion {
  const sesion = useContext(ContextoSesion);
  if (sesion === null) throw new Error("useSesion debe usarse dentro de <SesionProvider>");
  return sesion;
}
