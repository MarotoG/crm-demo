// Secciones de la app y quién ve cada una (T18). Es el único sitio que lo decide: la barra de
// secciones, la protección de cada dirección y la página de inicio de cada rol salen de aquí.
// Si algún día una cuenta tuviera varios roles o permisos sueltos, solo cambiaría este archivo.
//
// Ocultar una sección no protege nada: quien decide es la API (403). Aquí solo se evita pedir
// datos sin sentido y se le dice a cada uno dónde está lo suyo.

import type { Rol } from "./api";

export type Seccion =
  | "agenda"
  | "contactos"
  | "ficha"
  | "servicios"
  | "usuarios"
  | "miAgenda"
  | "misServicios"
  | "pendientes"
  | "portal";

// `enBarra: false`: una página a la que se llega desde otra (la ficha), no una sección de la barra.
type DatosSeccion = { ruta: string; nombre: string; roles: readonly Rol[]; enBarra?: false };

// En el orden de la barra. Los permisos internos están anidados (admin ⊃ recepción ⊃
// profesional): quien realiza servicios no necesita otro rol, basta con asignarle el servicio (T15).
export const SECCIONES: Record<Seccion, DatosSeccion> = {
  agenda: { ruta: "/agenda", nombre: "Agenda", roles: ["admin", "reception"] },
  contactos: { ruta: "/contactos", nombre: "Contactos", roles: ["admin", "reception"] },
  // El profesional abre en solo lectura la ficha de sus contactos desde su agenda (T20); la API
  // solo se la da si el contacto tiene alguna cita con él.
  ficha: { ruta: "/contactos/:id", nombre: "Ficha de contacto", roles: ["admin", "reception", "professional"], enBarra: false },
  servicios: { ruta: "/servicios", nombre: "Servicios", roles: ["admin", "reception"] },
  usuarios: { ruta: "/usuarios", nombre: "Usuarios", roles: ["admin"] },
  miAgenda: { ruta: "/mi-agenda", nombre: "Mi agenda", roles: ["professional"] },
  misServicios: { ruta: "/mis-servicios", nombre: "Mis servicios", roles: ["professional"] },
  pendientes: { ruta: "/pendientes", nombre: "Pendientes", roles: ["admin", "reception", "professional"] },
  portal: { ruta: "/portal", nombre: "Mis citas", roles: ["client"] },
};

export function puede(rol: Rol, seccion: Seccion): boolean {
  return SECCIONES[seccion].roles.includes(rol);
}

/** Las secciones de la barra que ve un rol, en su orden. */
export function seccionesDe(rol: Rol): Seccion[] {
  return (Object.keys(SECCIONES) as Seccion[]).filter((s) => SECCIONES[s].enBarra !== false && puede(rol, s));
}

/** Adónde va cada uno al entrar: su primera sección (la agenda para admin y recepción, «Mi agenda»
 * para el profesional). */
export function inicioDe(rol: Rol): string {
  return SECCIONES[seccionesDe(rol)[0]].ruta;
}
