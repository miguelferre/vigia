"""Formatos y robustez de ingesta, y la captura de `DatosNoValidos` (el
lanzamiento en `core/quality.py`; aquí se simula con `monkeypatch`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.core.schema import DatosNoValidos


def _crear_proyecto(client: TestClient, name: str) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir(
    client: TestClient, project_id: int, *, filename: str, content: bytes, content_type: str = "text/csv"
) -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": (filename, content, content_type)},
        data={"kind": "combined", "role": "production"},
        headers=actor_headers("miguel"),
    )
    return resp


def _mapear(client: TestClient, dataset_id: int, mapping: dict) -> dict:
    resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapping},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingerir(client: TestClient, dataset_id: int, **body) -> dict:
    body.setdefault("evaluate", False)
    resp = client.post(f"/api/datasets/{dataset_id}/ingest", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _records(client: TestClient, batch_id: int) -> list[dict]:
    resp = client.get(f"/api/batches/{batch_id}/records", params={"with_features": "true"})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


# ---------------------------------------------------------------------------
# Dialecto de CSV
# ---------------------------------------------------------------------------

_CONTENIDO_COMA = "id,edad,prob,pred\n1,30,0.55,1\n2,45,0.10,0\n"
_CONTENIDO_PUNTOYCOMA = "id;edad;prob;pred\n1;30;0,55;1\n2;45;0,10;0\n"
_CONTENIDO_TSV = "id\tedad\tprob\tpred\n1\t30\t0.55\t1\n2\t45\t0.10\t0\n"


def test_csv_coma_camino_principal_sin_regresion(client: TestClient):
    """El camino principal (coma, punto decimal, utf-8) no cambia con el sniff nuevo."""
    proyecto = _crear_proyecto(client, "c1-coma")
    resp = _subir(client, proyecto["id"], filename="f01.csv", content=_CONTENIDO_COMA.encode("utf-8"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [c["name"] for c in body["dataset"]["columns"]] == ["id", "edad", "prob", "pred"]
    assert body["dialect"] == {"encoding": "utf-8-sig", "separator": ",", "decimal": "."}
    assert body["preview"] == [
        {"id": 1, "edad": 30, "prob": 0.55, "pred": 1},
        {"id": 2, "edad": 45, "prob": 0.10, "pred": 0},
    ]


@pytest.mark.parametrize(
    "nombre,codificacion",
    [("f08_bom.csv", "utf-8-sig"), ("f09_sin_bom.csv", "utf-8-sig"), ("f10_cp1252.csv", "cp1252")],
)
def test_csv_excel_espanol_da_las_mismas_columnas_y_valores_que_el_canonico(
    client: TestClient, nombre: str, codificacion: str
):
    """`;` + coma decimal, con y sin BOM, dan lo mismo
    que el CSV canónico (coma, punto decimal)."""
    proyecto = _crear_proyecto(client, f"c1-{nombre}")
    contenido = _CONTENIDO_PUNTOYCOMA.encode(codificacion)
    resp = _subir(client, proyecto["id"], filename=nombre, content=contenido)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [c["name"] for c in body["dataset"]["columns"]] == ["id", "edad", "prob", "pred"]
    # El contenido es ASCII puro: cp1252 y utf-8-sig decodifican igual, así que
    # no hay forma de distinguirlos aquí (lo hace `test_cp1252_conserva_los_acentos`,
    # con acentos). Separador y decimal sí son observables siempre.
    assert body["dialect"]["separator"] == ";"
    assert body["dialect"]["decimal"] == ","
    # El dialecto queda guardado en el dataset, no solo en la subida.
    guardado = client.get(f"/api/datasets/{body['dataset']['id']}").json()
    assert guardado["dialect"] == body["dialect"]
    assert body["preview"] == [
        {"id": 1, "edad": 30, "prob": 0.55, "pred": 1},
        {"id": 2, "edad": 45, "prob": 0.10, "pred": 0},
    ]


def test_tsv_da_las_mismas_columnas_y_valores_que_el_canonico(client: TestClient):
    """Tabulador, utf-8."""
    proyecto = _crear_proyecto(client, "c1-tsv")
    resp = _subir(client, proyecto["id"], filename="f10_tsv.csv", content=_CONTENIDO_TSV.encode("utf-8"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [c["name"] for c in body["dataset"]["columns"]] == ["id", "edad", "prob", "pred"]
    assert body["dialect"] == {"encoding": "utf-8-sig", "separator": "\t", "decimal": "."}
    assert body["preview"] == [
        {"id": 1, "edad": 30, "prob": 0.55, "pred": 1},
        {"id": 2, "edad": 45, "prob": 0.10, "pred": 0},
    ]


def test_cp1252_conserva_los_acentos(client: TestClient):
    """Cp1252 sin BOM, con acentos en una columna de texto."""
    proyecto = _crear_proyecto(client, "c1-acentos")
    contenido = "id;region\n1;Andalucía\n2;Cataluña\n".encode("cp1252")
    resp = _subir(client, proyecto["id"], filename="regiones.csv", content=contenido)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dialect"]["encoding"] == "cp1252"
    assert body["preview"][0]["region"] == "Andalucía"
    assert body["preview"][1]["region"] == "Cataluña"


def test_csv_irreconocible_da_422_sin_traza(client: TestClient):
    """Si ni utf-8-sig ni cp1252 decodifican, 422 con el mensaje de dialecto, nunca un 500."""
    proyecto = _crear_proyecto(client, "c1-irreconocible")
    basura = bytes([0x81, 0x8D, 0x8F, 0x90, 0x9D]) * 20
    resp = _subir(client, proyecto["id"], filename="basura.csv", content=basura)
    assert resp.status_code == 422, resp.text
    detalle = resp.json()["detail"]
    assert "no se reconoce el formato del fichero" in detalle
    assert "Traceback" not in detalle


def test_csv_con_fila_de_longitud_irregular_da_422_no_500(client: TestClient):
    """Corrección: separador bien detectado pero una fila con más columnas
    que la cabecera lanzaba `pandas.errors.ParserError` sin capturar, y
    `/datasets/upload` (síncrono, sin `try/except` propio) lo dejaba subir
    como 500. Repro contra el endpoint real."""
    proyecto = _crear_proyecto(client, "c1-fila-irregular")
    contenido = b"a,b,c\n1,2,3\n4,5,6,7,8\n"
    resp = _subir(client, proyecto["id"], filename="irregular.csv", content=contenido)
    assert resp.status_code == 422, resp.text
    detalle = resp.json()["detail"]
    assert "fila con un n" in detalle
    assert "Traceback" not in detalle
    assert "tokenizing" not in detalle


# ---------------------------------------------------------------------------
# XLSX/XLS: 422 sin leer, por sufijo o por firma
# ---------------------------------------------------------------------------

_MSG_XLSX = (
    "Vigía lee CSV y JSON: abre el fichero en Excel y guárdalo como CSV "
    "(delimitado por comas o por punto y coma)"
)


def test_xlsx_por_sufijo_da_422_sin_leerlo(client: TestClient):
    proyecto = _crear_proyecto(client, "c1-xlsx-sufijo")
    # Contenido ZIP mínimo válido (firma real), como escribiría un .xlsx real.
    contenido = b"PK\x03\x04" + b"\x00" * 40
    resp = _subir(
        client,
        proyecto["id"],
        filename="libro.xlsx",
        content=contenido,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == _MSG_XLSX


def test_zip_renombrado_como_csv_da_422_por_firma(client: TestClient):
    """Detección por firma, no solo por sufijo (fichero renombrado)."""
    proyecto = _crear_proyecto(client, "c1-xlsx-firma")
    contenido = b"PK\x03\x04" + b"\x00" * 40
    resp = _subir(client, proyecto["id"], filename="disfrazado.csv", content=contenido)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == _MSG_XLSX


def test_xls_ole_por_firma_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, "c1-xls-ole")
    contenido = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40
    resp = _subir(client, proyecto["id"], filename="viejo.xls", content=contenido)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == _MSG_XLSX


# ---------------------------------------------------------------------------
# None/NA legítimos frente a nulos reales
# ---------------------------------------------------------------------------


def test_categorica_con_none_y_na_literales_no_se_pierde(client: TestClient):
    """Una columna sin mapear con 'None'/'NA' los conserva como texto."""
    proyecto = _crear_proyecto(client, "c1-none-categoria")
    contenido = b"prediction,label,resultado\n1,1,None\n0,0,Positivo\n1,1,NA\n0,0,Negativo\n"
    resp = _subir(client, proyecto["id"], filename="resultado.csv", content=contenido)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    columna = next(c for c in body["dataset"]["columns"] if c["name"] == "resultado")
    assert columna["n_null"] == 0
    assert body["preview"][0]["resultado"] == "None"
    assert body["preview"][2]["resultado"] == "NA"


def test_label_mapeada_con_na_sigue_siendo_nula(client: TestClient):
    """La columna mapeada como etiqueta conserva los nulos de pandas."""
    proyecto = _crear_proyecto(client, "c1-label-na")
    version_id = proyecto["active_version_id"]
    contenido = b"id,prediction,label,edad\n1,1,1,30\n2,0,NA,45\n3,1,0,50\n"
    resp = _subir(client, proyecto["id"], filename="con_na_en_label.csv", content=contenido)
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "feature_cols": ["edad"],
            "favorable_label": 1,
        },
    )
    resultado = _ingerir(client, dataset_id, model_version_id=version_id)["result"]
    registros = sorted(_records(client, resultado["batch_id"]), key=lambda r: r["seq"])
    assert [r["label"] for r in registros] == [1.0, None, 0.0]


# ---------------------------------------------------------------------------
# Columna mapeada que desaparece del fichero
# ---------------------------------------------------------------------------


def test_columna_mapeada_ausente_da_datosnovalidos_en_espanol(client: TestClient, tmp_path: Path):
    """Reescribir el fichero en bruto sin la columna de `feature_cols`
    (como si el usuario reingiriera un fichero que ya no la trae) da un
    mensaje en español, nunca un `KeyError` crudo."""
    proyecto = _crear_proyecto(client, "c2-columna-ausente")
    version_id = proyecto["active_version_id"]
    resp = _subir(
        client,
        proyecto["id"],
        filename="con_edad.csv",
        content=b"id,prediction,label,edad\n1,1,1,30\n2,0,0,45\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "feature_cols": ["edad"],
            "favorable_label": 1,
        },
    )
    # El fichero en bruto ya no trae 'edad' (mismo `file_path` que guardó la
    # subida): ruta real leída de la BD de la app.
    from sqlmodel import Session

    from vigia.app.models import Dataset as DatasetModel

    engine = client.app.state.engine
    with Session(engine) as s:
        ds = s.get(DatasetModel, dataset_id)
        ruta = Path(ds.file_path)
    ruta.write_bytes(b"id,prediction,label\n1,1,1\n2,0,0\n")

    ingest_resp = client.post(f"/api/datasets/{dataset_id}/ingest", json={"model_version_id": version_id})
    assert ingest_resp.status_code == 200, ingest_resp.text
    job = ingest_resp.json()
    assert job["status"] == "error", job
    assert job["error"] == (
        "el fichero ya no tiene la columna 'edad' que el mapeo necesita: "
        "revisa el mapeo o vuelve a subir el fichero"
    )
    assert "KeyError" not in job["error"]
    assert "Traceback" not in job["error"]


# ---------------------------------------------------------------------------
# Límite de un millón de filas
# ---------------------------------------------------------------------------


def test_mas_de_un_millon_de_filas_da_422_sin_construir_el_dataframe(client: TestClient):
    proyecto = _crear_proyecto(client, "c2-limite-filas")
    n = 1_000_001
    contenido = b"prediction,label\n" + (b"1,1\n" * n)
    resp = _subir(client, proyecto["id"], filename="enorme.csv", content=contenido)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == (
        "el fichero tiene 1 000 001 filas; el máximo por lote es 1 000 000: pártelo en varios lotes"
    )


# ---------------------------------------------------------------------------
# Captura por tipo de `DatosNoValidos` (lanzada en core/quality.py)
# ---------------------------------------------------------------------------


def _dataset_ingerido(client: TestClient, nombre_proyecto: str) -> tuple[int, int]:
    """Sube, mapea e ingiere (sin evaluar) un CSV mínimo. Devuelve (dataset_id, batch_id)."""
    proyecto = _crear_proyecto(client, nombre_proyecto)
    version_id = proyecto["active_version_id"]
    resp = _subir(
        client,
        proyecto["id"],
        filename="mini.csv",
        content=b"id,prediction,label,prob\n1,1,1,0.9\n2,0,0,0.1\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "probability_col": "prob",
            "favorable_label": 1,
        },
    )
    resultado = _ingerir(client, dataset_id, model_version_id=version_id)["result"]
    return dataset_id, resultado["batch_id"]


def test_ingesta_con_evaluate_captura_datosnovalidos_en_evaluate_motivo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """La ingesta captura `DatosNoValidos` (la lanza `core/quality.py`) y
    deja la ingesta en `terminado` con `evaluated=false`."""
    proyecto = _crear_proyecto(client, "c2-1-ingesta")
    version_id = proyecto["active_version_id"]
    resp = _subir(
        client,
        proyecto["id"],
        filename="mini2.csv",
        content=b"id,prediction,label,prob\n1,1,1,1.5\n2,0,0,0.1\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "probability_col": "prob",
            "favorable_label": 1,
        },
    )
    mensaje = "la probabilidad tiene 1 de 2 filas nulas o fuera de 0 a 1: revisa la columna prob del mapeo"

    def _falla(*args, **kwargs):
        raise DatosNoValidos(mensaje)

    monkeypatch.setattr("vigia.app.services.evaluate.evaluate_batch", _falla)

    ingest_resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_id, "evaluate": True},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    job = ingest_resp.json()
    assert job["status"] == "terminado", job
    assert job["result"]["evaluated"] is False
    assert job["result"]["evaluate_motivo"] == mensaje


def test_evaluacion_suelta_captura_datosnovalidos_y_deja_el_trabajo_en_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """`POST /batches/{id}/evaluate`: el trabajo queda en `error` con el texto
    de `DatosNoValidos` tal cual, sin la traza de una librería."""
    _dataset_id, batch_id = _dataset_ingerido(client, "c2-1-evaluate")
    mensaje = "la probabilidad tiene 2 de 2 filas nulas o fuera de 0 a 1: revisa la columna prob del mapeo"

    def _falla(*args, **kwargs):
        raise DatosNoValidos(mensaje)

    monkeypatch.setattr("vigia.app.services.evaluate.evaluate_batch", _falla)

    resp = client.post(f"/api/batches/{batch_id}/evaluate", json={"trigger": "manual"})
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "error", job
    assert job["error"] == mensaje
    assert "Traceback" not in job["error"]


# ---------------------------------------------------------------------------
# MappingBody con extra="forbid" (PUT /datasets/{id}/mapping)
# ---------------------------------------------------------------------------


def test_mapping_body_con_campo_extra_da_422(client: TestClient):
    """Corrección: `MappingBody` se quedó con el `extra="ignore"` por defecto
    de Pydantic. Hace falta `extra="forbid"` en `ColumnMapping` y en
    `MappingBody`."""
    proyecto = _crear_proyecto(client, "r2-n4-mapping-body")
    resp = _subir(
        client, proyecto["id"], filename="con_id.csv", content=b"id,prediction,label\n1,0,0\n2,1,1\n"
    )
    dataset_id = resp.json()["dataset"]["id"]
    mapping_resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={
            "mapping": {"prediction_col": "prediction", "label_col": "label", "id_col": "id"},
            "campo_inventado": "algo",
        },
        headers=actor_headers("miguel"),
    )
    assert mapping_resp.status_code == 422, mapping_resp.text


# ---------------------------------------------------------------------------
# favorable_label heredado (plantilla o línea base) o 422; comparación
# normalizada (número, texto con alias sí/no y verdadero/falso)
# ---------------------------------------------------------------------------


def test_favorable_heredado_de_plantilla_del_proyecto(client: TestClient):
    """Favorable_label omitido en el mapeo se hereda de
    `project.mapping_template_json`."""
    resp = client.post(
        "/api/projects",
        json={
            "name": "c3-1-plantilla-favorable",
            "domain": "reuma",
            "mapping_template": {"favorable_label": 0},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    resp = _subir(
        client,
        proyecto["id"],
        filename="con_plantilla.csv",
        content=b"id,prediction,label\n1,0,0\n2,1,1\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    guardado = _mapear(
        client, dataset_id, {"prediction_col": "prediction", "label_col": "label", "id_col": "id"}
    )
    assert guardado["mapping"]["favorable_label"] == 0


def test_favorable_heredado_del_mapeo_de_la_linea_base(client: TestClient):
    """Sin plantilla, se hereda del mapeo de la línea base congelada
    de la versión activa."""
    from sqlmodel import Session

    from vigia.app.models import ModelVersion

    proyecto = _crear_proyecto(client, "c3-1-linea-base-favorable")
    version_id = proyecto["active_version_id"]
    base = _subir(
        client, proyecto["id"], filename="base.csv", content=b"id,prediction,label\n1,0,0\n2,1,1\n"
    ).json()
    base_dataset_id = base["dataset"]["id"]
    _mapear(
        client,
        base_dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "favorable_label": 0,
        },
    )
    resultado = _ingerir(client, base_dataset_id, model_version_id=version_id)["result"]
    with Session(client.app.state.engine) as s:
        version = s.get(ModelVersion, version_id)
        version.baseline_batch_id = resultado["batch_id"]
        s.add(version)
        s.commit()

    lote = _subir(
        client, proyecto["id"], filename="lote.csv", content=b"id,prediction,label\n3,0,0\n4,1,1\n"
    ).json()
    dataset_id = lote["dataset"]["id"]
    guardado = _mapear(
        client, dataset_id, {"prediction_col": "prediction", "label_col": "label", "id_col": "id"}
    )
    assert guardado["mapping"]["favorable_label"] == 0


def test_favorable_sin_plantilla_ni_linea_base_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, "c3-1-sin-favorable")
    resp = _subir(
        client, proyecto["id"], filename="sin_favorable.csv", content=b"id,prediction,label\n1,0,0\n"
    )
    dataset_id = resp.json()["dataset"]["id"]
    mapping_resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": {"prediction_col": "prediction", "label_col": "label", "id_col": "id"}},
        headers=actor_headers("miguel"),
    )
    assert mapping_resp.status_code == 422, mapping_resp.text
    assert "clase favorable que heredar" in mapping_resp.json()["detail"]


def test_favorable_label_texto_si_no_normalizado(client: TestClient):
    """Favorable_label de texto ('Sí') compara con alias
    normalizados (`strip().casefold()`), no con `==` crudo."""
    proyecto = _crear_proyecto(client, "c3-1-texto-si-no")
    version_id = proyecto["active_version_id"]
    resp = _subir(
        client,
        proyecto["id"],
        filename="si_no.csv",
        content=b"id,prediction,label\n1,Si,No\n2,No,Si\n3,Si,Si\n4,No,No\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "favorable_label": "Sí",
        },
    )
    resultado = _ingerir(client, dataset_id, model_version_id=version_id)["result"]
    registros = sorted(_records(client, resultado["batch_id"]), key=lambda r: r["seq"])
    assert [r["prediction"] for r in registros] == [1, 0, 1, 0]
    assert [r["label"] for r in registros] == [0.0, 1.0, 1.0, 0.0]


def test_favorable_valor_sin_alias_pasa_a_nulo_y_se_cuenta(client: TestClient):
    """Un valor de etiqueta sin alias reconocido pasa a nulo, con
    recuento en el resultado; nunca a la clase no favorable en silencio."""
    proyecto = _crear_proyecto(client, "c3-1-sin-alias")
    version_id = proyecto["active_version_id"]
    resp = _subir(
        client,
        proyecto["id"],
        filename="tal_vez.csv",
        content=b"id,prediction,label\n1,Si,Si\n2,No,TalVez\n3,Si,No\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "favorable_label": "Si",
        },
    )
    resultado = _ingerir(client, dataset_id, model_version_id=version_id)["result"]
    registros = sorted(_records(client, resultado["batch_id"]), key=lambda r: r["seq"])
    assert [r["label"] for r in registros] == [1.0, None, 0.0]
    assert any("etiqueta" in a for a in resultado["avisos"])


def test_prediccion_sin_alias_reconocido_da_datosnovalidos(client: TestClient):
    """Una predicción sin alias reconocido no se aplana en silencio;
    la predicción es de guardado obligatorio, así que detiene la ingesta."""
    proyecto = _crear_proyecto(client, "c3-1-pred-sin-alias")
    version_id = proyecto["active_version_id"]
    resp = _subir(
        client,
        proyecto["id"],
        filename="pred_rara.csv",
        content=b"id,prediction,label\n1,Si,1\n2,TalVez,0\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "favorable_label": "Si",
        },
    )
    ingest_resp = client.post(
        f"/api/datasets/{dataset_id}/ingest", json={"model_version_id": version_id}
    )
    job = ingest_resp.json()
    assert job["status"] == "error", job
    assert "no coinciden con la clase favorable" in job["error"]


# ---------------------------------------------------------------------------
# prediction_col opcional en feedback, obligatorio en combined/payload
# ---------------------------------------------------------------------------


def test_feedback_sin_prediction_col_es_valido(client: TestClient):
    """Un dataset feedback se mapea con solo id_col y label_col."""
    proyecto = _crear_proyecto(client, "c3-2-feedback-sin-pred")
    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("fb.csv", b"id,label\n1,1\n2,0\n", "text/csv")},
        data={"kind": "feedback", "role": "production"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["dataset"]["id"]
    guardado = _mapear(
        client, dataset_id, {"label_col": "label", "id_col": "id", "favorable_label": 1}
    )
    assert guardado["mapping"]["prediction_col"] is None


def test_combined_sin_prediction_col_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, "c3-2-combined-sin-pred")
    resp = _subir(client, proyecto["id"], filename="c.csv", content=b"id,label\n1,1\n2,0\n")
    dataset_id = resp.json()["dataset"]["id"]
    mapping_resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": {"label_col": "label", "id_col": "id", "favorable_label": 1}},
        headers=actor_headers("miguel"),
    )
    assert mapping_resp.status_code == 422, mapping_resp.text
    assert "columna de predicción" in mapping_resp.json()["detail"]  # Sin nombres de la API


# ---------------------------------------------------------------------------
# Orden por lote descendente, n_ambiguos, n_id_duplicados
# ---------------------------------------------------------------------------


def test_feedback_ambiguo_aplica_al_lote_mas_reciente_y_lo_cuenta(client: TestClient):
    """Mismo id en dos lotes; el feedback lo aplica al más reciente
    (gana el último) y cuenta `n_ambiguos`."""
    proyecto = _crear_proyecto(client, "c3-3-ambiguo")
    version_id = proyecto["active_version_id"]
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "favorable_label": 1,
    }
    lote1 = _subir(
        client, proyecto["id"], filename="lote1.csv", content=b"id,prediction,label\nE1,0,\n"
    ).json()
    _mapear(client, lote1["dataset"]["id"], mapping)
    _ingerir(client, lote1["dataset"]["id"], model_version_id=version_id)

    lote2 = _subir(
        client, proyecto["id"], filename="lote2.csv", content=b"id,prediction,label\nE1,1,\n"
    ).json()
    _mapear(client, lote2["dataset"]["id"], mapping)
    resultado2 = _ingerir(client, lote2["dataset"]["id"], model_version_id=version_id)["result"]
    batch2_id = resultado2["batch_id"]

    fb = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("fb.csv", b"id,label\nE1,1\n", "text/csv")},
        data={"kind": "feedback", "role": "production"},
        headers=actor_headers("miguel"),
    ).json()
    _mapear(client, fb["dataset"]["id"], {"label_col": "label", "id_col": "id", "favorable_label": 1})
    resultado_fb = _ingerir(client, fb["dataset"]["id"], model_version_id=version_id)["result"]
    assert resultado_fb["n_matched"] == 1
    assert resultado_fb["n_ambiguos"] == 1

    registros_lote2 = _records(client, batch2_id)
    assert registros_lote2[0]["label"] == 1.0


def test_ids_duplicados_dentro_del_lote_y_contra_la_version_se_cuentan(client: TestClient):
    proyecto = _crear_proyecto(client, "c3-3-duplicados")
    version_id = proyecto["active_version_id"]
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "favorable_label": 1,
    }
    lote1 = _subir(
        client, proyecto["id"], filename="lote1.csv", content=b"id,prediction,label\nE1,1,1\nE2,0,0\n"
    ).json()
    _mapear(client, lote1["dataset"]["id"], mapping)
    _ingerir(client, lote1["dataset"]["id"], model_version_id=version_id)

    # E1 repite la versión (ya ingerido en el lote 1); E3 se repite dentro
    # de este segundo lote.
    lote2 = _subir(
        client,
        proyecto["id"],
        filename="lote2.csv",
        content=b"id,prediction,label\nE1,1,1\nE3,0,0\nE3,1,1\n",
    ).json()
    _mapear(client, lote2["dataset"]["id"], mapping)
    resultado = _ingerir(client, lote2["dataset"]["id"], model_version_id=version_id)["result"]
    assert resultado["n_id_duplicados"] == 2
    assert any("identificador" in a for a in resultado["avisos"])


def test_ids_duplicados_se_cuentan_bien_con_el_conteo_troceado(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Corrección: `_ingest_crear` hacía `Record.external_id.in_(ids_lote)`
    con el conjunto completo, sin trocear (SQLite limita las variables por
    consulta; con más de ~33 000 ids distintos daba `OperationalError`, sin
    capturar). Ahora se trocea en bloques de `_BLOQUE` y se suman los
    `count()` parciales: con `_BLOQUE` forzado a 2, un lote con más
    duplicados que el tamaño del bloque comprueba que la suma across bloques
    sigue siendo correcta, no solo el último."""
    monkeypatch.setattr("vigia.app.services.ingest._BLOQUE", 2)
    proyecto = _crear_proyecto(client, "c2-troceo-ids")
    version_id = proyecto["active_version_id"]
    mapping = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "favorable_label": 1,
    }
    lote1 = _subir(
        client,
        proyecto["id"],
        filename="lote1.csv",
        content=b"id,prediction,label\nE1,1,1\nE2,0,0\nE3,1,1\nE4,0,0\nE5,1,1\n",
    ).json()
    _mapear(client, lote1["dataset"]["id"], mapping)
    _ingerir(client, lote1["dataset"]["id"], model_version_id=version_id)

    # Los cinco ids del lote 1 repiten contra la versión (más de dos bloques
    # de tamaño 2 en la consulta troceada); ninguno se repite dentro de este
    # segundo lote.
    lote2 = _subir(
        client,
        proyecto["id"],
        filename="lote2.csv",
        content=b"id,prediction,label\nE1,1,1\nE2,0,0\nE3,1,1\nE4,0,0\nE5,1,1\n",
    ).json()
    _mapear(client, lote2["dataset"]["id"], mapping)
    resultado = _ingerir(client, lote2["dataset"]["id"], model_version_id=version_id)["result"]
    assert resultado["n_id_duplicados"] == 5


