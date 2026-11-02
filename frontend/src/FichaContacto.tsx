// Ficha de un contacto (T13): sus datos, quién lo creó y quién lo cambió por última vez,
// y «Editar». Dirección propia (/recepcion/contactos/7, /admin/contactos/7): se puede
// recargar y ahí irán después sus citas y seguimientos.
//
// Bloqueo optimista: la ficha guarda la versión que leyó y la envía al guardar. Si otra
// persona guardó antes, la API responde 409; entonces se pide la ficha actual y, si su
// versión ha cambiado, se muestra con un aviso en vez de pisar el cambio ajeno.

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { actualizarContacto, ErrorApi, obtenerContacto, type ContactoDetalle } from "./api";
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

type EstadoFicha =
  | { tipo: "cargando" }
  | { tipo: "no-existe" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "ok"; ficha: ContactoDetalle };

/** Lo que se ve en el formulario al empezar a editar: los datos guardados, teléfono legible. */
function datosDe(ficha: ContactoDetalle): DatosFormulario {
  return {
    first_name: ficha.first_name,
    last_name: ficha.last_name,
    email: ficha.email ?? "",
    phone: ficha.phone ? formatoTelefono(ficha.phone) : "",
    source: ficha.source,
  };
}

export default function FichaContacto() {
  const { estado: sesion, caducada } = useSesion();
  const { id } = useParams();
  const contactoId = Number(id);
  const [estado, setEstado] = useState<EstadoFicha>({ tipo: "cargando" });
  const [editando, setEditando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "exito" | "conflicto"; texto: string } | null>(null);
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
          aviso={aviso}
          alEditar={() => {
            setAviso(null);
            setEditando(true);
          }}
          alCancelar={() => setEditando(false)}
          alGuardar={(ficha) => {
            setEstado({ tipo: "ok", ficha });
            setEditando(false);
            setAviso({ tipo: "exito", texto: "Cambios guardados" });
          }}
          alConflicto={async () => {
            // ¿Es otra versión (alguien guardó antes) o un duplicado? Se pregunta la ficha actual.
            try {
              const actual = await obtenerContacto(contactoId);
              if (actual.version === estado.ficha.version) return false; // duplicado: lo explica el formulario
              setEstado({ tipo: "ok", ficha: actual });
              setEditando(false);
              setAviso({ tipo: "conflicto", texto: AVISO_OTRA_VERSION });
              return true;
            } catch {
              return false;
            }
          }}
        />
      )}
    </section>
  );
}

function Ficha({
  ficha,
  editando,
  aviso,
  alEditar,
  alCancelar,
  alGuardar,
  alConflicto,
}: {
  ficha: ContactoDetalle;
  editando: boolean;
  aviso: { tipo: "exito" | "conflicto"; texto: string } | null;
  alEditar: () => void;
  alCancelar: () => void;
  alGuardar: (ficha: ContactoDetalle) => void;
  alConflicto: () => Promise<boolean>;
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
      {editando ? (
        <FormularioContacto
          titulo="Editar contacto"
          textoGuardar="Guardar cambios"
          inicial={datosDe(ficha)}
          guardar={(datos, csrf) => actualizarContacto(ficha.id, { ...datos, version: ficha.version }, csrf)}
          alGuardar={alGuardar}
          alCancelar={alCancelar}
          alConflicto={alConflicto}
        />
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
          <button type="button" onClick={alEditar}>
            Editar
          </button>
        </>
      )}
    </>
  );
}
