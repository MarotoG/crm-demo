// Ficha de un contacto (T13): sus datos, quién lo creó y quién lo cambió por última vez,
// y «Editar». Dirección propia (/recepcion/contactos/7, /admin/contactos/7): se puede
// recargar y ahí irán después sus citas y seguimientos. En T14, el responsable y los
// botones de estado comercial.
//
// Bloqueo optimista: la ficha guarda la versión que leyó y la envía al guardar o al cambiar
// el estado. Si otra persona guardó antes, la API responde 409; entonces se pide la ficha
// actual y, si su versión ha cambiado, se muestra con un aviso en vez de pisar el cambio ajeno.

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import {
  actualizarContacto,
  cambiarEstado,
  ErrorApi,
  listarResponsables,
  obtenerContacto,
  type ContactoDetalle,
  type EstadoContacto,
  type Responsable,
} from "./api";
import {
  formatoFecha,
  formatoTelefono,
  FormularioContacto,
  NOMBRE_ESTADO,
  NOMBRE_ORIGEN,
  type DatosFormulario,
} from "./Contactos";
import { AREA_DE, useSesion } from "./sesion";

export const AVISO_OTRA_VERSION =
  "Otra persona ha cambiado esta ficha mientras la editabas. Se muestran los datos actuales; si hace falta, vuelve a editarla.";

// Cambios de estado a mano (decisión T14), los mismos que permite la API: se avanza de Nuevo a
// Contactado, Perdido vale desde cualquiera y un Perdido se reabre como Contactado. «Cita
// agendada» y «Cliente» los pondrán las citas.
const ACCION_CONTACTADO = { destino: "contacted", texto: "Marcar como contactado" } as const;
const ACCION_PERDIDO = { destino: "lost", texto: "Marcar como perdido" } as const;
export const ACCIONES_DE_ESTADO: Record<EstadoContacto, { destino: EstadoContacto; texto: string }[]> = {
  new: [ACCION_CONTACTADO, ACCION_PERDIDO],
  contacted: [ACCION_PERDIDO],
  scheduled: [ACCION_PERDIDO],
  client: [ACCION_PERDIDO],
  lost: [{ destino: "contacted", texto: "Reabrir (pasa a Contactado)" }],
};

type EstadoFicha =
  | { tipo: "cargando" }
  | { tipo: "no-existe" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; ficha: ContactoDetalle };

type Aviso = { tipo: "exito" | "conflicto" | "error"; texto: string };

type EstadoResponsables = { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; lista: Responsable[] };

/** Lo que se ve en el formulario al empezar a editar: los datos guardados, teléfono legible. */
function datosDe(ficha: ContactoDetalle): DatosFormulario {
  return {
    first_name: ficha.first_name,
    last_name: ficha.last_name,
    email: ficha.email ?? "",
    phone: ficha.phone ? formatoTelefono(ficha.phone) : "",
    source: ficha.source,
    owner_id: ficha.owner_id === null ? "" : String(ficha.owner_id),
  };
}

/** Las opciones del desplegable; si el responsable actual ya no puede serlo (cuenta de baja), se
 * añade para que guardar sin tocarlo no lo cambie. */
function opcionesDeResponsable(lista: Responsable[], ficha: ContactoDetalle): Responsable[] {
  if (ficha.owner_id === null || lista.some((r) => r.id === ficha.owner_id)) return lista;
  return [...lista, { id: ficha.owner_id, email: `${ficha.owner_email ?? "cuenta"} (ya no disponible)` }];
}

