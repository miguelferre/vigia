"""Casos borde: el diario de uso y el alta multiclase.

Cubre una clase rara en el diario, `k = 2` declarado como multiclase, las celdas
de clase que el normalizador (`parse_clase`) ve como «01», «1», «nan» y espacios,
y el conjunto favorable que cambia entre lotes.

Cada test fija un comportamiento esperado. Un test que describe un defecto lleva
`xfail(strict=True)` con el defecto descrito: si alguien lo arregla, pasa a verde y
strict avisa de que hay que quitar la marca.
"""

from __future__ import annotations

import math

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api import _datos_multiclase as d
from tests.api.conftest import actor_headers
from vigia.app.models import ModelVersion, Project, UsageLog
from vigia.app.services import human_layer
from vigia.app.services.usage_log_clases import MENSAJE_SIN_CLASES, parse_clase
from vigia.core.schema import TaskSpec

CLASES = ["ok", "spam", "odio", "desnudez", "otra"]
CABECERA = "date,human_decision,model_output,ground_truth,clinician_pseudonym,subgroup"


# ---------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------


def _crear(client: TestClient, nombre: str, *, clases=None, favorables=("spam", "odio"), **extra) -> dict:
    cuerpo: dict = {
        "name": nombre,
        "domain": "libre",
        "task_type": "multiclass",
        "classes": clases or CLASES,
        "mapping_template": {"favorable_label": list(favorables) if favorables else None},
    }
    cuerpo.update(extra)
    resp = client.post("/api/projects", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir_uso(client: TestClient, proyecto_id: int, contenido: str):
    return client.post(
        f"/api/projects/{proyecto_id}/usage-logs/upload",
        files={"file": ("uso.csv", contenido.encode(), "text/csv")},
        headers=actor_headers("miguel"),
    )


def _diario(filas: list[tuple[str, str, str]], *, dia0: int = 1) -> str:
    """Un diario de `(humano, modelo, verdad)`; dos subgrupos y cuatro profesionales."""
    lineas = [CABECERA]
    for i, (humano, modelo, verdad) in enumerate(filas):
        lineas.append(
            f"2026-01-{dia0 + i % 28:02d},{humano},{modelo},{verdad},clin-{i % 4},{'a' if i % 2 else 'b'}"
        )
    return "\n".join(lineas) + "\n"


def _diario_base(n: int = 240) -> list[tuple[str, str, str]]:
    """Sin ninguna fila de `otra`: ok, spam, odio y desnudez, con un 15 % de correcciones."""
    base = ["ok", "ok", "ok", "spam", "odio", "desnudez"]
    filas = []
    for i in range(n):
        verdad = base[i % len(base)]
        modelo = verdad if i % 5 else "ok"
        humano = modelo if i % 7 else "spam"
        filas.append((humano, modelo, verdad))
    return filas


def _filas_uso(session: Session, proyecto_id: int) -> list[UsageLog]:
    return list(
        session.exec(
            select(UsageLog).where(UsageLog.project_id == proyecto_id).order_by(UsageLog.id)  # type: ignore[arg-type]
        ).all()
    )


def _marco(session: Session, proyecto_id: int):
    p = session.get(Project, proyecto_id)
    v = session.get(ModelVersion, p.active_version_id)
    return human_layer.usage_frame(session, p, v)


def _tarea(clases, favorables=()) -> TaskSpec:
    return TaskSpec(task_type="multiclass", classes=tuple(clases), favorables=tuple(favorables))


# ---------------------------------------------------------------------------
# 1. Diario de uso con una clase rara
# ---------------------------------------------------------------------------


def test_una_clase_con_una_sola_fila_en_el_diario_se_guarda_y_las_vistas_responden(
    client: TestClient, session: Session
):
    proyecto = _crear(client, "borde-clase-rara")
    filas = _diario_base() + [("otra", "otra", "otra")]
    resp = _subir_uso(client, proyecto["id"], _diario(filas))
    assert resp.status_code == 200, resp.text
    assert resp.json()["n_rows"] == len(filas)

    guardadas = _filas_uso(session, proyecto["id"])
    rara = [f for f in guardadas if f.truth_class == "otra"]
    assert len(rara) == 1
    assert (rara[0].human_class, rara[0].model_class) == ("otra", "otra")
    # `otra` no es favorable: pertenencia 0 en los tres enteros.
    assert (rara[0].human_decision, rara[0].model_output, rara[0].ground_truth) == (0, 0, 0)

    for ruta in ("overrides?by=subgroup", "overrides?by=phase", "deskilling"):
        r = client.get(f"/api/projects/{proyecto['id']}/{ruta}")
        assert r.status_code == 200, (ruta, r.text)
    por_grupo = client.get(f"/api/projects/{proyecto['id']}/overrides?by=subgroup").json()
    assert por_grupo["n_total"] == len(filas)
    assert "otra" in client.get(f"/api/projects/{proyecto['id']}/usage-logs/export.csv").text


def test_una_clase_rara_en_el_diario_no_rompe_las_cruzadas(client: TestClient, session: Session):
    proyecto = _crear(client, "borde-clase-rara-cruzadas")
    filas = _diario_base(400) + [("otra", "otra", "otra")]
    assert _subir_uso(client, proyecto["id"], _diario(filas)).status_code == 200
    p = session.get(Project, proyecto["id"])
    version = session.get(ModelVersion, proyecto["active_version_id"])
    calibracion = human_layer.evaluate_cross_for_project(session, p, version=version)
    assert calibracion is not None and calibracion.result_json["mode"] == "calibracion"
    session.commit()
    vigilancia = human_layer.evaluate_cross_for_project(session, p, version=version)
    assert vigilancia is not None and vigilancia.result_json["mode"] == "vigilancia"
    for m in vigilancia.result_json["measurements"]:
        valor = m.get("value")
        assert valor is None or not math.isnan(valor), m  # ningún NaN suelto como valor


def test_una_clase_que_solo_elige_la_persona_cuenta_como_override(client: TestClient, session: Session):
    """La clase `otra` nunca sale del modelo ni de la verdad: solo la elige el
    profesional una vez. Es una discrepancia entre dos clases."""
    proyecto = _crear(client, "borde-clase-solo-humana")
    filas = _diario_base(120) + [("otra", "ok", "ok")]
    assert _subir_uso(client, proyecto["id"], _diario(filas)).status_code == 200
    (fila,) = [f for f in _filas_uso(session, proyecto["id"]) if f.human_class == "otra"]
    assert (fila.model_class, fila.truth_class) == ("ok", "ok")
    marco = _marco(session, proyecto["id"])
    assert (marco["human_decision"] == "otra").sum() == 1
    assert "otra" not in set(marco["model_output"]) | set(marco["ground_truth"])


def test_un_diario_que_usa_solo_dos_de_las_cinco_clases_vale(client: TestClient, session: Session):
    proyecto = _crear(client, "borde-dos-clases-usadas")
    filas = [("ok", "ok", "ok"), ("spam", "ok", "spam"), ("ok", "spam", "ok"), ("spam", "spam", "spam")] * 20
    resp = _subir_uso(client, proyecto["id"], _diario(filas))
    assert resp.status_code == 200, resp.text
    assert {f.human_class for f in _filas_uso(session, proyecto["id"])} == {"ok", "spam"}
    assert client.get(f"/api/projects/{proyecto['id']}/deskilling").status_code == 200


# ---------------------------------------------------------------------------
# 2. k = 2 declarado como multiclase
# ---------------------------------------------------------------------------


def test_el_alta_multiclase_con_dos_clases_da_422_que_manda_al_proyecto_binario(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={"name": "borde-k2", "domain": "libre", "task_type": "multiclass", "classes": ["a", "b"]},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422
    detalle = resp.text
    assert "3 a 20 clases" in detalle and "hay 2" in detalle and "proyecto binario" in detalle
    assert "borde-k2" not in client.get("/api/projects").text  # no deja un proyecto a medias


def test_el_alta_multiclase_con_una_clase_da_422(client: TestClient):
    resp = client.post(
        "/api/projects",
        json={"name": "borde-k1", "domain": "libre", "task_type": "multiclass", "classes": ["a"]},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422 and "hay 1" in resp.text


def test_declarar_dos_clases_despues_del_alta_tambien_da_422(client: TestClient):
    """El parche de la plantilla fija las clases una vez: con dos, 422 y
    el proyecto sigue sin clases."""
    p = client.post(
        "/api/projects",
        json={"name": "borde-k2-patch", "domain": "libre", "task_type": "multiclass"},
        headers=actor_headers("miguel"),
    ).json()
    resp = client.patch(
        f"/api/projects/{p['id']}",
        json={"actor": "miguel", "motivo": "clases", "mapping_template": {"classes": ["a", "b"], "favorable_label": ["a"]}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422 and "binario" in resp.text
    assert client.get(f"/api/projects/{p['id']}").json()["classes"] in (None, [])


def test_una_linea_base_de_dos_clases_en_un_proyecto_multiclase_da_422_y_no_fija_clases(client: TestClient):
    p = client.post(
        "/api/projects",
        json={"name": "borde-k2-base", "domain": "libre", "task_type": "multiclass"},
        headers=actor_headers("miguel"),
    ).json()
    dos = ["a", "b"]
    sub = d.subir(client, p["id"], d.a_csv(d.filas_multiclase(300, clases=dos, prevalencia=[0.5, 0.5])))
    resp = d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase(dos))
    assert resp.status_code == 422
    assert "binario" in resp.text and "hay 2" in resp.text
    assert client.get(f"/api/projects/{p['id']}").json()["classes"] in (None, [])


def test_el_diario_de_un_proyecto_multiclase_sin_clases_dice_que_congele_la_linea_base(client: TestClient):
    p = client.post(
        "/api/projects",
        json={"name": "borde-sin-clases", "domain": "libre", "task_type": "multiclass"},
        headers=actor_headers("miguel"),
    ).json()
    resp = _subir_uso(client, p["id"], CABECERA + "\n2026-01-05,a,b,a,c1,x\n")
    assert resp.status_code == 422
    assert resp.json()["detail"] == MENSAJE_SIN_CLASES


def test_si_un_proyecto_llegara_al_diario_con_dos_clases_se_valida_contra_ellas(
    client: TestClient, session: Session
):
    """`classes_json` de dos clases no se puede crear por la API, pero el
    diario no repite esa regla: valida contra la lista guardada, sin excepción.
    Fija ese reparto (la barrera está en el alta, el parche y el mapeo)."""
    proyecto = _crear(client, "borde-k2-forzado", clases=["a", "b", "c"], favorables=("a",))
    p = session.get(Project, proyecto["id"])
    p.classes_json = ["a", "b"]
    session.add(p)
    session.commit()

    ok = _subir_uso(client, proyecto["id"], CABECERA + "\n2026-01-05,a,b,a,c1,x\n2026-01-06,b,b,b,c1,x\n")
    assert ok.status_code == 200, ok.text
    fuera = _subir_uso(client, proyecto["id"], CABECERA + "\n2026-01-07,a,c,a,c1,x\n")
    assert fuera.status_code == 422
    assert "fila 1" in fuera.json()["detail"] and "(a, b)" in fuera.json()["detail"]


# ---------------------------------------------------------------------------
# 3. parse_clase con "01", "1", 1, "nan", float("nan") y espacios
# ---------------------------------------------------------------------------


def _parse(valor, tarea, columna="human_decision"):
    return parse_clase(valor, tarea, fila_n=2, columna=columna)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("1", ("1", 1)),
        (1, ("1", 1)),
        (" 1 ", ("1", 1)),
        ("\t1\n", ("1", 1)),
        ("1.0", ("1", 1)),  # el diario se lee como texto: un 1.0 de hoja de cálculo vale 1
        (1.0, ("1", 1)),
        ("2", ("2", 0)),
        ("2.0", ("2", 0)),
        ("3", ("3", 0)),
    ],
)
def test_parse_clase_numerica_reconoce_el_mismo_numero_escrito_de_varias_formas(valor, esperado):
    assert _parse(valor, _tarea(["1", "2", "3"], ["1"])) == esperado


@pytest.mark.parametrize("valor", [None, "", "   ", "nan", "NaN", "NAN", float("nan"), " nan "])
def test_parse_clase_una_celda_en_blanco_o_nan_no_es_una_clase(valor):
    assert _parse(valor, _tarea(["1", "2", "3"], ["1"])) == (None, None)


@pytest.mark.parametrize("valor", ["4", "0", "1.5", "uno", "None", "refer"])
def test_parse_clase_una_clase_que_no_esta_da_422_con_la_fila_y_las_clases(valor):
    with pytest.raises(HTTPException) as exc:
        _parse(valor, _tarea(["1", "2", "3"], ["1"]), columna="ground_truth")
    assert exc.value.status_code == 422
    detalle = exc.value.detail
    assert "la fila 2" in detalle and "ground_truth" in detalle
    assert "1, 2, 3" in detalle or "(1, 2, 3)" in detalle


def test_parse_clase_01_y_1_son_clases_distintas_cuando_las_dos_estan_declaradas():
    t = _tarea(["01", "1", "2"], ["01"])
    assert _parse("01", t) == ("01", 1)
    assert _parse("1", t) == ("1", 0)
    assert _parse(" 01 ", t) == ("01", 1)
    assert _parse(1, t) == ("1", 0)


def test_parse_clase_01_con_las_clases_01_02_10_no_se_confunde_con_1():
    t = _tarea(["01", "02", "10"], ["01"])
    assert _parse("01", t) == ("01", 1)
    with pytest.raises(HTTPException) as exc:
        _parse("1", t)  # «1» no es «01»: es una clase que no está
    assert exc.value.status_code == 422


def test_parse_clase_mayusculas_solo_si_hay_una_coincidencia():
    t = _tarea(["spam", "Odio", "ok"], ["spam"])
    assert _parse("SPAM", t) == ("spam", 1)
    assert _parse("odio", t) == ("Odio", 0)
    ambigua = _tarea(["spam", "Spam", "ok"], ["spam"])
    assert _parse("spam", ambigua) == ("spam", 1)  # coincidencia exacta primero
    with pytest.raises(HTTPException):
        _parse("SPAM", ambigua)  # dos candidatas sin exacta: no se adivina


def test_parse_clase_refer_dice_que_es_de_los_modelos_binarios():
    with pytest.raises(HTTPException) as exc:
        _parse("no-refer", _tarea(["a", "b", "c"], ["a"]), columna="model_output")
    assert "binarios" in exc.value.detail and "multiclase" in exc.value.detail


@pytest.mark.parametrize("valor", ["01", "+1", "1e0"])
def test_parse_clase_01_no_es_la_clase_1_cuando_solo_esta_la_1(valor):
    with pytest.raises(HTTPException) as exc:
        _parse(valor, _tarea(["1", "2", "3"], ["1"]))
    assert exc.value.status_code == 422


def test_parse_clase_01_en_la_ingesta_del_lote_es_clase_desconocida_no_la_1():
    """Referencia de la regla que el diario debería seguir."""
    import pandas as pd

    from vigia.core.loaders import to_canonical
    from vigia.core.schema import ColumnMapping

    cl = ["1", "2", "3"]
    m = ColumnMapping(
        prediction_col="p", label_col="l", id_col="i", classes=cl,
        probability_cols=["a", "b", "c"], favorable_label=["1"],
    )
    df = pd.DataFrame({"i": [1, 2], "p": ["1", "2"], "l": ["01", " 1 "], "a": [0.6, 0.2], "b": [0.2, 0.6], "c": [0.2, 0.2]})
    canon = to_canonical(df, m, batch_seq=0, seq_start=0, task=_tarea(cl, ["1"]))
    assert canon["label_class"].tolist() == ["01", "1"]  # «01» queda sin clase asignada
    assert pd.isna(canon["label"].iloc[0]) and canon["label"].iloc[1] == 1


def test_una_clase_llamada_nan_se_rechaza_en_el_alta():
    """«nan» se lee como celda vacía en los ficheros, así que no sirve como clase."""
    from vigia.core.schema import MappingTemplate

    for nombre in ("nan", "NaN", " nan "):
        with pytest.raises(ValueError, match="«nan» no sirve como nombre de clase"):
            MappingTemplate(classes=[nombre, "spam", "odio"], favorable_label=["spam"])


def test_una_clase_llamada_na_o_con_barra_si_se_guarda_como_clase(client: TestClient, session: Session):
    """Los nombres que parecen un nulo («NA», «N/A») no se pierden: el diario se
    lee como texto, sin la lista de nulos de pandas."""
    for nombre in ("NA", "N/A"):
        proyecto = _crear(client, f"borde-clase-{nombre.replace('/', '-')}", clases=[nombre, "spam", "odio"], favorables=("spam",))
        resp = _subir_uso(client, proyecto["id"], CABECERA + f"\n2026-01-05,{nombre},spam,{nombre},c1,a\n")
        assert resp.status_code == 200, resp.text
        (fila,) = _filas_uso(session, proyecto["id"])[-1:]
        assert (fila.human_class, fila.truth_class) == (nombre, nombre)


def test_clases_numericas_en_el_alta_y_el_diario_con_ceros_a_la_izquierda(client: TestClient, session: Session):
    """Proyecto con clases «01», «02», «10» (códigos): se guardan como texto y
    el diario las reconoce tal cual."""
    proyecto = _crear(client, "borde-codigos", clases=["01", "02", "10"], favorables=("01",))
    assert proyecto["classes"] == ["01", "02", "10"]
    resp = _subir_uso(client, proyecto["id"], CABECERA + "\n2026-01-05,01,02,10,c1,a\n2026-01-06,10,10,01,c1,a\n")
    assert resp.status_code == 200, resp.text
    filas = _filas_uso(session, proyecto["id"])
    assert [(f.human_class, f.model_class, f.truth_class) for f in filas] == [
        ("01", "02", "10"),
        ("10", "10", "01"),
    ]
    assert [(f.human_decision, f.model_output, f.ground_truth) for f in filas] == [(1, 0, 0), (0, 0, 1)]


# ---------------------------------------------------------------------------
# 4. El conjunto favorable cambia entre lotes: el diario ya subido conserva su 0/1
# ---------------------------------------------------------------------------


def _linea_base(client: TestClient, nombre: str, *, favorables):
    """Proyecto multiclase de cinco clases con la línea base ingerida con ese conjunto."""
    proyecto = d.crear_proyecto_multiclase(client, nombre, mapping_template=None)
    sub = d.subir(client, proyecto["id"], d.a_csv(d.filas_multiclase(300)))
    assert d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase(favorable_label=favorables)).status_code == 200
    assert d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])["status"] == "terminado"
    return proyecto


