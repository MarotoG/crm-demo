# Estado del CRM de clínicas y continuidad entre herramientas

Actualizado: 2026-10-30 tras la entrega local de T04 (esqueleto FastAPI). Este archivo registra contexto; no acredita código ni despliegue por sí mismo: la evidencia está en cada sección.

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

## Próxima acción

T05 entregado, pendiente de revisión del alumno, commit y push. Siguiente propuesta: T06, esqueleto React/TypeScript/Vite que llama a `/api/health` y muestra el error si falla, pendiente de aprobación.

En paralelo, T02b: el alumno puede ejecutar en Quijote los comandos de solo lectura del anexo A del informe y aportar la salida revisada sin secretos; confirmar en Cloudflare si `crm.marotothecreator.com` está libre y en el aula la hora/zona de entrega.

## Registro vivo

| Campo | Estado |
|---|---|
| Tarea actual | T05 entregado en local (pendiente de revisión, commit y push); T01, T03, T04 y encargo B cerrados; T02a documental revisado; T02b real pendiente |
| Último commit verificado | `a55738f` en `main`, publicado en GitHub (30/10/2026) |
| Comandos reales de arranque/pruebas | Raíz: `docker compose up -d db`. Desde `backend/`: `.venv\Scripts\python.exe -m pytest -v`; `.venv\Scripts\alembic.exe upgrade head`; `.venv\Scripts\python.exe -m uvicorn app.main:app --reload` (ver README) |
| Evidencia observada | Inventario local T01; informe Quijote con hash comprobado; local 30/10: pytest 5 passed, PostgreSQL healthy, migración aplicada, `/api/health/db` 200/503, persistencia tras `down`/`up`; servidor no observado |
| Próximo hito | T06: esqueleto React responsive conectado a `/api/health` |

Conservar una copia principal de este estado en el repositorio cuando exista y trasladarla al cambiar entre ChatGPT, Claude y editor. No hay sincronización automática. Si código y estado difieren, contrastar los hechos antes de actualizar. Las respuestas del usuario sobre prioridades prevalecen sobre suposiciones anteriores del borrador.


## Cierre aprobado de Quijote — 30/10/2026

El alumno aprobó actualizar documentación y guías. Se incorporan contexto revisado 14, resumen 15 y guía 16. Las propuestas del informe no son aprobación de cambios en servidor. Datos documentados antiguos: unos 16 GB compartidos, SSD/HDD, red y túnel compartidos; no confirmar capacidad o disponibilidad actuales sin observación.

Quedan pendientes topología final, túnel/hostname, Access, rutas/SSD-HDD, UID/GID según imagen, recursos actuales, backup propio y restauración. Plan B local y vídeo. El aislamiento de red no elimina acceso de administradores con control Docker. Verificaciones nuevas ajustan la estimación orientativa a 65 h incluyendo revisión y margen; a 4 h/día será necesario redistribuir o recortar extras.

La copia principal de este estado es `D:\CRMProject\documentacion\04_ESTADO_CRM.md`. Al cerrar tareas, actualizar allí y trasladar la versión a los tutores; no mantener varias copias de estado como si se sincronizaran automáticamente.
