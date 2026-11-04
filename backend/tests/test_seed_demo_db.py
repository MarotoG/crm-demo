"""El comando de cuentas de demo contra PostgreSQL real (antes solo había evidencia manual)."""

from sqlalchemy import func, select

from app.models import Contact, Role, User
from app.security import verify_password
from app.seed_demo import DEMO_EMAILS, DemoPasswords, upsert_demo_users


def passwords(sufijo: str) -> DemoPasswords:
    return DemoPasswords(_env_file=None, **{role.value: f"demo-{role.value}-{sufijo}" for role in Role})


def test_crea_cuatro_cuentas_y_es_idempotente(db, monkeypatch):
    for role in Role:
        monkeypatch.delenv(f"CRM_DEMO_PASSWORD_{role.name}", raising=False)

    primera = upsert_demo_users(db, passwords("uno"))
    db.flush()
    segunda = upsert_demo_users(db, passwords("dos"))
    db.flush()

    assert all(linea.startswith("creada") for linea in primera)
    assert all(linea.startswith("actualizada") for linea in segunda)
    assert db.scalar(select(func.count()).select_from(User)) == 4
    for role, email in DEMO_EMAILS.items():
        user = db.scalar(select(User).where(User.email == email))
        assert user.role == role and user.active
        assert verify_password(user.password_hash, f"demo-{role.value}-dos")
        assert not verify_password(user.password_hash, f"demo-{role.value}-uno")


def test_solo_la_cuenta_de_cliente_queda_vinculada_a_un_unico_contacto_ficticio(db):
    upsert_demo_users(db, passwords("uno"))
    db.flush()
    upsert_demo_users(db, passwords("dos"))
    db.flush()

    contacto = db.scalar(select(Contact))
    assert db.scalar(select(func.count()).select_from(Contact)) == 1
    assert contacto.email == DEMO_EMAILS[Role.CLIENT] and contacto.status == "new"
    for role, email in DEMO_EMAILS.items():
        user = db.scalar(select(User).where(User.email == email))
        assert user.contact_id == (contacto.id if role == Role.CLIENT else None)


def test_vincula_la_cuenta_de_cliente_que_ya_existia_sin_contacto(db):
    db.add(User(email=DEMO_EMAILS[Role.CLIENT], password_hash="x", role=Role.CLIENT))
    db.flush()

    upsert_demo_users(db, passwords("uno"))
    db.flush()

    user = db.scalar(select(User).where(User.email == DEMO_EMAILS[Role.CLIENT]))
    assert user.contact_id == db.scalar(select(Contact.id))
