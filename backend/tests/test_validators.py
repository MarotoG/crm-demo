"""Validación propia de nombres, emails y teléfonos (T11), sin BD."""

import pytest

from app.validators import normalize_contact_email, normalize_name, normalize_phone

# --- Nombres ------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Ana", "Ana"),
        ("  Ana   María  ", "Ana María"),
        ("María\tJosé", "María José"),
        ("O'Connor-Smith", "O'Connor-Smith"),
        ("Ana María", "Ana María"),  # espacio no separable → espacio normal
        ("José", "José"),  # «e» + tilde suelta → «é» de un solo carácter (NFC)
    ],
)
def test_nombres_validos_se_normalizan(entrada, esperado):
    assert normalize_name(entrada, "nombre") == esperado


def test_email_con_tilde_suelta_se_une_en_un_caracter():
    assert normalize_contact_email("josé@clinica.com") == "josé@clinica.com"


@pytest.mark.parametrize(
    "entrada",
    ["", "   ", "Ana​María", "Ana‮María", "Ana\x00", "A" * 101],
    ids=["vacío", "solo espacios", "ancho cero", "cambio de dirección", "control", "101 caracteres"],
)
def test_nombres_no_validos(entrada):
    with pytest.raises(ValueError):
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
        "ana​@clinica.com",
        "ana@-clinica.com",
        "ana@clinica-.com",
        "ana@clinica..com",
        "ana@josé.com",
        "a" * 65 + "@x.com",
        "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 63 + ".com",
    ],
    ids=[
        "sin arroba", "sin dominio", "sin usuario", "dos arrobas", "sin punto", "terminación de 1 letra",
        "terminación con cifra", "espacio", "ancho cero", "guion inicial", "guion final", "punto doble",
        "dominio con tilde (límite asumido)", "usuario de 65", "más de 254",
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
