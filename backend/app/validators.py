"""Normalización y validación de datos de contacto (T11), con código propio y sin dependencias.

Cada función devuelve el valor ya normalizado (el que se guarda) o lanza ValueError con
un mensaje para el usuario. La BD repite las reglas básicas con restricciones CHECK.

Sin tildes (decisión T12b): el MVP es para clínicas de EE. UU.; nombres y emails solo
admiten caracteres ASCII. Una lista cerrada de caracteres permitidos deja fuera también,
sin reglas aparte, los invisibles, los de control y las letras que imitan a otras
(«А» cirílica). Si hiciera falta admitir tildes, sería una versión posterior.
"""

import re

MAX_EMAIL_LENGTH = 254
MAX_LOCAL_PART_LENGTH = 64
MAX_NAME_LENGTH = 100

NO_ACCENTS_MESSAGE = "No se permiten tildes ni caracteres especiales (á, ñ, ü…)"

# Nombre o apellidos: empieza por letra; después letras, espacio, guion, apóstrofo o punto
# (Mary-Jane, O'Connor, Jr.). La BD repite esta misma expresión (ck_contacts_*_ascii).
_NAME = re.compile(r"^[A-Za-z][A-Za-z '.-]*$")
# Email: caracteres ASCII visibles, sin espacios (de «!» a «~»).
_EMAIL_CHARS = re.compile(r"^[!-~]+$")
# Parte de dominio: letras, cifras y guiones, sin guion al principio ni al final.
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TLD = re.compile(r"^[a-z]{2,63}$")
_PHONE_SEPARATORS = re.compile(r"[\s().\-]")


def normalize_name(value: str, field: str) -> str:
    """Nombre o apellidos: sin espacios en los extremos ni repetidos; no vacío; sin tildes."""
    name = " ".join(value.split())
    if not name:
        raise ValueError(f"El {field} no puede estar vacío")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"El {field} no puede tener más de {MAX_NAME_LENGTH} caracteres")
    if not name.isascii():
        raise ValueError(NO_ACCENTS_MESSAGE)
    if not _NAME.match(name):
        raise ValueError(f"El {field} solo puede tener letras, espacios, guiones, apóstrofos y puntos, y empezar por letra")
    return name


def normalize_contact_email(value: str) -> str:
    """Email en minúsculas y sin espacios en los extremos, con un formato razonable y sin tildes.

    No comprueba que el buzón exista: eso solo se sabe enviando un correo.
    """
    email = value.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValueError(f"El email no puede tener más de {MAX_EMAIL_LENGTH} caracteres")
    if not email.isascii():
        raise ValueError(NO_ACCENTS_MESSAGE)
    if not _EMAIL_CHARS.match(email):
        raise ValueError("El email contiene espacios o caracteres no permitidos")
    if email.count("@") != 1:
        raise ValueError("El email debe tener una sola @")
    local, domain = email.split("@")
    if not local or len(local) > MAX_LOCAL_PART_LENGTH:
        raise ValueError("El email no es válido: falta lo que va antes de la @ o es demasiado largo")
    labels = domain.split(".")
    if len(labels) < 2 or not all(_DOMAIN_LABEL.match(label) for label in labels) or not _TLD.match(labels[-1]):
        raise ValueError("El dominio del email no es válido (por ejemplo: nombre@clinica.com)")
    return email


def normalize_phone(value: str) -> str:
    """Teléfono en formato E.164 (+ y de 8 a 15 cifras).

    EE. UU. (decisión T11): 10 cifras, o 11 empezando por 1, se guardan como +1XXXXXXXXXX y
    se exige el formato norteamericano (prefijo de zona y central que no empiecen por 0 ni 1).
    Otros países: deben empezar por + y el prefijo del país.
    """
    raw = value.strip()
    digits = _PHONE_SEPARATORS.sub("", raw)
    international = digits.startswith("+")
    if international:
        digits = digits[1:]
    if not digits.isdigit() or not digits.isascii():
        raise ValueError("El teléfono solo puede tener cifras, espacios, guiones, puntos, paréntesis y un + inicial")

    if not international:
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) != 10:
            raise ValueError("Teléfono de EE. UU.: 10 cifras. Para otros países, empieza por + y el prefijo")
        digits = "1" + digits

    if digits.startswith("1"):
        national = digits[1:]
        if len(national) != 10 or national[0] in "01" or national[3] in "01":
            raise ValueError("El teléfono de EE. UU. no es válido (p. ej. (212) 555-0123)")
    elif not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise ValueError("El teléfono internacional no es válido (+ prefijo del país y de 8 a 15 cifras)")
    return "+" + digits
