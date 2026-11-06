# Backlog atómico y calendario del CRM de clínicas

Fecha de entrega confirmada: 15/11/2026. Disponibilidad: 4–5 h de calidad al día. Desde el 31/10 al 15/11 hay 16 jornadas: 64–80 h, más lo que se haga el 30/10. Son estimaciones, no un compromiso de viabilidad de un alcance ilimitado. Confirmar hora/zona de entrega.

Prioridad confirmada: personal de clínica + portal básico de cliente; fotos después. Stack preferido: FastAPI/PostgreSQL. React/TypeScript y el detalle del alcance son propuestas revisables. Trabajo mixto alumno/IA, con inspección y supervisión en cada tarea.

## Contrato de cada tarea

Un objetivo y un cambio comprobable. Antes: inspeccionar estado, instrucciones y archivos pertinentes; explicar el plan breve. Durante: resolver únicamente la tarea y mantener contratos existentes. Después: revisar diff, ejecutar pruebas adecuadas y explicar al alumno el recorrido. Registrar estado, evidencias y próximo paso. El agente no convierte este backlog en autorización para ejecutar todas las tareas seguidas.

Sesiones de 45–90 minutos cuando sea posible; dividir una fila mayor si el alumno no puede revisar sus cambios de una vez. Al terminar el encargo actual, entregar resultados y esperar el siguiente encargo del alumno. Evitar confirmaciones repetidas para los pasos rutinarios dentro del encargo autorizado. Los tiempos incluyen una primera revisión, pero no garantizan cubrir incidencias desconocidas.

## Tareas propuestas

