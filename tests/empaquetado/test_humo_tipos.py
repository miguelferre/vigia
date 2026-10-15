"""`build/humo_tipos.py`: el paso nuevo del 9 de `humo_zip`.

Funciones puras, el generador frente a las plantillas reales y una corrida completa contra
la app en proceso (sin red, sin zip). El humo contra el Python embebido del zip lo corre
el cierre.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vigia.app.main import create_app
from vigia.app.services import plantillas_datos
from vigia.app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
HUMO_TIPOS = REPO_ROOT / "build" / "humo_tipos.py"
HUMO_ZIP = REPO_ROOT / "build" / "humo_zip.py"

if not HUMO_TIPOS.is_file():
    pytest.skip("build/humo_tipos.py no está en este árbol", allow_module_level=True)


def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ht = _cargar("vigia_humo_tipos", HUMO_TIPOS)
hz = _cargar("vigia_humo_zip_tipos", HUMO_ZIP)
BASE = "http://127.0.0.1:8765"


def _plantilla(tipo: str) -> str:
    contenido = plantillas_datos.plantilla_csv(tipo)[1]
    return contenido if isinstance(contenido, str) else contenido.decode("utf-8")


def _filas(texto: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(texto)))


# --------------------------------------------------------------------------
# la biblioteca estándar y nada más
# --------------------------------------------------------------------------


def test_humo_tipos_solo_importa_la_biblioteca_estandar():
    """Corre con el Python embebido del zip: nada de numpy, pandas ni vigia."""
    import ast

    arbol = ast.parse(HUMO_TIPOS.read_text(encoding="utf-8"))
    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split(".")[0])
    assert importados <= set(sys.stdlib_module_names), sorted(importados - set(sys.stdlib_module_names))


# --------------------------------------------------------------------------
# generador frente a las plantillas reales
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", ht.TIPOS)
def test_el_csv_generado_lleva_las_columnas_de_la_plantilla_en_su_orden(tipo: str):
    cabecera = ht.leer_cabecera(_plantilla(tipo))
    texto = ht.generar_csv(tipo, cabecera, clave="B", mes=2)
    assert ht.leer_cabecera(texto) == cabecera
    filas = _filas(texto)
    assert len(filas) == ht.FILAS
    assert len({f["id"] for f in filas}) == ht.FILAS
    assert all(f["date"].startswith("2026-02-") for f in filas)


def test_el_csv_generado_es_determinista():
    cabecera = ht.leer_cabecera(_plantilla("regresion"))
    a = ht.generar_csv("regresion", cabecera, clave="L", mes=3)
    assert a == ht.generar_csv("regresion", cabecera, clave="L", mes=3)
    assert a != ht.generar_csv("regresion", cabecera, clave="B", mes=3)


def test_multiclase_generada_suma_uno_y_usa_las_clases_de_la_plantilla():
    cabecera = ht.leer_cabecera(_plantilla("multiclase"))
    clases = list(plantillas_datos.CLASES_PLANTILLA_MULTICLASE)
    assert ht.clases_de_cabecera(cabecera) == clases
    filas = _filas(ht.generar_csv("multiclase", cabecera, clave="B", mes=2))
    for f in filas:
        assert abs(sum(float(f[f"prob_{c}"]) for c in clases) - 1.0) < 1e-6
        assert f["prediction"] in clases and f["label"] in clases
    assert {f["label"] for f in filas} == set(clases)


def test_regresion_generada_son_numeros_sin_unidad():
    cabecera = ht.leer_cabecera(_plantilla("regresion"))
    for f in _filas(ht.generar_csv("regresion", cabecera, clave="B", mes=2)):
        assert float(f["prediction"]) >= 0 and float(f["label"]) > 0


def test_una_columna_nueva_en_la_plantilla_hace_fallar_el_humo_con_su_nombre():
    cabecera = [*ht.leer_cabecera(_plantilla("regresion")), "columna_nueva"]
    with pytest.raises(ht.FalloHumo, match="columna_nueva"):
        ht.generar_csv("regresion", cabecera, clave="B", mes=2)


def test_tipo_desconocido():
    with pytest.raises(ht.FalloHumo, match="desconocido"):
        ht.generar_csv("otro", ["id"], clave="B", mes=2)


# --------------------------------------------------------------------------
# cuerpos de alta y mapeo
# --------------------------------------------------------------------------


def test_cuerpo_de_alta_multiclase_trae_clases_y_plantilla_de_mapeo():
    cabecera = ht.leer_cabecera(_plantilla("multiclase"))
    cuerpo = ht.cuerpo_proyecto("multiclase", "x", cabecera)
    assert cuerpo["task_type"] == "multiclass"
    assert cuerpo["classes"] == ["leve", "moderada", "grave"]
    assert cuerpo["mapping_template"]["probability_cols"] == ["prob_leve", "prob_moderada", "prob_grave"]
    assert "favorable_label" not in cuerpo  # en multiclase va en la plantilla de mapeo


def test_cuerpo_de_alta_regresion_trae_unidad_y_rango():
    cuerpo = ht.cuerpo_proyecto("regresion", "x", ht.leer_cabecera(_plantilla("regresion")))
    assert cuerpo["task_type"] == "regression"
    assert cuerpo["target_unit"] == plantillas_datos.UNIDAD_PLANTILLA_REGRESION
    assert cuerpo["favorable_ranges"] == [[0.0, 7.0]]


def test_multiclase_con_menos_de_tres_columnas_de_probabilidad_falla():
    with pytest.raises(ht.FalloHumo, match="3 o más"):
        ht.cuerpo_proyecto("multiclase", "x", ["id", "prob_a", "prob_b"])


def test_mapeo_final_respeta_lo_sugerido_y_rellena_lo_que_falta():
    cabecera = ht.leer_cabecera(_plantilla("regresion"))
    mapeo = ht.mapeo_final("regresion", {"prediction_col": "prediction", "target_unit": "horas"}, cabecera)
    assert mapeo["target_unit"] == "horas"  # lo sugerido manda
    assert mapeo["favorable_ranges"] == [[0.0, 7.0]]
    assert mapeo["feature_cols"] == ["age_years", "crp", "esr", "joint_count"]
    multi = ht.mapeo_final("multiclase", {}, ht.leer_cabecera(_plantilla("multiclase")))
    assert multi["classes"] == ["leve", "moderada", "grave"]
    assert multi["favorable_label"] == ["leve"]


# --------------------------------------------------------------------------
# qué cuenta como evaluación con error
# --------------------------------------------------------------------------

BUENA = {"monitor_type": "quality", "status": "ok", "measurements": [{"metric_key": "r2", "value": 0.8}]}


def test_una_evaluacion_buena_no_da_errores():
    assert ht.evaluaciones_con_error([BUENA]) == []


def test_equidad_sin_datos_no_es_error_pero_calidad_sin_medidas_si():
    equidad = {"monitor_type": "fairness", "status": "ok", "worst_state": "sin_datos", "measurements": []}
    assert ht.evaluaciones_con_error([equidad]) == []
    vacia = {"monitor_type": "quality", "status": "ok", "measurements": []}
    assert ht.evaluaciones_con_error([vacia]) == ["quality: ninguna medida con valor"]
    sin_valor = {"monitor_type": "drift", "status": "ok", "measurements": [{"value": None}, {"value": True}]}
    assert ht.evaluaciones_con_error([sin_valor]) == ["drift: ninguna medida con valor"]


@pytest.mark.parametrize("malo", [{"status": "error"}, {"status": ""}, {"status": "ok", "error": "boom"}])
def test_estado_distinto_de_ok_o_con_error_es_error(malo: dict):
    ev = {"monitor_type": "quality", "measurements": BUENA["measurements"], **malo}
    assert len(ht.evaluaciones_con_error([ev])) == 1


def test_multipart_lleva_campos_y_fichero():
    cuerpo, tipo = ht.multipart({"kind": "combined", "role": "baseline", "name": None}, "a.csv", b"x,y\n1,2\n")
    borde = tipo.split("boundary=")[1]
    texto = cuerpo.decode("utf-8")
    assert tipo.startswith("multipart/form-data")
    assert 'name="kind"\r\n\r\ncombined' in texto and 'name="role"\r\n\r\nbaseline' in texto
    assert 'name="name"' not in texto
    assert 'name="file"; filename="a.csv"' in texto and "x,y\n1,2\n" in texto
    assert texto.endswith(f"--{borde}--\r\n")


# --------------------------------------------------------------------------
# corrida completa contra la app en proceso
# --------------------------------------------------------------------------


@pytest.fixture
def cliente(tmp_path: Path) -> Iterator[TestClient]:
    datos = tmp_path / "vigia-datos"
    datos.mkdir()
    settings = Settings(
        data_dir=datos, host="127.0.0.1", port_start=8765, open_browser=False, jobs_inline=True, sse_heartbeat_s=0.2
    )
    app = create_app(settings)
    app.state.port = 8765
    app.state.shutdown_token = "test-token"
    with TestClient(app, base_url=BASE) as c:
        yield c


@pytest.fixture
def humo_en_proceso(cliente: TestClient, monkeypatch: pytest.MonkeyPatch):
    """`humo_tipos` habla con la app en proceso en vez de abrir un socket."""

    def abrir(req):
        ruta = req.full_url.removeprefix(BASE)
        resp = cliente.request(req.get_method(), ruta, content=req.data, headers=dict(req.header_items()))
        texto = resp.text
        return resp.status_code, (json.loads(texto) if texto.strip()[:1] in ("{", "[") else texto)

    monkeypatch.setattr(ht, "_abrir", abrir)
    return ht


def test_el_humo_da_de_alta_evalua_y_deja_los_dos_proyectos(humo_en_proceso, cliente: TestClient):
    informe = humo_en_proceso.correr(BASE)
    assert informe["ok"], informe
    assert [t["tipo"] for t in informe["tipos"]] == ["multiclase", "regresion"]
    for t in informe["tipos"]:
        assert t["filas_linea_base"] == ht.FILAS and t["filas_lote"] == ht.FILAS
        assert t["evaluaciones"] == 3
    proyectos = {p["task_type"] for p in cliente.get("/api/projects").json()["items"]}
    assert proyectos == {"multiclass", "regression"}


def test_un_fallo_de_un_tipo_no_impide_probar_el_otro(humo_en_proceso, monkeypatch: pytest.MonkeyPatch):
    original = ht.cuerpo_proyecto

    def roto(tipo, nombre, cabecera):
        cuerpo = original(tipo, nombre, cabecera)
        if tipo == "multiclase":
            cuerpo["classes"] = ["una_sola"]
        return cuerpo

    monkeypatch.setattr(ht, "cuerpo_proyecto", roto)
    informe = humo_en_proceso.correr(BASE)
    assert informe["ok"] is False
    multi, reg = informe["tipos"]
    assert multi["ok"] is False and "alta del proyecto multiclase" in multi["error"]
    assert reg["ok"] is True


def test_main_imprime_json_y_sale_con_0_o_1(humo_en_proceso, capsys: pytest.CaptureFixture[str]):
    assert ht.main(["--url", BASE, "--tipos", "regresion"]) == 0
    texto = capsys.readouterr().out
    salida = json.loads(texto)
    assert salida["ok"] and [t["tipo"] for t in salida["tipos"]] == ["regresion"]
    # La salida es ASCII: el Python embebido de Windows imprime con la página de códigos local.
    assert texto.isascii()


# --------------------------------------------------------------------------
# lo que humo_zip hace con la salida
# --------------------------------------------------------------------------


def test_humo_zip_interpreta_la_salida_aunque_venga_precedida_de_avisos():
    informe = {"ok": True, "tipos": [{"tipo": "regresion", "ok": True, "segundos": 1.8, "evaluaciones": 3}]}
    salida = "aviso suelto\n" + json.dumps(informe, indent=2)
    assert hz.interpretar_salida_tipos(salida) == informe
    assert hz.interpretar_salida_tipos("sin json") == {}
    assert hz.interpretar_salida_tipos("{roto") == {}
    assert hz.interpretar_salida_tipos("[1, 2]") == {}


def test_humo_zip_resume_los_tipos_buenos_y_los_que_fallan():
    informe = {
        "tipos": [
            {"tipo": "multiclase", "ok": True, "segundos": 9.2, "evaluaciones": 3},
            {"tipo": "regresion", "ok": False, "error": "FalloHumo: alta"},
        ]
    }
    texto = hz.resumen_tipos(informe)
    assert "multiclase 9.2 s (3 evaluaciones)" in texto and "regresion FALLA: FalloHumo: alta" in texto
    assert hz.resumen_tipos({}) == "sin tipos"
