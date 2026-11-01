"""Login con sesión en servidor (T08): credenciales, sesiones y límite de intentos.

Recorrido: el login comprueba email y contraseña, crea una fila en sessions y
devuelve un token aleatorio en una cookie HttpOnly. En cada petición posterior,
get_current_user busca el hash de ese token y decide si la sesión sigue valiendo.
"""

import hashlib
import secrets
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserSession
from app.security import hash_password, normalize_email, verify_password

SESSION_COOKIE = "crm_session"
SESSION_DURATION = timedelta(hours=8)  # una jornada de clínica (decisión T08)

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


def get_current_user(
    crm_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Dependencia de las rutas protegidas: 401 si no hay una sesión válida."""
    if crm_session:
        user = db.scalar(
            select(User)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                UserSession.token_hash == hash_token(crm_session),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > datetime.now(UTC),
                User.active.is_(True),
            )
        )
        if user is not None:
            return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")


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
