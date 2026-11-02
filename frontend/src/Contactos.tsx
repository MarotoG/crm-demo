// Contactos (T12): alta, lista de los 20 más recientes y búsqueda mientras se escribe.
// Lo usan recepción (/recepcion) y administración (/admin). Quién puede ver y crear lo
// decide la API (403 para profesional y cliente); aquí solo se muestra.

import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";

import {
  crearContacto,
  ErrorApi,
  listarContactos,
  type Contacto,
  type EstadoContacto,
  type ListaContactos,
  type NuevoContacto,
  type OrigenContacto,
} from "./api";
import { AREA_DE, useSesion } from "./sesion";

/** Espera tras la última tecla antes de buscar: no se lanza una petición por letra. */
export const PAUSA_BUSQUEDA_MS = 300;

// Sin tildes (T12b): el MVP es para clínicas de EE. UU. El mismo texto que da la API (422).
export const AVISO_TILDES = "No se permiten tildes ni caracteres especiales (á, ñ, ü…)";

/** Cualquier carácter fuera de ASCII: tildes, ñ, ü, emojis, letras de otros alfabetos… */
export function tieneTildes(texto: string): boolean {
  return [...texto].some((c) => c.charCodeAt(0) > 0x7f);
}

export const NOMBRE_ORIGEN: Record<OrigenContacto, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  google: "Google",
  website: "Web de la clínica",
  referral: "Recomendación",
  walk_in: "En persona",
  other: "Otro",
};

export const NOMBRE_ESTADO: Record<EstadoContacto, string> = {
  new: "Nuevo",
  contacted: "Contactado",
  scheduled: "Cita agendada",
  client: "Cliente",
  lost: "Perdido",
};

/** +12125550123 → (212) 555-0123; los de otros países, tal cual (E.164). */
export function formatoTelefono(telefono: string): string {
  const eeuu = /^\+1(\d{3})(\d{3})(\d{4})$/.exec(telefono);
  return eeuu ? `(${eeuu[1]}) ${eeuu[2]}-${eeuu[3]}` : telefono;
}

// Zona de la clínica (decisión T03): las fechas se muestran en su hora, y se dice cuál es.
export const ZONA_CLINICA = "America/New_York";
const FORMATO_FECHA = new Intl.DateTimeFormat("es-ES", { dateStyle: "short", timeStyle: "short", timeZone: ZONA_CLINICA });

/** 2026-11-02T23:05:00Z → «2/11/26, 18:05 (hora de Nueva York)». */
export function formatoFecha(iso: string): string {
  return `${FORMATO_FECHA.format(new Date(iso))} (hora de Nueva York)`;
}

type EstadoLista ={ tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "ok"; lista: ListaContactos };

export default function Contactos() {
  const { caducada } = useSesion();
  const [texto, setTexto] = useState(""); // lo que hay escrito en el buscador
  const [busqueda, setBusqueda] = useState(""); // lo que se busca, tras la pausa
  const [recarga, setRecarga] = useState(0);
  const [lista, setLista] = useState<EstadoLista>({ tipo: "cargando" });
  const [formularioAbierto, setFormularioAbierto] = useState(false);
  const [creado, setCreado] = useState<string | null>(null);

  useEffect(() => {
    const espera = setTimeout(() => setBusqueda(texto.trim()), PAUSA_BUSQUEDA_MS);
    return () => clearTimeout(espera);
  }, [texto]);

  useEffect(() => {
    // Si llega tarde la respuesta de una búsqueda anterior, se descarta: solo vale la última.
    let vigente = true;
    setLista({ tipo: "cargando" });
    listarContactos(busqueda)
      .then((resultado) => vigente && setLista({ tipo: "ok", lista: resultado }))
      .catch((error: unknown) => {
        if (!vigente) return;
        if (error instanceof ErrorApi && error.status === 401) return caducada();
        setLista({ tipo: "error", mensaje: error instanceof ErrorApi ? error.message : "Error inesperado" });
      });
    return () => {
      vigente = false;
    };
  }, [busqueda, recarga, caducada]);

  function alCrear(contacto: Contacto) {
    setFormularioAbierto(false);
    setCreado(`Contacto creado: ${contacto.first_name} ${contacto.last_name}`);
    // Se vacía la búsqueda para que el nuevo aparezca el primero de la lista.
    setTexto("");
    setBusqueda("");
    setRecarga((n) => n + 1);
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-contactos">
      <h2 id="titulo-contactos">Contactos</h2>

      {creado && (
        <p className="exito" role="status">
          {creado}
        </p>
      )}

      {formularioAbierto ? (
        <FormularioContacto guardar={crearContacto} alGuardar={alCrear} alCancelar={() => setFormularioAbierto(false)} />
      ) : (
        <button
          type="button"
          onClick={() => {
            setCreado(null);
            setFormularioAbierto(true);
          }}
        >
          Nuevo contacto
        </button>
      )}

      <label className="buscador">
        Buscar por nombre, apellidos, email o teléfono
        <input
          type="search"
          value={texto}
          maxLength={100}
          aria-describedby={tieneTildes(texto) ? "aviso-busqueda" : undefined}
          onChange={(e) => setTexto(e.target.value)}
        />
      </label>
      {/* Se busca igual (no encontrará nada): el aviso recuerda la norma a quien la olvide. */}
      {tieneTildes(texto) && (
        <p className="aviso-campo" id="aviso-busqueda">
          {AVISO_TILDES}
        </p>
      )}

      {lista.tipo === "cargando" && <p>Cargando contactos…</p>}
      {lista.tipo === "error" && (
        <>
          <p className="error" role="alert">
            {lista.mensaje}
          </p>
          <button type="button" className="secundario" onClick={() => setRecarga((n) => n + 1)}>
            Reintentar
          </button>
        </>
      )}
      {lista.tipo === "ok" && <ListaDeContactos lista={lista.lista} busqueda={busqueda} />}
    </section>
  );
}

