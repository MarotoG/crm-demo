"""Configuración de la API leída de variables de entorno o del .env de la raíz."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# El mismo .env que usa Docker Compose: D:\CRMProject\.env (no se versiona).
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="CRM_", extra="ignore")

    env: str = "development"
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "crm_demo"
    db_user: str = "crm_demo"
    db_password: SecretStr  # obligatoria: sin valor por defecto

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
