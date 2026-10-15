"""Ingesta de una regresión.

Se prueba por la API. Datos sintéticos de `_datos_regresion`.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from tests.api import _datos_regresion as r
from tests.api.conftest import actor_headers
from vigia.app.models import Batch, Project, Record


def _registros(client: TestClient, batch_id: int) -> list[Record]:
    with Session(client.app.state.engine) as s:
        return list(s.exec(select(Record).where(Record.batch_id == batch_id).order_by(Record.seq)).all())


def test_la_ingesta_guarda_el_valor_continuo_y_la_pertenencia_al_rango(client: TestClient):
    _proyecto, trabajo = r.linea_base_regresion(client, "r5-ing-valor", n=300)
    filas = _registros(client, trabajo["result"]["batch_id"])
    assert len(filas) == 300
    df = r.filas_regresion(300)
    # El valor continuo se guarda sin truncar...
    esperado = df["prediction"].to_numpy()
    obtenido = np.array([f.prediction_value for f in filas])
    assert np.allclose(obtenido, esperado, atol=1e-9)
    assert np.allclose(np.array([f.label_value for f in filas]), df["label"].to_numpy(), atol=1e-9)
    assert any(f.prediction_value != int(f.prediction_value) for f in filas)
    # ... y `prediction` / `label` son el 0/1 de pertenencia a «desde 12».
    assert [f.prediction for f in filas] == [int(v >= 12.0) for v in esperado]
    assert [f.label for f in filas] == [float(v >= 12.0) for v in df["label"]]
    # Las columnas continuas no son variables del modelo (COLUMNAS_CANONICAS).
    assert all(set(f.features_json) == {"x1", "x2"} for f in filas)


def test_sin_rango_la_prediccion_es_cero_y_la_etiqueta_cero_con_etiqueta(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-ing-sin-rango", rangos=None)
    df = r.filas_regresion(120, semilla=2)
    df.loc[df.index[:20], "label"] = np.nan
    trabajo = r.subir_e_ingerir(client, proyecto, df)
    filas = _registros(client, trabajo["result"]["batch_id"])
    assert {f.prediction for f in filas} == {0}
    assert {f.label for f in filas if f.label_value is not None} == {0.0}
    assert all(f.label is None for f in filas if f.label_value is None)
    assert sum(f.label_value is None for f in filas) == 20
    assert trabajo["result"]["n_labeled"] == 100


def test_los_registros_del_lote_devuelven_los_valores_continuos(client: TestClient):
    _p, trabajo = r.linea_base_regresion(client, "r5-ing-records", n=60)
    resp = client.get(f"/api/batches/{trabajo['result']['batch_id']}/records", params={"limit": 5})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    df = r.filas_regresion(60)
    assert items[0]["prediction_value"] == pytest.approx(df["prediction"].iloc[0])
    assert items[0]["label_value"] == pytest.approx(df["label"].iloc[0])
    assert items[0]["prediction"] in (0, 1)


def test_el_frame_de_la_evaluacion_lleva_los_valores_continuos(client: TestClient):
    from vigia.app.services import evaluate as evaluate_service

    _p, trabajo = r.linea_base_regresion(client, "r5-ing-frame", n=50)
    with Session(client.app.state.engine) as s:
        lote = s.get(Batch, trabajo["result"]["batch_id"])
        frame = evaluate_service._frame_from_records(s, lote)
    assert {"prediction_value", "label_value"} <= set(frame.columns)
    assert frame["prediction_value"].dtype.kind == "f"
    assert frame["prediction_value"].notna().all()


def test_el_mapeo_sugerido_de_una_regresion_no_propone_favorable_ni_probabilidad(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-ing-sugerido")
    sub = d.subir(client, proyecto["id"], r.a_csv(r.filas_regresion(40)))
    sugerido = sub["dataset"]["suggested_mapping"]
    assert sugerido["favorable_label"] is None
    assert sugerido["probability_col"] is None
    assert sugerido["probability_cols"] == []
    assert sugerido["prediction_col"] == "prediction"
    assert sugerido["label_col"] == "label"


def test_set_mapping_no_hereda_ni_exige_clase_favorable(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-ing-sin-favorable")
    sub = d.subir(client, proyecto["id"], r.a_csv(r.filas_regresion(40)))
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion())
    assert resp.status_code == 200, resp.text
    assert resp.json()["mapping"]["favorable_label"] is None


def test_una_prediccion_con_unidad_pegada_da_422_en_el_mapeo(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-ing-unidad-pegada")
    df = r.filas_regresion(40)
    df["prediction"] = df["prediction"].map(lambda v: f"{v:.1f} h")
    sub = d.subir(client, proyecto["id"], r.a_csv(df))
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion())
    assert resp.status_code == 422, resp.text
    assert "predicción" in resp.text and "unidad" in resp.text


def test_una_etiqueta_de_clases_de_texto_da_422_en_el_mapeo(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-ing-etiqueta-texto")
    df = r.filas_regresion(40)
    df["label"] = np.where(np.arange(len(df)) % 2, "alto", "bajo")
    sub = d.subir(client, proyecto["id"], r.a_csv(df))
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion())
    assert resp.status_code == 422, resp.text
    assert "etiquetas" in resp.text and "clasificación" in resp.text


def test_un_mapeo_de_regresion_con_probabilidad_o_favorable_nombra_el_campo(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-ing-rechazos")
    sub = d.subir(client, proyecto["id"], r.a_csv(r.filas_regresion(40)))
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion(favorable_label=1))
    assert resp.status_code == 422
    assert "favorable_label" in resp.text
    resp = d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion(probability_col="prediction"))
    assert resp.status_code == 422
    assert "probability_col" in resp.text


def test_una_regresion_no_lleva_los_avisos_de_cardinalidad_binaria_ni_de_alias(client: TestClient):
    _p, trabajo = r.linea_base_regresion(client, "r5-ing-avisos", n=100)
    avisos = " ".join(trabajo["result"].get("avisos") or [])
    assert "modelos binarios" not in avisos
    assert "clase favorable" not in avisos


def test_un_binario_con_prediccion_continua_remite_al_tipo_regresion(client: TestClient):
    creada = client.post(
        "/api/projects", json={"name": "r5-ing-binario-continuo"}, headers=actor_headers("miguel")
    )
    assert creada.status_code == 200, creada.text
    proyecto = creada.json()
    df = r.filas_regresion(80)
    df["label"] = (df["label"] >= 12).astype(int)  # etiqueta 0/1; la predicción es continua
    sub = d.subir(client, proyecto["id"], r.a_csv(df))
    resp = d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1,
         "feature_cols": ["x1", "x2"]},
    )
    assert resp.status_code == 200, resp.text
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    avisos = [a for a in trabajo["result"].get("avisos") or [] if "prediction" in a]
    assert len(avisos) == 1 and "proyecto de regresión" in avisos[0]
    # El aviso de siempre (más de dos clases) no se repite para la misma columna.
    assert "Vigía vigila hoy modelos binarios: la columna prediction" not in avisos[0]


def test_un_binario_con_etiqueta_continua_remite_al_tipo_regresion_en_el_mapeo(client: TestClient):
    creada = client.post(
        "/api/projects", json={"name": "r5-ing-binario-etiqueta"}, headers=actor_headers("miguel")
    )
    proyecto = creada.json()
    sub = d.subir(client, proyecto["id"], r.a_csv(r.filas_regresion(80)))
    resp = d.mapear(
        client,
        sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1},
    )
    assert resp.status_code == 422
    assert "proyecto de regresión" in resp.text


def test_el_feedback_de_una_regresion_escribe_label_value_y_recalcula_la_pertenencia(client: TestClient):
    proyecto, _trabajo = r.linea_base_regresion(client, "r5-ing-feedback", n=40)
    lote = r.filas_regresion(30, semilla=9, prefijo="n", con_etiqueta=False)
    t2 = r.subir_e_ingerir(client, proyecto, lote, rol="production")
    batch_id = t2["result"]["batch_id"]
    assert all(f.label_value is None and f.label is None for f in _registros(client, batch_id))
    reales = r.filas_regresion(30, semilla=9, prefijo="n")[["id", "label"]]
    reales.loc[0, "label"] = 20.0
    reales.loc[1, "label"] = 4.0
    sub = d.subir(client, proyecto["id"], r.a_csv(reales), rol="production", kind="feedback")
    resp = d.mapear(client, sub["dataset"]["id"], {"id_col": "id", "label_col": "label"})
    assert resp.status_code == 200, resp.text
    ing = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    assert ing["status"] == "terminado", ing
    filas = _registros(client, batch_id)
    assert filas[0].label_value == 20.0 and filas[0].label == 1.0
    assert filas[1].label_value == 4.0 and filas[1].label == 0.0
    assert all(f.label_value is not None for f in filas)
    with Session(client.app.state.engine) as s:
        assert s.get(Batch, batch_id).n_labeled == 30
    avisos = " ".join(ing["result"].get("avisos") or [])
    assert "clase favorable" not in avisos


def test_el_feedback_con_id_numerico_y_etiqueta_decimal_empareja(client: TestClient):
    """Hallazgo de G: `iterrows` pasaba el id 7151 a «7151.0» cuando la
    etiqueta es decimal, y el feedback no emparejaba ninguna fila."""
    proyecto, _t = r.linea_base_regresion(client, "r5-ing-feedback-id-numerico", n=40)
    lote = r.filas_regresion(20, semilla=5, prefijo="z", con_etiqueta=False)
    lote["id"] = list(range(7151, 7171))
    t2 = r.subir_e_ingerir(client, proyecto, lote, rol="production")
    reales = r.filas_regresion(20, semilla=5, prefijo="z")[["id", "label"]]
    reales["id"] = list(range(7151, 7171))
    reales["label"] = reales["label"].astype(float) + 0.25
    sub = d.subir(client, proyecto["id"], r.a_csv(reales), rol="production", kind="feedback")
    assert d.mapear(client, sub["dataset"]["id"], {"id_col": "id", "label_col": "label"}).status_code == 200
    ing = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    assert ing["status"] == "terminado", ing
    assert ing["result"]["n_matched"] == 20, ing["result"]
    filas = _registros(client, t2["result"]["batch_id"])
    assert all(f.label_value is not None for f in filas)


def test_una_etiqueta_de_feedback_que_no_es_un_numero_se_cuenta_y_no_se_aplica(client: TestClient):
    proyecto, _t = r.linea_base_regresion(client, "r5-ing-feedback-texto", n=40)
    lote = r.filas_regresion(10, semilla=3, prefijo="q", con_etiqueta=False)
    t2 = r.subir_e_ingerir(client, proyecto, lote, rol="production")
    reales = r.filas_regresion(10, semilla=3, prefijo="q")[["id", "label"]].astype({"label": object})
    reales.loc[0, "label"] = "12 h"
    sub = d.subir(client, proyecto["id"], r.a_csv(reales), rol="production", kind="feedback")
    assert d.mapear(client, sub["dataset"]["id"], {"id_col": "id", "label_col": "label"}).status_code == 200
    ing = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])
    filas = _registros(client, t2["result"]["batch_id"])
    assert filas[0].label_value is None and filas[0].label is None
    assert all(f.label_value is not None for f in filas[1:])
    assert any("no traen un número" in a for a in ing["result"]["avisos"])


def _eventos_mapeo_distinto(client: TestClient, proyecto_id: int) -> int:
    from vigia.app.models import Event

    with Session(client.app.state.engine) as s:
        return len(
            s.exec(
                select(Event).where(
                    Event.project_id == proyecto_id, Event.action == "dataset.mapeo_distinto_plantilla"
                )
            ).all()
        )


def test_nota_5_un_mapeo_que_repite_la_unidad_y_el_rango_de_la_plantilla_no_se_aparta(client: TestClient):
    """El mapeo da tuplas y el JSON de la plantilla listas: comparados normalizados, no hay
    un apartamiento falso; un mapeo que no dice unidad ni rango tampoco se aparta."""
    # `protected_kind` categórico en la plantilla: su valor por defecto («rangos numéricos»)
    # ya era un apartamiento con un atributo protegido categórico.
    proyecto = r.crear_proyecto_regresion(
        client, "r5-ing-no-se-aparta", mapping_template={"protected_kind": "categorical"}
    )
    for mapeo in (
        r.mapeo_regresion(),
        r.mapeo_regresion(target_unit=r.UNIDAD, favorable_ranges=[[12, None]]),
    ):
        sub = d.subir(client, proyecto["id"], r.a_csv(r.filas_regresion(30)))
        assert d.mapear(client, sub["dataset"]["id"], mapeo).status_code == 200
    assert _eventos_mapeo_distinto(client, proyecto["id"]) == 0


def test_nota_5_un_mapeo_con_otra_unidad_antes_de_congelar_si_se_aparta_de_la_plantilla(client: TestClient):
    proyecto = r.crear_proyecto_regresion(
        client, "r5-ing-se-aparta", mapping_template={"protected_kind": "categorical"}
    )
    sub = d.subir(client, proyecto["id"], r.a_csv(r.filas_regresion(30)))
    assert d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion(target_unit="días")).status_code == 200
    assert _eventos_mapeo_distinto(client, proyecto["id"]) == 1


# ---------------------------------------------------------------------------
# El qué hacer del 422 según lo que haya en la predicción
# ---------------------------------------------------------------------------


def _mapear_con_prediccion(client: TestClient, nombre: str, valores: list) -> object:
    proyecto = r.crear_proyecto_regresion(client, nombre)
    df = r.filas_regresion(len(valores))
    df["prediction"] = valores
    sub = d.subir(client, proyecto["id"], r.a_csv(df))
    return d.mapear(client, sub["dataset"]["id"], r.mapeo_regresion())


def test_una_prediccion_de_clases_de_texto_remite_a_clasificacion(client: TestClient):
    resp = _mapear_con_prediccion(client, "r5-ing-pred-clases", ["a", "b", "c", "a", "b", "c"] * 7)
    assert resp.status_code == 422, resp.text
    assert "clasificación" in resp.text and "binario o multiclase" in resp.text
    assert "unidad pegada" not in resp.text


def test_una_prediccion_con_infinitos_pide_quitarlos(client: TestClient):
    valores = [float(v) for v in range(40)]
    valores[7] = float("inf")
    resp = _mapear_con_prediccion(client, "r5-ing-pred-inf", valores)
    assert resp.status_code == 422, resp.text
    assert "infinitos" in resp.text
    assert "unidad pegada" not in resp.text and "clasificación" not in resp.text


def test_una_prediccion_con_unidad_pegada_pide_quitar_la_unidad(client: TestClient):
    valores = [f"{v:.1f} h" for v in np.linspace(5, 20, 40)]
    resp = _mapear_con_prediccion(client, "r5-ing-pred-unidad", valores)
    assert resp.status_code == 422, resp.text
    assert "unidad pegada" in resp.text and "clasificación" not in resp.text


# ---------------------------------------------------------------------------
# Avisos del motor que llegan al resultado del trabajo
# ---------------------------------------------------------------------------


def test_una_prediccion_de_dos_valores_avisa_de_que_puede_ser_un_clasificador(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-ing-aviso-dos-valores")
    df = r.filas_regresion(80)
    df["prediction"] = [10.0, 20.0] * 40
    trabajo = r.subir_e_ingerir(client, proyecto, df)
    assert any("clasificación" in a for a in trabajo["result"]["avisos"]), trabajo["result"]["avisos"]


def test_una_prediccion_constante_avisa_de_que_no_dice_nada(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-ing-aviso-constante")
    df = r.filas_regresion(80)
    df["prediction"] = 30.0
    trabajo = r.subir_e_ingerir(client, proyecto, df)
    assert any("mismo valor" in a for a in trabajo["result"]["avisos"]), trabajo["result"]["avisos"]


# ---------------------------------------------------------------------------
# La composición de un lote no inventa tasas favorables sin rango
# ---------------------------------------------------------------------------


def test_la_composicion_de_una_regresion_sin_rango_no_da_tasas_favorables(client: TestClient):
    proyecto = r.crear_proyecto_regresion(client, "r5-comp-sin-rango", rangos=None)
    trabajo = r.subir_e_ingerir(client, proyecto, r.filas_regresion(200))
    comp = client.get(f"/api/batches/{trabajo['result']['batch_id']}/composition").json()
    assert comp["motivo"] and "rango favorable" in comp["motivo"]
    assert comp["total"]["pred_favorable_rate"] is None and comp["total"]["label_favorable_rate"] is None
    assert comp["total"]["n"] == 200 and comp["total"]["n_labeled"] == 200
    for g in comp["groups"]:
        assert g["pred_favorable_n"] is None and g["pred_favorable_rate"] is None
        assert g["label_favorable_n"] is None and g["label_favorable_rate"] is None
        assert g["n"] > 0 and g["n_labeled"] > 0


def test_la_composicion_de_una_regresion_con_rango_lleva_las_tasas_de_pertenencia(client: TestClient):
    _p, trabajo = r.linea_base_regresion(client, "r5-comp-con-rango", n=200)
    comp = client.get(f"/api/batches/{trabajo['result']['batch_id']}/composition").json()
    assert comp["motivo"] is None
    assert 0.0 < comp["total"]["pred_favorable_rate"] < 1.0
    assert 0.0 < comp["total"]["label_favorable_rate"] < 1.0
    assert all(g["pred_favorable_n"] is not None for g in comp["groups"])


def test_la_composicion_de_un_binario_no_cambia(client: TestClient):
    binario = client.post("/api/projects", json={"name": "r5-comp-binario"}, headers=actor_headers("miguel")).json()
    df = r.filas_regresion(120)
    df["label"] = (df["label"] >= 12).astype(int)
    df["prediction"] = (df["prediction"] >= 12).astype(int)
    sub = d.subir(client, binario["id"], r.a_csv(df))
    assert d.mapear(
        client, sub["dataset"]["id"],
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1,
         "feature_cols": ["x1", "x2"]},
    ).status_code == 200
    trabajo = d.ingerir(client, sub["dataset"]["id"], binario["active_version_id"])
    comp = client.get(f"/api/batches/{trabajo['result']['batch_id']}/composition").json()
    assert comp["motivo"] is None
    assert comp["total"]["pred_favorable_rate"] == pytest.approx(float(df["prediction"].mean()))
    assert comp["groups"][0]["pred_favorable_n"] is not None


# ---------------------------------------------------------------------------
# Reiniciar un proyecto no deja el «sin rango» fijado
# ---------------------------------------------------------------------------


def test_tras_reiniciar_un_proyecto_congelado_sin_rango_el_mapeo_nuevo_puede_traer_uno(
    client: TestClient,
):
    proyecto = r.crear_proyecto_regresion(client, "r5-reset-rango", rangos=None)
    r.subir_e_ingerir(client, proyecto, r.filas_regresion(120))  # congela: fija «sin rango»
    with Session(client.app.state.engine) as s:
        assert s.get(Project, proyecto["id"]).favorable_ranges_json == []
    resp = client.post(
        f"/api/projects/{proyecto['id']}/reset",
        json={"actor": "miguel", "motivo": "empezar de nuevo", "confirm": True},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    with Session(client.app.state.engine) as s:
        assert s.get(Project, proyecto["id"]).favorable_ranges_json is None
    trabajo = r.subir_e_ingerir(
        client, proyecto, r.filas_regresion(120), mapeo=r.mapeo_regresion(favorable_ranges=[[12, None]])
    )
    filas = _registros(client, trabajo["result"]["batch_id"])
    assert any(f.prediction == 1 for f in filas)  # el rango del mapeo rige: hay favorables
