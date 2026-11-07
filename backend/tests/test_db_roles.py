"""El usuario limitado de la API (T28): lo que puede y lo que no, comprobado actuando con ese usuario."""

import pytest
from psycopg.errors import InsufficientPrivilege
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.db_roles import AppRoleSettings, apply_app_role, main
from app.models import Base

ROLE = "crm_app_prueba"


@pytest.fixture
def limited(db: Session) -> Session:
    apply_app_role(db.connection(), ROLE, "una-contrasena-de-prueba")
    db.execute(text(f"SET LOCAL ROLE {ROLE}"))
    return db


def assert_denied(session: Session, sql: str) -> None:
    # «permission denied» o «must be owner», según la operación: las dos son esta misma clase de error.
    with pytest.raises(ProgrammingError) as error:
        with session.begin_nested():
            session.execute(text(sql))
    assert isinstance(error.value.orig, InsufficientPrivilege)


def test_sin_poderes_de_administracion(db: Session) -> None:
    apply_app_role(db.connection(), ROLE, "una-contrasena-de-prueba")
    fila = db.execute(
        text("SELECT rolsuper, rolcreatedb, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname = :r"), {"r": ROLE}
    ).one()
    assert tuple(fila) == (False, False, False, True)


def test_la_contrasena_no_se_guarda_en_claro(db: Session) -> None:
    apply_app_role(db.connection(), ROLE, "una-contrasena-de-prueba")
    guardada = db.scalar(text("SELECT rolpassword FROM pg_authid WHERE rolname = :r"), {"r": ROLE})
    assert guardada.startswith("SCRAM-SHA-256$")
    assert "una-contrasena-de-prueba" not in guardada


def test_repetir_actualiza_la_contrasena_sin_fallar(db: Session) -> None:
    consulta = text("SELECT rolpassword FROM pg_authid WHERE rolname = :r")
    apply_app_role(db.connection(), ROLE, "una-contrasena-de-prueba")
    primera = db.scalar(consulta, {"r": ROLE})
    apply_app_role(db.connection(), ROLE, "otra-contrasena-de-prueba")
    assert db.scalar(consulta, {"r": ROLE}) != primera


def test_puede_trabajar_con_todas_las_tablas_de_la_app(db: Session) -> None:
    apply_app_role(db.connection(), ROLE, "una-contrasena-de-prueba")
    tablas = {t.name for t in Base.metadata.sorted_tables}
    assert {"users", "contacts", "appointments", "sessions", "audit_events"} <= tablas
    for tabla in tablas:
        for privilegio in ("SELECT", "INSERT"):
            assert db.scalar(select(text(f"has_table_privilege('{ROLE}', '{tabla}', '{privilegio}')")))
        puede_cambiar = tabla != "audit_events"
        for privilegio in ("UPDATE", "DELETE"):
            assert db.scalar(select(text(f"has_table_privilege('{ROLE}', '{tabla}', '{privilegio}')"))) is puede_cambiar


def test_puede_insertar_de_verdad_usando_las_secuencias(limited: Session) -> None:
    nuevo = limited.scalar(text("INSERT INTO services (name, duration_minutes) VALUES ('Prueba rol', 30) RETURNING id"))
    assert nuevo is not None
    limited.execute(text("INSERT INTO audit_events (action) VALUES ('login_failed')"))
    assert limited.scalar(text("SELECT count(*) FROM audit_events")) >= 1


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_events SET action = 'login_failed'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
        "TRUNCATE contacts",
        "SELECT * FROM alembic_version",
        "CREATE TABLE intrusa (id int)",
        "DROP TABLE contacts",
        "ALTER TABLE contacts DROP COLUMN email",
        "ALTER TABLE appointments DROP CONSTRAINT ex_appointments_staff_overlap",
        "CREATE ROLE otra LOGIN",
    ],
)
def test_no_puede(limited: Session, sql: str) -> None:
    assert_denied(limited, sql)


def test_main_sin_contrasena_avisa_y_no_toca_la_bd(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.delenv("CRM_APP_DB_PASSWORD", raising=False)
    monkeypatch.setitem(AppRoleSettings.model_config, "env_file", None)
    assert main() == 1
    assert "CRM_APP_DB_PASSWORD" in capsys.readouterr().err
