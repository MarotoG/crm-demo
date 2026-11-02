"""Configuración de la API leída de variables de entorno o del .env de la raíz."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# El mismo .env que usa Docker Compose: D:\CRMProject\.env (no se versiona).
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


# Valor de ejemplo de .env.example: nunca se acepta como clave real.
SECRET_KEY_PLACEHOLDER = "cambiar-por-una-clave-aleatoria"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    # hide_input_in_errors: si una variable no es válida, el error no muestra su valor.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_prefix="CRM_", extra="ignore", hide_input_in_errors=True
    )

    env: str = "development"
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "crm_demo"
    db_user: str = "crm_demo"
    db_password: SecretStr  # obligatoria: sin valor por defecto
    # Firma los tokens CSRF (T09). Opcional aquí para que /api/health/db no dependa de
    # ella; las rutas de sesión fallan con un mensaje claro si falta.
    secret_key: SecretStr | None = None

    @field_validator("secret_key")
    @classmethod
    def _secret_key_valida(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            if value.get_secret_value() == SECRET_KEY_PLACEHOLDER:
                raise ValueError("CRM_SECRET_KEY tiene el valor de ejemplo: genera una propia")
            if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
                raise ValueError(f"CRM_SECRET_KEY debe tener al menos {MIN_SECRET_KEY_LENGTH} caracteres")
        return value

    @property
    def database_url(self) -> URL:
        # URL.create escapa caracteres especiales de la contraseña y la oculta al imprimirla.
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    # Se lee al primer uso, no al importar: /api/health funciona aunque falte el .env.
    return Settings()
