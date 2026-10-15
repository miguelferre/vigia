"""Capa humana de la regresión y punta a punta.

Un proyecto de regresión con rango favorable («desde 12 horas por semana») acepta el registro de uso
con cifras; el diario guarda la cifra y la pertenencia al rango, y las cruzadas, el deskilling
y los overrides ven una decisión binaria derivada. La tabla de cambios vive en
`test_regresion_capa_humana_cambios.py`.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api import _datos_regresion as r
from tests.api.conftest import actor_headers
from tests.api.test_dossiers import _crear_dossier
from vigia.app.models import Dataset, UsageLog
from vigia.app.services import human_layer, tarea
from vigia.core.schema import MOTIVO_CAPA_HUMANA_SIN_RANGO, en_rango

HUMANO = actor_headers("miguel")
CABECERA = "date,human_decision,model_output,ground_truth,clinician_pseudonym,subgroup"
RANGOS = ((12.0, None),)
FRASE = "en regresión el registro trae las cifras"


def _subir(client: TestClient, proyecto_id: int, contenido: str, **datos):
    return client.post(
        f"/api/projects/{proyecto_id}/usage-logs/upload",
        files={"file": ("uso.csv", contenido.encode(), "text/csv")},
        data=datos or None,
        headers=HUMANO,
    )


def _filas(session: Session, proyecto_id: int) -> list[UsageLog]:
    session.expire_all()
    return list(
        session.exec(
            select(UsageLog).where(UsageLog.project_id == proyecto_id).order_by(UsageLog.id)  # type: ignore[arg-type]
        ).all()
    )


def diario_regresion(n: int = 300, *, semilla: int = 3, dias: int = 28) -> tuple[str, list[dict[str, Any]]]:
    """CSV de uso de una regresión y sus registros. El modelo da cifras alrededor de 12; el
    profesional se aparta de la cifra del modelo la mitad de las veces."""
    rng = random.Random(semilla)
    texto = [CABECERA]
    registros: list[dict[str, Any]] = []
    for i in range(n):
        modelo = round(rng.gauss(12, 3), 2)
        humano = round(modelo + rng.gauss(0, 1.5), 2) if rng.random() < 0.5 else modelo
        verdad = round(modelo + rng.gauss(0, 1.5), 2)
        fecha = (date(2026, 1, 5) + timedelta(days=i % dias)).isoformat()
        sub, clin = ("A" if i % 2 else "B"), f"enf-{i % 4}"
        registros.append(
            {"date": fecha, "humano": humano, "modelo": modelo, "verdad": verdad, "sub": sub, "clin": clin}
        )
        texto.append(f"{fecha},{humano},{modelo},{verdad},{clin},{sub}")
    return "\n".join(texto) + "\n", registros


def _dentro(valor: float) -> int:
    return int(bool(en_rango(valor, RANGOS)))


# -- El registro con cifras y lo que se guarda --------------------------------------


def test_el_registro_con_cifras_guarda_la_cifra_y_la_pertenencia_al_rango(
    client: TestClient, session: Session
):
    p = r.crear_proyecto_regresion(client, "r5-uso-cifras")
    csv = (
        CABECERA + "\n"
        "2026-01-05,14.5,10,13,c1,A\n"  # humano dentro, modelo fuera, verdad dentro
        "2026-01-06,12,12,11.99,c1,A\n"  # el 12 exacto cuenta (extremos incluidos); 11.99, no
        "2026-01-07,3,9.5,,c2,B\n"  # sin verdad todavía
        "2026-01-08,,8,20,c2,B\n"  # sin decisión del profesional
        "2026-01-09,-1e0,1.5E1,0.5,c2,B\n"  # notación científica y negativo
    )
    resp = _subir(client, p["id"], csv)
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["n_rows"] == 5
    assert cuerpo["valor_favorable"] is None
    filas = _filas(session, p["id"])
    assert [(f.human_value, f.model_value, f.truth_value) for f in filas] == [
        (14.5, 10.0, 13.0),
        (12.0, 12.0, 11.99),
        (3.0, 9.5, None),
        (None, 8.0, 20.0),
        (-1.0, 15.0, 0.5),
    ]
    assert [(f.human_decision, f.model_output, f.ground_truth) for f in filas] == [
        (1, 0, 1),
        (1, 1, 0),
        (0, 0, None),
        (None, 0, 1),
        (0, 1, 0),
    ]
    # Las clases quedan nulas.
    assert all(f.human_class is None and f.model_class is None and f.truth_class is None for f in filas)
    ds = session.get(Dataset, cuerpo["dataset_id"])
    assert ds is not None and ds.mapping_json == {"valor_favorable": None}


def test_la_exportacion_devuelve_las_cifras(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-uso-export")
    csv = CABECERA + "\n2026-01-05,14.5,10,13,c1,A\n2026-01-06,12,12.25,,c1,A\n"
    assert _subir(client, p["id"], csv).status_code == 200
    salida = client.get(f"/api/projects/{p['id']}/usage-logs/export.csv").text.splitlines()
    assert salida[1].split(",")[:4] == ["2026-01-05", "14.5", "10", "13"]
    assert salida[2].split(",")[:4] == ["2026-01-06", "12", "12.25", ""]


@pytest.mark.parametrize("columna", ["human_decision", "model_output", "ground_truth"])
@pytest.mark.parametrize("texto", ["refer", "No-Refer"])
def test_refer_y_no_refer_dan_422_con_la_fila_y_que_hacer(client: TestClient, columna: str, texto: str):
    p = r.crear_proyecto_regresion(client, f"r5-uso-refer-{columna}-{texto}")
    celdas = {"human_decision": "10", "model_output": "11", "ground_truth": "12"}
    celdas[columna] = texto
    csv = (
        CABECERA + "\n2026-01-05,10,11,12,c1,A\n"
        f"2026-01-06,{celdas['human_decision']},{celdas['model_output']},{celdas['ground_truth']},c1,A\n"
    )
    resp = _subir(client, p["id"], csv)
    assert resp.status_code == 422, resp.text
    detalle = resp.json()["detail"]
    assert FRASE in detalle and "fila 2" in detalle and columna in detalle
    assert "Escribe la cifra (horas por semana)" in detalle
    assert human_layer.MENSAJE_REGISTRO_CIFRAS == FRASE


@pytest.mark.parametrize(
    ("celda", "pista"),
    [("abc", False), ("\"38,5\"", True), ("40 h", False), ("1_000", False), ("inf", False), ("1e999", False), ("--3", False)],
)
def test_una_celda_no_numerica_da_422_con_la_fila(client: TestClient, celda: str, pista: bool):
    p = r.crear_proyecto_regresion(client, f"r5-uso-celda-{celda}")
    csv = CABECERA + f"\n2026-01-05,10,11,12,c1,A\n2026-01-06,10,{celda},12,c1,A\n"
    resp = _subir(client, p["id"], csv)
    assert resp.status_code == 422, resp.text
    detalle = resp.json()["detail"]
    assert "fila 2" in detalle and "model_output" in detalle and FRASE in detalle
    assert ("coma decimal" in detalle) == pista
    # Una subida rechazada no deja nada.
    assert client.get(f"/api/projects/{p['id']}/usage-logs/export.csv").text.count("\n") <= 1


@pytest.mark.parametrize("valor", ["refer", "no-refer", "1", "0"])
def test_valor_favorable_con_valor_da_422_en_regresion(client: TestClient, valor: str):
    p = r.crear_proyecto_regresion(client, f"r5-uso-valor-{valor}")
    resp = _subir(client, p["id"], CABECERA + "\n2026-01-05,10,11,12,c1,A\n", valor_favorable=valor)
    assert resp.status_code == 422, resp.text
    assert FRASE in resp.json()["detail"] and "valor_favorable" in resp.json()["detail"]
    assert resp.json()["detail"] == human_layer.MENSAJE_VALOR_FAVORABLE_REGRESION


def test_sin_valor_favorable_la_clasificacion_sigue_con_refer(client: TestClient, session: Session):
    """El valor por defecto pasa a nulo (para distinguirlo en regresión) y se resuelve a `refer`."""
    binario = client.post("/api/projects", json={"name": "r5-uso-binario"}, headers=HUMANO).json()
    csv = "date,human_decision,model_output,ground_truth\n2026-01-05,refer,no-refer,refer\n"
    resp = _subir(client, binario["id"], csv)
    assert resp.status_code == 200, resp.text
    assert resp.json()["valor_favorable"] == "refer"
    assert [(f.human_decision, f.model_output, f.ground_truth) for f in _filas(session, binario["id"])] == [(1, 0, 1)]
    # Y con `no-refer` explícito se recodifica como siempre. El mismo
    # fichero en el mismo proyecto da 409, así que la recodificación va a otro proyecto.
    assert _subir(client, binario["id"], csv, valor_favorable="no-refer").status_code == 409
    otro = client.post("/api/projects", json={"name": "r5-uso-binario-no-refer"}, headers=HUMANO).json()
    resp = _subir(client, otro["id"], csv, valor_favorable="no-refer")
    assert resp.status_code == 200 and resp.json()["valor_favorable"] == "no-refer"
    assert _filas(session, otro["id"])[-1].human_decision == 0


def test_una_clasificacion_con_cifras_no_cambia_de_camino(client: TestClient):
    """En binario `38.5` sigue siendo 422 con el vocabulario de siempre, no con el de regresión."""
    binario = client.post("/api/projects", json={"name": "r5-uso-binario-cifras"}, headers=HUMANO).json()
    resp = _subir(client, binario["id"], "date,human_decision,model_output,ground_truth\n2026-01-05,38.5,1,1\n")
    assert resp.status_code == 422
    assert FRASE not in resp.json()["detail"]


# -- La comprobación de codificación no corre ----------------------------------------------


def test_la_comprobacion_de_codificacion_no_corre_en_regresion(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-uso-codificacion", n=300)
    texto, _ = diario_regresion(250)
    resp = _subir(client, p["id"], texto)
    assert resp.status_code == 200, resp.text
    comprobacion = resp.json()["comprobacion_codificacion"]
    assert comprobacion["estado"] == "inconcluso"
    assert comprobacion["r"] is None and comprobacion["p"] is None
    assert comprobacion["n"] == 250
    assert comprobacion["motivo"] == human_layer.MOTIVO_CODIFICACION_REGRESION


# -- Sin rango, un test por punto ----------------------------------------------------------


def _sin_rango(client: TestClient, nombre: str) -> int:
    p, _t = r.linea_base_regresion(client, nombre, rangos=None, n=300)
    return p["id"]


def test_sin_rango_la_subida_da_422(client: TestClient):
    id_ = _sin_rango(client, "r5-uso-sin-rango-subida")
    resp = _subir(client, id_, CABECERA + "\n2026-01-05,10,11,12,c1,A\n")
    assert resp.status_code == 422 and resp.json()["detail"] == tarea.texto_guardia_capa_humana(sin_rango=True)


def test_sin_rango_las_cruzadas_dan_el_motivo(client: TestClient):
    id_ = _sin_rango(client, "r5-uso-sin-rango-cruzadas")
    trabajo = client.get(f"/api/jobs/{client.post(f'/api/projects/{id_}/cross/evaluate', headers=HUMANO).json()['id']}").json()
    assert trabajo["result"]["evaluation_id"] is None and trabajo["result"]["motivo"] == MOTIVO_CAPA_HUMANA_SIN_RANGO
    assert client.get(f"/api/projects/{id_}/cross/latest").json()["motivo"] == MOTIVO_CAPA_HUMANA_SIN_RANGO


def test_sin_rango_el_deskilling_da_el_motivo(client: TestClient):
    id_ = _sin_rango(client, "r5-uso-sin-rango-deskilling")
    deskilling = client.get(f"/api/projects/{id_}/deskilling").json()
    assert deskilling["sin_datos"] is True and deskilling["motivo"] == MOTIVO_CAPA_HUMANA_SIN_RANGO


@pytest.mark.parametrize("por", ["subgroup", "phase", "clinician"])
def test_sin_rango_los_overrides_dan_el_motivo(client: TestClient, por: str):
    id_ = _sin_rango(client, f"r5-uso-sin-rango-overrides-{por}")
    cuerpo = client.get(f"/api/projects/{id_}/overrides", params={"by": por})
    assert cuerpo.status_code == 200, cuerpo.text
    assert cuerpo.json()["motivo"] == MOTIVO_CAPA_HUMANA_SIN_RANGO


def test_sin_rango_overrides_me_da_el_motivo(client: TestClient):
    id_ = _sin_rango(client, "r5-uso-sin-rango-me")
    cuerpo = client.get(f"/api/projects/{id_}/overrides/me", params={"clinician": "enf-1"})
    assert cuerpo.status_code == 200, cuerpo.text
    assert cuerpo.json()["motivo"] == MOTIVO_CAPA_HUMANA_SIN_RANGO


def test_sin_rango_los_cambios_dan_el_motivo(client: TestClient):
    id_ = _sin_rango(client, "r5-uso-sin-rango-cambios")
    cambios = client.get(f"/api/projects/{id_}/overrides/cambios").json()
    assert cambios["motivo"] == MOTIVO_CAPA_HUMANA_SIN_RANGO
    assert cambios["categorias"] == [] and cambios["filas"] == [] and cambios["task_type"] == "regression"


def test_dos_intervalos_y_extremo_abierto_inferior_marcan_la_pertenencia(client: TestClient, session: Session):
    rangos = [[None, 5], [10, 12]]
    p, _t = r.linea_base_regresion(client, "r5-uso-dos-intervalos", rangos=rangos, n=300)
    # 4 dentro del primero (extremo inferior abierto), 11 en el segundo, 7 en el hueco, 12 exacto, 20 fuera.
    cifras = [(-3.0, 1), (4.0, 1), (11.0, 1), (7.0, 0), (12.0, 1), (20.0, 0)]
    texto = [CABECERA] + [f"2026-01-05,{v},{v},{v},c1,A" for v, _e in cifras]
    resp = _subir(client, p["id"], "\n".join(texto) + "\n")
    assert resp.status_code == 200, resp.text
    filas = _filas(session, p["id"])
    assert [f.human_decision for f in filas] == [e for _v, e in cifras]
    assert [f.model_output for f in filas] == [e for _v, e in cifras]
    assert [f.truth_value for f in filas] == [v for v, _e in cifras]


def test_una_cifra_con_digitos_no_ascii_da_422(client: TestClient):
    p, _t = r.linea_base_regresion(client, "r5-uso-digitos-unicode", n=300)
    resp = _subir(client, p["id"], CABECERA + "\n2026-01-05,\u0661\u0662,11,12,c1,A\n")
    assert resp.status_code == 422 and FRASE in resp.json()["detail"]


def test_la_guardia_con_rango_no_hace_nada_y_sin_rango_no_admite_sin_rango_falso():
    with pytest.raises(ValueError):
        tarea.texto_guardia_capa_humana(sin_rango=False)


# -- Diferencia media en la unidad ---------------------------------------------------------


@pytest.mark.parametrize("por", ["subgroup", "phase"])
def test_diferencia_media_por_grupo_en_la_unidad(client: TestClient, por: str):
    p, _t = r.linea_base_regresion(client, f"r5-uso-diferencia-{por}", n=300)
    texto, registros = diario_regresion(400)
    assert _subir(client, p["id"], texto).status_code == 200
    cuerpo = client.get(f"/api/projects/{p['id']}/overrides", params={"by": por}).json()
    assert cuerpo["unidad"] == r.UNIDAD and cuerpo["n_total"] == 400 and cuerpo["motivo"] is None
    if por == "phase":
        # Sin lote enlazado todo el diario cae en una fase.
        assert [g["group"] for g in cuerpo["groups"]] == ["sin_fase"]
        esperado = {"sin_fase": registros}
    else:
        esperado = {s: [x for x in registros if x["sub"] == s] for s in ("A", "B")}
    for grupo in cuerpo["groups"]:
        filas = esperado[grupo["group"]]
        media = sum(abs(x["humano"] - x["modelo"]) for x in filas) / len(filas)
        assert grupo["diferencia_media"] == pytest.approx(media)
        assert grupo["diferencia_media"] > 0
        # El override cuenta solo los cambios que cruzan el corte (límite conocido).
        cruces = sum(_dentro(x["humano"]) != _dentro(x["modelo"]) for x in filas) / len(filas)
        assert grupo["tasa"] == pytest.approx(cruces)
        assert cruces < sum(x["humano"] != x["modelo"] for x in filas) / len(filas)


def test_con_menos_de_min_n_filas_con_las_dos_cifras_es_nula(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-uso-diferencia-min-n")
    texto, _ = diario_regresion(40)
    assert _subir(client, p["id"], texto).status_code == 200
    grupos = client.get(f"/api/projects/{p['id']}/overrides", params={"by": "subgroup"}).json()["groups"]
    assert all(g["n"] == 20 and g["tasa"] is None and g["diferencia_media"] is None for g in grupos)
    # Con `min_n` bajo sí sale, y las filas sin decisión del profesional no entran en la media.
    grupos = client.get(f"/api/projects/{p['id']}/overrides", params={"by": "subgroup", "min_n": 5}).json()["groups"]
    assert all(g["diferencia_media"] is not None for g in grupos)


def test_en_clasificacion_los_dos_campos_son_nulos(client: TestClient):
    binario = client.post("/api/projects", json={"name": "r5-diferencia-binario"}, headers=HUMANO).json()
    csv = "date,human_decision,model_output,ground_truth,subgroup\n" + "\n".join(
        f"2026-01-{1 + i % 20:02d},{'refer' if i % 3 else 'no-refer'},refer,refer,a" for i in range(60)
    )
    assert _subir(client, binario["id"], csv + "\n").status_code == 200
    cuerpo = client.get(f"/api/projects/{binario['id']}/overrides", params={"by": "subgroup"}).json()
    assert cuerpo["unidad"] is None
    assert cuerpo["groups"] and all(g["diferencia_media"] is None for g in cuerpo["groups"])


# -- Punta a punta -------------------------------------------------------------------------------


def test_punta_a_punta_una_regresion_con_rango_recorre_la_capa_humana_sin_500(client: TestClient):
    p, t = r.linea_base_regresion(client, "r5-uso-e2e", n=500)
    lote = r.subir_e_ingerir(client, p, r.filas_regresion(300, semilla=11, prefijo="p", fecha="2026-01-12"), rol="production", evaluar=True)
    assert lote["result"]["batch_id"] and t["result"]["batch_id"]
    texto, registros = diario_regresion(480, dias=35)
    assert _subir(client, p["id"], texto).status_code == 200

    # Cruzadas: calibración la primera vez y vigilancia después; ambas con medidas.
    for modo in ("calibracion", "vigilancia"):
        trabajo = client.get(f"/api/jobs/{client.post(f'/api/projects/{p['id']}/cross/evaluate', headers=HUMANO).json()['id']}").json()
        assert trabajo["status"] == "terminado", trabajo
        assert trabajo["result"]["evaluation_id"] is not None and trabajo["result"]["mode"] == modo
    ultimo = client.get(f"/api/projects/{p['id']}/cross/latest").json()
    assert ultimo["estado"] == "con_datos" and ultimo["motivo"] is None
    reglas = {x["rule"] for x in ultimo["rules"]}
    assert {"CX-5", "human_review_zero"} <= reglas

    # Deskilling: las ventanas suman el diario.
    deskilling = client.get(f"/api/projects/{p['id']}/deskilling").json()
    assert deskilling["sin_datos"] is False and deskilling["motivo"] is None
    assert sum(w["n"] for w in deskilling["windows"]) == 480
    assert all(w["agreement_rate"] is not None for w in deskilling["windows"])

    # Overrides: el recuento coincide con los cruces del rango.
    cruces = [_dentro(x["humano"]) != _dentro(x["modelo"]) for x in registros]
    for por in ("subgroup", "phase", "clinician"):
        cuerpo = client.get(f"/api/projects/{p['id']}/overrides", params={"by": por})
        assert cuerpo.status_code == 200, cuerpo.text
        assert cuerpo.json()["n_total"] == 480 and cuerpo.json()["motivo"] is None
    por_grupo = client.get(f"/api/projects/{p['id']}/overrides", params={"by": "subgroup"}).json()["groups"]
    ponderada = sum(g["tasa"] * g["n"] for g in por_grupo) / sum(g["n"] for g in por_grupo)
    assert ponderada == pytest.approx(sum(cruces) / len(cruces))
    yo = client.get(f"/api/projects/{p['id']}/overrides/me", params={"clinician": "enf-1"})
    assert yo.status_code == 200 and yo.json()["motivo"] is None and yo.json()["windows"]

    # Tabla de cambios: dentro/fuera del rango, con los recuentos del diario.
    cambios = client.get(f"/api/projects/{p['id']}/overrides/cambios").json()
    assert cambios["categorias"] == ["dentro del rango", "fuera del rango"]
    assert cambios["unidad"] == r.UNIDAD and cambios["rangos_favorables"] == [[12.0, None]]
    assert cambios["n_total"] == 480 and cambios["n_sin_decision"] == 0 and cambios["motivo"] is None
    n_modelo_dentro = sum(_dentro(x["modelo"]) for x in registros)
    fila_dentro, fila_fuera = cambios["filas"]
    assert fila_dentro["n"] == n_modelo_dentro and fila_fuera["n"] == 480 - n_modelo_dentro
    assert fila_dentro["n"] + fila_fuera["n"] == 480
    cambiaron = (
        fila_dentro["celdas"][1]["n"] + fila_fuera["celdas"][0]["n"]
    )
    assert cambiaron == sum(cruces)

    assert client.get(f"/api/projects/{p['id']}/usage-logs/export.csv").text.count("\n") == 481

    # El dossier con telemetría lee el deskilling de la decisión derivada y se revisa sin 500.
    dossier = _crear_dossier(client, p["id"], include_telemetry=True, system_name="Atención semanal")
    assert dossier.status_code == 200, dossier.text
    assert dossier.json()["telemetry_included"] is True
    revision = client.post(
        f"/api/dossiers/{dossier.json()['id']}/reviews",
        json={"approach": "b0", "corpus": "todas", "dedup": True, "crosswalk": True,
              "actor": "miguel", "role": "auditor", "motivo": "revisión de la regresión"},
        headers=HUMANO,
    )
    assert revision.status_code == 200 and revision.json()["status"] == "terminado", revision.text