| ID | Tarea | Horas estimadas | Aceptación y evidencia |
|---|---|---:|---|
| T01 | Inventario local y del repositorio | 0.5 | Rutas reales, instrucciones, Git y herramientas detectadas; sin crear código ni instalar. Entregar tres próximos pasos. |
| T02a | Inventario documental de Quijote | 0.5 | Recibido y revisado; fuente sin acceso real. Consultar 14 y conservar pendientes. |
| T02b | Comprobación actual del servidor | 1 | Consulta autorizada de capacidad, redes, túnel, rutas y políticas. Diferenciar observado/documentado; sin cambios ni secretos. |
| T03 | Cerrar alcance y reglas de demo | 1 | Una clínica, cuatro roles, portal propio de consulta, servicios/citas y seguimiento; fotos aplazadas. Registrar matriz de permisos y escenario. |
| T04 | Esqueleto FastAPI y primera prueba | 1.5 | API mínima con endpoint de salud y prueba ejecutable; documentar comandos. Nada de CRUD masivo. |
| T05 | PostgreSQL y primera migración | 1.5 | Entorno local y migración mínima; arrancar/reiniciar con datos persistentes. No crear todas las tablas a ciegas. |
| T06 | Esqueleto React responsive y conexión API | 1.5 | Página mínima llama al health endpoint y muestra error si falla; build y ejecución comprobados. |
| T07 | Usuarios y cuentas de demo | 1 | Crear usuarios ficticios con hash y roles, sin contraseñas reales en código. Procedimiento reproducible. |
| T08 | Login y sesión | 2 | Login correcto/incorrecto; cookie/sesión según decisión; errores sin filtrar secretos. Pruebas API. |
| T09 | Logout y permisos básicos | 1.5 | Sesión deja de ser válida; endpoints protegidos; recepción no administra usuarios. Pruebas de acceso negativas. |
| T10 | Login en interfaz y rutas por rol | 1.5 | Entrar/salir desde navegador; acceso directo a área ajena no concede datos en API. Estados carga/error. |
| T11 | Crear contacto: backend y prueba | 1.5 | Datos válidos persisten y los inválidos se rechazan; campos mínimos, sin historia clínica. |
| T12 | Crear/listar contacto desde la interfaz | 2 | Recepción crea y recupera un contacto tras recargar; estados de formulario y lista claros. |
| T13 | Buscar y editar un contacto | 1.5 | Búsqueda y actualización conservan el ID; profesional ve solo contactos permitidos. Pruebas API/UI apropiadas. |
| T14 | Estado comercial y responsable | 1 | Transiciones simples y filtros de lead; se conserva una sola ficha al convertirlo a cliente. |
| T15 | Servicios y vínculo de profesional | 1 | Duraciones positivas y cuentas internas activas; datos iniciales suficientes para agenda, sin CRUD accesorio extenso. |
| T16 | Crear cita: caso de uso y migración | 2 | Fecha/fin, relaciones y duración validados; prueba de negocio sin navegador. |
| T17 | Concurrencia y solapamientos | 2 | Dos solicitudes simultáneas no reservan el mismo profesional/franja; cita adyacente permitida, cancelada libera según regla. |
| T18 | Agenda de recepción | 2 | Crear cita desde formulario y verla en lista diaria; filtrar profesional/fecha; no hace falta calendario drag-and-drop. |
| T19 | Reprogramar y cancelar | 1.5 | Mismas validaciones al editar; conflicto explicado, datos consistentes. Regresión de T17. |
| T20 | Área del profesional | 1.5 | Solo agenda y contactos asignados; cambio de estado permitido y prueba de acceso a cita ajena. |
| T21 | Invitación al portal y cuenta cliente | 2.5 | Recepción/admin generan enlace de un solo uso, con caducidad de 24 h, para cualquier contacto salvo Perdido (decisión T21; antes, «con al menos una cita»); el cliente elige email y contraseña. Vínculo explícito y único; enlace caducado/reutilizado rechazado; recepción no crea cuentas internas. Incluye la lista de citas en la ficha del contacto (decisión T21). Plan B: contraseña temporal del admin. |
| T21b | Email obligatorio y único por contacto | 2.5 | Un email por persona, obligatorio; teléfono opcional. La cuenta usa el email de la ficha y corregirlo cambia también el de acceso. Nota corta en ficha y cita, sin datos clínicos y sin llegar al portal. Surgida al probar T21; estimación orientativa, fuera de la suma de abajo. |
| T22 | API del portal propio | 1.5 | Lista de citas del usuario, próximas y anteriores (decisión T22: sin ruta de detalle, porque no añade datos y no deja ID que manipular); cliente A no obtiene B manipulando filtros. Sin campos internos. Hecha junto con T23. |
| T23 | Interfaz del portal de cliente | 1.5 | Acceso, citas propias y estado vacío responsive; comparación visual A/B y comprobación desde navegador. |
| T24 | Seguimiento: crear y asignar tarea | 1.5 | Tarea de contacto con responsable y vencimiento; validaciones y consulta autorizada. Decisión T24: la crean admin y recepción, solo ligada al contacto y con vencimiento por fecha; un profesional solo es responsable si tiene alguna cita con el contacto. |
| T25 | Panel de pendientes y completar | 1.5 | Recepción/profesional ven las tareas permitidas, vencidas y hechas; no se implementa push. Decisión T25: sección con contador, todas con filtro para admin y recepción, «Reabrir» sin límite, y editar y reasignar incluidos. |
| T26 | Eventos de auditoría mínimos | 1 | Acciones relevantes registradas sin secretos/payload clínico; describir límites, no afirmar inmutabilidad. Decisión T26: cambios de datos, acceso y fichas abiertas; nombres de campos y estados, sin valores; pantalla de solo lectura para administración. |
| T27 | Revisión de flujo y permisos | 2 | Login → lead → cita → seguimiento → portal; pruebas de acceso y errores relevantes; registrar resultados reales. Decisión T27: antes de congelar funciones solo entran los datos de demo; el personal se sigue mostrando por su email. |
| T28 | Publicación mínima sin datos reales | 2.5 | Proyecto/BD propios y dependencia de túnel decidida; verificar HTTPS, cabeceras y acceso del evaluador. No modificar stack ajeno por inferencia. Comprobar desde otro navegador y registrar artefacto exacto. |
| T29 | Persistencia, backup y restauración | 2 | Backup propio y restauración aislada comprobados, sin tocar bases ajenas; reversión compatible con migraciones, límites y pérdida de datos documentados. |
| T30 | README desde instalación limpia | 2 | Comprobar los apartados del PDF; comandos reales, cuentas de demo y límites. Se alimenta desde tareas previas. |
| T31 | Slides y ensayo explicativo | 2 | Presentación del problema, solución, arquitectura, demo, pruebas y aprendizaje; enlaces accesibles. |
| T32 | Grabar y publicar vídeo | 2 | Explicación propia con captura de pantalla; comprobar acceso público y añadir URL en README. |
| T33 | Paquete, enlaces y formulario | 1 | Matriz académica revisada; GitHub/slides/vídeo/demo accesibles; alumno envía y conserva confirmación si existe. |

