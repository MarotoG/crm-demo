"""Normalización y validación de datos de contacto (T11), servicios (T15) y la hora de las citas
(T16), con código propio y sin dependencias.

Cada función devuelve el valor ya normalizado (el que se guarda) o lanza ValueError con
un mensaje para el usuario. La BD repite las reglas básicas con restricciones CHECK.

Sin tildes (decisión T12b): el MVP es para clínicas de EE. UU.; nombres y emails solo
admiten caracteres ASCII. Una lista cerrada de caracteres permitidos deja fuera también,
sin reglas aparte, los invisibles, los de control y las letras que imitan a otras
(«А» cirílica). Si hiciera falta admitir tildes, sería una versión posterior.
"""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

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


# --- Servicios (T15) -------------------------------------------------------------

MAX_SERVICE_NAME_LENGTH = 120
# Nombre de servicio: empieza por letra o cifra; después letras sin tilde, cifras, espacio y
# . , ' & + / ( ) - («Botox (forehead)», «Peel 2/3»). La BD repite la expresión.
_SERVICE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,'&+/()-]*$")

# Duración (decisión T15): múltiplos de 5 minutos, hasta 4 horas. La BD repite la regla.
MIN_DURATION_MINUTES = 5
MAX_DURATION_MINUTES = 240
DURATION_STEP_MINUTES = 5


def normalize_service_name(value: str) -> str:
    """Nombre de servicio: sin espacios en los extremos ni repetidos; no vacío; sin tildes."""
    name = " ".join(value.split())
    if not name:
        raise ValueError("El nombre del servicio no puede estar vacío")
    if len(name) > MAX_SERVICE_NAME_LENGTH:
        raise ValueError(f"El nombre no puede tener más de {MAX_SERVICE_NAME_LENGTH} caracteres")
    if not name.isascii():
        raise ValueError(NO_ACCENTS_MESSAGE)
    if not _SERVICE_NAME.match(name):
        raise ValueError("El nombre solo puede tener letras, cifras, espacios y . , ' & + / ( ) -, y empezar por letra o cifra")
    return name


def check_duration(minutes: int) -> int:
    if not MIN_DURATION_MINUTES <= minutes <= MAX_DURATION_MINUTES or minutes % DURATION_STEP_MINUTES:
        raise ValueError(
            f"La duración debe ser un múltiplo de {DURATION_STEP_MINUTES} minutos, "
            f"entre {MIN_DURATION_MINUTES} y {MAX_DURATION_MINUTES} (4 horas)"
        )
    return minutes


# --- Citas (T16) -----------------------------------------------------------------

# Hora de inicio (decisión T16): la hora local de la clínica, sin zona, en minutos exactos.
# [0-9] y no \d: en Python, \d acepta también cifras de otras escrituras («２０２７»).
_LOCAL_START = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}")
START_STEP_MINUTES = 5
START_FORMAT_MESSAGE = "Indica la fecha y la hora de inicio como AAAA-MM-DDTHH:MM, en hora de la clínica"


def parse_local_start(value: str) -> datetime:
    """«2027-01-11T09:30» → datetime sin zona. Sin segundos ni zona: la zona es siempre la de la clínica."""
    # fullmatch y no match: con «$», un salto de línea final también pasaría.
    if not _LOCAL_START.fullmatch(value):
        raise ValueError(START_FORMAT_MESSAGE)
    try:
        local = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("Esa fecha u hora no existe") from None
    if local.minute % START_STEP_MINUTES:
        raise ValueError(f"La hora de inicio debe ir en múltiplos de {START_STEP_MINUTES} minutos (9:00, 9:05, 9:10…)")
    return local


def clinic_instant(local: datetime, zone: ZoneInfo) -> datetime:
    """La hora local de la clínica como instante en UTC, rechazando las horas dudosas del cambio de horario.

    En primavera el reloj salta de 1:59 a 3:00: las 2:30 no existen ese día. En otoño vuelve de
    1:59 a 1:00: la 1:30 ocurre dos veces. Las dos se rechazan en vez de adivinar cuál quería.
    """
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        # Ida y vuelta: una hora que no existe cambia al pasar a UTC y volver; una repetida, no.
        if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local:
            raise ValueError("Esa hora no existe ese día: el reloj se adelanta una hora por el cambio de horario")
        raise ValueError("Esa hora se repite ese día por el cambio de horario: elige otra")
    return first.astimezone(UTC)


# --- Cancelación de una cita (T19) --------------------------------------------------

MAX_CANCEL_NOTE_LENGTH = 200
# Una línea de caracteres ASCII visibles y espacios. La BD repite la regla (ck_appointments_cancel_note_ascii).
_CANCEL_NOTE = re.compile(r"[ -~]+")


def _short_line(value: str, name: str) -> str | None:
    note = " ".join(value.split())
    if not note:
        return None
    if len(note) > MAX_CANCEL_NOTE_LENGTH:
        raise ValueError(f"{name} no puede tener más de {MAX_CANCEL_NOTE_LENGTH} caracteres")
    if not _CANCEL_NOTE.fullmatch(note):
        raise ValueError(NO_ACCENTS_MESSAGE)
    return note


def normalize_cancel_note(value: str) -> str | None:
    """Detalle opcional de la cancelación: una línea sin espacios repetidos; vacío → sin detalle."""
    return _short_line(value, "El detalle")


# --- Notas de la ficha y de la cita (T21b) -------------------------------------------

MAX_NOTE_LENGTH = MAX_CANCEL_NOTE_LENGTH


def normalize_note(value: str) -> str | None:
    """Nota opcional, con la misma forma que el detalle de una cancelación; vacía → sin nota."""
    return _short_line(value, "La nota")
