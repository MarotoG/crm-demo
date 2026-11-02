# Estado del CRM de clínicas y continuidad entre herramientas

Actualizado: 2026-11-02 tras la entrega local de T09 (logout, CSRF, purga de sesiones y permisos por rol). Este archivo registra contexto; no acredita código ni despliegue por sí mismo: la evidencia está en cada sección.

## Confirmado

- Cliente objetivo: clínicas estéticas pequeñas/medianas locales en Estados Unidos, no grandes franquicias.
- Producto: CRM web con acceso móvil; visión futura de instalación y notificaciones.
- Prioridad elegida: personal de clínica + portal básico del cliente; fotos antes/después para después.
- Entrega: 15/11/2026. Disponibilidad: 4–5 h de calidad diarias. Falta hora/zona de entrega y posibles instrucciones posteriores del aula.
- Desde cero en `D:\CRMProject`, con VS Code y versiones en GitHub. En la revisión inicial solo se ha localizado un borrador Markdown de especificaciones, sin código del CRM inspeccionado.
- Stack preferido por el alumno: FastAPI y PostgreSQL; admite propuestas. React/TypeScript/Vite es la recomendación de frontend, todavía no instalado ni aceptado como decisión técnica definitiva.
- Infraestructura comunicada: ordenador antiguo con Linux, SSH, Docker en marcha y dominio propio. Se ha recibido un informe documental de Quijote sin acceso al servidor. Resumen revisado en 14; comprobación real T02b pendiente.
- Método: trabajo mixto alumno/IA; alumno supervisa fases y revisa código; encargos pequeños, uno cada vez.
- Directrices TFM leídas: README detallado, GitHub, slides, vídeo propio con pantalla y formulario; despliegue recomendado y objetivo personal.

## Propuesta de alcance, pendiente de cerrar detalles

Una clínica por instancia; administrador, recepción, profesional y cliente; leads/contactos, agenda por profesional, seguimientos internos y portal de consulta de citas propias. Un solo sistema web responsive. PWA instalable solo si queda margen; push, fotos, Stripe, facturación, widget, n8n, salas, multiempresa y app nativa después.

Documentos de diseño: `10_ESPECIFICACIONES_CRM_CLINICAS.md` y `11_BACKLOG_ATOMICO_CRM.md`. El mercado EE. UU. no acredita por sí mismo que una clínica esté cubierta por HIPAA; el TFM se plantea con datos ficticios y sin promesa de preparación comercial sanitaria.

## Pendiente

Datos actuales del servidor (T02b) y decisiones de despliegue (túnel, hostname, Access, almacenamiento, backup); hora exacta de entrega (zona Europe/Madrid confirmada por el alumno el 30/10; objetivo 15/11, el alumno menciona 15–16/11 como mediados de noviembre: planificar contra el 15/11 hasta confirmar la hora límite); hostname `crm.marotothecreator.com` indicado por el alumno como utilizable, sin comprobación propia del panel; versiones exactas del frontend (T06); revisar PostgreSQL 18.6 antes del despliegue. Resuelto en T03: zona IANA, recorrido comercial, estados, permisos, sesión, nombre/visibilidad del repositorio y cuenta del portal por invitación (ver `10`, sección 14). Agente del editor en uso: Claude Code en VS Code.

## Implementación y evidencias

