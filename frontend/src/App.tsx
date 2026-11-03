// Rutas de la app (T10; fichas de contacto en T13; servicios en T15). Desde T18 cada sección tiene
// una dirección neutra (/agenda, /contactos…), la misma para todos los roles que la ven: quién la
// ve lo decide permisos.ts. El router (BrowserRouter en main.tsx, MemoryRouter en las pruebas) lo
// pone quien monta App.

import { Route, Routes } from "react-router";

import Agenda from "./Agenda";
import { Bienvenida, ConPermiso, Inicio, NoEncontrada, RedirigirFicha, RutaProtegida, Usuarios } from "./Areas";
import Contactos from "./Contactos";
import FichaContacto from "./FichaContacto";
import Login from "./Login";
import Servicios, { MisServicios } from "./Servicios";
import { SesionProvider } from "./sesion";

export default function App() {
  return (
    <SesionProvider>
      <Routes>
        <Route path="/" element={<Inicio />} />
        <Route path="/login" element={<Login />} />
        <Route element={<RutaProtegida />}>
          <Route path="/agenda" element={<ConPermiso seccion="agenda"><Agenda /></ConPermiso>} />
          <Route path="/contactos" element={<ConPermiso seccion="contactos"><Contactos /></ConPermiso>} />
          <Route path="/contactos/:id" element={<ConPermiso seccion="contactos"><FichaContacto /></ConPermiso>} />
          <Route path="/servicios" element={<ConPermiso seccion="servicios"><Servicios /></ConPermiso>} />
          <Route path="/usuarios" element={<ConPermiso seccion="usuarios"><Usuarios /></ConPermiso>} />
          <Route path="/profesional" element={<ConPermiso seccion="profesional"><Bienvenida /><MisServicios /></ConPermiso>} />
          <Route path="/portal" element={<ConPermiso seccion="portal"><Bienvenida /></ConPermiso>} />
          {/* Direcciones de antes de T18: llevan a la nueva para no romper enlaces guardados. */}
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
