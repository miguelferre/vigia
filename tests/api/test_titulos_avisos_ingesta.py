"""Textos de título y aviso, avisos de la
ingesta y la reevaluación de la línea base."""

from __future__ import annotations

from sqlmodel import Session, select

from tests.api.test_ciclo_de_vida_proyecto import (
    _crear_proyecto,
    _evaluar,
    _ingerir,
    _linea_base_y_evento,
    _mapear,
    _subir,
)
from vigia.app.models import Evaluation
from vigia.app.models import Measurement as MeasurementRow


def _cuenta(session: Session, batch_id: int) -> tuple[int, int]:
    session.expire_all()
    evs = session.exec(select(Evaluation).where(Evaluation.batch_id == batch_id)).all()
    ms = session.exec(
        select(MeasurementRow).where(MeasurementRow.evaluation_id.in_([e.id for e in evs]))
    ).all()
    return len(evs), len(ms)


def test_reevaluar_la_linea_base_sustituye_sus_medidas(client, session: Session):
    """La segunda evaluación de la línea base no duplica evaluaciones ni medidas."""
    proyecto = _crear_proyecto(client, "r3b-linea-base")
    base = _subir(client, proyecto["id"], "01_baseline_feedback.json", role="baseline")
    _mapear(client, base)
    r = _ingerir(client, base["dataset"]["id"])
    _evaluar(client, r["batch_id"])
    primera = _cuenta(session, r["batch_id"])
    assert primera[0] == 3 and primera[1] > 0
    _evaluar(client, r["batch_id"])
    assert _cuenta(session, r["batch_id"]) == primera


def test_reevaluar_un_lote_de_produccion_sigue_acumulando(client, session: Session):
    _proyecto, _base, evento = _linea_base_y_evento(client, "r3b-produccion")
    antes = _cuenta(session, evento["batch_id"])
    _evaluar(client, evento["batch_id"])
    despues = _cuenta(session, evento["batch_id"])
    assert despues[0] == 2 * antes[0]


# --- Motivo de la comprobación inconclusa --------------------------------


def test_motivo_inconcluso_da_las_proporciones_y_la_separacion():
    from vigia.app.services.human_layer import comprobar_codificacion

    c = comprobar_codificacion(r=0.30, p=0.64, n=800)
    assert c.estado == "inconcluso"
    assert "64 % de decisiones favorables" in c.motivo
    assert "36 % de desfavorables" in c.motivo
    assert "(0,28)" in c.motivo
    assert "por debajo del 0,30" in c.motivo
    assert "casi tantas" not in c.motivo


# --- Título de las alertas cruzadas ------------------------------


def test_titulo_cx6_dice_que_compara_y_el_estadistico():
    from vigia.app.services.alerting import titulo_cruzada

    titulo = titulo_cruzada("CX-6", "urgencias", value=0.098, reference=0.150, z=-6.18, n=300)
    assert titulo == (
        "Diferencia de tasa de correcciones por grupo sin alerta de equidad en urgencias: "
        "override 9,8 % frente a 15,0 % en el resto (z -6,18)"
    )
    assert "umbral" not in titulo


def test_titulos_de_las_demas_cruzadas():
    from vigia.app.services.alerting import titulo_cruzada

    assert titulo_cruzada("CX-1", "18-35", value=0.05, reference=0.2, z=-4.0, n=50) == (
        "Tasa de correcciones en el grupo con más error en 18-35: override 5,0 % frente a 20,0 % en el resto (z -4,00)"
    )
    assert "de la referencia" in titulo_cruzada("CX-2", None, value=0.4, reference=0.2, z=4.5, n=90)
    cx5 = titulo_cruzada("CX-5", None, value=0.00002, reference=0.001, z=60.0, n=900)
    assert "p < 0,0001" in cx5 and "chi2 60,00" in cx5 and "Diferencia de tasa de correcciones entre profesionales" in cx5
    assert titulo_cruzada("CX-4", None, value=1.0, reference=None, z=None, n=10).endswith("disparada")
    assert "z de nivel 3,40" in titulo_cruzada("CX-4", None, value=1.0, reference=None, z=3.4, n=10)


