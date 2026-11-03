// Configuración común de las pruebas de la interfaz (T18).
//
// Testing Library espera como mucho 1 s a que aparezca algo (findBy…). Con los archivos de pruebas
// en paralelo, la primera prueba de cada archivo arranca en frío y en Windows ha llegado a tardar
// unos 1,7 s: fallaba de vez en cuando sin que la interfaz estuviera mal. 3 s solo alarga la espera
// máxima; una prueba que no encuentra lo que busca sigue fallando.
import { configure } from "@testing-library/react";

configure({ asyncUtilTimeout: 3000 });