- Código implementado: esqueleto FastAPI en `backend/` (T04); PostgreSQL 18.4 en Docker Compose, `GET /api/health/db` y primera migración Alembic con la tabla `services` (T05). Sin CRUD.
- Frontend (T06): React/TypeScript/Vite en `frontend/`, página de estado que consulta `/api/health` y `/api/health/db`. Sin pruebas automáticas de frontend todavía (comprobación de tipos, build y verificación visual).
- Pruebas del CRM ejecutadas: 5 con pytest (salud, salud de BD con la BD sustituida, configuración), pasan en local el 30/10; conexión real, restricción y persistencia comprobadas a mano (sección T05).
- Git local: inicializado el 30/10 en rama `main` (encargo B). D: es exFAT, sin propietarios: se añadió `safe.directory D:/CRMProject` a la configuración global de Git. `.gitignore` ampliado, `.gitattributes` (LF), `README.md` provisional y `.env.example` creados; exclusión de biblioteca, `ZZZIGNORAR/`, doc 14 y `.env` comprobada con `git check-ignore`/`git ls-files`. Por decisión del alumno, de `documentacion/` solo se versionan 04, 07, 10 y 11 (lista blanca en `.gitignore`); guías/prompts del tutor, síntesis M12, borrador y doc 14 quedan en local. GitHub: https://github.com/MarotoG/crm-demo — creado por el alumno; push de `main` el 30/10 (commit `1d6cc36`). Comprobado sin credenciales vía API: `visibility: public` y solo los 11 archivos previstos publicados.
- Despliegue: pendiente; no se ha tocado servidor, DNS, puertos ni túnel.
- Entregables académicos del software: pendientes según `07_MATRIZ_CUMPLIMIENTO_TFM.md`.
- Biblioteca/documentación: preparada y revisada; originales académicos y borrador se conservan.

## T01 — inventario local (30/10/2026, Claude Code en VS Code)

Observado con consultas de lectura, sin instalar ni modificar nada:

- Raíz: `documentacion/`, `materiales_sintetizados_vscode/` (208 Markdown + `plantillas_raiz/`), `.github/copilot-instructions.md`, `AGENTS.md` y `CLAUDE.md` (idénticos), `.gitignore`, `ZZZIGNORAR/`. Sin código del CRM ni `.git`.
- `ZZZIGNORAR/` faltaba en la primera consulta; el alumno lo restauró (borrado accidental). SHA-256 del informe comprobado: coincide con el registrado en `14`.
- Windows: Git 2.55.0 (identidad global configurada), Python 3.15.0 por defecto y 3.13 disponible (`py -3.13`), pip 26.2.1, Node 24.22.1, npm 11.19.1. **Ausentes:** Docker/Compose, psql, uv, gh.
- WSL2: Ubuntu 24.04.4 LTS x86_64, sin Docker ni psql.
- Riesgo: Python 3.15 es muy reciente para paquetes compilados; se usa 3.13.

## T03 — alcance y decisiones mínimas (30/10/2026)

Cerrado en sesión de preguntas con el alumno; detalle en `10_ESPECIFICACIONES_CRM_CLINICAS.md`, sección 14, y matriz de la sección 5. Resumen: `crm-demo`, GitHub público; desarrollo en D: con PostgreSQL en Docker y API/Vite nativos; flujo portátil → GitHub → pull en servidor; zona `America/New_York`; sesión con cookie de servidor; 5 estados de contacto y conversión automática a Cliente con la primera cita Realizada; 4 estados de cita, solo Cancelada libera; recepción marca asistencia y ve todos los seguimientos; invitación de un solo uso al portal (T21 pasa a 2,5 h, total 66,5 h); ampliaciones: PWA, fotos y reserva desde portal. Solo cambios documentales.

## T04 — esqueleto FastAPI y primera prueba (30/10/2026)

- Estructura: `backend/app/main.py` (aplicación y `GET /api/health` → `{"status":"ok"}`), `backend/tests/test_health.py`, `backend/pyproject.toml` (solo configuración de pytest), `requirements.txt` y `requirements-dev.txt`.
- `.venv` creado con `py -3.13` (Python 3.13.0). Dependencias fijadas, incluidas transitivas: 23 paquetes; `pip check` sin errores; el entorno se recreó desde cero con los archivos finales antes de probar.
- Criterio de versiones: ninguna publicada después del 16/10/2026, comprobado con la API JSON de PyPI. FastAPI 0.143.2 (15/10; se evita la ráfaga de ~20 versiones del 16–23/10), Starlette 1.8.0, Pydantic 2.14.1, Uvicorn 0.54.0, pytest 9.1.1. pip trajo por defecto transitivas recientes (Starlette 1.10.0, Pydantic 2.14.2, certifi y opentelemetry-api de finales de octubre) y se bajaron a la última elegible.
- `TestClient` usa `httpx2` 2.13.1 en lugar de `httpx`: con Starlette 1.8, `httpx` provoca `StarletteDeprecationWarning`.
- Evidencia: `pytest -v` → `1 passed in 0.83s`, sin avisos. Uvicorn en `127.0.0.1:8000`: `/api/health` 200 `application/json` `{"status":"ok"}`; `/docs` 200 (título «crm-demo API - Swagger UI»); `/openapi.json` 200 con la ruta `/api/health`; ruta inexistente 404. Comprobado por HTTP, no visualmente en navegador: Swagger UI carga recursos desde un CDN.
- Comandos documentados en `README.md`. `.venv`, `__pycache__` y `.pytest_cache` excluidos por `.gitignore`.

