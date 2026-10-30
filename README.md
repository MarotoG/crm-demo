# crm-demo — CRM para pequeñas clínicas estéticas

> **Estado: en desarrollo (Trabajo Fin de Máster, entrega noviembre de 2026).** Todavía no hay código ejecutable. Este README es provisional y se completará con hechos comprobados a medida que avance el proyecto.

## Descripción

CRM web responsive para clínicas estéticas pequeñas y medianas de Estados Unidos. Objetivo: seguir el recorrido de un contacto desde la primera consulta comercial hasta la cita y su seguimiento, con un portal donde cada cliente consulta solo sus propias citas.

Núcleo previsto: login con cuatro roles (administración, recepción, profesional y cliente), contactos/leads, agenda por profesional sin solapamientos, seguimientos internos y portal de cliente por invitación.

**Solo datos ficticios.** Este proyecto académico no está preparado para tratar datos reales de pacientes ni se presenta como conforme a HIPAA.

## Stack previsto

- Backend: Python 3.13 + FastAPI, SQLAlchemy y Alembic
- Base de datos: PostgreSQL
- Frontend: React + TypeScript + Vite
- Despliegue: Docker Compose

Las versiones exactas se fijarán al crear cada parte.

## Estructura prevista

```
backend/    API FastAPI y pruebas
frontend/   interfaz React
nginx/      servidor web y proxy de /api
documentacion/  especificaciones, backlog y estado del proyecto
```

## Instalación y ejecución

Pendiente. Requisitos previstos: Git, Python 3.13, Node.js 24 LTS y Docker Desktop. La configuración se hará copiando `.env.example` a `.env`.

## Pendiente de completar

Funcionalidades verificadas, cuentas de demostración, URL de publicación, slides, vídeo, pruebas y limitaciones.
