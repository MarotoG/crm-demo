// Rutas de la app (T10; fichas de contacto en T13; servicios en T15; área del profesional en T20,
// con «Mi agenda», que es la agenda en solo lectura con sus citas). Desde T18 cada sección tiene
// una dirección neutra (/agenda, /contactos…), la misma para todos los roles que la ven: quién la
// ve lo decide permisos.ts. El router (BrowserRouter en main.tsx, MemoryRouter en las pruebas) lo
// pone quien monta App.

import { Route, Routes } from "react-router";

import Agenda from "./Agenda";
import { ConPermiso, Inicio, NoEncontrada, RedirigirFicha, RutaProtegida, Usuarios } from "./Areas";
import Contactos from "./Contactos";
import FichaContacto from "./FichaContacto";
import Invitacion from "./Invitacion";
import Login from "./Login";
import Portal from "./Portal";
import Servicios, { MisServicios } from "./Servicios";
import { SesionProvider } from "./sesion";

export default function App() {
  return (
    <SesionProvider>
      <Routes>
        <Route path="/" element={<Inicio />} />
        <Route path="/login" element={<Login />} />
        <Route path="/invitacion" element={<Invitacion />} />
        <Route element={<RutaProtegida />}>
          <Route path="/agenda" element={<ConPermiso seccion="agenda"><Agenda /></ConPermiso>} />
          <Route path="/contactos" element={<ConPermiso seccion="contactos"><Contactos /></ConPermiso>} />
          <Route path="/contactos/:id" element={<ConPermiso seccion="ficha"><FichaContacto /></ConPermiso>} />
          <Route path="/servicios" element={<ConPermiso seccion="servicios"><Servicios /></ConPermiso>} />
          <Route path="/usuarios" element={<ConPermiso seccion="usuarios"><Usuarios /></ConPermiso>} />
          <Route path="/mi-agenda" element={<ConPermiso seccion="miAgenda"><Agenda propia /></ConPermiso>} />
          <Route path="/mis-servicios" element={<ConPermiso seccion="misServicios"><MisServicios /></ConPermiso>} />
          <Route path="/portal" element={<ConPermiso seccion="portal"><Portal /></ConPermiso>} />
          {/* Direcciones antiguas (antes de T18; /profesional, antes de T20): llevan a la nueva para no romper enlaces guardados. */}
          <Route path="/profesional" element={<Inicio />} />
          <Route path="/admin" element={<Inicio />} />
          <Route path="/recepcion" element={<Inicio />} />
          <Route path="/admin/contactos/:id" element={<RedirigirFicha />} />
          <Route path="/recepcion/contactos/:id" element={<RedirigirFicha />} />
        </Route>
        <Route path="*" element={<NoEncontrada />} />
      </Routes>
    </SesionProvider>
  );
}
