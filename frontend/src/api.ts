// Comprobaciones de salud de la API. Las rutas son relativas (/api/...):
// en desarrollo las reenvía el proxy de Vite y en producción las reenviará nginx.

export type EstadoSalud =
  | { tipo: "cargando" }
  | { tipo: "ok" }
  | { tipo: "error"; mensaje: string };

// Holgado respecto a los 3 s que la API espera a PostgreSQL (connect_timeout),
// para mostrar su 503 real y no un "sin respuesta" engañoso.
const TIEMPO_MAXIMO_MS = 10000;

export async function comprobarSalud(ruta: string): Promise<EstadoSalud> {
  let respuesta: Response;
  try {
    respuesta = await fetch(ruta, {
      headers: { Accept: "application/json" },
      // Un estado de salud nunca debe salir de la caché. Además evita que el navegador
      // ponga en fila peticiones idénticas simultáneas esperando poder reutilizarlas.
      cache: "no-store",
      signal: AbortSignal.timeout(TIEMPO_MAXIMO_MS),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      return { tipo: "error", mensaje: `Sin respuesta en ${TIEMPO_MAXIMO_MS / 1000} s` };
    }
    return { tipo: "error", mensaje: "No se pudo contactar con el servidor" };
  }

  if (!respuesta.ok) {
    return { tipo: "error", mensaje: mensajeDeError(respuesta.status) };
  }

  try {
    const cuerpo: unknown = await respuesta.json();
    if (typeof cuerpo === "object" && cuerpo !== null && "status" in cuerpo && cuerpo.status === "ok") {
      return { tipo: "ok" };
    }
  } catch {
    // Cuerpo que no es JSON: se trata como respuesta inesperada.
  }
  return { tipo: "error", mensaje: "Respuesta inesperada del servidor" };
}

function mensajeDeError(status: number): string {
  // 502/504 los genera el proxy (Vite o nginx) cuando la API no contesta;
  // 503 lo devuelve la propia API cuando no llega a la base de datos.
  if (status === 502 || status === 504) return `La API no responde (HTTP ${status})`;
  if (status === 503) return `No disponible (HTTP ${status})`;
  return `Error del servidor (HTTP ${status})`;
}