T04 cerrado: aprobado por el alumno, commit `a55738f` publicado en GitHub el 30/10 (comprobado sin credenciales vía API: 17 archivos, sin `.venv` ni cachés).

## T05 — PostgreSQL y primera migración (30/10/2026)

- Docker Desktop instalado por el alumno con `winget` (silencioso, backend WSL2, sin contenedores Windows). Primer fallo: la aplicación no se había abierto tras instalar. Al abrirla: cliente/servidor 29.9.2 `linux/amd64`, Compose v5.6.1, `hello-world` correcto, distribución `docker-desktop` Running.
- Decisión del alumno: `/api/health` no toca la BD; `/api/health/db` sí la consulta (`SELECT 1`) y responde 503 `{"status":"error","database":"unavailable"}` sin detalles internos; el motivo queda en el log del servidor.
- `compose.yaml` (proyecto `crm-demo`, servicio `db`, volumen con nombre `crm-demo_db_data`, healthcheck `pg_isready`, `restart: unless-stopped`) y `compose.override.yaml` (solo local: puerto `127.0.0.1:5432`). Imagen `postgres:18.4-trixie@sha256:a02db8ca…31636` (05/08/2026; no existe etiqueta 18.5 y 18.6 es del 28/10: revisar al cumplir el plazo, antes del despliegue). En PG 18 el volumen se monta en `/var/lib/postgresql`. Volumen con nombre y no carpeta de D: porque exFAT no guarda permisos Linux.
- `.env` creado por el alumno en la raíz con contraseña y clave aleatorias generadas sin mostrarse; comprobado sin leer valores: ignorado por Git, sin BOM, 8 variables, sin valores de ejemplo. `CRM_DB_HOST` pasa a `127.0.0.1` en `.env.example`. Sin `.env`, Compose se niega a arrancar con un mensaje claro.
- Backend: `app/config.py` (pydantic-settings, lee `CRM_*` del `.env` de la raíz; contraseña obligatoria y oculta al imprimir la URL), `app/db.py` (Engine síncrono, `pool_pre_ping`, `connect_timeout` 3 s), `app/models.py` (Base con convención de nombres y modelo `Service`: id, name 120, duration_minutes > 0, active true por defecto). Alembic: URL desde `app.config`, nunca en `alembic.ini`; archivos con fecha. Migración `18953254f3b5` autogenerada y revisada.
- Dependencias nuevas (≤ 16/10): SQLAlchemy 2.1.4, Alembic 1.20.0, psycopg[binary] 3.3.6, pydantic-settings 2.15.0 (se evita 2.16.0, del límite del plazo y con dos parches posteriores) y transitivas; `tzdata` bajado de 2026.6 a 2026.5. 32 paquetes fijados, entorno recreado desde cero, `pip check` limpio.
- Evidencia: `pytest -v` → 5 passed. `docker compose up -d db` → healthy en ~6 s. `alembic upgrade head` → `18953254f3b5 (head)`; `\d services` muestra columnas y `ck_services_duration_minutes_positive`; insertar duración 0 se rechaza. API real: BD encendida → `/api/health/db` 200; `docker compose stop db` → 503 en ~3 s y `/api/health` sigue 200; al arrancar, se recupera sola. Persistencia: `docker compose down` (sin `-v`) elimina contenedor y red, el volumen sigue; `up` crea un contenedor nuevo y los 2 servicios de demo y la versión de migración siguen. La contraseña no aparece en el log de la API (comprobado sin mostrarla).
- Entorno del alumno: activó `python.terminal.useEnvFile` en VS Code (en `.vscode/settings.json`, ignorado por Git): las terminales nuevas reciben las variables del `.env`. Recomendación: desactivarlo (ver conversación).

