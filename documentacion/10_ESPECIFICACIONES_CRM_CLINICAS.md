# CRM para pequeñas clínicas estéticas — especificaciones revisadas

Edición: 2026-10-30. Revisión del borrador `especificaciones_t_cnicas_y_hoja_de_ruta.md`, conservado como referencia. Proyecto desde cero en `D:\CRMProject`, con VS Code y control de versiones en GitHub. Este documento propone el diseño; no acredita implementación ni cumplimiento normativo de un producto comercial.

## 1. Decisiones confirmadas y propuestas

**Confirmado por el alumno:** mercado inicial Estados Unidos; clínicas estéticas pequeñas/medianas locales, no grandes franquicias; entrega 15/11/2026; 4–5 horas de calidad diarias; aprendizaje mixto con supervisión y trabajo dividido; preferencia FastAPI y PostgreSQL. Prioridad acordada: personal de clínica y portal básico del cliente; fotos antes/después después del TFM.

**Entorno comunicado:** PC local con VS Code, versiones en GitHub, servidor físico antiguo con Linux, acceso SSH y Docker funcionando. Dominio propio y propuesta de Cloudflare. Recursos, arquitectura CPU, puertos, servicios existentes y configuración real de red no inspeccionados.

**Propuestas de esta revisión, pendientes de validar al iniciar:** React + TypeScript + Vite, una clínica por instancia, cuatro roles, agenda sin salas y seguimientos internos. La hora/zona exacta de entrega, el estado estadounidense inicial, la zona horaria de la clínica, el hardware y la extensión IA concreta de VS Code siguen pendientes.

## 2. Visión de producto y alcance del TFM

Ayudar a una clínica pequeña a pasar de una consulta comercial a una cita y un seguimiento, manteniendo un portal de cliente que solo muestre su propia información. Diferenciación propuesta: seguimiento pendiente visible y trazabilidad del recorrido lead → cita → seguimiento con una experiencia en español adaptada al móvil. No afirmar validación de mercado sin entrevistar usuarios.

Una sola web responsive con áreas según rol. Una PWA permite instalación desde navegadores compatibles; no equivale a publicar apps nativas en App Store o Google Play. El mismo backend y las mismas reglas sirven a escritorio y móvil.

Para el TFM se usan exclusivamente datos ficticios y cuentas de demostración. La versión académica puede demostrar reglas y arquitectura sin declararse lista para pacientes reales o venderse como servicio clínico conforme a HIPAA. El paso a comercialización requiere evaluación adicional técnica, operativa y jurídica contextualizada.

### Núcleo propuesto para entregar

1. Login/logout y permisos de administrador, recepción, profesional y cliente.
2. Captura interna de lead/contacto, búsqueda y actualización de estado comercial.
3. Servicios con duración; agenda de citas por profesional, con cancelación y rechazo de solapamientos.
4. Tarea de seguimiento asignada a un miembro del personal, fecha prevista y marcado de realizada. Panel de pendientes; no requiere push ni automatización.
5. Portal básico de cliente: consultar sus próximas citas y el detalle permitido de las mismas, sin ver clientes ajenos ni información interna. Acceso web y móvil.
6. Datos de demostración y un recorrido completo comprobable.
7. Documentos del TFM: README, GitHub, slides, vídeo propio con pantalla, enlaces y formulario. Despliegue recomendado académicamente y objetivo personal.

El MVP no incluye autogestión pública de reservas. La recepción registra al lead y reserva; el cliente consulta desde su portal. Publicar una agenda de disponibilidad y dejar reservar introduce identificación, abuso y concurrencia adicionales: se planifica después.

### Fuera del núcleo, sin perder la visión comercial

Fotos antes/después; historial clínico, alergias y notas SOAP; consentimientos digitales; recurso/sala; cobros Stripe, depósitos, facturación fiscal y caja; widget/iframe público; Meta Ads; WhatsApp/SMS/email automatizado; notificaciones push; multiempresa y suscripciones SaaS; app nativa; trabajo offline con información personal. No añadir estas piezas por iniciativa del agente antes de cerrar el núcleo y entregables.

