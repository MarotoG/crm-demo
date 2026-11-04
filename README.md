# crm-demo — CRM para pequeñas clínicas estéticas

> **Estado: en desarrollo (Trabajo Fin de Máster, entrega noviembre de 2026).** Por ahora existen el esqueleto de la API, PostgreSQL en Docker, las migraciones de servicios y usuarios, un procedimiento para crear las cuentas de demo, login y logout con sesión en servidor y protección CSRF, y una interfaz con pantalla de login, un área por rol (la de administración lista los usuarios) y el estado de la API y de la base de datos; la gestión básica de contactos (alta, lista, búsqueda, ficha, edición, estado comercial y responsable) para recepción y administración, los servicios de la clínica (nombre, duración y quién los realiza) la agenda de recepción (citas de un día o de un mes por persona; dar una cita desde la agenda o desde la ficha; reprogramarla y cancelarla con motivo), sin solapamientos por persona, el área del profesional («Mi agenda» con solo sus citas y la ficha de sus contactos en solo lectura) la asistencia (Realizada / No presentado, con el paso a Cliente), el portal del cliente con sus citas y las tareas de seguimiento en la ficha; faltan las demás funcionalidades del CRM (panel de pendientes y completar tareas, auditoría). Este README es provisional y se completará con hechos comprobados a medida que avance el proyecto.

## Descripción

CRM web responsive para clínicas estéticas pequeñas y medianas de Estados Unidos. Objetivo: seguir el recorrido de un contacto desde la primera consulta comercial hasta la cita y su seguimiento, con un portal donde cada cliente consulta solo sus propias citas.

Núcleo previsto: login con cuatro roles (administración, recepción, profesional y cliente), contactos/leads, agenda por profesional sin solapamientos, seguimientos internos y portal de cliente por invitación.

**Solo datos ficticios.** Este proyecto académico no está preparado para tratar datos reales de pacientes ni se presenta como conforme a HIPAA.

## Stack previsto

- Backend: Python 3.13 + FastAPI, SQLAlchemy y Alembic
- Base de datos: PostgreSQL 18.4 (imagen oficial fijada por digest en `compose.yaml`)
- Frontend: React 19 + TypeScript 7 + Vite 8
- Despliegue: Docker Compose

Las versiones exactas se fijan al crear cada parte (backend: `backend/requirements*.txt`; frontend: `frontend/package-lock.json`).

## Estructura prevista

```
backend/                API FastAPI, pruebas y migraciones (Alembic)
frontend/               interfaz React + TypeScript (Vite)
nginx/                  servidor web y proxy de /api (pendiente)
compose.yaml            servicios Docker comunes (por ahora, PostgreSQL)
compose.override.yaml   ajustes solo locales (puerto de la BD en 127.0.0.1)
documentacion/          especificaciones, backlog y estado del proyecto
```

## Instalación y ejecución

Requisitos: Git, Python 3.13, Node.js 24 LTS y Docker Desktop (backend WSL2). En desarrollo, PostgreSQL corre en Docker y la API y Vite se ejecutan directamente en Windows.

### 1. Configuración (`.env`)

Docker Compose y la API leen el mismo `.env` de la raíz, que no se versiona. Para crearlo desde la plantilla con contraseña y clave aleatorias, sin mostrarlas en pantalla (PowerShell, desde la raíz del proyecto):

```powershell
$pw  = py -3.13 -c "import secrets; print(secrets.token_urlsafe(24))"
$key = py -3.13 -c "import secrets; print(secrets.token_urlsafe(48))"
$txt = (Get-Content .env.example -Raw -Encoding UTF8).Replace('cambiar-por-una-contrasena-local', $pw).Replace('cambiar-por-una-clave-aleatoria', $key)
[IO.File]::WriteAllText("$PWD\.env", $txt, (New-Object Text.UTF8Encoding $false))
Remove-Variable pw, key, txt
```

La contraseña de la BD solo se aplica cuando el volumen se crea por primera vez; cambiarla después en `.env` no cambia la de PostgreSQL.

