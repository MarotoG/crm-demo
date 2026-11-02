# crm-demo — CRM para pequeñas clínicas estéticas

> **Estado: en desarrollo (Trabajo Fin de Máster, entrega noviembre de 2026).** Por ahora existen el esqueleto de la API, PostgreSQL en Docker, las migraciones de servicios y usuarios, un procedimiento para crear las cuentas de demo, login y logout con sesión en servidor, protección CSRF y un primer permiso por rol, por API (todavía sin pantalla de login) y una interfaz mínima que muestra el estado de la API y de la base de datos; todavía sin funcionalidades del CRM. Este README es provisional y se completará con hechos comprobados a medida que avance el proyecto.

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
```

En desarrollo el navegador solo habla con Vite (puerto 5173), que reenvía `/api/*` a la API (puerto 8000). La página muestra si la API y la base de datos están disponibles, y un error comprensible si no lo están.

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

El comando se puede repetir: crea las cuentas que falten y, en las existentes, aplica la contraseña actual del `.env`, restaura el rol y las reactiva. Si falta alguna variable o es demasiado corta, no modifica la BD y dice cuál. Nunca muestra contraseñas ni hashes. Todavía no hay pantalla de login; las credenciales de prueba de la entrega se documentarán al terminarla.

## Pendiente de completar

Funcionalidades verificadas, cuentas de demostración, URL de publicación, slides, vídeo, pruebas y limitaciones.