T05 cerrado: aprobado por el alumno, commit `fa20405` publicado en GitHub el 30/10 (comprobado sin credenciales vía API: 29 archivos, sin `.env`, `.venv`, cachés ni `.vscode`).

## T06 — esqueleto React responsive y conexión API (30/10/2026)

- Escrito a mano en `frontend/` (sin la plantilla de `create vite`, que añade ESLint y ~10 dependencias): `package.json`, `.npmrc` (`save-exact`), `tsconfig.json` (estricto, solo comprobación de tipos), `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/api.ts`, `src/index.css`.
- Versiones exactas: React/React DOM 19.3.1 (14/10, parche publicado a la vez en todas las ramas de React), Vite 8.3.4, @vitejs/plugin-react 6.1.2, TypeScript 7.0.2, @types/react(-dom) 19.3.0. Instaladas con `npm install --before=2026-10-16`: las 68 entradas de `package-lock.json` (con binarios opcionales de otras plataformas) comprobadas en el registro, ninguna posterior al corte. `npm ci` desde el lockfile: 24 paquetes instalados (25 auditados contando el propio proyecto), 0 vulnerabilidades.
- Proxy de Vite: el navegador solo habla con `127.0.0.1:5173` y Vite reenvía `/api` a `127.0.0.1:8000`; un único origen como tras nginx, sin CORS.
- Página: estado de API y BD con estados cargando/ok/error, botón «Volver a comprobar» desactivado mientras carga, `aria-live`, móvil primero (fila en ≥ 30rem). Mensajes por código: 502/504 «La API no responde» (lo genera el proxy), 503 «No disponible», otros «Error del servidor»; sin conexión o sin respuesta en 10 s, mensaje propio.
- Problema encontrado y corregido: con la BD parada, la segunda petición idéntica a `/api/health/db` tardaba 6 s en vez de 3. Chrome pone en fila GET idénticos simultáneos para reutilizar la caché, y `StrictMode` duplica el efecto en desarrollo. Medido en el navegador (Resource Timing): 3075/6115 ms → con `cache: "no-store"` 3045/3063 ms. Límite del cliente subido de 5 a 10 s, holgado frente a los 3 s de `connect_timeout` de la API.
- Evidencia: `tsc` 7.0.2 revisa los 4 archivos y detecta un error de tipo provocado (exit 1). `npm run build` → `dist/` (JS 221 kB, 69 kB gzip). `npm run dev`: HTML servido, `/api/health` y `/api/health/db` 200 a través del proxy; BD parada → 503; API apagada → 502 del proxy. Capturas con Chrome headless (perfil temporal) a 375 px y 800 px de los estados todo OK, API caída, BD caída y cargando; guardadas fuera del repositorio, en el scratchpad de la sesión.
- Sin pruebas automáticas de frontend (Vitest u otra herramienta): se propondrán cuando haya lógica de interfaz con reglas (login, formularios).
- Revisión previa al commit, pedida por el alumno (30/10): pytest 5 passed; `pip check` limpio; 32 fijados = 32 instalados; `alembic check` sin diferencias entre modelos y BD; `compileall` OK; `npm ls` sin errores (solo dependencias opcionales no usadas); `npm audit` 0; `tsc` OK; Vite 8 y plugin-react 6 exigen Node ^20.19 o ≥22.12 (hay 24.22.1); `docker compose config` válido; sin CRLF. Evaluación SOLID/KISS/YAGNI y riesgos en la conversación. Riesgo detectado: con `python.terminal.useEnvFile` activo, una terminal abierta antes de regenerar `.env` conserva variables `CRM_*` antiguas, que tienen prioridad sobre el `.env` en pydantic-settings y en Compose.

