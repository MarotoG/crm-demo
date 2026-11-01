# Matriz de cumplimiento y evidencias del TFM

Fuente: `M12_A01_D01__documentacion_tfm.md`, contrastado con el PDF original de dos páginas. Estado inicial de esta edición: pendiente de verificar sobre el CRM. Los IDs TFM-Rxx son de organización local, no numeración oficial del PDF.

## Requisitos académicos

| ID | Exigencia o condición | Fuente | Evidencia a preparar | Estado |
|---|---|---|---|---|
| TFM-R01 | Aplicación real adaptada al nivel; conocimientos del máster, originalidad y valor personal como objetivos | p. 1, Objetivo | Problema/usuario, flujo funcional y explicación de decisiones propias | Pendiente |
| TFM-R02 | README completo y detallado | p. 1, 1 | README del CRM con descripción, stack, instalación/ejecución, estructura y funciones | En curso: `README.md` provisional con `.env`, PostgreSQL en Docker, migraciones, pruebas, arranque del backend y del frontend comprobados en Windows (T04–T06, 30/10/2026) y procedimiento de cuentas de demo (T07, 31/10/2026); faltan funciones, credenciales de prueba publicadas, despliegue, slides y vídeo |
| TFM-R03 | Cuenta de prueba si hay login | p. 1, 1.f; p. 2, Entrega | Usuario y contraseña de demo en README y formulario; acceso comprobado | En curso: 4 cuentas ficticias (una por rol) creadas con `python -m app.seed_demo`, hash Argon2id, contraseñas solo en `.env` local (T07, 31/10/2026). Login por API con sesión en servidor (T08, 31/10/2026); falta pantalla de login (T10) y probar el acceso con las credenciales finales. Decisión abierta antes de la entrega: el PDF pide las credenciales en README y formulario; el alumno prefiere entregarlas aparte al profesor |
| TFM-R04 | Código en GitHub; público por defecto | p. 2, 2 | URL accesible y versión entregable identificada | En curso: https://github.com/MarotoG/crm-demo, público (comprobado sin credenciales el 31/10/2026; último commit comprobado `e42670a`, T07); versión entregable por identificar |
| TFM-R05 | Si es privado: justificación y permisos al evaluador indicado | p. 2, 2.b | Justificación y acceso de mouredev@gmail.com comprobados | No aplica mientras se mantenga público (decisión T03, 30/10/2026); revisar si cambia |
| TFM-R06 | Slides del proyecto | p. 2, 4 | URL pública o archivo junto al código, con referencia en README | Pendiente |
| TFM-R07 | Vídeo con explicación propia y captura de pantalla | p. 2, 5 | Grabación revisada; pantalla visible y explicación del alumno | Pendiente |
| TFM-R08 | URL pública del vídeo en documentación | p. 2, 5.a | Enlace en README probado sin depender de la sesión del propietario | Pendiente |
| TFM-R09 | Documentación, información del despliegue y slides/referencia en el directorio del código | p. 2, tras requisito 5 | Revisión del repositorio entregado; estado del despliegue descrito fielmente | Pendiente |
| TFM-R10 | Entrega mediante el formulario de la lección Proyecto Final | p. 2, Entrega | Formulario localizado y envío realizado por el alumno, con comprobación disponible | Pendiente |
| TFM-R11 | Datos y URLs del formulario | p. 2, Entrega | Nombre, email de inscripción, repo, slides, vídeo y despliegue/cuenta si corresponden | Pendiente |

## Recomendación del PDF y objetivo del alumno

| ID | Naturaleza | Resultado | Evidencia | Estado |
|---|---|---|---|---|
| TFM-D01 | Despliegue recomendado por el PDF; objetivo expreso del alumno | CRM accesible en servidor propio y URL documentada si existe | Uso desde navegador externo, acceso de demo y persistencia | Pendiente |

Rostro en vídeo: opcional. Fecha oficial: consultar el temario; no está en el PDF. Presentación y vídeo: no hay duración especificada. La adecuación técnica no sustituye la entrega documental.

## Formato para actualizar la evidencia

Para cada fila anota: estado (pendiente/en curso/verificado/no aplica con motivo), ruta o URL, fecha de comprobación, versión/commit si corresponde, resultado observado y límite conocido. Solo usa «no aplica» para condiciones que realmente no concurren; no lo uses para omitir README, GitHub, slides, vídeo o formulario.

## Comprobación antes de entregar

- Abrir el repositorio con el acceso previsto; si es privado, comprobar la excepción y permisos.
- Seguir README desde un entorno limpio o reproducible; registrar instalación y ejecución reales.
- Abrir las slides y el vídeo con los permisos del evaluador; revisar pantalla y explicación.
- Si hay login, probar las credenciales de demo y su alcance; utilizar datos ficticios.
- Si hay publicación, abrir la URL real y comprobar el flujo; reflejar su estado exacto en README.
- Verificar que el formulario tiene los enlaces finales, sin marcadores pendientes; conservar evidencia del envío cuando exista.

## Criterios técnicos del proyecto (separados de exigencias académicas)

Persistencia, validación, permisos cuando exista acceso restringido, errores comprensibles, pruebas según riesgo, configuración sin secretos reales y recuperación del despliegue son criterios de calidad del CRM. Se concretan según el alcance aprobado y no se atribuyen al PDF como baremo numérico.
