// Secciones de la app y quién ve cada una (T18). Es el único sitio que lo decide: la barra de
// secciones, la protección de cada dirección y la página de inicio de cada rol salen de aquí.
// Si algún día una cuenta tuviera varios roles o permisos sueltos, solo cambiaría este archivo.
//
// Ocultar una sección no protege nada: quien decide es la API (403). Aquí solo se evita pedir
// datos sin sentido y se le dice a cada uno dónde está lo suyo.

import type { Rol } from "./api";

export type Seccion = "agenda" | "contactos" | "servicios" | "usuarios" | "profesional" | "portal";

type DatosSeccion = { ruta: string; nombre: string; roles: readonly Rol[] };

// En el orden de la barra. Los permisos internos están anidados (admin ⊃ recepción ⊃
// profesional): quien realiza servicios no necesita otro rol, basta con asignarle el servicio (T15).
export const SECCIONES: Record<Seccion, DatosSeccion> = {
  agenda: { ruta: "/agenda", nombre: "Agenda", roles: ["admin", "reception"] },
  contactos: { ruta: "/contactos", nombre: "Contactos", roles: ["admin", "reception"] },
  servicios: { ruta: "/servicios", nombre: "Servicios", roles: ["admin", "reception"] },
  usuarios: { ruta: "/usuarios", nombre: "Usuarios", roles: ["admin"] },
  profesional: { ruta: "/profesional", nombre: "Mi área", roles: ["professional"] },
  portal: { ruta: "/portal", nombre: "Mis citas", roles: ["client"] },
};

export function puede(rol: Rol, seccion: Seccion): boolean {
  return SECCIONES[seccion].roles.includes(rol);
}

/** Las secciones que ve un rol, en el orden de la barra. */
export function seccionesDe(rol: Rol): Seccion[] {
  return (Object.keys(SECCIONES) as Seccion[]).filter((s) => puede(rol, s));
}

/** Adónde va cada uno al entrar: su primera sección (la agenda para admin y recepción). */
export function inicioDe(rol: Rol): string {
  return SECCIONES[seccionesDe(rol)[0]].ruta;
}
