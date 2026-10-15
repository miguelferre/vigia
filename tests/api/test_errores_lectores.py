"""Los tres lectores de CSV comparten mensajes y no
dejan colas `{exc}` de pandas."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from vigia.app.services.human_layer import _read_usage_csv
from vigia.app.services.outcomes import _read_outcomes_csv
from vigia.core.loaders import (
    MSG_CODIFICACION,
    MSG_FICHERO_VACIO,
    MSG_FORMATO_NO_RECONOCIDO,
    read_csv_smart,
    sniff_csv_dialect,
)
from vigia.core.schema import DatosNoValidos

# la fila 3 (línea 4 del fichero) trae una columna de más
CSV_ROTO = b"date,human_decision,model_output,ground_truth\n2026-01-01,refer,refer,refer\n2026-01-02,refer,refer,refer\n2026-01-03,refer,refer,refer,sobra\n"


def _mensaje_del_lector(leer, raw: bytes) -> str:
    try:
        leer(raw)
    except HTTPException as exc:
        assert exc.status_code == 422
        return str(exc.detail)
    except DatosNoValidos as exc:
        return str(exc)
    raise AssertionError("el lector no ha fallado")


def test_los_tres_lectores_dan_el_mismo_mensaje_con_el_numero_de_linea():
    mensajes = {
        "loaders": _mensaje_del_lector(lambda r: read_csv_smart(r), CSV_ROTO),
        "uso": _mensaje_del_lector(_read_usage_csv, CSV_ROTO),
        "outcomes": _mensaje_del_lector(_read_outcomes_csv, CSV_ROTO),
    }
    assert len(set(mensajes.values())) == 1, mensajes
    texto = mensajes["uso"]
    assert "línea 4" in texto
    assert "pandas" not in texto.lower() and "Error tokenizing" not in texto and "C error" not in texto


def test_los_lectores_de_uso_y_outcomes_leen_punto_y_coma_y_cp1252():
    uso = "date;human_decision;model_output;ground_truth\n2026-01-01;refer;refer;refer\n".encode("cp1252")
    df = _read_usage_csv(uso)
    assert list(df.columns)[:2] == ["date", "human_decision"]
    out = "period;metric_key;value;source\n2026-01;acierto;0,8;ref\n".encode("cp1252")
    assert len(_read_outcomes_csv(out)) == 1


def test_faltan_columnas_lista_sin_corchetes_de_python():
    texto = _mensaje_del_lector(_read_usage_csv, b"date,human_decision\n2026-01-01,refer\n")
    assert texto.startswith("faltan columnas obligatorias")
    assert "[" not in texto and "'" not in texto
    texto = _mensaje_del_lector(_read_outcomes_csv, b"period,metric_key\n2026-01,x\n")
    assert texto.startswith("faltan columnas obligatorias")
    assert "[" not in texto


def test_loaders_fichero_vacio_o_en_blanco():
    for raw in (b"", b"   \r\n  \n"):
        with pytest.raises(DatosNoValidos, match="el fichero está vacío"):
            sniff_csv_dialect(raw)
    assert "vacío" in MSG_FICHERO_VACIO


def test_loaders_binario_no_dice_xlsx():
    with pytest.raises(DatosNoValidos) as err:
        sniff_csv_dialect(b"PK\x03\x04\x00\x00\x00binario")
    texto = str(err.value)
    assert texto == MSG_FORMATO_NO_RECONOCIDO
    assert "XLSX" not in texto
    assert "guárdalo como CSV" in texto


def test_loaders_cp1252_roto_dice_que_codificaciones_prueba():
    # 0x81 no existe en cp1252 y no es utf-8 válido
    with pytest.raises(DatosNoValidos) as err:
        sniff_csv_dialect(bytes([0x81, 0x8D, 0x8F, 0x90, 0x9D]) * 10)
    texto = str(err.value)
    assert texto == MSG_CODIFICACION
    assert "UTF-8" in texto and "Windows-1252" in texto
    assert texto.startswith("no se reconoce el formato del fichero")


def test_loaders_codificacion_rota_mas_alla_de_la_muestra():
    cuerpo = b"a,b\n" + b"1,2\n" * 30000 + b"\x81,\x8d\n"
    with pytest.raises(DatosNoValidos) as err:
        read_csv_smart(cuerpo)
    assert str(err.value) == MSG_CODIFICACION


def test_fila_con_columnas_de_menos_tambien_da_su_numero_de_linea():
    corto = b"date,human_decision,model_output,ground_truth\n2026-01-01,refer,refer,refer\n2026-01-02,refer,refer\n"
    for leer in (_read_usage_csv, _read_outcomes_csv):
        texto = _mensaje_del_lector(leer, corto)
        assert "línea 3" in texto and "número de columnas distinto" in texto
    # las líneas en blanco y los campos vacíos al final no cuentan como filas rotas
    bien = b"date,human_decision,model_output,ground_truth\n\n2026-01-01,refer,refer,\n"
    assert len(_read_usage_csv(bien)) == 1
