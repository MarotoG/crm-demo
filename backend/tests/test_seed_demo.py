"""Validación de contraseñas de demo sin BD; la escritura se comprueba con la BD real (ver README)."""

import pytest

from app.models import Role
from app.seed_demo import DEMO_EMAILS, DemoPasswords, check_passwords


@pytest.fixture(autouse=True)
def sin_variables_de_demo(monkeypatch):
    # Una terminal con CRM_DEMO_PASSWORD_* cargadas no debe alterar las pruebas.
    for role in Role:
        monkeypatch.delenv(f"CRM_DEMO_PASSWORD_{role.name}", raising=False)


def passwords(**values):
    # _env_file=None: la prueba no depende del .env local.
    return DemoPasswords(_env_file=None, **values)


VALIDAS = {role.value: f"demo-{role.value}-larga" for role in Role}


def test_sin_problemas_si_estan_las_cuatro():
    assert check_passwords(passwords(**VALIDAS)) == []


def test_avisa_de_las_que_faltan_y_de_las_cortas_sin_mostrar_valores():
    problems = check_passwords(passwords(admin="corta", professional=VALIDAS["professional"]))

    assert problems == [
        "CRM_DEMO_PASSWORD_ADMIN tiene menos de 12 caracteres",
        "falta CRM_DEMO_PASSWORD_RECEPTION",
        "falta CRM_DEMO_PASSWORD_CLIENT",
    ]
    assert not any("corta" in problem for problem in problems)


def test_hay_una_cuenta_por_rol_con_email_ficticio():
    assert set(DEMO_EMAILS) == set(Role)
    assert all(email.endswith("@demo.example.com") for email in DEMO_EMAILS.values())
