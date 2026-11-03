"""Validación propia de nombres, emails y teléfonos (T11; sin tildes desde T12b) y de la hora de
las citas (T16), sin BD."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.validators import clinic_instant, normalize_contact_email, normalize_name, normalize_phone, parse_local_start

# --- Nombres ------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Ana", "Ana"),
        ("  Ana   Maria  ", "Ana Maria"),
        ("Maria\tJose", "Maria Jose"),
        ("O'Connor-Smith", "O'Connor-Smith"),
        ("Mary-Jane", "Mary-Jane"),
        ("John Jr.", "John Jr."),
        ("St. John", "St. John"),
        ("Ana\u00a0Maria", "Ana Maria"),  # espacio no separable (p. ej., pegado) → espacio normal
    ],
)
def test_nombres_validos_se_normalizan(entrada, esperado):
    assert normalize_name(entrada, "nombre") == esperado


@pytest.mark.parametrize(
    "entrada",
    ["José", "Jose\u0301", "Muñoz", "Zoë", "\u0410na", "Ana\u200bMaria", "Ana\u202eMaria", "Ana \U0001f600"],
    ids=["tilde", "tilde suelta", "eñe", "diéresis", "A cirílica", "ancho cero", "cambio de dirección", "emoji"],
)
def test_nombres_con_tildes_o_caracteres_especiales_se_rechazan_con_el_aviso(entrada):
    with pytest.raises(ValueError, match=r"^No se permiten tildes ni caracteres especiales \(á, ñ, ü…\)$"):
        normalize_name(entrada, "nombre")


@pytest.mark.parametrize(
    "entrada, mensaje",
    [
        ("", "El nombre no puede estar vacío"),
        ("   ", "El nombre no puede estar vacío"),
        ("A" * 101, "El nombre no puede tener más de 100 caracteres"),
        ("Ana\x00", "El nombre solo puede tener letras"),
        ("Ana2", "El nombre solo puede tener letras"),
        ("Ana@", "El nombre solo puede tener letras"),
        ("-Ana", "El nombre solo puede tener letras"),
        (".", "El nombre solo puede tener letras"),
    ],
    ids=["vacío", "solo espacios", "101 caracteres", "control", "cifra", "arroba", "guion inicial", "solo un punto"],
)
def test_nombres_no_validos(entrada, mensaje):
    with pytest.raises(ValueError, match=f"^{mensaje}"):
        normalize_name(entrada, "nombre")


# --- Emails -------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("ana@clinica.com", "ana@clinica.com"),
        ("  Ana.Smith@Clinica.COM ", "ana.smith@clinica.com"),
        ("ana+promo@mail.clinica.co", "ana+promo@mail.clinica.co"),
        ("o'neil@x-y.example.com", "o'neil@x-y.example.com"),
        ("a" * 64 + "@x.com", "a" * 64 + "@x.com"),
    ],
)
def test_emails_validos_se_normalizan(entrada, esperado):
    assert normalize_contact_email(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "ana",
        "ana@",
        "@clinica.com",
        "ana@@clinica.com",
        "ana@clinica",
        "ana@clinica.c",
        "ana@clinica.c0m",
        "ana @clinica.com",
        "ana\u200b@clinica.com",
        "ana@-clinica.com",
        "ana@clinica-.com",
        "ana@clinica..com",
        "ana@josé.com",
        "josé@clinica.com",
        "ana\x7f@clinica.com",
        "a" * 65 + "@x.com",
        "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 63 + ".com",
    ],
    ids=[
        "sin arroba", "sin dominio", "sin usuario", "dos arrobas", "sin punto", "terminación de 1 letra",
        "terminación con cifra", "espacio", "ancho cero", "guion inicial", "guion final", "punto doble",
        "dominio con tilde", "usuario con tilde", "carácter de control DEL", "usuario de 65", "más de 254",
    ],
)
def test_emails_no_validos(entrada):
    with pytest.raises(ValueError):
        normalize_contact_email(entrada)


# --- Teléfonos ----------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("(212) 555-0123", "+12125550123"),
        ("212.555.0123", "+12125550123"),
        ("2125550123", "+12125550123"),
        ("1-212-555-0123", "+12125550123"),
        ("+1 212 555 0123", "+12125550123"),
        ("+34 612 345 678", "+34612345678"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_telefonos_validos_en_e164(entrada, esperado):
    assert normalize_phone(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "123",
        "(123) 555-0123",
        "(212) 155-0123",
        "212-555-012",
        "612 345 678",
        "+0123456789",
        "+1234567",
        "+1234567890123456",
        "abc",
        "212-555-0123 ext 4",
        "٢١٢٥٥٥٠١٢٣",
        "+",
    ],
    ids=[
        "corto", "zona empieza por 1", "central empieza por 1", "9 cifras", "extranjero sin +", "país empieza por 0",
        "7 cifras", "16 cifras", "letras", "extensión", "cifras no ASCII", "solo +",
    ],
)
def test_telefonos_no_validos(entrada):
    with pytest.raises(ValueError):
        normalize_phone(entrada)


def test_email_con_tilde_da_el_aviso_de_tildes():
    with pytest.raises(ValueError, match=r"^No se permiten tildes"):
        normalize_contact_email("josé@clinica.com")


# --- Hora de las citas (T16) --------------------------------------------------------

NUEVA_YORK = ZoneInfo("America/New_York")
FORMATO = "Indica la fecha y la hora de inicio como AAAA-MM-DDTHH:MM, en hora de la clínica"


def test_hora_local_valida():
    assert parse_local_start("2027-01-11T09:30") == datetime(2027, 1, 11, 9, 30)


@pytest.mark.parametrize(
    "entrada, mensaje",
    [
        ("2027-01-11T09:30:00", FORMATO),  # con segundos
        ("2027-01-11 09:30", FORMATO),  # sin la T
        ("2027-01-11T09:30-05:00", FORMATO),  # con desfase: la zona es siempre la de la clínica
        ("2027-01-11T09:30Z", FORMATO),
        ("2027-01-11", FORMATO),
        ("11/01/2027 09:30", FORMATO),
        ("", FORMATO),
        ("２０２７-01-11T09:30", FORMATO),  # cifras de ancho completo
        ("2027-01-11T09:30\n", FORMATO),
        (" 2027-01-11T09:30", FORMATO),
        ("2027-02-30T09:30", "Esa fecha u hora no existe"),
        ("2027-01-11T24:00", "Esa fecha u hora no existe"),
        ("2027-01-11T09:32", "La hora de inicio debe ir en múltiplos de 5 minutos (9:00, 9:05, 9:10…)"),
    ],
)
def test_hora_local_no_valida(entrada, mensaje):
    with pytest.raises(ValueError) as error:
        parse_local_start(entrada)
    assert str(error.value) == mensaje


@pytest.mark.parametrize(
    "local, utc",
    [
        (datetime(2027, 1, 11, 9, 30), datetime(2027, 1, 11, 14, 30, tzinfo=UTC)),  # invierno: −5 h
        (datetime(2027, 7, 1, 9, 30), datetime(2027, 7, 1, 13, 30, tzinfo=UTC)),  # verano: −4 h
        # Justo antes y justo después de las horas dudosas de 2027 (14/03 y 07/11).
        (datetime(2027, 3, 14, 1, 55), datetime(2027, 3, 14, 6, 55, tzinfo=UTC)),
        (datetime(2027, 3, 14, 3, 0), datetime(2027, 3, 14, 7, 0, tzinfo=UTC)),
        (datetime(2027, 11, 7, 0, 55), datetime(2027, 11, 7, 4, 55, tzinfo=UTC)),
        (datetime(2027, 11, 7, 2, 0), datetime(2027, 11, 7, 7, 0, tzinfo=UTC)),
    ],
)
def test_hora_local_a_instante(local, utc):
    assert clinic_instant(local, NUEVA_YORK) == utc


@pytest.mark.parametrize("hora", [datetime(2027, 3, 14, 2, 0), datetime(2027, 3, 14, 2, 30), datetime(2027, 3, 14, 2, 55)])
def test_hora_que_no_existe_por_el_cambio_de_horario(hora):
    with pytest.raises(ValueError, match="^Esa hora no existe ese día"):
        clinic_instant(hora, NUEVA_YORK)


@pytest.mark.parametrize("hora", [datetime(2027, 11, 7, 1, 0), datetime(2027, 11, 7, 1, 30), datetime(2027, 11, 7, 1, 55)])
def test_hora_que_se_repite_por_el_cambio_de_horario(hora):
    with pytest.raises(ValueError, match="^Esa hora se repite ese día"):
        clinic_instant(hora, NUEVA_YORK)


def test_otra_zona_otro_instante():
    assert clinic_instant(datetime(2027, 1, 11, 9, 30), ZoneInfo("America/Los_Angeles")) == datetime(
        2027, 1, 11, 17, 30, tzinfo=UTC
    )
