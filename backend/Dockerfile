# Imagen de la API (T28). La misma sirve para las migraciones y los datos de demo.
# Python 3.13.17 sobre Debian 13, fijado por digest (publicado el 24/10/2026).
FROM python:3.13.17-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962

# Sin .pyc (el contenedor va de solo lectura) y sin retrasos en los logs.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /srv

# Primero las dependencias: si solo cambia el código, esta capa se reutiliza.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini logging.json ./
COPY migrations ./migrations
COPY app ./app

# Sin privilegios: el proceso no es root dentro del contenedor.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin crm
USER crm

# Sin registro de accesos aquí: ya lo lleva nginx, con la IP real y sin parámetros de la dirección.
# WEB_CONCURRENCY y FORWARDED_ALLOW_IPS (procesos e IP de confianza) llegan desde el Compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "logging.json", "--no-access-log", "--no-server-header"]
