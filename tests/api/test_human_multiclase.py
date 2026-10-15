"""Diario de uso multiclase, overrides por clase
y los campos nuevos del deskilling con M1x."""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Dataset, ModelVersion, Project, UsageLog
from vigia.app.services import human_layer
from vigia.app.services.usage_log_clases import MENSAJE_VALOR_FAVORABLE

CLASES = ["ok", "spam", "odio", "desnudez", "otra"]
FAVORABLES = ["spam", "odio"]
CABECERA = "date,human_decision,model_output,ground_truth,clinician_pseudonym,subgroup"


def _crear(client: TestClient, name: str, *, favorables: list[str] | None = FAVORABLES) -> dict:
    cuerpo: dict = {
        "name": name,
        "domain": "libre",
        "task_type": "multiclass",
        "classes": CLASES,
        "mapping_template": {"favorable_label": favorables},
    }
    resp = client.post("/api/projects", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir(client: TestClient, project_id: int, contenido: str, **datos):
    return client.post(
        f"/api/projects/{project_id}/usage-logs/upload",
        files={"file": ("uso.csv", contenido.encode(), "text/csv")},
        data=datos or None,
        headers=actor_headers("miguel"),
    )


def _diario(n: int, *, semilla: int = 1, dias: int = 28) -> str:
    """5 clases. El modelo acierta el 70 %; el profesional corrige el 20 % de las
    veces y, al corregir, elige otra clase (a veces no favorable, a veces sí)."""
    rng = random.Random(semilla)
    filas = [CABECERA]
    for i in range(n):
        verdad = rng.choice(CLASES)
        modelo = verdad if rng.random() < 0.7 else rng.choice([c for c in CLASES if c != verdad])
        humano = modelo if rng.random() > 0.2 else rng.choice([c for c in CLASES if c != modelo])
        filas.append(
            f"2026-01-{1 + i % dias:02d},{humano},{modelo},{verdad},clin-{i % 4},{'a' if i % 2 else 'b'}"
        )
    return "\n".join(filas) + "\n"


def _filas(session: Session, project_id: int) -> list[UsageLog]:
    return list(
        session.exec(
            select(UsageLog).where(UsageLog.project_id == project_id).order_by(UsageLog.id)  # type: ignore[arg-type]
        ).all()
    )


def test_guarda_las_clases_y_la_pertenencia_al_conjunto_favorable(
    client: TestClient, session: Session
):
    proyecto = _crear(client, "uso-clases")
    csv = (
        CABECERA + "\n"
        "2026-01-05,spam,ok,spam,c1,a\n"  # humano y verdad favorables, modelo no
        "2026-01-06,ok,ok,odio,c1,a\n"  # solo la verdad es favorable
        "2026-01-07,desnudez,otra,ok,c2,b\n"  # nada favorable, humano distinto del modelo
        "2026-01-08,odio,odio,,c2,b\n"  # sin verdad todavía
    )
    resp = _subir(client, proyecto["id"], csv)
    assert resp.status_code == 200, resp.text
    assert resp.json()["n_rows"] == 4

    filas = _filas(session, proyecto["id"])
    assert [(f.human_class, f.model_class, f.truth_class) for f in filas] == [
        ("spam", "ok", "spam"),
        ("ok", "ok", "odio"),
        ("desnudez", "otra", "ok"),
        ("odio", "odio", None),
    ]
    assert [(f.human_decision, f.model_output, f.ground_truth) for f in filas] == [
        (1, 0, 1),
        (0, 0, 1),
        (0, 0, 0),
        (1, 1, None),
    ]


def test_la_clase_se_reconoce_sin_distinguir_mayusculas_ni_espacios(
    client: TestClient, session: Session
):
    proyecto = _crear(client, "uso-mayusculas")
    csv = CABECERA + "\n2026-01-05, SPAM ,Ok,spam,c1,a\n"
    assert _subir(client, proyecto["id"], csv).status_code == 200
    (fila,) = _filas(session, proyecto["id"])
    assert (fila.human_class, fila.model_class) == ("spam", "ok")


def test_clase_desconocida_da_422_con_la_fila_y_las_clases_validas(
    client: TestClient, session: Session
):
    proyecto = _crear(client, "uso-desconocida")
    csv = CABECERA + "\n2026-01-05,spam,ok,spam,c1,a\n2026-01-06,violencia,ok,ok,c1,a\n"
    resp = _subir(client, proyecto["id"], csv)
    assert resp.status_code == 422
    detalle = resp.json()["detail"]
    assert "fila 2" in detalle and "violencia" in detalle and "human_decision" in detalle
    for clase in CLASES:
        assert clase in detalle
    # Una subida rechazada no deja filas ni dataset de uso.
    assert _filas(session, proyecto["id"]) == []
    assert not [
        d for d in session.exec(select(Dataset).where(Dataset.project_id == proyecto["id"])).all()
        if d.kind == "usage_log" and d.file_path
    ]


@pytest.mark.parametrize("celda", ["refer", "no-refer", "Refer"])
def test_refer_y_no_refer_dan_422_en_multiclase(client: TestClient, celda: str):
    proyecto = _crear(client, "uso-refer")
    csv = CABECERA + f"\n2026-01-05,spam,ok,{celda},c1,a\n"
    resp = _subir(client, proyecto["id"], csv)
    assert resp.status_code == 422
    detalle = resp.json()["detail"]
    assert "ground_truth" in detalle and "binarios" in detalle and "multiclase" in detalle


@pytest.mark.parametrize("valor", ["no-refer", "1", "0"])
def test_la_inversion_por_valor_favorable_da_422_en_multiclase(client: TestClient, valor: str):
    proyecto = _crear(client, "uso-inversion")
    csv = CABECERA + "\n2026-01-05,spam,ok,spam,c1,a\n"
    resp = _subir(client, proyecto["id"], csv, valor_favorable=valor)
    assert resp.status_code == 422
    assert resp.json()["detail"] == MENSAJE_VALOR_FAVORABLE


def test_sin_conjunto_favorable_los_enteros_quedan_en_cero(client: TestClient, session: Session):
    proyecto = _crear(client, "uso-sin-conjunto", favorables=None)
    csv = CABECERA + "\n2026-01-05,spam,ok,spam,c1,a\n2026-01-06,odio,odio,,c1,a\n"
    assert _subir(client, proyecto["id"], csv).status_code == 200
    filas = _filas(session, proyecto["id"])
    assert [(f.human_class, f.model_class, f.truth_class) for f in filas] == [
        ("spam", "ok", "spam"),
        ("odio", "odio", None),
    ]
    assert [(f.human_decision, f.model_output, f.ground_truth) for f in filas] == [
        (0, 0, 0),
        (0, 0, None),
    ]


def test_proyecto_multiclase_sin_clases_fijadas_da_422_que_dice_que_congele(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={"name": "sin-clases", "domain": "libre", "task_type": "multiclass"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    proyecto = resp.json()
    if proyecto.get("active_version_id") is None:
        pytest.skip("el proyecto sin clases no tiene versión activa")
    respuesta = _subir(client, proyecto["id"], CABECERA + "\n2026-01-05,spam,ok,spam,c1,a\n")
    assert respuesta.status_code == 422
    assert "línea base" in respuesta.json()["detail"]


def test_la_exportacion_devuelve_los_nombres_de_clase(client: TestClient):
    proyecto = _crear(client, "uso-export")
    csv = CABECERA + "\n2026-01-05,spam,ok,odio,c1,a\n"
    assert _subir(client, proyecto["id"], csv).status_code == 200
    texto = client.get(f"/api/projects/{proyecto['id']}/usage-logs/export.csv").text
    assert "2026-01-05,spam,ok,odio,c1,a" in texto.replace("\r", "")


def test_usage_frame_multiclase_lleva_clases_y_la_pertenencia_para_cx1(
    client: TestClient, session: Session
):
    proyecto = _crear(client, "uso-frame")
    csv = CABECERA + "\n2026-01-05,ok,spam,odio,c1,a\n2026-01-06,ok,ok,ok,c1,a\n"
    assert _subir(client, proyecto["id"], csv).status_code == 200
    p = session.get(Project, proyecto["id"])
    version = session.get(ModelVersion, proyecto["active_version_id"])
    df = human_layer.usage_frame(session, p, version)
    assert list(df["model_output"]) == ["spam", "ok"]
    assert list(df["ground_truth"]) == ["odio", "ok"]
    assert list(df["truth_fav"]) == [1, 0]
    assert list(df["model_fav"]) == [1, 0]
    assert bool(df["conjunto_favorable"].all())


def test_override_por_subgrupo_compara_clases(client: TestClient):
    """Con 5 clases, la discrepancia entre dos clases no favorables es un override:
    la tasa del agregado sale de comparar clases, no su pertenencia al conjunto."""
    proyecto = _crear(client, "uso-override")
    filas = [CABECERA]
    # Subgrupo 'a': 40 decisiones, 10 con cambio entre dos clases no favorables (ok -> otra).
    for i in range(40):
        humano = "otra" if i < 10 else "ok"
        filas.append(f"2026-01-{1 + i % 28:02d},{humano},ok,ok,c{i % 2},a")
    # Subgrupo 'b': 40 decisiones sin ningún cambio.
    for i in range(40):
        filas.append(f"2026-01-{1 + i % 28:02d},ok,ok,ok,c{i % 2},b")
    assert _subir(client, proyecto["id"], "\n".join(filas) + "\n").status_code == 200

    cuerpo = client.get(f"/api/projects/{proyecto['id']}/overrides?by=subgroup").json()
    grupos = {g["group"]: g for g in cuerpo["groups"]}
    assert grupos["a"]["tasa"] == pytest.approx(10 / 40)
    assert grupos["b"]["tasa"] == 0.0


def test_deskilling_multiclase_lee_clases_y_trae_los_campos_de_m1x(client: TestClient):
    proyecto = _crear(client, "uso-deskilling")
    assert _subir(client, proyecto["id"], _diario(400, dias=28)).status_code == 200
    resp = client.get(f"/api/projects/{proyecto['id']}/deskilling")
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["sin_datos"] is False
    assert cuerpo["min_n"] == 30
    assert cuerpo["ventanas_excluidas"] == sum(w["excluida_de_pendiente"] for w in cuerpo["windows"])
    assert all(w["excluida_de_pendiente"] == (w["n"] < 30) for w in cuerpo["windows"])
    # Con nombres de clase el acuerdo se calcula sobre las clases: con tasa de
    # corrección del 20 % ronda el 0,8 en cada ventana.
    tasas = [w["agreement_rate"] for w in cuerpo["windows"] if w["agreement_rate"] is not None]
    assert tasas and all(0.6 < t < 0.95 for t in tasas)


def test_deskilling_excluye_las_ventanas_pequenas_y_las_enseña(client: TestClient):
    """Un lote pequeño al principio del periodo (2 semanas con 7 y 8 decisiones) y
    el grueso después: las dos ventanas pequeñas salen de la pendiente y siguen en
    la respuesta con su n."""
    proyecto = _crear(client, "uso-m1x")
    filas = [CABECERA]
    # 4 tramos de 30 días; los dos primeros con 7 y 8 filas, los dos últimos con 40.
    for tramo, n in enumerate((7, 8, 40, 40)):
        for k in range(n):
            dia = tramo * 30 + (k % 28)
            mes, d = divmod(dia, 28)
            filas.append(f"2026-{1 + mes:02d}-{1 + d:02d},ok,ok,ok,c{k % 2},a")
    assert _subir(client, proyecto["id"], "\n".join(filas) + "\n").status_code == 200
    cuerpo = client.get(f"/api/projects/{proyecto['id']}/deskilling").json()
    assert [w["n"] for w in cuerpo["windows"]] == [7, 8, 40, 40]
    assert [w["excluida_de_pendiente"] for w in cuerpo["windows"]] == [True, True, False, False]
    assert cuerpo["ventanas_excluidas"] == 2
    assert "se excluyen 2 ventanas con menos de 30 eventos" in cuerpo["summary_md"]


def test_evaluacion_cruzada_multiclase_de_punta_a_punta(client: TestClient, session: Session):
    """Calibra y vigila las cruzadas sobre un diario de 5 clases: el servicio
    pasa las clases y la pertenencia a `evaluate_cross` sin romper ninguna regla."""
    proyecto = _crear(client, "uso-cruzadas")
    assert _subir(client, proyecto["id"], _diario(800, semilla=3)).status_code == 200
    p = session.get(Project, proyecto["id"])
    version = session.get(ModelVersion, proyecto["active_version_id"])
    calibracion = human_layer.evaluate_cross_for_project(session, p, version=version)
    assert calibracion is not None and calibracion.result_json["mode"] == "calibracion"
    session.commit()
    vigilancia = human_layer.evaluate_cross_for_project(session, p, version=version)
    assert vigilancia is not None and vigilancia.result_json["mode"] == "vigilancia"
    claves = {m["metric_key"] for m in vigilancia.result_json["measurements"]}
    assert {"cx1_override_z:a", "cx1_override_z:b", "cx5_chi2_p", "cx2_override_z"} <= claves
    cx1 = next(m for m in vigilancia.result_json["measurements"] if m["metric_key"] == "cx1_model_fnr_z:a")
    # El proyecto tiene conjunto favorable: CX-1 lee la pertenencia (no es «sin conjunto»).
    assert cx1["motivo"] != "sin conjunto favorable: solo calidad por grupo"
    assert cx1["extra"]["positives_group"] > 0
