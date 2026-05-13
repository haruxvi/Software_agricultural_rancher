"""Tests unitarios para backend.utils.log_safe."""

from backend.utils.log_safe import sanitize_for_log


def test_newline_reemplazado() -> None:
    assert sanitize_for_log("predio\nid") == "predio_id"


def test_carriage_return_reemplazado() -> None:
    assert sanitize_for_log("predio\rid") == "predio_id"


def test_tab_reemplazado() -> None:
    assert sanitize_for_log("predio\tid") == "predio_id"


def test_null_byte_reemplazado() -> None:
    assert sanitize_for_log("predio\x00id") == "predio_id"


def test_string_normal_sin_cambios() -> None:
    assert sanitize_for_log("colchagua-norte-2024") == "colchagua-norte-2024"


def test_valor_no_string_se_convierte() -> None:
    assert sanitize_for_log(42) == "42"
    assert sanitize_for_log(3.14) == "3.14"
    assert sanitize_for_log(None) == "None"


def test_trunca_a_max_length() -> None:
    larga = "a" * 200
    resultado = sanitize_for_log(larga, max_length=100)
    assert len(resultado) == 100


def test_trunca_antes_de_sanitizar() -> None:
    # 98 'a' + newline + 'b' → truncado a 100 → newline queda dentro → se sanitiza
    entrada = "a" * 98 + "\n" + "b"
    resultado = sanitize_for_log(entrada, max_length=100)
    assert "\n" not in resultado
    assert len(resultado) == 100


def test_multiples_control_chars() -> None:
    assert sanitize_for_log("a\r\nb\tc\x00d") == "a__b_c_d"
