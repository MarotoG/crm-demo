"""LoginRateLimiter sin BD ni reloj real: el instante se pasa explícitamente."""

from app.auth import LoginRateLimiter

CLAVE = ("10.0.0.1", "ana@prueba.example.com")


def test_bloquea_al_llegar_al_maximo_de_fallos():
    limiter = LoginRateLimiter(max_failures=3, window_seconds=60)
    for t in range(2):
        limiter.register_failure(CLAVE, now=t)
    assert not limiter.is_blocked(CLAVE, now=2)

    limiter.register_failure(CLAVE, now=2)

    assert limiter.is_blocked(CLAVE, now=3)


def test_la_ventana_es_deslizante():
    limiter = LoginRateLimiter(max_failures=3, window_seconds=60)
    for t in (0, 10, 20):
        limiter.register_failure(CLAVE, now=t)

    assert limiter.is_blocked(CLAVE, now=59)
    assert not limiter.is_blocked(CLAVE, now=60)  # el fallo del instante 0 ya no cuenta


def test_reset_borra_los_fallos():
    limiter = LoginRateLimiter(max_failures=1, window_seconds=60)
    limiter.register_failure(CLAVE, now=0)

    limiter.reset(CLAVE)

    assert not limiter.is_blocked(CLAVE, now=1)


def test_la_memoria_no_crece_sin_limite():
    limiter = LoginRateLimiter(max_failures=5, window_seconds=60, max_keys=100)

    for i in range(1000):  # avalancha de emails distintos
        limiter.register_failure(("10.0.0.1", f"u{i}@x.example.com"), now=i * 0.001)

    assert len(limiter._failures) <= 100