def _lote_con_favorables(client: TestClient, proyecto: dict, favorables, semilla: int):
    sub = d.subir(client, proyecto["id"], d.a_csv(d.filas_multiclase(150, seed=semilla, prefijo_id=f"q{semilla}")), rol="production")
    resp = d.mapear(client, sub["dataset"]["id"], d.mapeo_multiclase(favorable_label=favorables))
    assert resp.status_code == 200, resp.text
    assert d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"])["status"] == "terminado"


def _enteros(session: Session, proyecto_id: int):
    return [
        (f.human_class, f.model_class, f.truth_class, f.human_decision, f.model_output, f.ground_truth)
        for f in _filas_uso(session, proyecto_id)
    ]


def test_un_diario_ya_subido_conserva_su_0_1_cuando_cambia_el_conjunto_favorable(
    client: TestClient, session: Session
):
    proyecto = _linea_base(client, "borde-fav-cambia", favorables=["permitido"])
    uso = CABECERA + "\n2026-01-05,permitido,spam,permitido,c1,a\n2026-01-06,spam,spam,odio,c1,a\n"
    assert _subir_uso(client, proyecto["id"], uso).status_code == 200
    antes = _enteros(session, proyecto["id"])
    assert [f[3:] for f in antes] == [(1, 0, 1), (0, 0, 0)]  # conjunto {permitido}

    _lote_con_favorables(client, proyecto, ["spam", "odio"], semilla=5)
    session.expire_all()
    assert _enteros(session, proyecto["id"]) == antes  # no se reescribe

    # El diario que se sube después ya usa el conjunto nuevo: {spam, odio}. Otras
    # fechas, mismas clases: el mismo fichero otra vez daría 409.
    uso_nuevo = uso.replace("2026-01-05", "2026-01-07").replace("2026-01-06", "2026-01-08")
    assert _subir_uso(client, proyecto["id"], uso_nuevo).status_code == 200
    session.expire_all()
    nuevas = _enteros(session, proyecto["id"])[2:]
    assert [f[:3] for f in nuevas] == [f[:3] for f in antes]  # mismas clases
    assert [f[3:] for f in nuevas] == [(0, 1, 0), (1, 1, 1)]  # pertenencia al conjunto nuevo


