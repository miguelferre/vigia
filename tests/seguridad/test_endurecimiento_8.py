"""Endurecimiento de SEGURIDAD.md, los textos y el informe de la revisión.

Un test por control; cada uno comprueba que el control existe.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from tests.api.test_dossiers import _SYSTEM_NAME, _crear_dossier, _reproducir_demo
from vigia.app.main import create_app
from vigia.app.models import Event
from vigia.app.services.evidence import render_events_html
from vigia.app.settings import Settings
from vigia.core.predict_onnx import ModeloEjecutableInvalido, build_artifact_inputs
from vigia.human import informe_revision

RAIZ = Path(__file__).resolve().parents[2]
CSP_INFORME = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    settings = Settings(
        data_dir=data_dir, host="127.0.0.1", port_start=8995, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )
    app: FastAPI = create_app(settings)
    app.state.port = 8995
    app.state.shutdown_token = "test-token"
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _leer(ruta: str) -> str:
    return (RAIZ / ruta).read_text(encoding="utf-8")


def _seccion(texto: str, titulo: str) -> str:
    m = re.search(rf"^## {re.escape(titulo)}\s*$(.*?)(?=^## |\Z)", texto, re.MULTILINE | re.DOTALL)
    assert m, f"falta la sección {titulo!r}"
    return m.group(1)


def test_informe_con_csp_sandbox_y_nosniff(client: TestClient):
    """El informe se sirve aislado también en pestaña nueva."""
    run = _reproducir_demo(client)
    dossier = _crear_dossier(client, run["project_id"], system_name=_SYSTEM_NAME).json()
    lanzada = client.post(
        f"/api/dossiers/{dossier['id']}/reviews",
        json={"approach": "b0", "corpus": "todas", "dedup": True, "crosswalk": False,
              "actor": "miguel", "role": "auditor", "motivo": "comprobar cabeceras del informe"},
        headers=actor_headers("miguel"),
    )
    assert lanzada.status_code == 200, lanzada.text
    review_id = client.get(f"/api/dossiers/{dossier['id']}").json()["reviews"][0]["id"]
    resp = client.get(f"/api/reviews/{review_id}/report")
    assert resp.status_code == 200 and "&lt;script&gt;" in resp.text, "control positivo"
    assert resp.headers["content-security-policy"] == CSP_INFORME
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_n_fuentes_se_escapa_en_el_informe():
    """El número de fuentes no entra sin escapar en el informe."""
    rev = {
        "dossier": {"system_name": "S", "domain": "D", "n_sources": "<script>x</script>"},
        "findings": [],
        "approach": "b0",
        "meta": {"date": "2026-10-07T10:00:00+00:00", "tool_version": "0.1.0", "model": "n/a"},
    }
    doc = informe_revision.dibujar(rev)
    assert "&lt;script&gt;x&lt;/script&gt;" in doc
    assert "<script>x" not in doc


def test_exportacion_html_del_diario_escapa_motivo_y_actor():
    """Texto con etiquetas en motivo y actor sale escapado."""
    evento = Event(
        id=1, ts="2026-10-07T10:00:00+00:00", actor_kind="humano", actor_id="<script>a()</script>",
        action="x.y", object_type="project", object_id=1, motivo="<script>m()</script>",
    )
    doc = render_events_html([evento])
    assert "&lt;script&gt;a()&lt;/script&gt;" in doc and "&lt;script&gt;m()&lt;/script&gt;" in doc
    assert "<script>" not in doc


@pytest.mark.parametrize(
    "ruta", ["vigia.lock", "vigia.log", "backups/vigia.db.bak", "vigia.db.bak", "uploads/a.csv", "artifacts/m.onnx"]
)
def test_gitignore_cubre_estado_de_instalacion(ruta: str):
    """Ningún fichero de estado de una instalación entra en un commit."""
    try:
        r = subprocess.run(["git", "check-ignore", "-q", ruta], cwd=RAIZ, capture_output=True, check=False)
    except FileNotFoundError:
        pytest.skip("git no está disponible")
    if r.returncode == 128:
        pytest.skip("la raíz no es un repositorio git")
    assert r.returncode == 0, f"{ruta} no está ignorada"


def test_web_principal_y_sin_ipv6_en_seguridad():
    """La web como principal figura y `::1` no se anuncia."""
    texto = _leer("SEGURIDAD.md")
    assert "::1" not in texto
    limites = _seccion(texto, "Qué no protege y qué hacer")
    assert "Origin" in limites and "127.0.0.1" in limites
    assert "*.bak" in limites and "clave de API" in limites


def test_seguridad_dice_quien_fija_cada_confirmacion():
    """No promete confirmaciones que fija quien llama."""
    texto = _leer("SEGURIDAD.md")
    assert "sin tu confirmación" not in texto.lower()
    assert "confirm=true" not in texto
    limites = _seccion(texto, "Qué no protege y qué hacer").lower()
    assert "fija sus propias confirmaciones" in limites and "host del mcp" in limites
    assert "pickle" in limites


def test_limites_conocidos_cubre_todos_los_limites_decididos():
    """Todos los límites decididos constan."""
    limites = _seccion(_leer("SEGURIDAD.md"), "Qué no protege y qué hacer").lower()
    for clave in ("autodeclarado", "permisos de carpetas", "lock", ".sha256", "poda nada", "ruta"):
        assert clave in limites, clave


def test_onnx_no_se_presenta_como_seguro_por_definicion():
    """La frase sobre ONNX no afirma lo que no se verifica."""
    for ruta in ("SEGURIDAD.md", "docs/manual/problemas.md"):
        assert "ONNX no ejecuta código y no pide" not in _leer(ruta), ruta
    assert "conoces su origen" in _leer("SEGURIDAD.md")


def test_guia_de_uso_dice_que_vigia_si_carga_modelos():
    """La guía de uso ya no dice que Vigía no ejecuta el modelo."""
    for ruta in ("src/vigia/content/guia-uso.json", "docs/manual/uso.md"):
        assert "Vigía no ejecuta el modelo" not in _leer(ruta), ruta
        assert "ONNX o pickle" in _leer(ruta), ruta


def test_el_identificador_se_guarda_sin_codificar():
    """Ni la ayuda ni la guía dicen que el identificador se codifica."""
    for ruta in ("src/vigia/content/textos-pantalla.json", "src/vigia/content/guia-uso.json",
                 "src/vigia/content/guia-datos.json"):
        assert not re.search(r"identificador( de la fila,)? (ya )?codificado", _leer(ruta)), ruta


def test_formulario_del_dossier_no_enseña_etiquetas_en_ingles():
    """La pantalla del dossier no pinta `original`, el texto inglés de la plantilla."""
    assert "pregunta.original" not in _leer("frontend/src/pages/auditoria/Formulario.tsx")


def test_ficha_dice_que_columnas_son_entrada_y_donde_va_la_politica():
    """La ficha pública marca la entrada del modelo y nombra la pestaña «Umbrales»."""
    if not (RAIZ / "build" / "validacion" / "publicos" / "ficha_html.py").is_file():
        pytest.skip("el generador de fichas no viaja en el árbol público")
    sys.path.insert(0, str(RAIZ / "build" / "validacion"))
    try:
        from publicos.ficha_html import construir_html
    finally:
        sys.path.pop(0)
    ficha = {
        "conjunto": "adult", "descripcion": "d", "aviso": "a",
        "fuente": {"url": "u", "licencia": "l", "atribucion": "a", "fecha_descarga": "f", "sha256_zip": "s"},
        "modelo": {"tipo": "t", "parametros": {}, "sklearn_version": "1", "semilla": 1,
                   "n_entrenamiento": 1, "sha256_joblib": "j"},
        "variables": [{"nombre": "age", "tipo": "numerica", "protegida": False},
                      {"nombre": "sex", "tipo": "categorica", "protegida": True}],
        "proteccion": {"nombre": "sex", "supervisado": "Female", "referencia": "Male"},
        "etiqueta": {}, "exportacion_onnx": {"disponible": False}, "politica_vigilancia": {},
        "rendimiento_linea_base": {"n": 1, "auroc": 0.9, "accuracy": 0.8, "prevalencia": 0.2,
                                   "tasa_favorable_por_grupo": {}},
    }
    doc = construir_html(ficha)
    assert "Entrada del modelo" in doc and "pestaña «Umbrales»" in doc
    assert "«Configurar»" not in doc
    assert "<td>sex</td><td>categorica</td><td>Sí</td><td>No</td>" in doc


def test_error_del_onnx_dice_como_se_corrige():
    """El error de una columna sin entrada indica rehacer el mapeo."""
    class _Entrada:
        def __init__(self, nombre: str) -> None:
            self.name, self.type = nombre, "tensor(float)"

    class _Sesion:
        def get_inputs(self):
            return [_Entrada("age")]

    with pytest.raises(ModeloEjecutableInvalido) as exc:
        build_artifact_inputs(_Sesion(), ["age", "sex"])  # type: ignore[arg-type]
    texto = str(exc.value)
    assert "sex" in texto and "Reiniciar despliegue" in texto and "mapeo" in texto


def test_revision_rapida_explica_que_no_lee_el_dossier():
    """La pantalla de lanzar la revisión avisa de que la rápida es una lista fija."""
    fuente = _leer("frontend/src/pages/auditoria/LanzarRevision.tsx")
    assert "lista de comprobación fija" in fuente and "no lee lo que escribiste" in fuente


def test_informe_sigue_aislado_en_iframe_y_enlace_externo():
    """El recuadro conserva `sandbox` y el enlace a pestaña nueva sigue ahí."""
    fuente = _leer("frontend/src/pages/auditoria/Informe.tsx")
    assert 'sandbox=""' in fuente and "Abrir en pestaña nueva" in fuente
