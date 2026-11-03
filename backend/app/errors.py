"""Errores de validación con el mensaje para el usuario, comunes a contactos (T11) y servicios (T15)."""

from collections.abc import Callable

from fastapi import HTTPException, status
from pydantic_core import PydanticCustomError


def user_message(normalize: Callable[[str], str]) -> Callable[[str], str]:
    """Convierte el ValueError de un validador en un error de Pydantic con el mensaje tal cual."""

    def validator(value: str) -> str:
        try:
            return normalize(value)
        except ValueError as error:
            raise PydanticCustomError("dato_no_valido", str(error)) from None

    return validator


def field_error(field: str, message: str) -> HTTPException:
    """422 con la misma forma que los de Pydantic, para que la interfaz lo muestre junto al campo."""
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"type": "dato_no_valido", "loc": ["body", field], "msg": message}],
    )