Si queda margen tras cerrar el núcleo, se elegirá entre las ideas de ampliación (sección 14). Si se elige la PWA instalable: shell estático y prueba en dispositivos reales, sin cachear API autenticada ni datos personales para offline.

## 3. Stack recomendado y alternativas

| Capa | Propuesta | Motivo para este proyecto |
|---|---|---|
| API | Python + FastAPI + validación de modelos | Preferencia del alumno, API explícita y documentación OpenAPI |
| Persistencia | PostgreSQL + SQLAlchemy + Alembic | Relaciones, transacciones y migraciones versionadas |
| Frontend | React + TypeScript + Vite + React Router | Interfaz privada responsive, rutas por área y contrato tipado con API |
| Estilo | CSS sencillo o una única biblioteca accesible | Reutilizar formularios/estados; evitar cambiar de sistema visual |
| Pruebas | pytest para API/reglas y pruebas de navegador para flujos críticos | Verificar permisos, agenda, persistencia y portal |
| Publicación | Docker Compose: interfaz/proxy, API y PostgreSQL; túnel según infraestructura | Entorno reproducible en el servidor existente |
| Versiones | Git con commits pequeños y GitHub | Revisar cambios y conservar evidencias de avance |

Fijar versiones estables y compatibles al preparar el entorno; conservar archivos de bloqueo y no usar versiones candidatas por novedad. Empezar con SQLAlchemy síncrono y un driver compatible si simplifica el aprendizaje; no mezclar acceso bloqueante en manejadores asíncronos sin comprender su ejecución.

Node.js puede ser necesario para construir el frontend; el backend de negocio sería FastAPI, no un segundo backend Node. No se necesita Next.js ni SSR para el área privada propuesta. Si se optase por Django con su administración integrada se reduciría parte del trabajo de gestión, pero cambiar de stack añade aprendizaje: mantendría FastAPI salvo una limitación concreta del entorno o del equipo.

## 4. Arquitectura proporcionada

Una aplicación modular y una base de datos por instancia de clínica, sin microservicios ni n8n en el núcleo. Separar las reglas de citas/seguimiento, los casos de uso, los adaptadores HTTP y la persistencia cuando permita probarlos con claridad. Evitar una clase o interfaz por cada operación CRUD si no resuelve un problema real.

Propuesta lógica: navegador → HTTPS/dominio → túnel si existe → interfaz/proxy del CRM → API `/api` → PostgreSQL privado. Una sola procedencia web simplifica cookies y configuración; sigue siendo necesario proteger las peticiones que cambian estado.

No se fija el nombre de un proxy nuevo antes de conocer el que ya existe. PostgreSQL no se publica a Internet. La base de datos conserva un volumen persistente; backups y restauración se prueban. El entorno local y el servidor tienen configuración separada. No alterar contenedores, redes ni túneles ajenos al CRM.

Cloudflare Tunnel, si es el mecanismo elegido, usa conexiones salientes y no necesita abrir puertos de entrada en el router para publicar a través del túnel. Esto no determina cómo está configurado el SSH ni sustituye la autorización de la aplicación. Revisar la infraestructura antes de tocar DNS, firewall o proxy. La configuración actual no ha sido inspeccionada.

## 5. Usuarios y permisos: cuatro roles, una sola aplicación

| Operación propuesta | Administrador | Recepción | Profesional | Cliente |
|---|---|---|---|---|
| Gestión de usuarios internos | Sí | No | No | No |
| Leads/contactos administrativos | Sí | Sí | Los que tienen alguna cita (pasada o futura) con él | Solo su perfil permitido |
| Crear/reprogramar/cancelar cita | Sí | Sí | Consultar las asignadas; cambios clínicos fuera del núcleo | Solo consulta propia en esta versión |
| Consultar agenda | Clínica | Clínica | Propia | Sus citas |
| Marcar cita realizada/no presentado | Sí | Sí | Solo las asignadas | No |
| Ver/gestionar seguimientos internos | Sí | Todos los de la clínica | Los asignados | No |
| Invitar al portal (cuenta de cliente) | Sí | Sí, solo rol cliente; cualquier contacto salvo Perdido (decisión T21) | No | Acepta su propia invitación |
| Consultar o subir fotos | Fuera del núcleo | Fuera del núcleo | Fuera del núcleo | Fuera del núcleo |