def test_las_clases_del_diario_no_cambian_con_el_conjunto_favorable(client: TestClient, session: Session):
    """Lo que manda para CX-2, CX-3, CX-5 y CX-6 son los nombres de clase, que no
    dependen del conjunto favorable."""
    proyecto = _linea_base(client, "borde-fav-clases", favorables=["permitido"])
    uso = CABECERA + "\n2026-01-05,permitido,spam,odio,c1,a\n"
    assert _subir_uso(client, proyecto["id"], uso).status_code == 200
    _lote_con_favorables(client, proyecto, ["violencia"], semilla=6)
    session.expire_all()
    marco = _marco(session, proyecto["id"])
    assert marco[["human_decision", "model_output", "ground_truth"]].iloc[0].tolist() == ["permitido", "spam", "odio"]


def test_si_el_conjunto_pasa_a_vacio_las_filas_con_0_1_dejan_de_leerse_en_cx1(
    client: TestClient, session: Session
):
    proyecto = _linea_base(client, "borde-fav-a-vacio", favorables=["spam"])
    assert _subir_uso(client, proyecto["id"], CABECERA + "\n2026-01-05,spam,spam,spam,c1,a\n").status_code == 200
    assert bool(_marco(session, proyecto["id"])["conjunto_favorable"].all())
    _lote_con_favorables(client, proyecto, [], semilla=7)
    session.expire_all()
    marco = _marco(session, proyecto["id"])
    assert not marco["conjunto_favorable"].any()
    assert marco["truth_fav"].isna().all() and marco["model_fav"].isna().all()


