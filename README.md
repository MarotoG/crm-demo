# crm-demo — CRM para pequeñas clínicas estéticas

> **Estado: en desarrollo (Trabajo Fin de Máster, entrega noviembre de 2026).** Por ahora existen el esqueleto de la API, PostgreSQL en Docker y la primera migración (tabla de servicios); todavía sin funcionalidades del CRM. Este README es provisional y se completará con hechos comprobados a medida que avance el proyecto.

## Descripción

CRM web responsive para clínicas estéticas pequeñas y medianas de Estados Unidos. Objetivo: seguir el recorrido de un contacto desde la primera consulta comercial hasta la cita y su seguimiento, con un portal donde cada cliente consulta solo sus propias citas.

Núcleo previsto: login con cuatro roles (administración, recepción, profesional y cliente), contactos/leads, agenda por profesional sin solapamientos, seguimientos internos y portal de cliente por invitación.

**Solo datos ficticios.** Este proyecto académico no está preparado para tratar datos reales de pacientes ni se presenta como conforme a HIPAA.

## Stack previsto

- Backend: Python 3.13 + FastAPI, SQLAlchemy y Alembic
- Base de datos: PostgreSQL 18.4 (imagen oficial fijada por digest en `compose.yaml`)
- Frontend: React + TypeScript + Vite
- Despliegue: Docker Compose

Las versiones exactas se fijan al crear cada parte (backend: `backend/requirements*.txt`).

## Estructura prevista

```
backend/                API FastAPI, pruebas y migraciones (Alembic)
frontend/               interfaz React (pendiente)
nginx/                  servidor web y proxy de /api (pendiente)
compose.yaml            servicios Docker comunes (por ahora, PostgreSQL)
compose.override.yaml   ajustes solo locales (puerto de la BD en 127.0.0.1)
documentacion/          especificaciones, backlog y estado del proyecto
```

## Instalación y ejecución

Requisitos: Git, Python 3.13, Docker Desktop (backend WSL2) y, más adelante, Node.js 24 LTS. En desarrollo, PostgreSQL corre en Docker y la API se ejecuta directamente en Windows.

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

# Pruebas (no necesitan la BD)
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

Dependencias: `requirements.txt` (ejecución) y `requirements-dev.txt` (pruebas), con todas las versiones fijadas, incluidas las transitivas.

## Pendiente de completar

Funcionalidades verificadas, cuentas de demostración, URL de publicación, slides, vídeo, pruebas y limitaciones.