T06 cerrado: el alumno comprobó la página en su navegador y aprobó; commit `f65d9bb` publicado en GitHub el 31/10 (comprobado sin credenciales vía API y `raw.githubusercontent.com`). El alumno mantenía entonces `python.terminal.useEnvFile` activo: si `/api/health/db` da 503 inesperado, abrir una terminal nueva y comprobar `Test-Path env:CRM_DB_PASSWORD`.

## T07 — usuarios y cuentas de demo (31/10/2026)

- Decisión del alumno (31/10): las contraseñas de demo viven solo en el `.env` local (ignorado por Git), en `CRM_DEMO_PASSWORD_ADMIN`, `_RECEPTION`, `_PROFESSIONAL` y `_CLIENT`; `.env.example` lleva los nombres vacíos. Qué credenciales se publican en README/formulario (el PDF pide usuario y contraseña de prueba en ambos; el alumno prefiere entregarlas aparte al profesor) se decide antes de la entrega.
- Dependencia nueva (corte 17/10, comprobada en PyPI con wheel cp313/abi3 para Windows): argon2-cffi 25.1.0 y transitivas argon2-cffi-bindings 26.1.0, cffi 2.1.1, pycparser 3.11 (se evita 3.12, del 22/10). 36 fijados = 36 instalados, `pip check` limpio. Parámetros por defecto: Argon2id, t=3, m=64 MiB, p=4 (RFC 9106, perfil de memoria reducida).
- `app/models.py`: `Role` (admin, reception, professional, client) y `User` (id, email 254 único, password_hash, role, active). La BD exige rol válido (`ck_users_role_valid`) y email normalizado (`ck_users_email_normalized`, `email = lower(btrim(email))`). El vínculo único con el contacto se añadirá cuando exista `contacts` (T11/T21). Migración `299ce8870114` autogenerada y revisada.
- `app/security.py`: `hash_password`, `verify_password` (devuelve False ante contraseña errónea o hash corrupto) y `normalize_email`. `app/seed_demo.py`: comando idempotente `python -m app.seed_demo`; valida las cuatro contraseñas (presentes, ≥ 12 caracteres) antes de tocar la BD y escribe las cuatro cuentas en una sola transacción; no muestra contraseñas ni hashes. Emails ficticios en `demo.example.com` (RFC 2606). No es una migración de datos, para no dejar hashes en el historial.
- Evidencia: `pytest -v` → 13 passed (8 nuevas: formato `$argon2id$`, verificación correcta/errónea, sal distinta, hash corrupto, normalización, validación de variables sin revelar valores, una cuenta por rol); las pruebas eliminan variables `CRM_DEMO_*` del entorno y no dependen del `.env`. `alembic upgrade head` → `299ce8870114`; `downgrade -1` y `upgrade` de nuevo correctos; `alembic check` sin diferencias. `\d users` muestra columnas, `pk_users`, `uq_users_email` y los dos CHECK; con SQL directo y `ROLLBACK` se rechazan email con mayúsculas, rol `superadmin` y email duplicado. Comando sin variables → exit 1, mensaje con las cuatro que faltan, 0 filas. Con contraseñas de un solo uso pasadas como variables del proceso (sin tocar `.env`): 1.ª ejecución crea 4, 2.ª actualiza 4 sin duplicar, 3.ª con contraseñas nuevas: la nueva verifica y la antigua no; ninguna contraseña aparece en la salida; hashes `$argon2id$v=19$m=65536,t=3,p=4$`. Cuenta admin desactivada y con rol cambiado a mano → el comando la reactiva y restaura `admin`. Mensajes correctos en PowerShell 5.1.
- El alumno rellenó las cuatro `CRM_DEMO_PASSWORD_*` en su `.env` y ejecutó `python -m app.seed_demo` (31/10): «actualizada» en las 4 cuentas, que ya tienen sus contraseñas en lugar de las de prueba.
- `.vscode/settings.json` tiene `python.terminal.useEnvFile: false` (observado el 31/10); pendiente de que el alumno confirme que lo desactivó.