Suma orientativa: **52,5 horas** de tareas (T21 ampliada a invitación en T03). Añadir **8 h** de aprendizaje/revisión adicional y **6 h** de margen para incidencias: **66,5 h**. Las guías y documentación se alimentan diariamente; no reservar todos los entregables para el último día. A 4 h/día hay menos holgura que a 5 h/día. Si el arranque consume el margen, reducir detalle visual, CRUD secundario y automatismos, conservando el portal básico acordado y las evidencias del TFM.

## Distribución de referencia (ajustar al avance real)

| Fechas | Objetivo |
|---|---|
| 30–31/10 | T01, T02a/T02b y T03: inventarios, alcance y preparación |
| 01–02/11 | T04–T10: esqueleto y acceso con roles |
| 03–04/11 | T11–T15: primer recorrido de contactos desde navegador |
| 05–07/11 | T16–T20: agenda y profesional; ensayo de publicación mínimo si la infraestructura está lista |
| 08–09/11 | T21–T23: portal propio y pruebas de aislamiento |
| 10/11 | T24–T26: seguimiento y eventos mínimos |
| 11–12/11 | T27–T30: estabilización, publicación/recuperación y README |
| 13/11 | T31 y preparación de grabación |
| 14/11 | T32; revisión de enlaces y permisos |
| 15/11 | T33 y margen final; intentar cerrar antes de la hora límite confirmada |

Estas bandas no sustituyen las estimaciones: si un día supera 4–5 h, desplazar trabajo a jornadas con hueco, dividir tareas y actualizar el plan. El inventario del servidor se solicita pronto; la exposición pública completa exige acceso y protección adecuados. No esperar al 11/11 para descubrir incompatibilidades.

## Puertas de revisión

- Tras T10: acceso de roles comprobado; no avanzar con privilegios solo en frontend.
- Tras T14: lead creado/editado desde navegador y persistente; alumno explica UI → API → BD.
- Tras T19: conflicto concurrente de agenda cubierto; no sustituirlo por una validación visual.
- Tras T23: dos clientes no ven información del otro. Mantener esta prioridad aunque se pospongan extras.
- Tras T27: congelar nuevas funciones y revisar matriz TFM.
- Antes de entrega: comprobar README, repositorio, slides, vídeo y formulario por separado.

## Hitos de Git propuestos

Commits pequeños por tarea coherente; una etiqueta al cerrar cada flujo demostrable: base/acceso, contactos, agenda, portal, seguimiento y candidato TFM. Versiones ilustrativas `v0.1.0` a `v0.6.0`, candidato `v0.9.0`; no son pasos obligatorios. Una etiqueta no demuestra cumplimiento ni que el software sea producto sanitario comercial listo.

## Ampliaciones aplazadas

Ideas de ampliación tras el núcleo (decisión T21, sustituye al orden de T03): PWA instalable, fotos antes/después y reserva por el cliente desde su portal. No tienen orden fijo: al cerrar el núcleo se mencionan y el alumno elige por cuál empezar según lo que más convenga, estimándola aparte y antes de grabar. La prioridad sigue siendo el personal de la clínica; el portal se queda en lo mínimo hasta entonces. Consentimiento de comunicaciones (anotado por el alumno, T21b): tener el email de un cliente no autoriza a enviarle campañas; antes de cualquier envío hará falta una casilla de autorización en el registro y revisar consentimiento y baja. No se construye ahora. Push, Stripe, facturación, widget sin registro, WhatsApp/n8n, salas y multiempresa quedan para versiones posteriores.


## Revisión de Quijote y contingencia

Se divide T02 en documental (completada) y observación (pendiente), quedando 34 filas de tareas pequeñas. La estimación se revisa a 51 h de tareas más 14 h de aprendizaje/margen: 65 h (66,5 h tras ampliar T21 en T03). No añadir esas horas como trabajo ya realizado ni prometer capacidad; si solo hay 64 h, redistribuir algo más de tiempo o reducir presentación visual/CRUD secundarios, sin eliminar los entregables ni el portal acordado.

El ensayo de publicación se prepara al cerrar T02b y se ejecuta pronto con un servicio mínimo protegido dentro del encargo que lo autorice. Antes de grabar, comprobar que la demo funciona localmente según README. El vídeo exigido por el TFM sirve además como evidencia si falla el acceso al servidor; no equivale a omitir el acceso que se prometa. Evitar cambios de versión del CRM durante la preparación final salvo correcciones justificadas; cambios de otros servicios quedan fuera del encargo.
