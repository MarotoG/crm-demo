"""Borra las sesiones caducadas hace más de 30 días (T09).

Uso, desde backend/:
    .venv\\Scripts\\python.exe -m app.purge_sessions

Cada login ya lo hace solo; este comando sirve para hacerlo a mano o programarlo
en el servidor (T28). Solo muestra cuántas filas ha borrado.
"""

import sys

from sqlalchemy.orm import Session

from app.auth import SESSION_RETENTION, purge_expired_sessions
from app.db import get_engine


def main() -> int:
    with Session(get_engine()) as session, session.begin():
        deleted = purge_expired_sessions(session)
    print(f"Sesiones borradas: {deleted} (caducadas hace más de {SESSION_RETENTION.days} días)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