T07 cerrado: aprobado por el alumno, commit `e42670a` publicado en GitHub el 31/10 (comprobado sin credenciales vía API: 12 archivos en el commit, 53 rastreados [corrección 01/11: eran 53 entradas del árbol contando carpetas; 44 archivos], sin `.env`, `historico/`, `.vscode`, `.venv` ni biblioteca; `seed_demo.py` accesible en `raw.githubusercontent.com`).

## T08 — login y sesión en servidor (31/10/2026)

- Decisiones del alumno (31/10): sesión de 8 h fijas; límite de 5 fallos en 15 min por (IP, email normalizado) con 429, sin bloquear la cuenta, en memoria; implementación propia y pequeña (tras explicarle sesión en servidor frente a cookie sellada, fastapi-users y SessionMiddleware); BD de pruebas `crm_demo_test` en el mismo contenedor. Por defecto aceptados: token de 32 bytes con solo su SHA-256 en BD, cookie `crm_session` HttpOnly, SameSite=Lax, Secure salvo `CRM_ENV=development`, Max-Age 8 h; 401 genérico con tiempo similar (hash ficticio si el email no existe); logout y CSRF en T09.
- Código: modelo `UserSession` (tabla `sessions`: token_hash único, user_id con `ON DELETE CASCADE` e índice, created/expires/revoked_at con zona); migración `a9c4f93aec77`. `app/auth.py` (`authenticate`, `create_session`, `get_current_user`, `LoginRateLimiter` con tope de memoria); `app/auth_routes.py` (`POST /api/auth/login`, `GET /api/auth/me`, longitudes máximas 254/1024). `app/db.py`: `get_db` (Depends) y `get_database_check`; `/api/health/db` recibe la comprobación por Depends (se elimina `monkeypatch`) y sigue dando 503 aunque falte el `.env`. Manejador global: `OperationalError` → 503 «Servicio no disponible» (antes 500). `migrations/env.py` acepta una conexión externa (pruebas). Sin dependencias nuevas.
- Pruebas: `tests/conftest.py` crea y migra `crm_demo_test`, una transacción deshecha por prueba, salvaguarda de nombre `_test` y barrera que hace fallar cualquier prueba que use la BD sin el fixture `db`; sin PostgreSQL esas pruebas se saltan. `pytest` → 45 passed (BD encendida) / 24 passed + 21 skipped (BD apagada). 10 mutaciones deliberadas (sin comprobar activo, caducidad, revocación, HttpOnly, reinicio del contador, normalización en el limitador, longitud máxima, token en claro, health_db) → las 10 detectadas. `crm_demo` intacta (4 usuarios, 0 sesiones) y `crm_demo_test` sin filas tras las pruebas.
- API real: `/api/auth/me` sin cookie o con token falso → 401; datos vacíos → 422; 5 fallos → el 6.º 429; tiempos con email existente/inexistente ~0,15 s ambos; BD parada → login y me 503 en ~3 s, log sin tokens ni contraseñas, recuperación al arrancar. Login correcto con contraseña real de demo: comprobado por el alumno con `Get-Credential` + `Invoke-RestMethod` contra `/api/auth/login` y `/api/auth/me`. Repetido el 01/11 antes del commit: `pytest` → 45 passed, `alembic check` sin diferencias.
- Revisión general (pedida por el alumno): pip check, 36 = 36, `alembic check`, compileall, `npm run build`, `npm audit` 0, Compose válido, sin CRLF. Casos límite y riesgos en la conversación y en `historico/T08_historico.md`: IP del proxy en producción (el limitador se volvería por email global), limitador por proceso, sesiones caducadas sin purga, caracteres invisibles en emails, carrera de dos `seed_demo` (la segunda falla con UniqueViolation, sin duplicados).