def test_la_alerta_cx6_abre_con_titulo_de_comparacion_y_lo_conserva_en_observacion(client, session: Session):
    from tests.api.test_human_cruzadas_cascada_servicio import _alertas_cx6, _preparar_hasta_cx6
    from tests.api.test_human_cruzadas_cascada_servicio import _evaluar as _evaluar_cruzadas
    from vigia.app.models import Monitor, Project
    from vigia.app.services import alerting
    from vigia.core.schema import State

    proyecto, _calibracion = _preparar_hasta_cx6(client, session, "r3b-titulo-cx6")
    _evaluar_cruzadas(client, proyecto["id"])
    alerta = _alertas_cx6(session, proyecto["id"])[0]
    assert alerta.title.startswith("Diferencia de tasa de correcciones por grupo sin alerta de equidad en b: override ")
    assert " frente a " in alerta.title and "en el resto (z " in alerta.title
    assert "umbral" not in alerta.title
    titulo = alerta.title

    # La medida vuelve a cumplir: pasa a observación y el título sigue siendo el del disparo.
    evaluacion = session.get(Evaluation, alerta.last_evaluation_id)
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == proyecto["id"], Monitor.type == "cross")
    ).one()
    alerting.sync_candidates(
        session,
        session.get(Project, proyecto["id"]),
        monitor,
        evaluacion,
        [{"metric_key": "CX-6", "group_code": "b", "state": State.ok, "value": -1.2}],
    )
    session.expire_all()
    alerta = _alertas_cx6(session, proyecto["id"])[0]
    assert alerta.status == "en_observacion"
    assert alerta.last_value == -1.2
    assert alerta.title == titulo


# --- Avisos de la ingesta -----------------------------------------


def _ingerir_csv(client, nombre: str, contenido: bytes, mapeo: dict) -> dict:
    from tests.api import test_ingesta_formatos as r2

    proyecto = r2._crear_proyecto(client, nombre)
    subida = r2._subir(client, proyecto["id"], filename="datos.csv", content=contenido).json()
    r2._mapear(client, subida["dataset"]["id"], mapeo)
    return r2._ingerir(client, subida["dataset"]["id"], model_version_id=proyecto["active_version_id"])["result"]


def test_un_registro_de_uso_subido_como_datos_del_modelo_avisa(client):
    contenido = (
        b"date,human_decision,model_output,ground_truth,clinician_pseudonym,subgroup\n"
        b"2026-01-01,refer,refer,refer,c1,a\n2026-01-02,no-refer,refer,no-refer,c2,b\n"
    )
    resultado = _ingerir_csv(
        client,
        "r3b-registro-como-datos",
        contenido,
        {
            "prediction_col": "model_output",
            "label_col": "ground_truth",
            "id_col": "date",
            "favorable_label": "refer",
            # Las dos columnas con nombre reservado se mapean; sin mapear, el
            # mapeo se rechaza antes de llegar a la ingesta (test_ingesta_mapeo).
            "clinician_col": "clinician_pseudonym",
            "subgroup_col": "subgroup",
        },
    )
    assert any("registro de uso" in a and "Capa humana > Registro de uso" in a for a in resultado["avisos"])


def test_un_fichero_de_datos_normal_no_avisa_de_registro_de_uso(client):
    resultado = _ingerir_csv(
        client,
        "r3b-sin-aviso-uso",
        b"id,prediction,label\n1,0,0\n2,1,1\n",
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1},
    )
    assert not any("registro de uso" in a for a in resultado["avisos"])
    assert not any("valores vacíos" in a for a in resultado["avisos"])


def test_los_nulos_de_una_variable_salen_en_los_avisos(client):
    filas = ["id,prediction,label,tono"] + [
        f"{i},{i % 2},{i % 2},{'' if i < 3 else '0.5'}" for i in range(10)
    ]
    resultado = _ingerir_csv(
        client,
        "r3b-nulos",
        ("\n".join(filas) + "\n").encode(),
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "favorable_label": 1,
            "feature_cols": ["tono"],
        },
    )
    assert any(
        a.startswith("la columna tono tiene 3 valores vacíos de 10 filas (30,0 %)") and "revisa" in a
        for a in resultado["avisos"]
    )


# --- Ayuda de las seis reglas cruzadas ----------------------------------


def test_las_seis_reglas_cruzadas_tienen_ayuda_con_vocabulario_generico(client):
    cuerpo = client.get("/api/content/metricas").json()
    for n in range(1, 7):
        entrada = cuerpo[f"CX-{n}"]
        assert entrada["monitor"] == "cross"
        assert entrada["que_mide"] and entrada["como_se_lee"] and entrada["formula"]
        texto = " ".join((entrada["que_mide"], entrada["como_se_lee"], entrada["formula"])).lower()
        assert "paciente" not in texto and "clínico" not in texto
    from vigia.app.services.alerting import _etiqueta_metrica

    assert _etiqueta_metrica("CX-6") == cuerpo["CX-6"]["etiqueta"]