# ---------------------------------------------------------------------------
# id_col obligatorio salvo acepta_feedback=false; "sin id" en el
# resultado del feedback en vez de n_unmatched mudo
# ---------------------------------------------------------------------------


def test_id_col_obligatorio_en_combined_da_422(client: TestClient):
    proyecto = _crear_proyecto(client, "c3-4-id-obligatorio")
    resp = _subir(client, proyecto["id"], filename="sin_id.csv", content=b"prediction,label\n1,1\n0,0\n")
    dataset_id = resp.json()["dataset"]["id"]
    mapping_resp = client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": {"prediction_col": "prediction", "label_col": "label", "favorable_label": 1}},
        headers=actor_headers("miguel"),
    )
    assert mapping_resp.status_code == 422, mapping_resp.text
    assert "columna de identificador" in mapping_resp.json()["detail"]  # Sin nombres de la API


def test_id_col_opcional_si_el_proyecto_no_acepta_feedback(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={"name": "c3-4-sin-feedback", "domain": "reuma", "acepta_feedback": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    resp = _subir(client, proyecto["id"], filename="sin_id.csv", content=b"prediction,label\n1,1\n0,0\n")
    dataset_id = resp.json()["dataset"]["id"]
    guardado = _mapear(
        client,
        dataset_id,
        {"prediction_col": "prediction", "label_col": "label", "favorable_label": 1},
    )
    assert guardado["mapping"]["id_col"] is None


def test_feedback_sin_ningun_id_en_la_version_lo_dice(client: TestClient):
    """Si la versión de destino no tiene ningún registro con
    id, el resultado del feedback lo dice en vez de un `n_unmatched` mudo."""
    resp = client.post(
        "/api/projects",
        json={"name": "c3-4-sin-id-version", "domain": "reuma", "acepta_feedback": False},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    version_id = proyecto["active_version_id"]
    lote = _subir(
        client, proyecto["id"], filename="lote.csv", content=b"prediction,label\n1,1\n0,0\n"
    ).json()
    _mapear(
        client,
        lote["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "favorable_label": 1},
    )
    _ingerir(client, lote["dataset"]["id"], model_version_id=version_id)

    fb = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("fb.csv", b"id,label\nE1,1\n", "text/csv")},
        data={"kind": "feedback", "role": "production"},
        headers=actor_headers("miguel"),
    ).json()
    _mapear(client, fb["dataset"]["id"], {"label_col": "label", "id_col": "id", "favorable_label": 1})
    resultado = _ingerir(client, fb["dataset"]["id"], model_version_id=version_id)["result"]
    assert resultado["n_matched"] == 0
    assert any("no se puede emparejar" in a for a in resultado["avisos"])


# ---------------------------------------------------------------------------
# Aviso de cardinalidad (más de dos valores) sin cambiar lo guardado
# ---------------------------------------------------------------------------


def test_cardinalidad_mas_de_dos_valores_da_aviso(client: TestClient):
    proyecto = _crear_proyecto(client, "c3-5-cardinalidad")
    version_id = proyecto["active_version_id"]
    resp = _subir(
        client,
        proyecto["id"],
        filename="tres_clases.csv",
        content=b"id,prediction,label\n1,0,0\n2,1,1\n3,2,0\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1},
    )
    resultado = _ingerir(client, dataset_id, model_version_id=version_id)["result"]
    avisos = resultado["avisos"]
    assert any("modelos binarios" in a and "prediction" in a for a in avisos)
    registros = _records(client, resultado["batch_id"])
    # El aviso no cambia lo que se guarda (la fila con predicción "2"
    # sigue guardada, no favorable frente a favorable_label=1).
    assert {r["prediction"] for r in registros} == {0, 1}


# ---------------------------------------------------------------------------
# Sugerencia de mapeo desde la plantilla del
# proyecto y aviso al apartarse de ella
# ---------------------------------------------------------------------------


def test_get_dataset_rellena_sugerencia_desde_plantilla(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={
            "name": "c4-1-plantilla-sugerencia",
            "domain": "reuma",
            "mapping_template": {"favorable_label": 0, "id_col": "id", "feature_cols": ["edad"]},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    resp = _subir(
        client,
        proyecto["id"],
        filename="con_plantilla.csv",
        content=b"id,prediction,label,edad\n1,0,0,30\n2,1,1,45\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    obtenido = client.get(f"/api/datasets/{dataset_id}").json()
    sugerido = obtenido["suggested_mapping"]
    assert sugerido["favorable_label"] == 0
    assert sugerido["id_col"] == "id"
    assert sugerido["feature_cols"] == ["edad"]
    # lo que la plantilla no fija lo sigue proponiendo `_suggest_mapping`
    assert sugerido["prediction_col"] == "prediction"


def test_mapeo_distinto_de_plantilla_deja_evento(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={
            "name": "c4-1-mapeo-distinto",
            "domain": "reuma",
            "mapping_template": {"favorable_label": 1, "id_col": "id"},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    resp = _subir(
        client,
        proyecto["id"],
        filename="otro_mapeo.csv",
        content=b"identificador,prediction,label\n1,0,0\n2,1,1\n",
    )
    dataset_id = resp.json()["dataset"]["id"]
    _mapear(
        client,
        dataset_id,
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "identificador",
            "favorable_label": 0,
        },
    )
    eventos = client.get(
        "/api/events", params={"object_type": "dataset", "object_id": dataset_id}
    ).json()["items"]
    acciones = {e["action"] for e in eventos}
    assert "dataset.mapeo_distinto_plantilla" in acciones