T08 cerrado: aprobado por el alumno, commit `d7ff293` publicado en GitHub el 01/11 (comprobado sin credenciales vía API: 15 archivos en el commit, 51 archivos rastreados iguales en local y remoto, sin `.env`, `historico/`, `.vscode`, `.venv` ni biblioteca; `auth.py` accesible en `raw.githubusercontent.com`).

## T09 — logout, CSRF, purga de sesiones y permisos por rol (02/11/2026)

- Decisiones del alumno (01–02/11, tras explicarle CSRF, purga, ruta de admin y alcance del logout): CSRF con token secreto (HMAC) en vez de solo comprobar `Origin`/`Sec-Fetch-Site`, porque protege también frente a otros subdominios del mismo dominio (p. ej. n8n); retención de sesiones de 30 días con borrado automático; `GET /api/users` solo para admin como primera ruta de administración (resto 403, sin sesión 401); logout solo de la sesión actual. Propuesto y aceptado por defecto: la purga automática se hace en cada login (sin tarea programada) y además hay comando manual. El registro de qué usuario accede a qué datos de qué cliente (control de auditoría, en la línea de HIPAA) queda para cuando existan los contactos (T11 en adelante), en una tabla propia: `sessions` no es ese registro. `CRM_SECRET_KEY` comprobada por el alumno sin mostrarla: 64 caracteres, distinta del ejemplo.
- Código: `app/config.py` valida `CRM_SECRET_KEY` (≥ 32, distinta del ejemplo; opcional para que `/api/health/db` no dependa de ella) y `hide_input_in_errors` evita que un error muestre valores. `app/auth.py`: `find_valid_session`, `csrf_token_for` (HMAC-SHA256 del token de sesión con la clave; no se guarda, se recalcula), `csrf_matches` (`compare_digest` sobre bytes), `require_csrf` (401 sin sesión, 403 sin token válido), `require_roles` (403 «Permiso denegado») y `purge_expired_sessions` (borra `expires_at < now − 30 días`). `app/auth_routes.py`: login y `/me` devuelven `csrf_token`; el login purga; `POST /api/auth/logout` → 204, revoca la sesión y borra la cookie con los mismos atributos; sin sesión válida 204; con sesión válida y sin token 403. `app/users_routes.py`: `GET /api/users` (id, email, rol, activo). `app/purge_sessions.py`: comando manual. Logs de 403 por rol y por CSRF con user_id, rol y ruta, sin tokens ni emails. Sin migración ni dependencias nuevas.
- Pruebas: `pytest` → 83 passed (38 nuevas: `test_csrf`, `test_logout`, `test_permissions`, `test_purge_sessions`, `test_route_protection`, que recorre el OpenAPI y exige 401 sin sesión en toda ruta no incluida en la lista de públicas). 15 mutaciones deliberadas → 15 detectadas (la de «clave de ejemplo aceptada» sobrevivió al principio porque el ejemplo ya era corto; se ajustó la prueba para exigir el mensaje concreto). `alembic check` sin diferencias, `pip check` limpio, sin CRLF, imports sin avisos. `crm_demo` intacta (4 usuarios, 1 sesión: la del login real del alumno) y `crm_demo_test` sin filas.
- API real (uvicorn en 8001 contra `crm_demo_test`, usuarios temporales con contraseña aleatoria no mostrada, borrados al final): login 200 con `csrf_token` y cookie HttpOnly/Lax/8 h; `/me` devuelve el mismo token; recepción en `/api/users` 403; logout sin cabecera o con token falso 403 y la sesión sigue; logout con token 204 y `Max-Age=0`; después `/me` 401, también reenviando la cookie antigua; la otra sesión (móvil) sigue en 200; logout repetido 204; profesional y cliente 403; admin 200 con 4 usuarios y campos `active, email, id, role`; sin sesión 401. `python -m app.purge_sessions` → «Sesiones borradas: 0», exit 0. Comprobado por el alumno el 02/11 con las cuentas de demo reales (`Get-Credential`, API en el 8000): admin → `/api/users` 200; recepción → 403; en ambas, logout sin token 403 y la sesión sigue (me 200), logout con token 204 y la cookie antigua 401.
- Límites asumidos: el login no lleva CSRF (no hay sesión de la que derivarlo; «login CSRF» aceptado); los logs `INFO` (logout) no se ven hasta configurar logging (T28); cambiar `CRM_SECRET_KEY` invalida los tokens CSRF vigentes; un XSS en el propio CRM anularía cualquier protección CSRF.