export default function FichaContacto() {
  const { estado: sesion, caducada } = useSesion();
  const { id } = useParams();
  const contactoId = Number(id);
  const [estado, setEstado] = useState<EstadoFicha>({ tipo: "cargando" });
  const [editando, setEditando] = useState(false);
  const [responsables, setResponsables] = useState<EstadoResponsables>({ tipo: "cargando" });
  const [cambiandoEstado, setCambiandoEstado] = useState(false);
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const [intento, setIntento] = useState(0);

  const tratarError = useCallback(
    (error: unknown) => {
      if (error instanceof ErrorApi && error.status === 401) return caducada();
      if (error instanceof ErrorApi && error.status === 404) return setEstado({ tipo: "no-existe" });
      setEstado({ tipo: "error", mensaje: error instanceof ErrorApi ? error.message : "Error inesperado" });
    },
    [caducada],
  );

  useEffect(() => {
    // Un id que no es un número entero positivo no puede existir: ni se pregunta a la API.
    if (!Number.isInteger(contactoId) || contactoId < 1) return setEstado({ tipo: "no-existe" });
    let vigente = true;
    setEstado({ tipo: "cargando" });
    obtenerContacto(contactoId)
      .then((ficha) => vigente && setEstado({ tipo: "ok", ficha }))
      .catch((error: unknown) => vigente && tratarError(error));
    return () => {
      vigente = false;
    };
  }, [contactoId, intento, tratarError]);

  if (sesion.tipo !== "dentro") return null;
  const area = AREA_DE[sesion.usuario.role];
  const csrf = sesion.usuario.csrf_token;

  /** Ante un 409: si la versión ha cambiado, se muestra la ficha actual con el aviso. */
  async function otraVersion(leida: number): Promise<boolean> {
    try {
      const actual = await obtenerContacto(contactoId);
      if (actual.version === leida) return false; // duplicado: lo explica el formulario
      setEstado({ tipo: "ok", ficha: actual });
      setEditando(false);
      setAviso({ tipo: "conflicto", texto: AVISO_OTRA_VERSION });
      return true;
    } catch {
      return false;
    }
  }

  function editar() {
    setAviso(null);
    setEditando(true);
    setResponsables({ tipo: "cargando" });
    listarResponsables()
      .then((lista) => setResponsables({ tipo: "ok", lista }))
      .catch((error: unknown) => {
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setResponsables({ tipo: "error", mensaje: error instanceof ErrorApi ? error.message : "Error inesperado" });
      });
  }

  async function aEstado(ficha: ContactoDetalle, destino: EstadoContacto) {
    setAviso(null);
    setCambiandoEstado(true);
    try {
      const nueva = await cambiarEstado(ficha.id, { status: destino, version: ficha.version }, csrf);
      setEstado({ tipo: "ok", ficha: nueva });
      setAviso({ tipo: "exito", texto: `Estado cambiado a «${NOMBRE_ESTADO[nueva.status]}»` });
    } catch (error) {
      if (error instanceof ErrorApi && error.status === 401) return caducada();
      if (error instanceof ErrorApi && error.status === 409 && (await otraVersion(ficha.version))) return;
      const texto = error instanceof ErrorApi ? (error.campos.status ?? error.message) : "Error inesperado";
      setAviso({ tipo: "error", texto });
    } finally {
      setCambiandoEstado(false);
    }
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-ficha">
      <p>
        <Link to={area}>← Volver a contactos</Link>
      </p>
      {estado.tipo === "cargando" && <p>Cargando la ficha…</p>}
      {estado.tipo === "no-existe" && <h2 id="titulo-ficha">Este contacto no existe</h2>}
      {estado.tipo === "error" && (
        <>
          <h2 id="titulo-ficha">No se pudo cargar la ficha</h2>
          <p className="error" role="alert">
            {estado.mensaje}
          </p>
          <button type="button" className="secundario" onClick={() => setIntento((n) => n + 1)}>
            Reintentar
          </button>
        </>
      )}
      {estado.tipo === "ok" && (
        <Ficha
          ficha={estado.ficha}
          editando={editando}
          responsables={responsables}
          cambiandoEstado={cambiandoEstado}
          aviso={aviso}
          alEditar={editar}
          alReintentarResponsables={editar}
          alCancelar={() => setEditando(false)}
          alGuardar={(ficha) => {
            setEstado({ tipo: "ok", ficha });
            setEditando(false);
            setAviso({ tipo: "exito", texto: "Cambios guardados" });
          }}
          alConflicto={() => otraVersion(estado.ficha.version)}
          alCambiarEstado={(destino) => aEstado(estado.ficha, destino)}
        />
      )}
    </section>
  );
}

