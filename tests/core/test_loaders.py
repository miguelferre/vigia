"""Tests de vigia.core.loaders sobre los fixtures sintéticos del repo."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from vigia.core.loaders import (
    LIMITE_FILAS_LOTE,
    comprobar_columnas_mapeo,
    concat_history,
    contar_filas_csv,
    contar_ids_duplicados_en_lote,
    contar_sin_alias_reconocido,
    detectar_cardinalidad_binaria,
    es_valor_nulo,
    load_feedback,
    load_harness_pair,
    load_payload,
    load_tabular,
    mensaje_limite_filas,
    read_csv_smart,
    resolver_favorable,
    sniff_csv_dialect,
    to_canonical,
)
from vigia.core.schema import (
    COL_GROUP,
    COL_LABEL,
    COL_PREDICTION,
    COL_PROB,
    HARNESS_PAYLOAD_MAPPING,
    ColumnMapping,
    DatosNoValidos,
)


def test_load_feedback_e1_450x49(e1_baseline_feedback_path):
    df = load_feedback(e1_baseline_feedback_path)
    assert df.shape == (450, 49)


def test_load_payload_e1_450x2_predicciones(e1_baseline_payload_path):
    df = load_payload(e1_baseline_payload_path)
    assert len(df) == 450
    assert "PREDICTION" in df.columns and "PROBABILITIES" in df.columns


def test_load_feedback_e2_evento_2000x2(e2_evento_feedback_path):
    df = load_feedback(e2_evento_feedback_path)
    assert df.shape[0] == 2000


def test_load_feedback_e2_recovery_3000x2(e2_recovery_feedback_path):
    df = load_feedback(e2_recovery_feedback_path)
    assert df.shape[0] == 3000


def test_canonico_evento_e1(evento_canonico):
    df = evento_canonico
    assert len(df) == 450
    assert pd.api.types.is_integer_dtype(df[COL_PREDICTION])
    assert df[COL_PROB].between(0, 1).all()
    assert df[COL_LABEL].notna().all()
    assert (df[COL_GROUP] == 0).sum() == 148
    assert (df[COL_GROUP] == 1).sum() == 246


def test_mapeo_columna_inexistente_lanza(e1_baseline_feedback_path):
    mapeo = ColumnMapping(prediction_col="no_existe")
    with pytest.raises(ValueError):
        load_tabular(e1_baseline_feedback_path, mapeo)


def test_load_tabular_csv_redondo(tmp_path, evento_canonico):
    ruta = tmp_path / "canon.csv"
    evento_canonico.to_csv(ruta, index=False)
    de_vuelta = load_tabular(ruta)
    assert len(de_vuelta) == len(evento_canonico)
    assert list(de_vuelta.columns) == list(evento_canonico.columns)


def test_load_tabular_parquet_redondo(tmp_path, evento_canonico):
    # exc_type=ImportError: pyarrow puede importarse pero fallar al cargar el
    # motor de parquet (bloqueado por el Control de aplicaciones del equipo).
    pytest.importorskip("pyarrow.parquet", exc_type=ImportError)
    ruta = tmp_path / "canon.parquet"
    evento_canonico.to_parquet(ruta, index=False)
    de_vuelta = load_tabular(ruta)
    assert len(de_vuelta) == len(evento_canonico)
    assert list(de_vuelta.columns) == list(evento_canonico.columns)


def test_load_harness_pair_ok(e1_evento_payload_path, e1_evento_feedback_path):
    df = load_harness_pair(e1_evento_payload_path, e1_evento_feedback_path, batch_seq=1)
    assert len(df) == 450


def test_load_harness_pair_orden_distinto(tmp_path, e1_evento_payload_path, e1_evento_feedback_path):
    feedback = json.loads(e1_evento_feedback_path.read_text(encoding="utf-8"))
    idx_pred = feedback["fields"].index("_original_prediction")
    feedback["values"][0][idx_pred] = 1 - int(feedback["values"][0][idx_pred])
    ruta = tmp_path / "feedback_desordenado.json"
    ruta.write_text(json.dumps(feedback), encoding="utf-8")
    with pytest.raises(ValueError, match="orden distinto"):
        load_harness_pair(e1_evento_payload_path, ruta)


def test_concat_history_seq_global_creciente(baseline_canonico, evento_canonico):
    hist = concat_history([baseline_canonico, evento_canonico])
    assert len(hist) == 900
    assert list(hist["seq"]) == list(range(900))


def test_to_canonical_payload_sin_label(e1_evento_payload_path):
    pl = load_payload(e1_evento_payload_path)
    canon = to_canonical(pl, HARNESS_PAYLOAD_MAPPING, batch_seq=1)
    assert canon[COL_LABEL].isna().all()


# ---------------------------------------------------------------------------
# Dialecto de CSV
# ---------------------------------------------------------------------------

_CONTENIDO_CANONICO = "id,edad,prob,pred\n1,30,0.55,1\n2,45,0.10,0\n"
_CONTENIDO_PUNTOYCOMA = "id;edad;prob;pred\n1;30;0,55;1\n2;45;0,10;0\n"
_CONTENIDO_TSV = "id\tedad\tprob\tpred\n1\t30\t0.55\t1\n2\t45\t0.10\t0\n"


def test_sniff_csv_dialect_camino_principal_coma():
    dialecto = sniff_csv_dialect(_CONTENIDO_CANONICO.encode("utf-8"))
    assert dialecto == {"encoding": "utf-8-sig", "separator": ",", "decimal": "."}


def test_sniff_csv_dialect_puntoycoma_bom_coma_decimal():
    dialecto = sniff_csv_dialect(_CONTENIDO_PUNTOYCOMA.encode("utf-8-sig"))
    assert dialecto == {"encoding": "utf-8-sig", "separator": ";", "decimal": ","}


def test_sniff_csv_dialect_puntoycoma_sin_bom():
    dialecto = sniff_csv_dialect(_CONTENIDO_PUNTOYCOMA.encode("utf-8"))
    assert dialecto == {"encoding": "utf-8-sig", "separator": ";", "decimal": ","}


def test_sniff_csv_dialect_cp1252_con_acentos():
    contenido = "id;region\n1;Andalucía\n2;Cataluña\n".encode("cp1252")
    dialecto = sniff_csv_dialect(contenido)
    assert dialecto == {"encoding": "cp1252", "separator": ";", "decimal": "."}


def test_sniff_csv_dialect_tsv():
    dialecto = sniff_csv_dialect(_CONTENIDO_TSV.encode("utf-8"))
    assert dialecto == {"encoding": "utf-8-sig", "separator": "\t", "decimal": "."}


def test_sniff_csv_dialect_una_sola_columna_es_valido():
    """Una cabecera sin ningún separador candidato es un CSV de una sola
    columna, no un fichero irreconocible: cae a coma (el separador por
    defecto de pandas)."""
    dialecto = sniff_csv_dialect(b"resultado\nPositivo\nNegativo\n")
    assert dialecto["separator"] == ","


def test_sniff_csv_dialect_nada_encaja_da_datosnovalidos():
    basura = bytes([0x81, 0x8D, 0x8F, 0x90, 0x9D]) * 10
    with pytest.raises(DatosNoValidos, match="no se reconoce el formato del fichero"):
        sniff_csv_dialect(basura)


@pytest.mark.parametrize(
    "nombre,codificacion",
    [
        ("f08_bom.csv", "utf-8-sig"),
        ("f09_sin_bom.csv", "utf-8"),
    ],
)
def test_load_tabular_excel_espanol_da_lo_mismo_que_el_canonico(tmp_path, nombre, codificacion):
    """Un CSV de Excel en español (`;`, coma decimal,
    con y sin BOM) se lee igual que el CSV canónico (coma, punto decimal)."""
    ruta = tmp_path / nombre
    ruta.write_bytes(_CONTENIDO_PUNTOYCOMA.encode(codificacion))
    df = load_tabular(ruta)
    assert list(df.columns) == ["id", "edad", "prob", "pred"]
    assert df["edad"].tolist() == [30, 45]
    assert df["prob"].tolist() == [0.55, 0.10]


def test_load_tabular_tsv(tmp_path):
    """Tabulador, utf-8."""
    ruta = tmp_path / "f10_tsv.csv"
    ruta.write_bytes(_CONTENIDO_TSV.encode("utf-8"))
    df = load_tabular(ruta)
    assert list(df.columns) == ["id", "edad", "prob", "pred"]
    assert df["prob"].tolist() == [0.55, 0.10]


def test_load_tabular_cp1252(tmp_path):
    ruta = tmp_path / "regiones.csv"
    ruta.write_bytes("id;region\n1;Andalucía\n2;Cataluña\n".encode("cp1252"))
    df = load_tabular(ruta)
    assert df["region"].tolist() == ["Andalucía", "Cataluña"]


# ---------------------------------------------------------------------------
# None/NA legítimos frente a nulos reales
# ---------------------------------------------------------------------------


def test_read_csv_smart_conserva_none_na_literales_salvo_columnas_exentas():
    contenido = b"resultado,label\nNone,NA\nPositivo,1\nNA,0\nNegativo,NA\n"
    df, _dialecto = read_csv_smart(contenido, na_pandas_cols={"label"})
    assert df["resultado"].tolist() == ["None", "Positivo", "NA", "Negativo"]
    assert df["resultado"].isna().sum() == 0
    assert df["label"].isna().sum() == 2


def test_read_csv_smart_sin_columnas_exentas_ninguna_pierde_texto():
    contenido = b"resultado\nNone\nPositivo\nNA\n"
    df, _dialecto = read_csv_smart(contenido)
    assert df["resultado"].tolist() == ["None", "Positivo", "NA"]


def test_read_csv_smart_fila_con_columnas_de_mas_da_datosnovalidos_en_espanol():
    """Corrección: una fila de longitud distinta a la cabecera lanzaba
    `pandas.errors.ParserError` sin capturar; ahora es `DatosNoValidos` en
    español, igual que la codificación irreconocible en `sniff_csv_dialect`."""
    contenido = b"a,b,c\n1,2,3\n4,5,6,7,8\n"
    with pytest.raises(DatosNoValidos, match="fila con un n.mero de columnas distinto"):
        read_csv_smart(contenido)


# ---------------------------------------------------------------------------
# Columnas del mapeo ausentes (reutilizado por load_tabular y to_canonical)
# ---------------------------------------------------------------------------


def test_comprobar_columnas_mapeo_feature_col_ausente_da_mensaje_en_espanol():
    df = pd.DataFrame({"prediction": [1, 0], "label": [1, 0]})
    mapeo = ColumnMapping(prediction_col="prediction", label_col="label", feature_cols=["edad"])
    with pytest.raises(DatosNoValidos) as excinfo:
        comprobar_columnas_mapeo(df, mapeo)
    assert str(excinfo.value) == (
        "el fichero ya no tiene la columna 'edad' que el mapeo necesita: "
        "revisa el mapeo o vuelve a subir el fichero"
    )


def test_to_canonical_columna_mapeada_ausente_da_mensaje_en_espanol():
    """Antes reventaba con un `KeyError` crudo al construir `canon`."""
    df = pd.DataFrame({"prediction": [1, 0], "label": [1, 0]})
    mapeo = ColumnMapping(prediction_col="prediction", label_col="label", feature_cols=["edad"])
    with pytest.raises(DatosNoValidos, match="edad"):
        to_canonical(df, mapeo)


def test_load_tabular_columna_mapeada_ausente_da_datosnovalidos(tmp_path):
    ruta = tmp_path / "sin_edad.csv"
    ruta.write_bytes(b"prediction,label\n1,1\n0,0\n")
    mapeo = ColumnMapping(prediction_col="prediction", label_col="label", feature_cols=["edad"])
    with pytest.raises(DatosNoValidos, match="edad"):
        load_tabular(ruta, mapeo)


# ---------------------------------------------------------------------------
# Límite de un millón de filas, contado por trozos
# ---------------------------------------------------------------------------


def test_contar_filas_csv_cuenta_sin_construir_un_dataframe():
    contenido = b"a,b\n1,2\n3,4\n5,6\n"
    assert contar_filas_csv(contenido) == 3


def test_contar_filas_csv_sin_salto_de_linea_final():
    assert contar_filas_csv(b"a,b\n1,2\n3,4") == 2


def test_contar_filas_csv_por_encima_del_limite(tmp_path):
    ruta = tmp_path / "enorme.csv"
    with ruta.open("wb") as f:
        f.write(b"a,b\n")
        for _ in range(LIMITE_FILAS_LOTE + 1):
            f.write(b"1,2\n")
    n = contar_filas_csv(ruta.read_bytes())
    assert n == LIMITE_FILAS_LOTE + 1
    assert mensaje_limite_filas(n) == (
        "el fichero tiene 1 000 001 filas; el máximo por lote es 1 000 000: pártelo en varios lotes"
    )


# ---------------------------------------------------------------------------
# Comparación normalizada contra la clase favorable
# ---------------------------------------------------------------------------


def test_es_valor_nulo_none_y_nan():
    assert es_valor_nulo(None) is True
    assert es_valor_nulo(float("nan")) is True
    assert es_valor_nulo(0) is False
    assert es_valor_nulo("") is False


def test_resolver_favorable_numero_contra_numero():
    assert resolver_favorable(1, 1) is True
    assert resolver_favorable(0, 1) is False
    assert resolver_favorable(1.0, 1) is True


@pytest.mark.parametrize(
    "crudo,favorable,esperado",
    [
        ("Sí", "Sí", True),
        ("si", "Sí", True),
        ("Verdadero", 1, True),  # alias contra favorable numérico
        ("1", "true", True),
        ("No", "Sí", False),
        ("Falso", "verdadero", False),
        ("0", "sí", False),
        ("positivo", "positivo", True),  # coincidencia textual exacta, sin alias
    ],
)
def test_resolver_favorable_texto_normalizado(crudo, favorable, esperado):
    assert resolver_favorable(crudo, favorable) is esperado


def test_resolver_favorable_nulo_da_none():
    assert resolver_favorable(None, 1) is None
    assert resolver_favorable(float("nan"), "Sí") is None


def test_resolver_favorable_sin_alias_reconocido_da_none():
    """Un valor sin alias ni coincidencia con la clase favorable pasa a
    `None`, nunca a la clase no favorable en silencio."""
    assert resolver_favorable("tal vez", "Sí") is None
    assert resolver_favorable("positivo", "Sí") is None


def test_contar_sin_alias_reconocido_ignora_los_nulos_originales():
    serie = pd.Series(["Sí", "tal vez", None, "No"])
    assert contar_sin_alias_reconocido(serie, "Sí") == 1


def test_to_canonical_prediccion_texto_alias():
    """`favorable_label` de texto ya no se aplana con `==` crudo."""
    df = pd.DataFrame(
        {
            "prediction": ["Sí", "No", "Sí", "No"] * 5,
            "label": ["No", "Sí", "Sí", "No"] * 5,
        }
    )
    mapeo = ColumnMapping(prediction_col="prediction", label_col="label", favorable_label="Sí")
    canon = to_canonical(df, mapeo)
    assert canon[COL_PREDICTION].sum() == 10  # 10 de 20 favorables
    assert canon[COL_LABEL].sum() == 10.0


def test_to_canonical_prediccion_sin_alias_reconocido_lanza():
    df = pd.DataFrame({"prediction": ["Sí", "tal vez"], "label": ["Sí", "No"]})
    mapeo = ColumnMapping(prediction_col="prediction", label_col="label", favorable_label="Sí")
    with pytest.raises(DatosNoValidos, match="no coinciden con la clase favorable"):
        to_canonical(df, mapeo)


def test_to_canonical_etiqueta_sin_alias_reconocido_pasa_a_nula():
    df = pd.DataFrame({"prediction": ["Sí", "No"], "label": ["Sí", "tal vez"]})
    mapeo = ColumnMapping(prediction_col="prediction", label_col="label", favorable_label="Sí")
    canon = to_canonical(df, mapeo)
    assert canon[COL_LABEL].tolist()[0] == 1.0
    assert pd.isna(canon[COL_LABEL].tolist()[1])


# ---------------------------------------------------------------------------
# Ids duplicados dentro de un lote
# ---------------------------------------------------------------------------


def test_contar_ids_duplicados_en_lote():
    df = pd.DataFrame({"id": ["E1", "E2", "E1", "E3", "E3"]})
    assert contar_ids_duplicados_en_lote(df, "id") == 2  # E1 y un E3 repetidos


def test_contar_ids_duplicados_en_lote_sin_id_col():
    df = pd.DataFrame({"id": ["E1", "E1"]})
    assert contar_ids_duplicados_en_lote(df, None) == 0


# ---------------------------------------------------------------------------
# Aviso de cardinalidad (más de dos valores)
# ---------------------------------------------------------------------------


def test_detectar_cardinalidad_binaria_avisa_con_mas_de_dos_valores():
    df = pd.DataFrame({"prediction": [0, 1, 2], "label": [0, 1, 0]})
    mapeo = ColumnMapping(prediction_col="prediction", label_col="label")
    avisos = detectar_cardinalidad_binaria(df, mapeo)
    assert len(avisos) == 1
    assert "modelos binarios" in avisos[0]
    assert "prediction" in avisos[0]
    assert "3 valores" in avisos[0]


def test_detectar_cardinalidad_binaria_sin_aviso_con_dos_valores():
    df = pd.DataFrame({"prediction": [0, 1, 1], "label": [0, 1, 0]})
    mapeo = ColumnMapping(prediction_col="prediction", label_col="label")
    assert detectar_cardinalidad_binaria(df, mapeo) == []