Definir la autorización en cada caso de uso del backend, incluidos filtros y acceso por ID. Ocultar un botón no protege un endpoint. Para el portal usar la relación entre usuario autenticado y contacto; un parámetro `contact_id` aportado por el navegador no decide la identidad. Los endpoints de cliente devuelven solo los campos permitidos, sin notas internas ni datos de otros profesionales/clientes.

Prueba mínima: cliente A no obtiene las citas de B ni cambiando una URL; recepción no puede asignarse rol de administrador; profesional A no modifica citas de B. Cuando no deba revelarse la existencia de un registro, responder sin filtrar su información. Aplicar también a listas, búsquedas y exportaciones futuras.

Provisionar cuentas de demo mediante un procedimiento reproducible. El vínculo usuario-cliente debe ser explícito y único, y sale de la invitación; no vincular automáticamente por un email que cualquiera pueda introducir. Registro público y recuperación de contraseña por email quedan fuera del núcleo; limitar la demo y describir esa restricción antes de un uso real. La cuenta de cliente se obtiene por invitación de un solo uso (sección 14).

## 6. Modelo de datos mínimo propuesto

| Entidad | Campos/relaciones relevantes |
|---|---|
| users | id, email normalizado único, password_hash, role, active; vínculo único a contact para el cliente; su email es el de la ficha (T21b) |
| sessions | Identificador/token opaco protegido, usuario, vencimiento y revocación; si se elige esta estrategia |
| contacts | id, nombre, email obligatorio y único, teléfono opcional y único, nota corta, origen, estado comercial, responsable, fechas; sin alergias, DOB ni historia clínica en el núcleo |
| services | id, nombre, duración positiva, activo |
| appointments | id, contact_id, professional_id, service_id, start_at, end_at, status, nota corta, created_by, fechas de actualización |
| follow_up_tasks | id, contact_id, assigned_to, due_on (fecha, sin hora), texto administrativo limitado, created_by, created_at, completed_at, completed_by, version; sin enlace a una cita (decisión T24) |
| audit_events | actor, acción, tipo/id objetivo, instante y resultado necesario; sin credenciales ni contenido sensible completo |

Un lead y un cliente son estados/relaciones del mismo contacto, no dos fichas duplicadas. La regla exacta de conversión se acuerda; no crear un paciente clínico automáticamente por cualquier visita al widget. Cada contacto puede tener muchas citas/seguimientos; una cuenta de cliente solo está vinculada a su contacto.

Para una clínica por instancia no se promete multi-tenancy añadiendo un `clinic_id` decorativo. Una segunda clínica requiere otra instancia con separación de datos, cuentas y volúmenes; el SaaS compartido posterior necesita diseño y pruebas de aislamiento propios.

## 7. Agenda y seguimientos

Persistir inicio y fin con zona temporal apropiada (`timestamptz`); configurar una zona IANA de la clínica y mostrarla claramente. El mercado estadounidense no fija una sola zona horaria. Probar al menos límites de fechas y cambios de horario si la zona los utiliza.

Reglas: fin posterior a inicio; profesional activo autorizado; contacto/servicio válidos; duración de la cita registrada al crearla; restricciones de transición de estado. Cambiar después la duración de un servicio no reescribe citas históricas.

Evitar solapamientos por profesional usando intervalos semiabiertos `[inicio, fin)`: una cita puede comenzar justo cuando termina otra. Considerar para la restricción todas las citas que reservan tiempo, excluyendo canceladas según la regla aceptada. Validar también reprogramación y asignación de profesional, no solo creación.

Una consulta previa de disponibilidad no basta ante dos peticiones simultáneas. Usar una transacción y una restricción de exclusión de PostgreSQL, o una alternativa equivalente justificada y probada. Traducir el conflicto a una respuesta comprensible (por ejemplo 409). Prueba: dos reservas concurrentes para el mismo profesional y franja no pueden quedar ambas guardadas. Salas y bloqueo por recursos se añaden después del TFM.

