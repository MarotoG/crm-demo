# Estado del CRM de clínicas y continuidad entre herramientas

Actualizado: 2026-10-30 tras respuestas del alumno y revisión del borrador de especificaciones. Este archivo registra contexto; no acredita código ni despliegue.

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

Datos actuales del servidor (T02b) y decisiones de despliegue (túnel, hostname, Access, almacenamiento, backup); hora exacta de entrega (zona Europe/Madrid confirmada por el alumno el 30/10; objetivo 15/11, el alumno menciona 15–16/11 como mediados de noviembre: planificar contra el 15/11 hasta confirmar la hora límite); hostname `crm.marotothecreator.com` indicado por el alumno como utilizable, sin comprobación propia del panel; instalación de Docker Desktop (en T05); versiones exactas de dependencias (T04–T06). Resuelto en T03: zona IANA, recorrido comercial, estados, permisos, sesión, nombre/visibilidad del repositorio y cuenta del portal por invitación (ver `10`, sección 14). Agente del editor en uso: Claude Code en VS Code.

## Implementación y evidencias

- Código implementado: ninguno.
- Pruebas del CRM ejecutadas: ninguna.
- Git local: inicializado el 30/10 en rama `main` (encargo B). D: es exFAT, sin propietarios: se añadió `safe.directory D:/CRMProject` a la configuración global de Git. `.gitignore` ampliado, `.gitattributes` (LF), `README.md` provisional y `.env.example` creados; exclusión de biblioteca, `ZZZIGNORAR/`, doc 14 y `.env` comprobada con `git check-ignore`/`git ls-files`. Por decisión del alumno, de `documentacion/` solo se versionan 04, 07, 10 y 11 (lista blanca en `.gitignore`); guías/prompts del tutor, síntesis M12, borrador y doc 14 quedan en local. GitHub: repositorio público `crm-demo` decidido, no creado.
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

## Próxima acción

Encargo B propuesto, pendiente de aprobación: inicializar Git local, ampliar `.gitignore` (`.venv/`, `__pycache__/`, `node_modules/`, `dist/`, `.pytest_cache/`), añadir `.gitattributes` (LF), README provisional y `.env.example`; revisar `git status`/`git ls-files` y primer commit tras revisión del alumno. Crear el repositorio en GitHub y hacer push solo con confirmación explícita. Después, T04 (FastAPI con Python 3.13).

En paralelo, T02b: el alumno puede ejecutar en Quijote los comandos de solo lectura del anexo A del informe y aportar la salida revisada sin secretos; confirmar en Cloudflare si `crm.marotothecreator.com` está libre y en el aula la hora/zona de entrega.

## Registro vivo

| Campo | Estado |
|---|---|
| Tarea actual | T01 y T03 cerrados; T02a documental revisado; T02b real pendiente |
| Último commit verificado | Ninguno (sin repositorio) |
| Comandos reales de arranque/pruebas | Pendientes de configuración (T04) |
| Evidencia observada | Inventario local T01; informe Quijote con hash comprobado; sin aplicación ejecutada ni servidor observado |
| Próximo hito | Encargo B (Git y esqueleto) y T04 |

Conservar una copia principal de este estado en el repositorio cuando exista y trasladarla al cambiar entre ChatGPT, Claude y editor. No hay sincronización automática. Si código y estado difieren, contrastar los hechos antes de actualizar. Las respuestas del usuario sobre prioridades prevalecen sobre suposiciones anteriores del borrador.


## Cierre aprobado de Quijote — 30/10/2026

El alumno aprobó actualizar documentación y guías. Se incorporan contexto revisado 14, resumen 15 y guía 16. Las propuestas del informe no son aprobación de cambios en servidor. Datos documentados antiguos: unos 16 GB compartidos, SSD/HDD, red y túnel compartidos; no confirmar capacidad o disponibilidad actuales sin observación.

Quedan pendientes topología final, túnel/hostname, Access, rutas/SSD-HDD, UID/GID según imagen, recursos actuales, backup propio y restauración. Plan B local y vídeo. El aislamiento de red no elimina acceso de administradores con control Docker. Verificaciones nuevas ajustan la estimación orientativa a 65 h incluyendo revisión y margen; a 4 h/día será necesario redistribuir o recortar extras.

La copia principal de este estado es `D:\CRMProject\documentacion\04_ESTADO_CRM.md`. Al cerrar tareas, actualizar allí y trasladar la versión a los tutores; no mantener varias copias de estado como si se sincronizaran automáticamente.