function ListaDeContactos({ lista, busqueda }: { lista: ListaContactos; busqueda: string }) {
  const { estado } = useSesion();
  // Cada nombre abre su ficha (T13) dentro del área de quien la mira: /recepcion o /admin.
  const area = estado.tipo === "dentro" ? AREA_DE[estado.usuario.role] : "";
  if (lista.items.length === 0) {
    return (
      <p>
        {busqueda
          ? `No hay contactos que coincidan con «${busqueda}».`
          : "Todavía no hay contactos. Crea el primero con «Nuevo contacto»."}
      </p>
    );
  }
  return (
    <>
      <p className="resumen">
        {lista.total > lista.items.length
          ? `Mostrando los ${lista.items.length} más recientes de ${lista.total}. Busca para encontrar los demás.`
          : `${lista.total} ${lista.total === 1 ? "contacto" : "contactos"}`}
      </p>
      <ul className="contactos">
        {lista.items.map((c) => (
          <li key={c.id} className="contacto">
            <Link className="contacto__nombre" to={`${area}/contactos/${c.id}`}>
              {c.first_name} {c.last_name}
            </Link>
            <span className="contacto__datos">
              {[c.email, c.phone && formatoTelefono(c.phone)].filter(Boolean).join(" · ")}
            </span>
            <span className="contacto__meta">
              {NOMBRE_ESTADO[c.status]} · {NOMBRE_ORIGEN[c.source]}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

const VACIO = { first_name: "", last_name: "", email: "", phone: "", source: "" as OrigenContacto | "" };

type Campo = keyof typeof VACIO;

const ETIQUETAS: Record<Campo, string> = {
  first_name: "Nombre",
  last_name: "Apellidos",
  email: "Email",
  phone: "Teléfono",
  source: "Origen",
};

const CAMPOS_SIN_TILDES: Campo[] = ["first_name", "last_name", "email"];

export type DatosFormulario = typeof VACIO;

/**
 * Formulario de contacto para el alta (T12) y la edición (T13): mismos campos y mismas
 * comprobaciones; quien lo usa decide qué hace al guardar (`guardar`) y con el resultado.
 */
export function FormularioContacto<T>({
  titulo = "Nuevo contacto",
  textoGuardar = "Guardar contacto",
  inicial = VACIO,
  guardar,
  alGuardar,
  alCancelar,
  alConflicto,
}: {
  titulo?: string;
  textoGuardar?: string;
  inicial?: DatosFormulario;
  guardar: (datos: NuevoContacto, csrf: string) => Promise<T>;
  alGuardar: (resultado: T) => void;
  alCancelar: () => void;
  /** Ante un 409, devuelve true si quien usa el formulario lo ha resuelto (otra versión, T13). */
  alConflicto?: () => Promise<boolean>;
}) {
  const { estado, caducada } = useSesion();
  const [datos, setDatos] = useState(inicial);
  const [errores, setErrores] = useState<Partial<Record<Campo, string>>>({});
  const [general, setGeneral] = useState<string[]>([]);
  const [guardando, setGuardando] = useState(false);
  if (estado.tipo !== "dentro") return null;
  const csrf = estado.usuario.csrf_token;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErrores({});
    setGeneral([]);
    // Tildes y origen se comprueban aquí para avisar sin esperar a la API (que repite las
    // tildes y daría el origen en inglés); el resto lo valida la API.
    const previos: Partial<Record<Campo, string>> = {};
    for (const nombre of CAMPOS_SIN_TILDES) if (tieneTildes(datos[nombre])) previos[nombre] = AVISO_TILDES;
    if (!datos.source) previos.source = "Elige de dónde llegó el contacto";
    if (!datos.source || Object.keys(previos).length) {
      setErrores(previos);
      return;
    }
    setGuardando(true);
    try {
      const nuevo: NuevoContacto = { ...datos, source: datos.source };
      alGuardar(await guardar(nuevo, csrf));
    } catch (error) {
      setGuardando(false);
      if (!(error instanceof ErrorApi)) return setGeneral(["Error inesperado"]);
      if (error.status === 401) return caducada();
      if (error.status === 422) {
        setErrores(error.campos);
        setGeneral(error.general.length || Object.keys(error.campos).length ? error.general : [error.message]);
        return;
      }
      if (error.status === 409 && alConflicto && (await alConflicto())) return;
      setGeneral([error.message]); // 409 duplicado, 403, 503, sin conexión…
    }
  }

  /** Al cambiar un campo, su error anterior deja de valer: si no, seguiría visible ya corregido. */
  function cambiar(nombre: Campo, valor: string) {
    setDatos({ ...datos, [nombre]: valor });
    setErrores(({ [nombre]: _anterior, ...resto }) => resto);
  }

  function campo(nombre: Campo, tipo: "text" | "email" | "tel", autoComplete: string) {
    // El aviso de tildes sale mientras se escribe, sin esperar a pulsar «Guardar».
    const error =
      errores[nombre] ?? (CAMPOS_SIN_TILDES.includes(nombre) && tieneTildes(datos[nombre]) ? AVISO_TILDES : undefined);
    // El error va fuera de la etiqueta: si no, formaría parte del nombre del campo al leerlo.
    return (
      <div className="campo">
        <label htmlFor={`contacto-${nombre}`}>{ETIQUETAS[nombre]}</label>
        <input
          id={`contacto-${nombre}`}
          type={tipo}
          autoComplete={autoComplete}
          value={datos[nombre]}
          maxLength={nombre === "email" ? 254 : 100}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `error-${nombre}` : undefined}
          onChange={(e) => cambiar(nombre, e.target.value)}
        />
        {error && (
          <span className="error" id={`error-${nombre}`}>
            {error}
          </span>
        )}
      </div>
    );
  }

  return (
    <form className="formulario" onSubmit={enviar} noValidate aria-label={titulo}>
      {campo("first_name", "text", "off")}
      {campo("last_name", "text", "off")}
      {campo("email", "email", "off")}
      {campo("phone", "tel", "off")}
      <p className="ayuda">Indica al menos un email o un teléfono. Teléfonos de EE. UU.: (212) 555-0123; de otros países, con + y el prefijo.</p>
      <div className="campo">
        <label htmlFor="contacto-source">{ETIQUETAS.source}</label>
        <select
          id="contacto-source"
          value={datos.source}
          aria-invalid={errores.source ? true : undefined}
          aria-describedby={errores.source ? "error-source" : undefined}
          onChange={(e) => cambiar("source", e.target.value)}
        >
          <option value="">Elige el origen…</option>
          {Object.entries(NOMBRE_ORIGEN).map(([valor, nombre]) => (
            <option key={valor} value={valor}>
              {nombre}
            </option>
          ))}
        </select>
        {errores.source && (
          <span className="error" id="error-source">
            {errores.source}
          </span>
        )}
      </div>
      {general.map((mensaje) => (
        <p key={mensaje} className="error" role="alert">
          {mensaje}
        </p>
      ))}
      <div className="acciones">
        <button type="submit" disabled={guardando}>
          {guardando ? "Guardando…" : textoGuardar}
        </button>
        <button type="button" className="secundario" onClick={alCancelar} disabled={guardando}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