Seguimiento MVP: crear tarea manual ligada al contacto (decisión T24, sección 14), asignarla y verla por vencimiento. Notificación inicial significa indicador/listado dentro del sistema, no una promesa de push cuando está cerrado. Posteriormente añadir canales, consentimiento/preferencias, programación fiable, reintentos y prevención de duplicados.

## 8. Autenticación y seguridad proporcional

Propuesta para web de una sola procedencia: sesiones de servidor con cookie HttpOnly y Secure en publicación, política SameSite apropiada, vencimiento/revocación y protección CSRF en cambios de estado. La implementación debe apoyarse en componentes mantenidos; documentar por qué se elige y comprobar login/logout y permisos. JWT con refresh no es obligatorio para FastAPI ni equivale a más seguridad. Si se decide usarlo, documentar almacenamiento, revocación y pruebas en vez de implementar ambas estrategias.

Contraseñas con hash de contraseña moderno (p. ej. Argon2id mediante biblioteca mantenida). Un hash no es cifrado reversible. HTTPS protege el tránsito; cifrado de disco/volúmenes y de backups es otro control con claves y recuperación independientes. No afirmar que Docker cifra sus volúmenes por defecto.

Los eventos de auditoría ayudan a seguir acciones; una tabla normal no es inmutable. Restringir permisos y documentar el alcance; no prometer resistencia a manipulación ni cumplimiento por su mera existencia. Si la auditoría es exigida para una acción, definir cómo se conserva al confirmar esa acción y probar fallos relevantes. El registro de accesos a imágenes/datos clínicos se diseña con ese futuro módulo.

No almacenar secretos reales en GitHub, README o prompts. El TFM sí requiere credenciales de una cuenta limitada de demo si hay login: usar datos ficticios y diferenciarla de cuentas de infraestructura. Desactivar modo debug en publicación y sanear mensajes de error/logs.

## 9. HIPAA, consentimientos y paso a producto comercial

El usuario confirma Estados Unidos como mercado. El borrador presupone que toda clínica estética está automáticamente sujeta a HIPAA; hay que evaluar si la clínica y sus operaciones encajan en entidad cubierta y si el proveedor actúa como business associate. HHS delimita ese ámbito. Confirmar además estado, clientes y servicios antes del uso real; no tratar HIPAA como la única cuestión normativa.

Si se trata ePHI bajo HIPAA, autoalojar, cifrar o tener TLS no bastan para concluir cumplimiento. Deben evaluarse los proveedores y acuerdos pertinentes, incluido BAA cuando corresponda; también servicios intermediarios, copias, logs, notificaciones e imágenes según el flujo real. No asumir que un plan o túnel contratado admite ese tratamiento sin comprobar sus condiciones y responsabilidades.

Un checkbox de «consentimiento firmado en papel» registra una declaración del personal; no verifica el documento, validez, alcance, versión ni permisos de uso de imágenes. No delega obligaciones legales al papel ni acredita cumplimiento. No vincular por defecto tratamiento, marketing y cobro a un único consentimiento. El diseño final requiere definir los procesos y documentación aplicables.

En esta demo no capturar datos clínicos reales ni fotos de pacientes. Preparar la arquitectura para controles futuros no autoriza vender el prototipo como listo para producción sanitaria. La evaluación de uso real y requisitos aplicables es una fase comercial posterior separada del cumplimiento académico.

## 10. Fotos y notificaciones posteriores

Fotos antes/después (aplazadas por decisión del alumno): asociación a contacto/episodio, clasificación y fecha; almacenamiento privado; autorización del backend para leer/subir; validación del contenido real, tamaño/dimensiones y nombres; tratamiento de metadatos EXIF; backups y restauración coordinados con la BD; proceso de consentimiento/derechos revisado. Usar recursos sintéticos autorizados para la demostración futura. No servir un directorio público ni poner datos de pacientes en nombres de archivo.

PWA: manifest e iconos, experiencia responsive e instalación probada en dispositivos objetivos. No prometer que todos los móviles ofrecen el mismo flujo. Push es una ampliación independiente que exige permisos y soporte de navegador/plataforma, suscripciones, envío y pruebas. En iOS hay condiciones específicas para apps web añadidas a inicio; revisar documentación actual al implementarlo. No incluir información clínica en notificaciones visibles en pantalla bloqueada.

