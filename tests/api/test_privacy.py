"""Tests unitarios del servicio de privacidad ."""

from __future__ import annotations

import pandas as pd

from vigia.app.services import privacy


def test_privacy_report_marca_columnas_de_id_por_nombre():
    df = pd.DataFrame({"Patient_Id": ["a1", "a2"], "Episode_Id": ["e1", "e2"], "Age": [30, 40]})
    informe = privacy.privacy_report(df)
    nombres = {c["name"]: c for c in informe["columns"]}
    assert set(nombres) == {"Patient_Id", "Episode_Id"}
    for col in nombres.values():
        assert col["reason"] == "nombre"
        assert col["kind"] == "identificador"
        assert col["recommendation"] == "hashear"
    assert informe["n_flagged"] == 2


def test_privacy_report_marca_dni_y_nombre_en_csv():
    df = pd.DataFrame(
        {
            "DNI": ["12345678Z", "87654321X"],
            "Nombre": ["Ana", "Luis"],
            "Edad": [45, 50],
        }
    )
    informe = privacy.privacy_report(df)
    nombres = {c["name"] for c in informe["columns"]}
    assert nombres == {"DNI", "Nombre"}
    dni = next(c for c in informe["columns"] if c["name"] == "DNI")
    assert dni["kind"] == "identificador"
    assert dni["recommendation"] == "hashear"
    nombre = next(c for c in informe["columns"] if c["name"] == "Nombre")
    assert nombre["kind"] == "dato_personal"
    assert nombre["recommendation"] == "descartar"


def test_privacy_report_detecta_dni_por_valores_sin_nombre_sugerente():
    df = pd.DataFrame({"columna_x": ["12345678Z", "23456789X", "34567890Y"]})
    informe = privacy.privacy_report(df)
    assert informe["n_flagged"] == 1
    assert informe["columns"][0]["reason"] == "valores"


def test_hmac_id_estable_y_distinto_del_original():
    salt = "00" * 32
    h1 = privacy.hmac_id(salt, "episodio-123")
    h2 = privacy.hmac_id(salt, "episodio-123")
    h3 = privacy.hmac_id(salt, "episodio-456")
    assert h1 == h2
    assert h1 != "episodio-123"
    assert h1 != h3
    assert privacy.hmac_id(salt, None) is None


def test_hmac_id_cambia_con_la_sal():
    h1 = privacy.hmac_id("00" * 32, "episodio-123")
    h2 = privacy.hmac_id("ff" * 32, "episodio-123")
    assert h1 != h2


def test_apply_decisions_hashea_y_descarta():
    df = pd.DataFrame({"DNI": ["12345678Z"], "Nombre": ["Ana"], "Edad": [45]})
    informe = privacy.privacy_report(df)
    salida, aplicado = privacy.apply_decisions(
        df, informe, {"DNI": "hashear", "Nombre": "descartar"}, "00" * 32
    )
    assert "Nombre" not in salida.columns
    assert "DNI" in salida.columns
    assert salida.loc[0, "DNI"] != "12345678Z"
    assert aplicado == {"DNI": "hashear", "Nombre": "descartar"}


def test_apply_decisions_falla_si_falta_una_decision():
    df = pd.DataFrame({"DNI": ["12345678Z"], "Nombre": ["Ana"]})
    informe = privacy.privacy_report(df)
    try:
        privacy.apply_decisions(df, informe, {"DNI": "hashear"}, "00" * 32)
    except ValueError as exc:
        assert "Nombre" in str(exc)
    else:
        raise AssertionError("se esperaba ValueError por decisión de privacidad faltante")


def test_mask_preview_enmascara_columnas_marcadas():
    df = pd.DataFrame({"DNI": ["12345678Z"], "Edad": [45]})
    informe = privacy.privacy_report(df)
    filas = privacy.mask_preview(df, informe, n=1)
    assert filas[0]["DNI"] == "***"
    assert filas[0]["Edad"] == 45
