from app.security import hash_password, normalize_email, verify_password


def test_hash_es_argon2id_y_no_contiene_la_contrasena():
    password_hash = hash_password("caballo-bateria-grapa")

    assert password_hash.startswith("$argon2id$")
    assert "caballo-bateria-grapa" not in password_hash


def test_verifica_la_contrasena_correcta_y_rechaza_otra():
    password_hash = hash_password("caballo-bateria-grapa")

    assert verify_password(password_hash, "caballo-bateria-grapa") is True
    assert verify_password(password_hash, "caballo-bateria-grap") is False


def test_misma_contrasena_produce_hashes_distintos_por_la_sal():
    assert hash_password("caballo-bateria-grapa") != hash_password("caballo-bateria-grapa")


def test_hash_corrupto_se_rechaza_sin_lanzar_excepcion():
    assert verify_password("no-es-un-hash", "caballo-bateria-grapa") is False


def test_normaliza_email():
    assert normalize_email("  Ana.Lopez@Demo.Example.COM ") == "ana.lopez@demo.example.com"