## Próxima acción

T09 entregado en local, pendiente de revisión del alumno, commit y push (incluye la anotación de `d7ff293` en 04 y 07). Siguiente propuesta: T10, login en la interfaz y rutas por rol (entrar/salir desde el navegador, enviar `X-CSRF-Token`, estados de carga/error). Pendiente de aprobación.

En paralelo, T02b: el alumno puede ejecutar en Quijote los comandos de solo lectura del anexo A del informe y aportar la salida revisada sin secretos; confirmar en Cloudflare si `crm.marotothecreator.com` está libre y en el aula la hora/zona de entrega.

## Registro vivo

| Campo | Estado |
|---|---|
| Tarea actual | T09 entregado en local (pendiente de revisión, commit y push); T01, T03, T04, T05, T06, T07, T08 y encargo B cerrados; T02a documental revisado; T02b real pendiente |
| Último commit verificado | `d7ff293` (T08) en `main`, publicado en GitHub (01/11/2026) |
| Comandos reales de arranque/pruebas | Raíz: `docker compose up -d db`. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -v`; `.venv\Scripts\alembic.exe upgrade head`; `.venv\Scripts\python.exe -m app.seed_demo`; `.venv\Scripts\python.exe -m uvicorn app.main:app --reload`. Desde `frontend/`: `npm ci`; `npm run dev`; `npm run build` (ver README) |
| Evidencia observada | Inventario local T01; informe Quijote con hash comprobado; local 30/10: pytest 5 passed, PostgreSQL healthy, migración aplicada, persistencia tras `down`/`up`, interfaz build OK y estados OK/API caída/BD caída verificados en Chrome headless; 31/10: pytest 13 passed, migración `users` aplicada y reversible, cuentas de demo idempotentes con hash Argon2id; T08: pytest 45 passed con BD de pruebas, 10/10 mutaciones detectadas, login/me/429/503 en API real; T09: pytest 83 passed, 15/15 mutaciones, logout/CSRF/permisos en API real; servidor no observado |
| Próximo hito | Cerrar T09; después T10: login en la interfaz y rutas por rol |

Histórico narrativo por fases (decisiones, alternativas descartadas, dónde está cada cosa en el código y preguntas del tribunal) en `documentacion/historico/`, solo local e ignorado por Git; se actualiza al cerrar cada tarea, antes de proponer el commit.

Conservar una copia principal de este estado en el repositorio cuando exista y trasladarla al cambiar entre ChatGPT, Claude y editor. No hay sincronización automática. Si código y estado difieren, contrastar los hechos antes de actualizar. Las respuestas del usuario sobre prioridades prevalecen sobre suposiciones anteriores del borrador.


## Cierre aprobado de Quijote — 30/10/2026

El alumno aprobó actualizar documentación y guías. Se incorporan contexto revisado 14, resumen 15 y guía 16. Las propuestas del informe no son aprobación de cambios en servidor. Datos documentados antiguos: unos 16 GB compartidos, SSD/HDD, red y túnel compartidos; no confirmar capacidad o disponibilidad actuales sin observación.

Quedan pendientes topología final, túnel/hostname, Access, rutas/SSD-HDD, UID/GID según imagen, recursos actuales, backup propio y restauración. Plan B local y vídeo. El aislamiento de red no elimina acceso de administradores con control Docker. Verificaciones nuevas ajustan la estimación orientativa a 65 h incluyendo revisión y margen; a 4 h/día será necesario redistribuir o recortar extras.

La copia principal de este estado es `D:\CRMProject\documentacion\04_ESTADO_CRM.md`. Al cerrar tareas, actualizar allí y trasladar la versión a los tutores; no mantener varias copias de estado como si se sincronizaran automáticamente.
