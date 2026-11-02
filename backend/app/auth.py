"""Login con sesión en servidor (T08), logout, CSRF y permisos por rol (T09).

Recorrido: el login comprueba email y contraseña, crea una fila en sessions y
devuelve un token aleatorio en una cookie HttpOnly. En cada petición posterior,
get_current_user busca el hash de ese token y decide si la sesión sigue valiendo.
Las peticiones que cambian datos llevan además la cabecera X-CSRF-Token, y
require_roles decide qué roles pueden usar cada ruta.
"""

import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Role, User, UserSession
from app.security import hash_password, normalize_email, verify_password

logger = logging.getLogger(__name__)

SESSION_COOKIE = "crm_session"
SESSION_DURATION = timedelta(hours=8)  # una jornada de clínica (decisión T08)
# Las sesiones caducadas se guardan un mes y luego se borran (decisión T09). No es el
# registro de auditoría de accesos a datos de clientes: ese irá en su propia tabla.
SESSION_RETENTION = timedelta(days=30)
CSRF_HEADER = "X-CSRF-Token"

# Hash de una contraseña que nadie conoce. Si el email no existe se verifica contra
# él igualmente, para que la respuesta tarde lo mismo y no delate qué emails existen.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def hash_token(token: str) -> str:
    """SHA-256 basta para el token: es aleatorio y largo, no adivinable como una contraseña."""
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Devuelve el usuario si las credenciales son válidas y la cuenta está activa."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(_DUMMY_HASH, password)
        return None
    # Se verifica antes de mirar active: una cuenta desactivada tarda lo mismo en fallar.
    if not verify_password(user.password_hash, password) or not user.active:
        return None
    return user


def create_session(db: Session, user: User, now: datetime | None = None) -> str:
    """Crea la sesión y devuelve el token en claro (solo viaja en la cookie)."""
    now = now or datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    db.add(UserSession(token_hash=hash_token(token), user_id=user.id, expires_at=now + SESSION_DURATION))
    return token


def find_valid_session(db: Session, token: str) -> tuple[UserSession, User] | None:
    """La sesión y su usuario si el token vale: existe, no caducó, no se revocó y la cuenta está activa."""
    row = db.execute(
        select(UserSession, User)
        .join(User, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
            User.active.is_(True),
        )
    ).first()
    return None if row is None else (row[0], row[1])


def get_current_user(
    crm_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Dependencia de las rutas protegidas: 401 si no hay una sesión válida."""
    if crm_session:
        found = find_valid_session(db, crm_session)
        if found is not None:
            return found[1]
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")


def purge_expired_sessions(db: Session, now: datetime | None = None, retention: timedelta = SESSION_RETENTION) -> int:
    """Borra las sesiones caducadas hace más de `retention`; devuelve cuántas.

    Basta mirar expires_at: una sesión revocada también caduca, como mucho 8 h después de crearse.
    """
    now = now or datetime.now(UTC)
    result = db.execute(delete(UserSession).where(UserSession.expires_at < now - retention))
    return result.rowcount


# --- CSRF ------------------------------------------------------------------


def _csrf_key() -> bytes:
    key = get_settings().secret_key
    if key is None:
        raise RuntimeError("Falta CRM_SECRET_KEY en el .env de la raíz (ver .env.example)")
    return key.get_secret_value().encode()


def csrf_token_for(session_token: str, key: bytes | None = None) -> str:
    """Token CSRF de una sesión: HMAC-SHA256 del token de sesión con CRM_SECRET_KEY.

    Sin la cookie (HttpOnly) y sin la clave no se puede calcular, así que otra web
    no puede falsificarlo. No hace falta guardarlo: se recalcula en cada petición.
    """
    key = _csrf_key() if key is None else key
    return hmac.new(key, b"csrf:" + session_token.encode(), hashlib.sha256).hexdigest()


def csrf_matches(session_token: str, sent: str | None) -> bool:
    if not sent:
        return False
    # compare_digest tarda lo mismo acierte o falle; con bytes acepta también caracteres no ASCII.
    return hmac.compare_digest(csrf_token_for(session_token).encode(), sent.encode())


def require_csrf(
    request: Request,
    user: User = Depends(get_current_user),
    crm_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
) -> User:
    """Dependencia de toda ruta que cambie datos: 401 sin sesión y 403 sin token CSRF válido."""
    if crm_session is None or not csrf_matches(crm_session, x_csrf_token):
        logger.warning("CSRF rechazado: user_id=%s %s %s", user.id, request.method, request.url.path)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token CSRF ausente o no válido")
    return user


# --- Permisos por rol -------------------------------------------------------


def require_roles(*roles: Role) -> Callable[..., User]:
    """Dependencia que solo deja pasar a los roles indicados: 401 sin sesión, 403 con otro rol."""
    allowed = frozenset(roles)

    def dependency(request: Request, user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            logger.warning(
                "Permiso denegado: user_id=%s rol=%s %s %s", user.id, user.role, request.method, request.url.path
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permiso denegado")
        return user

    return dependency


class LoginRateLimiter:
    """Cuenta fallos de login por (IP, email) en una ventana deslizante, en memoria.

    No bloquea la cuenta (nadie puede dejar sin acceso a otro desde otra IP). Limitaciones
    asumidas: se reinicia con la API y no se comparte entre varios procesos.
    """

    def __init__(self, max_failures: int = 5, window_seconds: float = 15 * 60, max_keys: int = 10_000):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._failures: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()  # las rutas síncronas se ejecutan en varios hilos

    def is_blocked(self, key: tuple[str, str], now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            failures = self._prune(key, now)
            return failures is not None and len(failures) >= self.max_failures

    def register_failure(self, key: tuple[str, str], now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            if key not in self._failures and len(self._failures) >= self.max_keys:
                self._prune_all(now)
                if len(self._failures) >= self.max_keys:
                    # Tope de memoria ante una avalancha de emails distintos: se descarta
                    # la clave más antigua en vez de crecer sin límite.
                    self._failures.pop(next(iter(self._failures)))
            self._failures.setdefault(key, deque()).append(now)

    def reset(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()

    def _prune(self, key: tuple[str, str], now: float) -> deque[float] | None:
        failures = self._failures.get(key)
        if failures is None:
            return None
        while failures and now - failures[0] >= self.window_seconds:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return None
        return failures

    def _prune_all(self, now: float) -> None:
        for key in list(self._failures):
            self._prune(key, now)


login_limiter = LoginRateLimiter()
