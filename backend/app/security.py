"""Hash y verificación de contraseñas con Argon2id (argon2-cffi).

Un hash no se puede descifrar: para comprobar una contraseña se vuelve a calcular
con la sal y los parámetros guardados dentro del propio hash.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Parámetros por defecto de argon2-cffi 25.1: Argon2id, t=3, m=64 MiB, p=4
# (perfil de memoria reducida de la RFC 9106). Quedan escritos en cada hash.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True solo si la contraseña corresponde al hash; nunca lanza por datos erróneos."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def normalize_email(email: str) -> str:
    """Forma única del email para guardar y buscar: sin espacios y en minúsculas."""
    return email.strip().lower()