## 11. Diferencias principales respecto al borrador

| Borrador | Revisión propuesta y motivo |
|---|---|
| Reservas, fotos, cobro, facturación, automatización y consentimiento en el primer MVP | Núcleo CRM/agenda/seguimiento/portal; evitar integrar varios productos antes del plazo |
| Falta un frontend y un portal de cliente concretos | React responsive y permisos por recurso; un solo sistema con cuatro áreas |
| Pacientes con alergias e historial desde el inicio | Contactos administrativos; funcionalidad clínica fuera del TFM |
| Reservas triangulares por profesional y sala | Profesional + horario; salas posteriores |
| Widget público, Stripe y n8n como dependencias tempranas | Flujos internos primero; integraciones posteriores |
| JWT+refresh decidido sin analizar el cliente | Elegir una estrategia de sesión sencilla y comprobable |
| Auditoría «inmutable» por estar en BD | Registro de eventos con límites explícitos, permisos y pruebas |
| Consentimiento en papel como reducción de obligaciones | Declaración administrativa que no acredita cumplimiento legal |
| Infraestructura VPS, abrir puertos y proxy nuevo asumidos | Servidor físico existente; inventario primero, túnel saliente si corresponde |
| Backend por completo antes de integrar la interfaz | Cortes verticales pequeños; comprobar cada recorrido desde el navegador |
| Entrega TFM como última casilla | README, GitHub, slides, vídeo y formulario planificados en paralelo |

## 12. Relación con TFM y supervisión

Aplicar las directrices de `M12_A01_D01__documentacion_tfm.md` y la matriz `07_MATRIZ_CUMPLIMIENTO_TFM.md`. No confundir el índice de los temarios con el README de la raíz del CRM. Registrar en el README: descripción, stack, instalación/ejecución, estructura, funciones, credenciales de demo si hay login, enlaces de slides/vídeo y publicación si existe.

Cada tarea de `11_BACKLOG_ATOMICO_CRM.md` indica aceptación y evidencia. El agente inspecciona primero y trabaja un solo encargo delimitado; el alumno revisa diff, ejecución y explicación. Un commit pequeño por cambio coherente; etiquetas de versión solo en hitos demostrables. No etiquetar «v1.0» como producto clínico comercial por haber entregado el TFM.

Estado del documento: propuesta detallada de diseño. Usuario, mercado, plazo y prioridad portal/fotos están confirmados; no se han instalado dependencias, escrito el CRM ni ejecutado pruebas del producto en esta revisión.

## Referencias oficiales consultadas (30 de octubre de 2026)

