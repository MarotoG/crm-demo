# crm-demo — CRM para pequeñas clínicas estéticas

> **Estado: en desarrollo (Trabajo Fin de Máster, entrega noviembre de 2026).** Por ahora existen el esqueleto de la API, PostgreSQL en Docker, las migraciones de servicios y usuarios, un procedimiento para crear las cuentas de demo, login y logout con sesión en servidor y protección CSRF, y una interfaz con pantalla de login, un área por rol (la de administración lista los usuarios) y el estado de la API y de la base de datos; la gestión básica de contactos (alta, lista, búsqueda, ficha, edición, estado comercial y responsable) para recepción y administración, los servicios de la clínica (nombre, duración y quién los realiza) y la agenda de recepción (citas de un día por persona, y dar una cita desde la agenda o desde la ficha), sin solapamientos por persona; faltan las demás funcionalidades del CRM (reprogramar y cancelar, área del profesional, seguimientos, portal). Este README es provisional y se completará con hechos comprobados a medida que avance el proyecto.

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
- `POST /api/contacts` (admin y recepción, con `X-CSRF-Token`) con `first_name`, `last_name`, `source` y al menos `email` o `phone` → 201 con la ficha creada en estado `new` y, de responsable, quien la crea (`owner_id`, `owner_email`). Sin tildes (MVP para clínicas de EE. UU.): nombre y apellidos solo con letras sin tilde, espacios, guiones, apóstrofos y puntos (Mary-Jane, O'Connor, Jr.), y el email sin tildes; si no, 422 «No se permiten tildes ni caracteres especiales (á, ñ, ü…)». Se guardan normalizados: nombre sin espacios de más (respetando mayúsculas), email en minúsculas y teléfono en formato E.164 (un número de EE. UU. de 10 cifras como `(212) 555-0123` se guarda como `+12125550123`; los de otros países deben empezar por `+`). `source`: `instagram`, `facebook`, `google`, `website`, `referral`, `walk_in` u `other`. Datos no válidos: 422 con un mensaje por campo. Mismo nombre y apellidos con el mismo email o teléfono (sin distinguir mayúsculas): 409; una familia sí puede compartir email o teléfono. Sin datos clínicos ni notas libres
- `GET /api/contacts?q=texto` (admin y recepción) → `{"total": N, "items": [...]}`: los 20 contactos más recientes que coinciden con la búsqueda y cuántos coinciden en total. `q` es opcional (sin él, todos) y de 100 caracteres como máximo; busca parte del nombre y apellidos (en cualquier orden), del email o, si lleva al menos 3 cifras, del teléfono, sin distinguir mayúsculas (los datos no llevan tildes: una búsqueda con tilde no encuentra nada). Filtros combinables con la búsqueda: `status` (se puede repetir: `?status=new&status=contacted`; sin él, todos) y `owner=me` (los míos) u `owner=none` (sin responsable). Cada contacto trae su responsable. Profesional y cliente: 403
- `GET /api/contacts/{id}` (admin y recepción) → la ficha: los datos del contacto más `version`, `updated_at`, `created_by_email` y `updated_by_email` (quién lo creó y quién lo cambió por última vez). 404 si no existe; profesional y cliente: 403
- `PUT /api/contacts/{id}` (admin y recepción, con `X-CSRF-Token`) con la ficha entera (los mismos campos y reglas que el alta, más `owner_id`: el responsable, o `null` para dejarlo sin responsable) y la `version` que se leyó → 200 con la ficha actualizada y la versión siguiente. El id no cambia y no se crea otra ficha. Si otra persona guardó antes (la versión ya no coincide): 409 «Otra persona ha cambiado esta ficha mientras la editabas». Si la edición crea un duplicado: 409 como en el alta. Un responsable nuevo debe ser una cuenta activa de recepción o administración (si no, 422 en `owner_id`). El estado comercial, el autor y las fechas no se editan aquí. Los contactos no se borran
- `PUT /api/contacts/{id}/status` (admin y recepción, con `X-CSRF-Token`) con `status` y la `version` que se leyó → 200 con la ficha y la versión siguiente. A mano solo se permite Nuevo → Contactado, cualquier estado → Perdido y Perdido → Contactado (reabrir); «Cita agendada» y «Cliente» los ponen las citas («Cita agendada», al crear una; «Cliente», más adelante, al marcar Realizada la primera) y nunca se vuelve a Nuevo: cualquier otro cambio, 422 con el motivo. Comparte la versión con la edición: si otra persona cambió la ficha antes, 409
- `GET /api/contacts/owners` (admin y recepción) → quién puede ser responsable: `[{"id", "email"}]` de las cuentas activas de recepción y administración
- `GET /api/services` → los servicios con `id`, `name`, `duration_minutes`, `active`, `version` y `staff` (quién lo realiza: `id`, `email`, `role`, `active`). Admin y recepción: todos, primero los activos y por nombre. Profesional: solo los servicios activos que tiene asignados. Cliente: 403
- `GET /api/services/staff` (admin y recepción) → quién se puede asignar a un servicio: las cuentas internas activas (administración, recepción y profesional; el jefe o la recepcionista también pueden realizar servicios)
- `POST /api/services` (admin y recepción, con `X-CSRF-Token`) con `name`, `duration_minutes` y `staff_ids` (una o más personas) → 201 con el servicio activo. Duración: múltiplo de 5 minutos, de 5 a 240 (4 horas), y un número entero. Nombre sin tildes: letras, cifras, espacios y `. , ' & + / ( ) -`, hasta 120 caracteres. Las personas deben ser cuentas internas activas. Si no: 422 junto al campo. Un nombre que ya existe, sin distinguir mayúsculas y aunque esté desactivado: 409
- `PUT /api/services/{id}` (admin y recepción, con `X-CSRF-Token`) con el servicio entero (`name`, `duration_minutes`, `staff_ids`, `active`) y la `version` que se leyó → 200 con la versión siguiente. Sirve para editar, desactivar (`active: false`) y reactivar; los servicios no se borran. Un servicio activo necesita al menos una persona; uno desactivado puede quedarse sin nadie. Solo se comprueba a quien se añade: una persona ya asignada que se desactiva después no impide guardar. Si otra persona guardó antes: 409
- `POST /api/appointments` (admin y recepción, con `X-CSRF-Token`) con `contact_id`, `service_id`, `staff_id` (una de las personas que realizan el servicio) y `starts_at` en la **hora local de la clínica**, sin zona: `"2027-01-11T09:30"` → 201 con la cita en estado `scheduled`, `starts_at` y `ends_at` en la hora de la clínica con su desfase (`"2027-01-11T09:30:00-05:00"`), la `duration_minutes` copiada del servicio y la `version`. La duración no se envía: cambiar después el servicio no cambia las citas ya dadas. La hora va en múltiplos de 5 minutos, desde ahora y como mucho dentro de 365 días; las horas que no existen o se repiten por el cambio de horario se rechazan. El servicio debe estar activo y la persona, asignada a él y con su cuenta interna activa. Si el contacto está Nuevo o Contactado pasa a «Cita agendada» (y sube su versión); si está Perdido: 422, hay que reabrirlo antes. Datos no válidos: 422 junto al campo. Profesional y cliente: 403. **Sin solapamientos por persona**: si quien la realiza ya tiene otra cita que se pisa con esta, 409 «Esa persona ya tiene una cita de 9:30 a 10:30» (en la hora de la clínica, con la fecha si la otra empieza otro día; sin el nombre del otro contacto). Una cita puede empezar justo cuando acaba otra, y las canceladas no ocupan. Lo comprueba PostgreSQL con una restricción de exclusión (extensión `btree_gist`, incluida en PostgreSQL), así que dos peticiones simultáneas no pueden guardar las dos. Un mismo contacto sí puede tener dos citas a la vez con personas distintas (por ejemplo, tinte y pedicura). Sin notas por ahora
- `GET /api/appointments?date=AAAA-MM-DD` (admin y recepción) → las citas que ocupan parte de ese día de la clínica (también la que empieza la víspera, como una de 23:30 a 0:30), por hora de inicio, con `contact_name`, `service_name` y `staff_email` además de los datos de la cita y sus horas en la de la clínica. Filtros opcionales: `staff_id` (una persona) y `contact_id` (un contacto). El día del cambio de horario tiene 23 o 25 horas y se respeta. Un día que no existe o mal escrito: 422. Profesional y cliente: 403 (el profesional verá la suya más adelante)
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

Al abrir `http://127.0.0.1:5173` aparece la pantalla de login, con el estado de la API y de la base de datos debajo. Al entrar, administración y recepción llegan a la **Agenda** y tienen una barra de secciones: Agenda (`/agenda`), Contactos (`/contactos`), Servicios (`/servicios`) y, solo administración, Usuarios (`/usuarios`). Las direcciones son las mismas para todos los roles que ven la sección; las anteriores (`/admin`, `/recepcion`, `/recepcion/contactos/7`…) llevan a la nueva. El profesional va a `/profesional` (sus servicios) y el cliente a `/portal` (por ahora, una bienvenida), sin barra. En la Agenda se ven las citas de un día por hora (inicio y fin, contacto con enlace a su ficha, servicio y quién la realiza), con «← Día anterior», «Día siguiente →», «Hoy», un calendario para ir a cualquier día y el filtro «Persona»; el día y el filtro quedan en la dirección (`/agenda?fecha=2026-11-10`), así que se puede recargar. «Nueva cita» abre el formulario: el contacto se busca por nombre, email o teléfono (los Perdidos no aparecen), el servicio solo ofrece los activos con alguien que los realice, «Quién la realiza» solo ofrece a sus personas (y queda elegida si solo hay una), y la hora se elige con dos desplegables (los minutos de 5 en 5), siempre en la hora de Nueva York. Al elegir la persona se ve qué citas tiene ya ese día. Si el contacto ya tiene otra cita a esa hora (con otra persona), se avisa, pero se puede guardar igualmente (dos servicios a la vez). Si la persona ya tiene una cita que se pisa, el 409 de la API se muestra junto al formulario. En Servicios, «Añadir servicio» pide el nombre, la duración en minutos y quién lo realiza (casillas con las cuentas internas activas); cada servicio muestra su duración, si está activo y quién lo realiza, con «Editar» y «Desactivar» o «Reactivar». Si un servicio activo no tiene a nadie disponible, se avisa de que no se podrán dar citas. En Contactos, «Nuevo contacto» abre el formulario; al guardar, el contacto aparece el primero de la lista; un dato no válido se explica junto a su campo y un duplicado, encima de los botones. El buscador filtra al dejar de escribir; los desplegables «Estado» (por defecto, los activos: todos menos Perdido) y «Responsable» (Todos, Mis contactos, Sin responsable) se combinan con él. Cada fila muestra el estado, el origen y el responsable. Cada nombre de la lista abre su ficha (`/contactos/7`, que se puede recargar), con «Dar cita» (abre el formulario de la agenda con el contacto ya elegido; no sale si está Perdido), las fechas en la hora de la clínica (Nueva York), el responsable, el botón «Editar» (que permite cambiar también el responsable) y los botones de estado permitidos: «Marcar como contactado», «Marcar como perdido» o «Reabrir (pasa a Contactado)». Si otra persona guardó la ficha mientras la editabas, se muestra lo que guardó con un aviso, en lugar de pisarlo. Si se escribe una tilde, en el formulario o en el buscador, aparece al momento el aviso «No se permiten tildes ni caracteres especiales (á, ñ, ü…)» y el contacto no se envía. Escribir a mano una sección que el rol no ve muestra «No tienes acceso a esta área», y la API rechaza igualmente sus datos (403). «Cerrar sesión» solo vuelve al login cuando la API confirma el cierre. Si la sesión caduca mientras se usa, vuelve al login con un aviso. Recargar la página mantiene la sesión: la app pregunta a `/api/auth/me` y guarda el token CSRF solo en memoria.

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

El comando se puede repetir: crea las cuentas que falten y, en las existentes, aplica la contraseña actual del `.env`, restaura el rol y las reactiva. Si falta alguna variable o es demasiado corta, no modifica la BD y dice cuál. Nunca muestra contraseñas ni hashes. Con las cuentas creadas se puede entrar desde la pantalla de login; las credenciales de prueba de la entrega se documentarán antes de entregar.

## Pendiente de completar

Funcionalidades verificadas, cuentas de demostración, URL de publicación, slides, vídeo, pruebas y limitaciones.