function Ficha({
  ficha,
  editando,
  responsables,
  cambiandoEstado,
  aviso,
  alEditar,
  alReintentarResponsables,
  alCancelar,
  alGuardar,
  alConflicto,
  alCambiarEstado,
}: {
  ficha: ContactoDetalle;
  editando: boolean;
  responsables: EstadoResponsables;
  cambiandoEstado: boolean;
  aviso: Aviso | null;
  alEditar: () => void;
  alReintentarResponsables: () => void;
  alCancelar: () => void;
  alGuardar: (ficha: ContactoDetalle) => void;
  alConflicto: () => Promise<boolean>;
  alCambiarEstado: (destino: EstadoContacto) => void;
}) {
  return (
    <>
      <h2 id="titulo-ficha">
        {ficha.first_name} {ficha.last_name}
      </h2>
      {aviso?.tipo === "exito" && (
        <p className="exito" role="status">
          {aviso.texto}
        </p>
      )}
      {aviso?.tipo === "conflicto" && (
        <p className="aviso" role="alert">
          {aviso.texto}
        </p>
      )}
      {aviso?.tipo === "error" && (
        <p className="error" role="alert">
          {aviso.texto}
        </p>
      )}
      {editando ? (
        <>
          {responsables.tipo === "cargando" && <p>Cargando el formulario…</p>}
          {responsables.tipo === "error" && (
            <>
              <p className="error" role="alert">
                No se pudo cargar la lista de responsables: {responsables.mensaje}
              </p>
              <div className="acciones">
                <button type="button" className="secundario" onClick={alReintentarResponsables}>
                  Reintentar
                </button>
                <button type="button" className="secundario" onClick={alCancelar}>
                  Cancelar
                </button>
              </div>
            </>
          )}
          {responsables.tipo === "ok" && (
            <FormularioContacto
              titulo="Editar contacto"
              textoGuardar="Guardar cambios"
              inicial={datosDe(ficha)}
              responsables={opcionesDeResponsable(responsables.lista, ficha)}
              guardar={(datos, csrf) =>
                actualizarContacto(ficha.id, { ...datos, owner_id: datos.owner_id ?? null, version: ficha.version }, csrf)
              }
              alGuardar={alGuardar}
              alCancelar={alCancelar}
              alConflicto={alConflicto}
            />
          )}
        </>
      ) : (
        <>
          <dl className="ficha">
            <dt>Email</dt>
            <dd>{ficha.email ?? "—"}</dd>
            <dt>Teléfono</dt>
            <dd>{ficha.phone ? formatoTelefono(ficha.phone) : "—"}</dd>
            <dt>Origen</dt>
            <dd>{NOMBRE_ORIGEN[ficha.source]}</dd>
            <dt>Estado</dt>
            <dd>{NOMBRE_ESTADO[ficha.status]}</dd>
            <dt>Responsable</dt>
            <dd>{ficha.owner_email ?? "Sin responsable"}</dd>
            <dt>Creado</dt>
            <dd>
              {formatoFecha(ficha.created_at)} · {ficha.created_by_email ?? "cuenta ya no disponible"}
            </dd>
            {ficha.version > 1 && (
              <>
                <dt>Último cambio</dt>
                <dd>
                  {formatoFecha(ficha.updated_at)} · {ficha.updated_by_email ?? "cuenta ya no disponible"}
                </dd>
              </>
            )}
          </dl>
          <div className="acciones">
            <button type="button" onClick={alEditar} disabled={cambiandoEstado}>
              Editar
            </button>
            {ACCIONES_DE_ESTADO[ficha.status].map(({ destino, texto }) => (
              <button
                key={destino}
                type="button"
                className="secundario"
                disabled={cambiandoEstado}
                onClick={() => alCambiarEstado(destino)}
              >
                {texto}
              </button>
            ))}
          </div>
          {(ficha.status === "new" || ficha.status === "contacted") && (
            <p className="ayuda">«Cita agendada» y «Cliente» se pondrán solos al gestionar sus citas.</p>
          )}
        </>
      )}
    </>
  );
}