- [FastAPI en contenedores](https://fastapi.tiangolo.com/deployment/docker/): base para un despliegue reproducible; las decisiones concretas dependen del servidor.
- [React: crear una aplicación desde cero](https://react.dev/learn/build-a-react-app-from-scratch): herramientas como Vite, TypeScript y decisiones de routing/datos. Elegir esta opción es una propuesta específica para una interfaz privada consumiendo FastAPI, no una recomendación universal de React frente a sus frameworks.
- [PostgreSQL: rangos y restricciones de exclusión](https://www.postgresql.org/docs/current/rangetypes.html): mecanismo para rechazar reservas solapadas en la base de datos.
- [MDN: instalación de PWA](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable): requisitos y soporte dependientes del navegador/plataforma.
- [Apple: Web Push](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers): soporte específico de notificaciones web en dispositivos Apple; verificarlo al implementar.
- [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/): conexiones salientes sin exponer el origen mediante puertos de entrada para el túnel.
- [HHS: entidades cubiertas y business associates](https://www.hhs.gov/hipaa/for-professionals/covered-entities/index.html): el ámbito de HIPAA depende de las entidades y actividades implicadas.
- [HHS: HIPAA y servicios cloud](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html): requisitos aplicables a proveedores cuando se maneja ePHI, incluidos acuerdos BAA cuando correspondan.

- [OWASP: sesiones](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, ciclo de sesión y controles relacionados.
- [OWASP: autorización](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): verificar permisos por petición y relación con el registro.


## 13. Integración documental de Quijote aprobada

Consultar `14_CONTEXTO_SERVIDOR_QUIJOTE.md`. El reporte recibido no contiene observación actual del servidor: las rutas, unos 16 GB de RAM y los componentes existentes son información documentada, no validación de viabilidad. T02b debe contrastarla antes del despliegue.

Propuesta: Compose propio (candidato crm-demo), PostgreSQL propio, redes dedicadas para API/BD y proxy accesible al túnel mediante la conexión mínima necesaria. Si el proxy comparte red con otras aplicaciones, estas pueden alcanzarlo; no prometer aislamiento total del host ni frente a quien controla el daemon. No reutilizar la BD de n8n ni alterar sus servicios/backups.

Reutilización del túnel frente a conector independiente, Access, hostname, rutas de datos, SSD/HDD y límites siguen pendientes. No copiar UID/GID, puerto ni memoria de otra imagen/servicio. Revisar protocolo del origen/HTTPS y confianza de cabeceras, sin seleccionar automáticamente Flexible. Registrar digest/artefacto exacto y probar reversión compatible con migraciones, además de backup/restauración aislados.

La guía de entrega incluye ejecución local reproducible y vídeo como contingencia. Estas decisiones documentales no autorizan tocar servidor, DNS o servicios compartidos. El alcance funcional y las prioridades del CRM se conservan.

## 14. Decisiones cerradas en T03 — 30/10/2026

Aceptadas por el alumno tras T01. Prevalecen sobre las propuestas abiertas de las secciones anteriores; la matriz de la sección 5 ya las incorpora.

**Entorno y flujo de trabajo**

- Nombre del producto, repositorio y proyecto Compose: `crm-demo`. Repositorio GitHub **público** (lo pide el PDF; evita la excepción de repositorio privado). Biblioteca, `ZZZIGNORAR/` y el documento 14 quedan fuera por `.gitignore`.
- Desarrollo en el portátil (`D:\CRMProject`, Windows): PostgreSQL en Docker (Docker Desktop con WSL2, por instalar en T05); API en `.venv` con Python 3.13 (`py -3.13`, no el 3.15 por defecto) y Vite nativos. Antes de cada despliegue se prueba el Compose completo en contenedores Linux. Migrar a WSL más adelante sería un `git clone`, no un cambio de diseño.
- Publicación: portátil → GitHub → `git pull` en el servidor a una etiqueta de versión, seguido de `docker compose -p crm-demo up -d --build` y migraciones, con `pg_dump` previo. La primera vez se preparan a mano `.env` (600), ruta de datos y túnel/hostname. Se agrupará en un script de despliegue. Ninguna de estas acciones está autorizada todavía sobre Quijote (T02b, T28).
- Estructura: `backend/`, `frontend/`, `nginx/`, `compose.yaml` común, `compose.override.yaml` local (puertos en 127.0.0.1) y `compose.prod.yaml` del servidor, `.env.example`, `.gitattributes` con LF.
- Versiones: Python 3.13 y Node 24 LTS (instalados). PostgreSQL 18 y versiones exactas de FastAPI/SQLAlchemy/React/Vite son recomendación: se fijan con archivo de bloqueo/digest en T04–T06, sin versiones publicadas en las últimas dos semanas.

**Reglas de negocio**

- Zona IANA de la clínica de demo: `America/New_York` (tiene horario de verano: probar los días de cambio).
- Sesión: cookie de servidor con sesión en BD, HttpOnly, Secure en publicación, SameSite, revocación al logout y protección CSRF. No se implementa JWT.
- Estados comerciales del contacto: Nuevo → Contactado → Cita agendada → Cliente; Perdido desde cualquiera. El contacto pasa a Cliente automáticamente al marcar como Realizada su primera cita; sigue siendo la misma ficha.
- Estados de cita: Programada, Realizada, No presentado, Cancelada. Solo Cancelada libera la franja para la restricción de solapamiento.
- Recepción marca asistencia y ve/gestiona todos los seguimientos; el profesional, solo sus citas y seguimientos asignados, y los contactos con alguna cita con él.

**Recorrido del cliente y cuenta del portal**

1. Fuera del CRM: anuncio → web de la clínica → WhatsApp. El CRM registra el origen del contacto.
2. Recepción pide el email, que es obligatorio, y crea el contacto y la cita (T21b). Una persona, un contacto: email y teléfono no se repiten. Un menor no tiene ficha: su cita va a nombre de su madre o padre, con una nota. Un hijo adulto tiene su propia ficha y su propio email. Un trabajador que también sea cliente usa otro email distinto del de su cuenta.
3. Recepción o admin generan una invitación al portal para cualquier contacto salvo Perdido, con o sin citas (cambia en T21 la condición de T03, «al menos una cita»): enlace de un solo uso, ligado al contacto, que caduca a las 24 h (T21; T03 proponía 72 h). Generar otro anula el anterior. Recepción lo envía manualmente por WhatsApp; no hay envío automático de email en el núcleo.
4. El cliente abre el enlace, ve con qué email entrará (el de su ficha, T21b) y elige su contraseña; después entra por el login y consulta sus citas. Recepción solo puede crear cuentas de rol cliente. Si recepción corrige el email de la ficha, cambia también el de acceso y la contraseña sigue igual: así no se pierde el historial si el cliente pierde acceso a su correo. Sin recuperación de contraseña en la demo: límite documentado en el README.
5. Plan B si falta tiempo: cuenta creada por admin con contraseña temporal y cambio obligatorio.

**Alcance del portal (decisión del alumno, T21):** un CRM no necesita portal de cliente para ser útil, y la prioridad es el personal de la clínica. El portal se queda en lo mínimo (ver las citas propias): demuestra el acceso seguro a los datos de cada cliente y resuelve su identidad, que una reserva futura necesitaría. Se reconoce que, sin reserva, aporta poco al cliente final.

**Portal (T22 y T23):** el cliente ve sus próximas citas y las anteriores, con servicio, día, hora y estado real (también Cancelada y No presentado), en solo lectura. No ve quién la realiza (las cuentas internas aún no tienen nombre: se decidirá más adelante si se añade), motivo ni notas. Un contacto Perdido conserva el acceso: esa etiqueta es interna y el portal no la revela. Solo hay lista, sin página de detalle.

**Tareas de seguimiento (T24):** las crean admin y recepción desde la ficha, ligadas solo al contacto, con una descripción corta sin datos clínicos, una fecha prevista sin hora y un responsable. Pueden ser responsables las cuentas activas de administración y recepción, y un profesional solo si el contacto tiene alguna cita con él, también cancelada: así la tarea no le exige abrir una ficha que no puede ver. El profesional solo ve las suyas y no crea tareas; el cliente no las ve. Un contacto Perdido admite tareas (decisión del alumno), porque son recordatorios internos; citas e invitaciones siguen exigiendo reabrirlo.

**Panel de pendientes (T25):** sección «Pendientes» con un contador de vencidas y de hoy; es el aviso dentro del CRM, sin push. Admin y recepción ven las de toda la clínica, con filtro por persona y «Solo mías», y completan, reabren, editan y reasignan cualquiera; el profesional ve, completa y reabre solo las suyas, y no edita. Las reglas de responsable y fecha se aplican a lo que cambia, así que una vencida se reasigna sin moverle la fecha. «Reabrir» no tiene plazo. Una tarea hecha no se edita hasta reabrirla. Queda quién la marcó por última vez; el historial, en T26. Dos cambios a la vez sobre la misma tarea: gana el primero y el otro recibe 409.

**Notas (T21b):** la ficha y la cita admiten una nota corta, con aviso de no escribir datos clínicos. Las escriben admin y recepción, y la de la cita se edita con su propio botón, sin reprogramar. El profesional ve la de la ficha de sus contactos y la de sus citas. El cliente no las ve.

**Comunicaciones:** tener el email de un cliente no autoriza a enviarle campañas. Antes de cualquier envío hará falta una casilla de autorización en el registro y revisar consentimiento y baja; no se construye ahora.

**Ideas de ampliación tras el núcleo (decisión T21, sustituye al orden de T03):** PWA instalable, fotos antes/después y reserva por el cliente desde su portal. No tienen orden fijo: al cerrar el núcleo se mencionan y se elige por cuál empezar según lo que más convenga. Reservar sin registro previo (widget público) e integración con WhatsApp quedan para fases posteriores.