`CRM_CLINIC_TIMEZONE` es la zona horaria IANA de la clínica (por defecto `America/New_York`): las horas de las citas se escriben y se muestran en ella, y en la BD se guardan como instantes. Si no es una zona IANA válida, la configuración se rechaza al leerla (la primera petición que use la BD) con un error que nombra la variable, igual que con las demás variables. La API incluye `tzdata`, así que no depende de las zonas instaladas en el sistema.

### 2. Base de datos (PostgreSQL en Docker)

Con Docker Desktop abierto, desde la raíz del proyecto:

```powershell
docker compose up -d db      # arrancar (espera a que "ps" muestre "healthy")
docker compose ps            # estado
docker compose logs db       # registro de PostgreSQL
docker compose down          # parar y eliminar el contenedor; los datos se conservan
```

Los datos viven en el volumen `crm-demo_db_data`. **`docker compose down -v` borra ese volumen y todos los datos.** El puerto 5432 solo se publica en `127.0.0.1`. `docker compose config` muestra la contraseña: no compartir su salida.

### 3. Backend (API) en Windows

Comandos comprobados en Windows 11 con PowerShell 5.1 y Python 3.13.0. Se usa `py -3.13` explícitamente porque el Python predeterminado del equipo puede ser otro.

```powershell
cd backend
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# Pruebas (las de login y BD usan crm_demo_test; ver más abajo)
.venv\Scripts\python.exe -m pytest -v

# Aplicar migraciones a la BD (con el contenedor en marcha)
.venv\Scripts\alembic.exe upgrade head

# Arrancar la API en desarrollo (Ctrl+C para parar)
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Con la API en marcha:

- `http://127.0.0.1:8000/api/health` → `{"status":"ok"}` (la API está viva; no consulta la BD)
- `http://127.0.0.1:8000/api/health/db` → `{"status":"ok","database":"ok"}`, o HTTP 503 `{"status":"error","database":"unavailable"}` si la API no puede consultar PostgreSQL
- `http://127.0.0.1:8000/docs` → documentación interactiva (Swagger UI; carga sus estilos y scripts desde un CDN, necesita Internet)
- `POST /api/auth/login` con `{"email": "...", "password": "..."}` → 200 con id, email, rol y `csrf_token`, y una cookie de sesión `crm_session` (HttpOnly, 8 h). Si las credenciales no son válidas: 401 «Email o contraseña incorrectos», el mismo mensaje exista o no el email; tras 5 fallos en 15 min para el mismo email desde la misma IP: 429
- `GET /api/auth/me` → el usuario de la sesión actual y su `csrf_token`, o 401 sin sesión válida
- `POST /api/auth/logout` con la cabecera `X-CSRF-Token: <csrf_token>` → 204: revoca la sesión de ese dispositivo (las de otros dispositivos siguen) y borra la cookie. Sin el token correcto: 403. Sin sesión válida: 204 igualmente
- `POST /api/contacts` (admin y recepción, con `X-CSRF-Token`) con `first_name`, `last_name`, `email` y `source`, y opcionalmente `phone` y `note` → 201 con la ficha creada en estado `new` y, de responsable, quien la crea (`owner_id`, `owner_email`). Sin tildes (MVP para clínicas de EE. UU.): nombre y apellidos solo con letras sin tilde, espacios, guiones, apóstrofos y puntos (Mary-Jane, O'Connor, Jr.), y el email sin tildes; si no, 422 «No se permiten tildes ni caracteres especiales (á, ñ, ü…)». Se guardan normalizados: nombre sin espacios de más (respetando mayúsculas), email en minúsculas y teléfono en formato E.164 (un número de EE. UU. de 10 cifras como `(212) 555-0123` se guarda como `+12125550123`; los de otros países deben empezar por `+`). `source`: `instagram`, `facebook`, `google`, `website`, `referral`, `walk_in` u `other`. Datos no válidos: 422 con un mensaje por campo. **Una persona, un contacto:** el email es obligatorio y único, y el teléfono, opcional y único; repetir cualquiera de los dos, 409. Un email que ya es de una cuenta de la clínica: 422, hay que usar otro. Un menor no tiene ficha propia: su cita va a nombre de su madre o padre, con una nota. `note`: hasta 200 caracteres en una línea, sin tildes y sin datos clínicos
- `GET /api/contacts?q=texto` (admin y recepción) → `{"total": N, "items": [...]}`: los 20 contactos más recientes que coinciden con la búsqueda y cuántos coinciden en total. `q` es opcional (sin él, todos) y de 100 caracteres como máximo; busca parte del nombre y apellidos (en cualquier orden), del email o, si lleva al menos 3 cifras, del teléfono, sin distinguir mayúsculas (los datos no llevan tildes: una búsqueda con tilde no encuentra nada). Filtros combinables con la búsqueda: `status` (se puede repetir: `?status=new&status=contacted`; sin él, todos) y `owner=me` (los míos) u `owner=none` (sin responsable). Cada contacto trae su responsable. Profesional y cliente: 403
- `GET /api/contacts/{id}` (admin y recepción) → la ficha: los datos del contacto más `note`, `version`, `updated_at`, `created_by_email` y `updated_by_email` (quién lo creó y quién lo cambió por última vez). 404 si no existe. El profesional solo la de un contacto que tiene o tuvo alguna cita con él (también cancelada); si no, 404 igual que si no existiera, para no revelar que existe. Cliente: 403. El profesional no lista, crea ni cambia contactos (403)
- `PUT /api/contacts/{id}` (admin y recepción, con `X-CSRF-Token`) con la ficha entera (los mismos campos y reglas que el alta, más `owner_id`: el responsable, o `null` para dejarlo sin responsable) y la `version` que se leyó → 200 con la ficha actualizada y la versión siguiente. El id no cambia y no se crea otra ficha. Si otra persona guardó antes (la versión ya no coincide): 409 «Otra persona ha cambiado esta ficha mientras la editabas». Si la edición crea un duplicado: 409 como en el alta. **Si el contacto tiene cuenta, corregir su email cambia también el de acceso**, en la misma operación: la contraseña sigue igual, el historial no se toca y las sesiones abiertas siguen. Un responsable nuevo debe ser una cuenta activa de recepción o administración (si no, 422 en `owner_id`). El estado comercial, el autor y las fechas no se editan aquí. Los contactos no se borran
- `PUT /api/contacts/{id}/status` (admin y recepción, con `X-CSRF-Token`) con `status` y la `version` que se leyó → 200 con la ficha y la versión siguiente. A mano solo se permite Nuevo → Contactado, cualquier estado → Perdido y Perdido → Contactado (reabrir); «Cita agendada» y «Cliente» los ponen las citas («Cita agendada», al crear una; «Cliente», más adelante, al marcar Realizada la primera) y nunca se vuelve a Nuevo: cualquier otro cambio, 422 con el motivo. Comparte la versión con la edición: si otra persona cambió la ficha antes, 409
- `GET /api/contacts/owners` (admin y recepción) → quién puede ser responsable: `[{"id", "email"}]` de las cuentas activas de recepción y administración
- `GET /api/services` → los servicios con `id`, `name`, `duration_minutes`, `active`, `version` y `staff` (quién lo realiza: `id`, `email`, `role`, `active`). Admin y recepción: todos, primero los activos y por nombre. Profesional: solo los servicios activos que tiene asignados. Cliente: 403
- `GET /api/services/staff` (admin y recepción) → quién se puede asignar a un servicio: las cuentas internas activas (administración, recepción y profesional; el jefe o la recepcionista también pueden realizar servicios)
- `POST /api/services` (admin y recepción, con `X-CSRF-Token`) con `name`, `duration_minutes` y `staff_ids` (una o más personas) → 201 con el servicio activo. Duración: múltiplo de 5 minutos, de 5 a 240 (4 horas), y un número entero. Nombre sin tildes: letras, cifras, espacios y `. , ' & + / ( ) -`, hasta 120 caracteres. Las personas deben ser cuentas internas activas. Si no: 422 junto al campo. Un nombre que ya existe, sin distinguir mayúsculas y aunque esté desactivado: 409
- `PUT /api/services/{id}` (admin y recepción, con `X-CSRF-Token`) con el servicio entero (`name`, `duration_minutes`, `staff_ids`, `active`) y la `version` que se leyó → 200 con la versión siguiente. Sirve para editar, desactivar (`active: false`) y reactivar; los servicios no se borran. Un servicio activo necesita al menos una persona; uno desactivado puede quedarse sin nadie. Solo se comprueba a quien se añade: una persona ya asignada que se desactiva después no impide guardar. Si otra persona guardó antes: 409
- `POST /api/appointments` (admin y recepción, con `X-CSRF-Token`) con `contact_id`, `service_id`, `staff_id` (una de las personas que realizan el servicio) y `starts_at` en la **hora local de la clínica**, sin zona: `"2027-01-11T09:30"` → 201 con la cita en estado `scheduled`, `starts_at` y `ends_at` en la hora de la clínica con su desfase (`"2027-01-11T09:30:00-05:00"`), la `duration_minutes` copiada del servicio y la `version`. La duración no se envía: cambiar después el servicio no cambia las citas ya dadas. La hora va en múltiplos de 5 minutos, desde ahora y como mucho dentro de 365 días; las horas que no existen o se repiten por el cambio de horario se rechazan. El servicio debe estar activo y la persona, asignada a él y con su cuenta interna activa. Si el contacto está Nuevo o Contactado pasa a «Cita agendada» (y sube su versión); si está Perdido: 422, hay que reabrirlo antes. Datos no válidos: 422 junto al campo. Profesional y cliente: 403. **Sin solapamientos por persona**: si quien la realiza ya tiene otra cita que se pisa con esta, 409 «Esa persona ya tiene una cita de 9:30 a 10:30» (en la hora de la clínica, con la fecha si la otra empieza otro día; sin el nombre del otro contacto). Una cita puede empezar justo cuando acaba otra, y las canceladas no ocupan. Lo comprueba PostgreSQL con una restricción de exclusión (extensión `btree_gist`, incluida en PostgreSQL), así que dos peticiones simultáneas no pueden guardar las dos. Un mismo contacto sí puede tener dos citas a la vez con personas distintas (por ejemplo, tinte y pedicura). `note` opcional, con las mismas reglas que la de la ficha
- `GET /api/appointments?date=AAAA-MM-DD` o `?from=AAAA-MM-DD&to=AAAA-MM-DD` (admin, recepción y profesional) → las citas que ocupan parte de ese día (o de esos días, `to` incluido, 31 como mucho: la vista del mes) de la clínica (también la que empieza la víspera, como una de 23:30 a 0:30), por hora de inicio, con `contact_name`, `service_name` y `staff_email` además de los datos de la cita y sus horas en la de la clínica. Filtros opcionales: `staff_id` (una persona) y `contact_id` (un contacto). El día del cambio de horario tiene 23 o 25 horas y se respeta. Un día que no existe o mal escrito, `date` junto con `from`/`to`, falta uno de los dos, `to` anterior a `from` o más de 31 días: 422. **El profesional solo ve sus citas**: la API pone el filtro por su persona aunque no lo envíe, y pedir el `staff_id` de otra persona es 403 «Solo puedes ver tus citas». Cliente: 403. Cada cita trae también `note` y `cancel_reason` y `cancel_note` (solo en las canceladas)
- `PUT /api/appointments/{id}` (admin y recepción, con `X-CSRF-Token`) con `staff_id`, `starts_at` (hora local de la clínica, como al crearla) y la `version` que se leyó → 200 con la cita reprogramada y la versión siguiente. Cambia el día, la hora y la persona; el contacto y el servicio no cambian (para otro servicio, se cancela y se da otra cita) y la duración es la copiada al crearla. Se aplican las mismas reglas que al crear: hora válida, persona del servicio con su cuenta activa, servicio activo (si no, 422 «cancela la cita y da otra») y contacto no Perdido (422). Solo una cita Programada que no ha empezado: si no, 409 con el motivo. Si otra persona la cambió antes, 409 «Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo.». La regla de solapamientos también vale al reprogramar (409 que nombra la otra cita); la cita no choca consigo misma, así que se puede mover media hora dentro de su propia franja. No cambia el estado del contacto
- `POST /api/appointments/{id}/cancel` (admin y recepción, con `X-CSRF-Token`) con la `version`, el motivo `reason` (`client_request`, `clinic` u `other`, obligatorio) y, si se quiere, `note`: un detalle de una línea, hasta 200 caracteres sin tildes y **sin datos clínicos** → 200 con la cita en estado `cancelled`. La franja queda libre. Solo una cita Programada que no ha empezado, con la versión al día (409 si no). Se puede cancelar aunque el contacto esté Perdido o el servicio desactivado. Si el contacto estaba en «Cita agendada» y no le queda ninguna cita Programada, vuelve a Contactado (y sube su versión). La BD exige que una cita esté cancelada si y solo si tiene motivo
- `POST /api/appointments/{id}/attendance` (admin y recepción, cualquier cita; profesional, solo las suyas: las demás, 404 como si no existieran; con `X-CSRF-Token`) con la `version` y `status`: `completed` (Realizada) o `no_show` (No presentado) → 200 con la cita y `attended_at`, cuándo se marcó por primera vez. Se marca desde la hora de inicio de la cita (antes, 409), aunque hayan pasado semanas; una cancelada, 409. Se puede **corregir** de una a la otra durante 7 días desde que se marcó (después, 409); corregirla no cambia `attended_at`. Marcarla igual que está o con una versión antigua, 409. El estado del contacto se recalcula en la misma operación: con alguna Realizada es **Cliente** (la primera lo convierte, venga de donde venga); si se corrige su única Realizada, vuelve a «Cita agendada» si le queda alguna Programada, o a Contactado si no; un No presentado en la última Programada de un contacto en «Cita agendada» lo devuelve a Contactado, como al cancelar. La BD exige que una cita tenga `attended_at` si y solo si está Realizada o No presentado
- `PUT /api/appointments/{id}/note` (admin y recepción, con `X-CSRF-Token`) con `note` (o `null` para quitarla) y la `version` que se leyó → 200 con la cita y la versión siguiente. No cambia nada más y vale en cualquier estado. Si otra persona la cambió antes: 409. Profesional y cliente: 403
- `GET /api/appointments/by-contact/{id}` → las citas de un contacto para su ficha: `total` e `items` (las 20 de fecha más reciente, también canceladas). El profesional solo ve las suyas; sin ninguna con ese contacto, 404 igual que si no existiera. Cliente: 403
- `GET /api/contacts/{id}/portal` (admin y recepción) → `has_account` y `invitation_expires_at` (hasta cuándo vale el enlace sin usar, o `null`)
- `POST /api/contacts/{id}/portal-invitation` (admin y recepción, con `X-CSRF-Token`) → 201 con `token` y `expires_at` (24 h). Vale para cualquier contacto, con o sin citas; 409 si está Perdido o ya tiene cuenta. El token solo aparece en esta respuesta (en la BD queda su hash) y generar otro anula el anterior
- `POST /api/portal-invitations/check` con `token` (sin sesión) → 200 con `email`, con el que entrará el cliente, si el enlace vale; 410 con el mismo mensaje, sin dar ningún dato, si no existe, caducó, ya se usó, se anuló o el contacto pasó a Perdido
- `POST /api/portal-invitations/accept` con `token` y `password` (sin sesión) → 204: crea una cuenta siempre de rol cliente, con el email de la ficha y vinculada a su contacto, y gasta el enlace; no inicia sesión. Contraseña de 12 a 1024 caracteres. Si ya hay otra cuenta con ese email: 409 y el enlace sigue valiendo. Datos no válidos o campos de más, como un rol o un email: 422. Enlace que no vale: 410
- `GET /api/portal/appointments` (solo cliente) → las citas de quien tiene la sesión: `upcoming` (no han terminado y están Programadas o Canceladas, de la más cercana a la más lejana), `past` (el resto, las 20 más recientes) y `past_total`. Cada cita trae solo `id`, `service_name`, `starts_at`, `ends_at` y `status`: sin notas, motivo ni detalle de cancelación, quién la realiza ni versión. No acepta parámetros: enviar `contact_id` u otro no cambia nada, y no hay ruta por ID. Personal: 403. Sin vínculo con un contacto: listas vacías
- `POST /api/contacts/{id}/follow-ups` (admin y recepción, con `X-CSRF-Token`) con `description`, `due_on` (`AAAA-MM-DD`, un día de la clínica, desde hoy y como mucho dentro de 365 días) y `assigned_to_id` → 201 con la tarea de seguimiento. Descripción obligatoria: hasta 200 caracteres en una línea, sin tildes y **sin datos clínicos**. El responsable debe ser una cuenta activa de administración o recepción, o un profesional con alguna cita con ese contacto, también cancelada; si no, 422 junto al campo. Campos de más, como el autor: 422. Vale también para un contacto Perdido. Contacto que no existe: 404. Profesional y cliente: 403
- `GET /api/contacts/{id}/follow-ups` → `total` e `items`: las 20 tareas de fecha más cercana, con su responsable y quién la creó. **El profesional solo ve las suyas**, lo decide la API aunque envíe otros parámetros; sin citas con ese contacto, 404 igual que si no existiera. Cliente: 403
- `GET /api/contacts/{id}/follow-up-assignees` (admin y recepción) → a quién se le puede asignar una tarea de ese contacto: `[{"id", "email"}]`
- `GET /api/users` → lista de usuarios (id, email, rol, activo; nunca el hash), solo para el rol administrador: 403 «Permiso denegado» con otro rol y 401 sin sesión
- Si PostgreSQL no responde, las rutas que lo usan devuelven 503 «Servicio no disponible», sin detalles

**Protección CSRF.** Toda petición que cambie datos (salvo el login) debe llevar la cabecera `X-CSRF-Token` con el `csrf_token` que devuelven el login y `/api/auth/me`. Se calcula con `CRM_SECRET_KEY` (obligatoria para el login: al menos 32 caracteres y distinta del valor de ejemplo); si cambia la clave, los tokens anteriores dejan de valer y basta volver a pedir `/api/auth/me`.

**Sesiones antiguas.** Cada login borra las sesiones caducadas hace más de 30 días. También puede hacerse a mano, desde `backend/`: `.venv\Scripts\python.exe -m app.purge_sessions` (solo muestra cuántas ha borrado). La tabla de sesiones no es un registro de auditoría de accesos a datos de clientes.

**Pruebas y base de datos.** Las pruebas que necesitan PostgreSQL usan una base aparte, `crm_demo_test`, en el mismo contenedor: se crea sola la primera vez, se migra al empezar y cada prueba deshace sus cambios, así que `crm_demo` no se toca. Con la BD apagada esas pruebas se saltan con un aviso (`pytest -rs` muestra el motivo) y el resto se ejecuta.

Dependencias: `requirements.txt` (ejecución) y `requirements-dev.txt` (pruebas), con todas las versiones fijadas, incluidas las transitivas.

### 4. Frontend (interfaz) en Windows

Comprobado con Node.js 24.22.1 y npm 11.19.1. En otra terminal, con la API en marcha:

```powershell
cd frontend
npm ci              # instala exactamente lo que fija package-lock.json
npm run dev         # http://127.0.0.1:5173 (Ctrl+C para parar)
npm run build       # comprueba tipos (tsc) y genera dist/
npm test            # pruebas de la interfaz (Vitest + Testing Library; no necesitan la API)
```

En desarrollo el navegador solo habla con Vite (puerto 5173), que reenvía `/api/*` a la API (puerto 8000).

Al abrir `http://127.0.0.1:5173` aparece la pantalla de login, con el estado de la API y de la base de datos debajo. Al entrar, administración y recepción llegan a la **Agenda** y tienen una barra de secciones: Agenda (`/agenda`), Contactos (`/contactos`), Servicios (`/servicios`) y, solo administración, Usuarios (`/usuarios`). Las direcciones son las mismas para todos los roles que ven la sección; las anteriores (`/admin`, `/recepcion`, `/recepcion/contactos/7`…) llevan a la nueva. El profesional llega a **Mi agenda** (`/mi-agenda`) y su barra tiene Mi agenda y Mis servicios (`/mis-servicios`); la dirección antigua `/profesional` lleva a Mi agenda. El cliente va a **Mis citas** (`/portal`), sin barra y en solo lectura: «Próximas» y «Anteriores», con día, hora de Nueva York, servicio y estado (una cita pasada que la clínica no ha marcado sale como «Sin confirmar»); sin citas, «Aún no tienes citas. Escribe a la clínica para reservar.». Un contacto Perdido conserva el acceso. En la Agenda se ven las citas de un día por hora (inicio y fin, contacto con enlace a su ficha, servicio y quién la realiza), con «← Día anterior», «Día siguiente →», «Hoy», un calendario para ir a cualquier día y el filtro «Persona»; el día y el filtro quedan en la dirección (`/agenda?fecha=2026-11-10`), así que se puede recargar. «Nueva cita» abre el formulario: el contacto se busca por nombre, email o teléfono (los Perdidos no aparecen), el servicio solo ofrece los activos con alguien que los realice, «Quién la realiza» solo ofrece a sus personas (y queda elegida si solo hay una), y la hora se elige con dos desplegables (los minutos de 5 en 5), siempre en la hora de Nueva York. Al elegir la persona se ve qué citas tiene ya ese día. Si el contacto ya tiene otra cita a esa hora (con otra persona), se avisa, pero se puede guardar igualmente (dos servicios a la vez). Si la persona ya tiene una cita que se pisa, el 409 de la API se muestra junto al formulario. Cada cita Programada que aún no ha empezado tiene «Reprogramar» y «Cancelar cita». «Reprogramar» abre el mismo formulario con el contacto y el servicio fijos y la hora y la persona ya elegidas (`/agenda?reprogramar=12`, que se puede recargar); si otra persona cambió la cita mientras tanto, se avisa, la agenda se recarga y basta con revisar y volver a guardar. «Cancelar cita» abre en la misma fila un recuadro con el motivo (obligatorio) y un detalle opcional, con el aviso de no escribir datos clínicos. Las canceladas siguen en la lista, tachadas y con su motivo. Los botones «Día» y «Mes» cambian la vista (`?vista=mes`, que se puede recargar): la del mes muestra todas sus citas agrupadas por día, con «← Mes anterior», «Mes siguiente →» y «Este mes», «Ver el día» en cada día y, arriba, cuántas citas Programadas hay de cada servicio (para preparar el material; las canceladas no cuentan); desde el mes se puede reprogramar o cancelar sin ir día a día. En las citas que ya han empezado aparecen «Realizada» y «No presentado» (también en el mes y en Mi agenda, para las suyas); una ya marcada muestra su estado y, durante 7 días desde que se marcó, «Cambiar a No presentado» o «Cambiar a Realizada»; si otra persona la marcó antes, se avisa y la lista se recarga. «Solo mis citas» aplica el filtro con la propia cuenta, para el admin o la recepcionista que también realizan servicios. **Mi agenda** del profesional es la misma agenda, de día o de mes, solo con sus citas y en solo lectura: sin «Nueva cita», sin filtro de persona y sin reprogramar ni cancelar, pero con los botones de asistencia de sus citas. El nombre del contacto abre su ficha en solo lectura (sin editar, sin cambiar el estado ni dar cita), con «← Volver a mi agenda»; la de un contacto sin citas con él dice «Este contacto no existe o no tiene citas contigo». En Servicios, «Añadir servicio» pide el nombre, la duración en minutos y quién lo realiza (casillas con las cuentas internas activas); cada servicio muestra su duración, si está activo y quién lo realiza, con «Editar» y «Desactivar» o «Reactivar». Si un servicio activo no tiene a nadie disponible, se avisa de que no se podrán dar citas. En Contactos, «Nuevo contacto» abre el formulario; al guardar, el contacto aparece el primero de la lista; un dato no válido se explica junto a su campo y un duplicado, encima de los botones. El buscador filtra al dejar de escribir; los desplegables «Estado» (por defecto, los activos: todos menos Perdido) y «Responsable» (Todos, Mis contactos, Sin responsable) se combinan con él. Cada fila muestra el estado, el origen y el responsable. Cada nombre de la lista abre su ficha (`/contactos/7`, que se puede recargar), con «Dar cita» (abre el formulario de la agenda con el contacto ya elegido; no sale si está Perdido), las fechas en la hora de la clínica (Nueva York), el responsable, el botón «Editar» (que permite cambiar también el responsable) y los botones de estado permitidos: «Marcar como contactado», «Marcar como perdido» o «Reabrir (pasa a Contactado)». Si otra persona guardó la ficha mientras la editabas, se muestra lo que guardó con un aviso, en lugar de pisarlo. Bajo los datos, la ficha lista sus citas (la fecha lleva a la agenda de ese día; el profesional solo ve las suyas). Administración y recepción ven también «Portal del cliente»: «Invitar al portal» genera un enlace de un solo uso que caduca a las 24 h, con «Copiar enlace» para enviarlo a mano; solo se ve al generarlo y «Generar otro enlace» anula el anterior. No se ofrece a un contacto Perdido ni a quien ya tiene cuenta. El cliente abre el enlace (`/invitacion#…`), ve con qué email entrará y elige su contraseña; después entra por el login. Si recepción corrige el email de la ficha, cambia también con el que entra. Cada cita muestra su nota, y en la agenda se edita con «Añadir nota» o «Editar nota», sin reprogramar; en «Mi agenda» solo se lee, y el cliente no la ve. En la ficha, «Seguimientos» lista las tareas del contacto, de la más cercana a la más lejana, y «Nueva tarea» pide qué hay que hacer, la fecha prevista y quién se encarga (un profesional solo aparece si el contacto tiene alguna cita con él). El profesional ve solo las suyas en «Tus seguimientos», sin crear tareas, y el cliente no las ve. Todavía no se pueden editar, reasignar ni completar. **Límite de la demo:** no hay recuperación de contraseña: quien la olvide no tiene forma de restablecerla desde la aplicación. Si se escribe una tilde, en el formulario o en el buscador, aparece al momento el aviso «No se permiten tildes ni caracteres especiales (á, ñ, ü…)» y el contacto no se envía. Escribir a mano una sección que el rol no ve muestra «No tienes acceso a esta área», y la API rechaza igualmente sus datos (403). «Cerrar sesión» solo vuelve al login cuando la API confirma el cierre. Si la sesión caduca mientras se usa, vuelve al login con un aviso. Recargar la página mantiene la sesión: la app pregunta a `/api/auth/me` y guarda el token CSRF solo en memoria.

### 5. Cuentas de demostración (local)

Hay una cuenta ficticia por rol, con email del dominio reservado `demo.example.com`. Las contraseñas no están en el código: se guardan en el `.env` local y se aplican con un comando. La BD solo guarda su hash Argon2id.

| Rol | Email |
|---|---|
| Administración | `admin@demo.example.com` |
| Recepción | `recepcion@demo.example.com` |
| Profesional | `profesional@demo.example.com` |
| Cliente | `cliente@demo.example.com` |

1. En `.env`, rellenar `CRM_DEMO_PASSWORD_ADMIN`, `CRM_DEMO_PASSWORD_RECEPTION`, `CRM_DEMO_PASSWORD_PROFESSIONAL` y `CRM_DEMO_PASSWORD_CLIENT` con contraseñas ficticias de al menos 12 caracteres (por ejemplo, generadas con `py -3.13 -c "import secrets; print(secrets.token_urlsafe(12))"`).
2. Con la BD en marcha y las migraciones aplicadas, desde `backend/`:

```powershell
.venv\Scripts\python.exe -m app.seed_demo
```

El comando se puede repetir: crea las cuentas que falten y, en las existentes, aplica la contraseña actual del `.env`, restaura el rol y las reactiva. La cuenta de cliente queda vinculada a un contacto ficticio, «Demo Cliente», que se crea si falta y aparece en la lista de contactos. Si falta alguna variable o es demasiado corta, no modifica la BD y dice cuál. Nunca muestra contraseñas ni hashes. Con las cuentas creadas se puede entrar desde la pantalla de login; las credenciales de prueba de la entrega se documentarán antes de entregar.

## Pendiente de completar

Funcionalidades verificadas, cuentas de demostración, URL de publicación, slides, vídeo, pruebas y limitaciones.