def test_un_diario_subido_sin_conjunto_no_cuenta_ceros_falsos_cuando_luego_se_fija_uno(
    client: TestClient, session: Session
):
    proyecto = _linea_base(client, "borde-fav-de-vacio", favorables=[])
    uso = CABECERA + "\n2026-01-05,spam,spam,spam,c1,a\n2026-01-06,permitido,permitido,permitido,c1,a\n"
    assert _subir_uso(client, proyecto["id"], uso).status_code == 200
    antes = _marco(session, proyecto["id"])
    assert not antes["conjunto_favorable"].any() and antes["truth_fav"].isna().all()

    _lote_con_favorables(client, proyecto, ["spam"], semilla=8)
    session.expire_all()
    despues = _marco(session, proyecto["id"])
    fila_spam = despues[despues["ground_truth"] == "spam"].iloc[0]
    fila_permitido = despues[despues["ground_truth"] == "permitido"].iloc[0]
    # La pertenencia se recalcula desde la clase guardada con el conjunto de hoy.
    assert fila_spam["truth_fav"] == 1 and fila_spam["model_fav"] == 1
    assert fila_permitido["truth_fav"] == 0 and fila_permitido["model_fav"] == 0


def test_una_clase_llamada_nan_da_422_en_el_alta(client: TestClient):
    cuerpo = {"name": "borde-clase-nan", "domain": "libre", "task_type": "multiclass",
              "classes": ["nan", "spam", "odio"], "mapping_template": {"favorable_label": ["spam"]}}
    resp = client.post("/api/projects", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 422, resp.text
    assert "nan" in resp.text
