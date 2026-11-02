// Rutas de la app (T10; fichas de contacto en T13). Cada rol tiene su área con dirección propia; el router
// (BrowserRouter en main.tsx, MemoryRouter en las pruebas) lo pone quien monta App.

import { Route, Routes } from "react-router";

import { AreaAdmin, Bienvenida, Inicio, NoEncontrada, RutaProtegida, SoloRol } from "./Areas";
import Contactos from "./Contactos";
import FichaContacto from "./FichaContacto";
import Login from "./Login";
import { SesionProvider } from "./sesion";

export default function App() {
  return (
    <SesionProvider>
      <Routes>
        <Route path="/" element={<Inicio />} />
        <Route path="/login" element={<Login />} />
        <Route element={<RutaProtegida />}>
          <Route path="/admin" element={<SoloRol rol="admin"><AreaAdmin /></SoloRol>} />
          <Route path="/admin/contactos/:id" element={<SoloRol rol="admin"><FichaContacto /></SoloRol>} />
          <Route path="/recepcion" element={<SoloRol rol="reception"><Contactos /></SoloRol>} />
          <Route path="/recepcion/contactos/:id" element={<SoloRol rol="reception"><FichaContacto /></SoloRol>} />
          <Route path="/profesional" element={<SoloRol rol="professional"><Bienvenida /></SoloRol>} />
          <Route path="/portal" element={<SoloRol rol="client"><Bienvenida /></SoloRol>} />
        </Route>
        <Route path="*" element={<NoEncontrada />} />
      </Routes>
    </SesionProvider>
  );
}
