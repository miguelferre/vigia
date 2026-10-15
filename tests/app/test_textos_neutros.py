"""Texto neutro en el backend, el simulador, el MCP y la CLI.

Decisiones de producto: el caso de demo Digestivo se queda como ejemplo
de sanidad; todo lo demás del producto habla para cualquier sector. Las claves
(`clinician_pseudonym`, `criterio_clinico`, rol `clinico`, `cribado_retrospectivo`)
no cambian: solo la etiqueta que se ve.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd

import vigia
from vigia.app import models
from vigia.app.schemas.projects import MENSAJE_SIM_LOGISTIC
from vigia.app.services import alerting, plantillas_datos, projects, settings
from vigia.core import schema
from vigia.human import cross_alerts
from vigia.sim.scenarios import SCENARIOS

RAIZ = Path(__file__).resolve().parents[2]
CODIGO = RAIZ / "src" / "vigia"

# Texto que no debe llegar a nadie fuera de la demo de sanidad. `clinician` (clave) no entra.
PROHIBIDO = re.compile(
    r"(?<!criterio_)cl[ií]nic(?!ian)|pacientes?\b|\bderivar\b|derivaci[oó]n|derivan siempre|"
    r"cribado(?!_retrospectivo)|tasa_derivacion|sanitari|hospital|"
    r"no (?:es )?un diagn[oó]stico|no es un diagn|Diagn[oó]stico de alerta|d[ií]as de estancia",
    re.IGNORECASE,
)

# Módulos que cuentan la historia del caso de demo (reumatología / Digestivo) o usan la
# palabra con otro sentido (`derivación` de un estado, `diagnóstico` de una columna CIAP-2).
EXENTOS = {
    "sim/__init__.py", "sim/model.py", "sim/generators.py", "sim/human.py", "sim/serialize.py",
    "app/services/demo_files.py",   # columnas CIAP-2 de la demo, con su nombre original
    "app/services/protocol_steps.py",  # «derivación» de un estado, no una derivación clínica
    "core/explain.py",  # `diagnóstico no presente`: columna CIAP-2 de la demo
}


def _docstrings(arbol: ast.AST) -> set[int]:
    ids: set[int] = set()
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            cuerpo = n.body
            if cuerpo and isinstance(cuerpo[0], ast.Expr):
                v = getattr(cuerpo[0], "value", None)
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    ids.add(id(v))
    return ids


def _cadenas_con_texto(ruta: Path):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and " " in n.value:
            yield n.lineno, n.value


def _ficheros():
    for p in sorted(CODIGO.rglob("*.py")):
        rel = p.relative_to(CODIGO).as_posix()
        if rel.startswith(("content/", "static/", "human/_vendor/")) or rel in EXENTOS:
            continue
        yield rel, p


def test_ninguna_cadena_ni_docstring_del_backend_habla_de_sanidad():
    """Cadenas y docstrings (los de rutas y tools salen en OpenAPI y en el MCP) sin vocabulario clínico."""
    infracciones = []
    for rel, p in _ficheros():
        for linea, texto in _cadenas_con_texto(p):
            m = PROHIBIDO.search(texto)
            if m:
                infracciones.append(f"{rel}:{linea}: {m.group(0)!r}")
    # Las del caso de demo se admiten por su nombre propio, no por estas palabras.
    assert not infracciones, "\n".join(infracciones)


def test_los_titulos_y_relatos_de_los_guiones_son_neutros():
    texto = []
    for esc in SCENARIOS.values():
        texto += [esc.title, esc.description]
        for fase in esc.phases:
            texto += [fase.title, fase.narrative or ""]
    plano = "\n".join(texto)
    assert not PROHIBIDO.search(plano), PROHIBIDO.search(plano)
    assert "Evento E2: protocolo nuevo" in plano
    assert "salud" not in SCENARIOS["consejeria_regional"].title.lower()
    # La identidad del caso de demo se queda.
    assert SCENARIOS["caso_digestivo"].title == "Caso Digestivo"


def test_el_titulo_de_la_fase_e2_dice_protocolo_nuevo():
    e2 = next(f for f in SCENARIOS["timeline_completo"].phases if f.key == "e2_evento")
    assert e2.title == "Evento E2: protocolo nuevo"


def test_la_accion_retrospectiva_cambia_de_etiqueta_pero_no_de_clave():
    assert alerting.ETIQUETAS_ACCION["cribado_retrospectivo"] == "Revisión retrospectiva"
    assert "cribado_retrospectivo" in models.ACCIONES_ALERTA


def test_los_protocolos_de_alerta_usan_texto_neutro():
    for clave, texto in projects._PROTOCOLOS.items():
        assert not PROHIBIDO.search(texto), (clave, texto)
    assert "Contener (revisión retrospectiva)" in projects._PROTOCOLOS["cross"]
    assert "criterio del responsable" in projects._PROTOCOLOS["explain"]
    assert "Escalar al responsable si persiste" in projects._PROTOCOLOS["fairness"]


def test_las_claves_de_los_origenes_y_del_rol_no_cambian():
    assert "criterio_clinico" in projects._ORIGENES_DE_PERSONA
    assert "clinico" in settings.ROLES
    assert "criterio_clinico" in schema.ThresholdOrigen.__args__


def test_la_plantilla_de_resultados_usa_tasa_decision_correcta():
    csv = plantillas_datos._OUTCOMES
    assert "tasa_decision_correcta" in csv
    assert "tasa_derivacion_correcta" not in csv


def test_los_motivos_de_las_cruzadas_hablan_de_la_decision_favorable():
    for pos_g, pos_c in ((1, 2), (9, 2), (2, 9), (9, 9)):
        m = cross_alerts._motivo_positivos_insuficientes(pos_g, pos_c, 5)
        assert "necesitaban la decisión favorable" in m, m
        assert not PROHIBIDO.search(m), m


def _uso(n_a: int, n_b: int, ov_a: int, ov_b: int) -> pd.DataFrame:
    filas = []
    for prof, n, ov in (("p-1", n_a, ov_a), ("p-2", n_b, ov_b)):
        for i in range(n):
            filas.append({
                "clinician_pseudonym": prof,
                "model_output": 1,
                "human_decision": 0 if i < ov else 1,
                "ground_truth": 1,
                "subgroup": "a",
            })
    return pd.DataFrame(filas)


def test_los_motivos_de_cx5_nombran_profesionales():
    config = cross_alerts.CrossConfig()
    una_sola, _ = cross_alerts._cx5(_uso(40, 3, 5, 1), config=config)
    assert "profesionales con al menos" in una_sola.motivo
    ninguno_varia, _ = cross_alerts._cx5(_uso(40, 40, 0, 0), config=config)
    assert "profesionales cualificados coinciden" in ninguno_varia.motivo
    pocas, _ = cross_alerts._cx5(_uso(31, 31, 1, 0), config=config)
    assert "profesionales cualificados" in pocas.motivo
    _, alerta = cross_alerts._cx5(_uso(60, 60, 55, 3), config=config)
    assert alerta is not None and "profesionales muestran patrones" in alerta.motivo
    for texto in (una_sola.motivo, ninguno_varia.motivo, alerta.motivo):
        assert not PROHIBIDO.search(texto), texto
    assert una_sola.extra["n_clinicos"] == 1  # la clave de `extra` no cambia


def test_la_cli_y_el_paquete_hablan_de_modelos_en_produccion():
    assert "modelos de IA en producción" in vigia.__doc__
    fuente = (CODIGO / "cli.py").read_text(encoding="utf-8")
    assert "IA clínica" not in fuente
    assert "vigilancia de modelos de IA en producción" in fuente


def test_los_textos_de_deskilling_no_dicen_diagnostico():
    for modulo in ("deskilling_texto.py", "ir_adapter.py"):
        fuente = (CODIGO / "human" / modulo).read_text(encoding="utf-8")
        assert "no es una conclusión" in fuente or "no una conclusión" in fuente
        # La clave inglesa del paquete original conserva su «not a diagnosis»: no cuenta.
        sin_ingles = re.sub(r'"[^"\n]*not a diagnosis[^"\n]*"', "", fuente)
        assert "un diagnóstico" not in sin_ingles, modulo


def test_el_prompt_de_alerta_se_llama_analisis_y_conserva_su_clave():
    fuente = (CODIGO / "mcp" / "prompts.py").read_text(encoding="utf-8")
    assert '@mcp.prompt(title="Análisis de alerta")' in fuente
    assert "async def diagnostico_de_alerta(" in fuente


def test_el_mensaje_del_modelo_simulado_sigue_nombrando_los_dominios_de_la_demo():
    assert "reuma, digestivo" in MENSAJE_SIM_LOGISTIC
