"""scenarios — Guiones de demo (`timeline_completo`, `consejeria_regional`,
`caso_digestivo`) como datos.

Cada `Scenario` es una secuencia de `Phase` inmutables: qué generador y
parámetros usar, qué enlatado de `data/demo` corresponde y qué estado se
espera por monitor. `materialize_phase` produce el frame puntuado y los
dos JSON (payload/feedback) de una fase, ya sea leyendo el enlatado o
llamando al generador — la reproducción por SSE y la persistencia son de
Aquí solo hay datos y una función pura.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from . import generators as gen
from . import serialize as ser

__all__ = [
    "SCENARIOS",
    "Phase",
    "PhaseData",
    "Scenario",
    "baseline_phase",
    "demo_data_dir",
    "fecha_simulada_fase",
    "get_scenario",
    "list_scenarios",
    "materialize_phase",
    "phase_sequence",
]

VAR_DATOS_DEMO = "VIGIA_DEMO_DATA"


def _candidatos_datos_demo() -> list[Path]:
    """Rutas donde puede vivir `data/demo`, en orden de preferencia."""
    candidatos: list[Path] = []
    crudo = os.environ.get(VAR_DATOS_DEMO, "").strip()
    if crudo:
        candidatos.append(Path(crudo).expanduser())
    aqui = Path(__file__).resolve()
    # Instalado: los datos viajan dentro del paquete (vigia/data/demo).
    candidatos.append(aqui.parents[1] / "data" / "demo")
    # En el repositorio: <raíz>/data/demo, la fuente (datos sintéticos).
    candidatos.append(aqui.parents[3] / "data" / "demo")
    return candidatos


def demo_data_dir() -> Path:
    """Carpeta con los datos enlatados de la demo.

    Prueba en orden la variable de entorno `VIGIA_DEMO_DATA`, la copia incluida
    en el paquete por el `force-include` del wheel y la carpeta del repositorio.
    Si ninguna existe, falla listando las rutas probadas: `parents[3]` a secas
    resolvía a `Lib/data/demo` dentro del paquete y la demo moría con un
    `FileNotFoundError` sin contexto.
    """
    candidatos = _candidatos_datos_demo()
    for candidato in candidatos:
        if candidato.is_dir():
            return candidato
    probadas = "\n".join(f"  - {c}" for c in candidatos)
    raise FileNotFoundError(
        "no se encuentran los datos enlatados de la demo (data/demo).\n"
        f"Rutas probadas:\n{probadas}\n"
        f"Fija {VAR_DATOS_DEMO} con la carpeta que los contiene."
    )

_MOTIVO_REORDER = (
    "reordenado por el harness con reorder_for_fairness_window para que la "
    "ventana de últimos 200 no dispare equidad"
)


@dataclass(frozen=True)
class Phase:
    key: str
    title: str
    kind: Literal["baseline", "evento", "recovery"]
    generator: str
    params: dict[str, Any]
    label_accuracy: float | None
    model_version: str
    freeze_baseline: bool
    canned: tuple[str, str] | None
    orden_manipulado: bool
    motivo_manipulacion: str | None
    reorder: dict[str, Any] | None
    expected: dict[str, str]
    explain_global: bool = False
    narrative: str = ""
    # Solo `caso_digestivo` lo declara (`b1` seis semanas atrás …
    # `e1_recovery` hoy); `None` en los guiones antiguos, que siguen con
    # `now_iso()` real al ingerir. Ver `fecha_simulada_fase`.
    semanas_atras: int | None = None


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    domain: str
    description: str
    phases: tuple[Phase, ...]
    default_params: dict[str, Any] = field(default_factory=dict)
    # Umbrales inferiores de calidad que el
    # atado/la creación fijan en el proyecto de la demo antes de evaluar,
    # para que el monitor de calidad quede en correcto en todas las fases
    # del guion (`app.services.demo_adoptar._fijar_umbral_calidad_demo`).
    # `None` en los guiones antiguos, que no cambian.
    umbrales_calidad: dict[str, float] | None = None
    # Parámetros de la simulación humana propios del
    # guion (`vigia.sim.human.HumanParams`), base sobre la que se aplica el
    # `params_override["human"]` que mande quien reproduce. Con `{}` (los
    # guiones antiguos) el comportamiento es el de siempre.
    human_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhaseData:
    phase: Phase
    df_scored: pd.DataFrame
    payload: dict[str, Any]
    feedback: dict[str, Any]
    permutation: np.ndarray | None
    source: Literal["canned", "generate"]


_GENERATORS: dict[str, Callable[..., Any]] = {
    "e1_baseline": gen.generate_e1_baseline,
    "e1_event": gen.generate_e1_event,
    "e1_recovery": gen.generate_e1_recovery,
    "e2_event": gen.generate_e2_event,
    "e2_recovery": gen.generate_e2_recovery,
}


# ---------------------------------------------------------------------------
# Guion timeline_completo — 9 fases: 5 baselines, evento E1, recovery E1,
# evento E2, recovery E2.
# ---------------------------------------------------------------------------

_B1 = Phase(
    key="b1",
    title="Baseline 1",
    kind="baseline",
    generator="e1_baseline",
    params={"seed": 7000},
    label_accuracy=0.88,
    model_version="v1",
    freeze_baseline=True,
    canned=("escenario_1/01_baseline_payload.json", "escenario_1/01_baseline_feedback.json"),
    orden_manipulado=False,
    motivo_manipulacion=None,
    reorder=None,
    expected={"fairness": "ok", "quality": "ok", "drift": "ok"},
    # Timeline_completo es el guion del
    # onboarding y su escena 1 («cinco semanas en verde, explicabilidad
    # global >= 0,99») necesita explicabilidad en las cinco baselines, no
    # solo en la primera. Medido con build/demo_local.py:
    # ~450 filas y 41 features por permutación no mueve el total de forma
    # apreciable, así que se activa en las cinco (b1 fija la referencia).
    explain_global=True,
    narrative=(
        "Primera subida de referencia: reparto demográfico y de decisión favorable "
        "dentro de rango en los tres monitores."
    ),
)

_BASELINES = tuple(
    replace(_B1, key=f"b{i}", title=f"Baseline {i}", freeze_baseline=False) for i in range(2, 6)
)
_BASELINES = (_B1,) + _BASELINES

_E1_EVENTO = Phase(
    key="e1_evento",
    title="Evento E1: sesgo por edad",
    kind="evento",
    generator="e1_event",
    params={"seed": 1001, "frac_young": 0.33, "bias_additive": 1.1},
    label_accuracy=0.86,
    model_version="v1",
    freeze_baseline=False,
    canned=("escenario_1/02_evento_payload.json", "escenario_1/02_evento_feedback.json"),
    orden_manipulado=False,
    motivo_manipulacion=None,
    reorder=None,
    expected={"fairness": "alerta", "quality": "ok"},
    narrative=(
        "El modelo penaliza a las personas de 18 a 35 años: la ventana "
        "fairness dispara alerta mientras quality sigue en verde."
    ),
)

_E1_RECOVERY = Phase(
    key="e1_recovery",
    title="Recovery E1",
    kind="recovery",
    generator="e1_recovery",
    params={"seed": 7003},
    label_accuracy=0.88,
    model_version="v1",
    freeze_baseline=False,
    canned=("escenario_1/03_recovery_payload.json", "escenario_1/03_recovery_feedback.json"),
    orden_manipulado=False,
    motivo_manipulacion=None,
    reorder=None,
    expected={"fairness": "ok", "quality": "ok", "drift": "ok"},
    narrative="Un batch limpio desplaza la ventana del evento: los tres monitores vuelven a OK.",
)

_E2_EVENTO = Phase(
    key="e2_evento",
    title="Evento E2: protocolo nuevo",
    kind="evento",
    generator="e2_event",
    params={"seed": 3003},
    label_accuracy=None,
    model_version="v1",
    freeze_baseline=False,
    canned=("escenario_2/02_evento_payload.json", "escenario_2/02_evento_feedback.json"),
    orden_manipulado=True,
    motivo_manipulacion=_MOTIVO_REORDER,
    reorder={"window_size": 200, "target_young": 30, "target_pos_young": 5, "seed": 3003},
    expected={"quality": "alerta", "fairness": "ok"},
    narrative=(
        "El protocolo cambia (L88.01/L18.01 pasan siempre a la decisión favorable) y el modelo, "
        "aún con el peso antiguo, cae en quality; fairness no se ve afectado."
    ),
)

_E2_RECOVERY = Phase(
    key="e2_recovery",
    title="Recovery E2",
    kind="recovery",
    generator="e2_recovery",
    params={"seed": 7777},
    label_accuracy=0.92,
    model_version="v2",
    freeze_baseline=True,
    canned=("escenario_2/03_recovery_payload.json", "escenario_2/03_recovery_feedback.json"),
    orden_manipulado=True,
    motivo_manipulacion=_MOTIVO_REORDER,
    reorder={"window_size": 200, "target_young": 30, "target_pos_young": 5, "seed": 7777},
    expected={"quality": "ok", "fairness": "ok"},
    narrative=(
        "El modelo v2, ya reentrenado con el protocolo nuevo, recupera accuracy "
        "por encima del umbral."
    ),
)

_TIMELINE_DEFAULT_PARAMS: dict[str, Any] = {
    "bias_additive": 1.1,
    # `frac_young` unifica el control que antes vivía repartido
    # como `frac_young` (evento) y `young_frac` (baseline/recovery) en
    # `sim/generators.py`; un único nombre, una única entrada aquí.
    "frac_young": 0.33,
    "label_accuracy": 0.86,
    "min_records": 200,
}

_TIMELINE_COMPLETO = Scenario(
    key="timeline_completo",
    title="Timeline completo",
    domain="reuma",
    description=(
        "Guion largo de demo: cinco baselines, el evento de sesgo por edad de "
        "escenario 1 con su recovery, y el evento de protocolo nuevo de "
        "escenario 2 con su recovery en el modelo v2."
    ),
    phases=_BASELINES + (_E1_EVENTO, _E1_RECOVERY, _E2_EVENTO, _E2_RECOVERY),
    default_params=_TIMELINE_DEFAULT_PARAMS,
)


# ---------------------------------------------------------------------------
# Guion consejeria_regional — 6 fases: 5 baselines con explicabilidad global,
# un evento; sin recovery.
# ---------------------------------------------------------------------------

_CM_BASELINES = tuple(replace(p, explain_global=True) for p in _BASELINES)

_CONSEJERIA_REGIONAL = Scenario(
    key="consejeria_regional",
    title="Caso regional",
    domain="reuma",
    description=(
        "Guion corto de introducción: cinco baselines con "
        "explicabilidad global y el evento de sesgo por edad, sin recovery."
    ),
    phases=_CM_BASELINES + (_E1_EVENTO,),
    default_params=_TIMELINE_DEFAULT_PARAMS,
)

# ---------------------------------------------------------------------------
# Guion caso_digestivo — 7 fases: cinco semanas de línea base (b1 congela,
# b2..b5 en papel producción, igual que timeline_completo) más el evento de
# escenario 1 y su recovery.
# Reutiliza _BASELINES tal cual (misma tupla que timeline_completo: b2..b5 ya
# heredan explain_global=True de _B1 por el replace() de más arriba) y solo
# añade `semanas_atras` para la fecha simulada de cada fase: b1 seis
# semanas atrás … e1_recovery hoy. _E1_EVENTO/_E1_RECOVERY sí necesitan el
# replace() de explain_global (False por defecto en timeline_completo).
# ---------------------------------------------------------------------------

_CASO_DIGESTIVO_BASELINES = tuple(
    replace(p, semanas_atras=6 - i) for i, p in enumerate(_BASELINES)
)
_CASO_DIGESTIVO_EVENTO = replace(_E1_EVENTO, explain_global=True, semanas_atras=1)
_CASO_DIGESTIVO_RECOVERY = replace(_E1_RECOVERY, explain_global=True, semanas_atras=0)

_CASO_DIGESTIVO_PHASES = _CASO_DIGESTIVO_BASELINES + (
    _CASO_DIGESTIVO_EVENTO,
    _CASO_DIGESTIVO_RECOVERY,
)

# Umbrales inferiores de calidad elegidos
# para que las 13 métricas de `DEFAULT_QUALITY_THRESHOLDS` (core/thresholds.py)
# den `ok` (nunca `aviso` ni `alerta`, banda del 10 % incluida) en las siete
# fases de `caso_digestivo`; verificado con `core.engine.run_scenario` sobre
# los valores reales del guion (el peor caso siempre es `e1_evento`). El resto
# de métricas de calidad (area_under_pr, precision, f1_measure,
# matthews_correlation_coefficient, false_positive_rate, log_loss,
# brier_score, label_skew) ya dan `ok` con el umbral por defecto y no se tocan.
_CASO_DIGESTIVO_UMBRALES_CALIDAD: dict[str, float] = {
    "accuracy": 0.75,
    "area_under_roc": 0.70,
    "true_positive_rate": 0.65,
    "recall": 0.65,
    "gini_coefficient": 0.50,
}

# El grupo de 18 a 35 años corrige al modelo la mitad de
# veces que el resto (`k_sub`, multiplicador de la probabilidad de override).
# Es la condición de override de CX-1, convergencia silenciosa; la de error
# del modelo la pone el propio evento E1 (FNR 0,617 en el grupo joven frente
# a 0,142 en el resto). Con los valores por defecto de `HumanParams` ninguna
# de las seis reglas cruzadas dispara en este guion (z de override 0,08). El
# valor está elegido con un barrido contra el motor real (0,25 a 0,65): con
# 0,5 la ventana acumulada de la línea base se queda en z = -2,68 (ninguna
# alerta cruzada en b1..b5, que es lo que el guion promete en el paso 5, «la
# tabla de alertas vacía») y el evento la lleva a z = -3,60, por debajo del
# umbral de -3,0: CX-1 abre alerta justo en el lote del evento, y en el de
# recuperación se le suma CX-6.
_CASO_DIGESTIVO_HUMAN_PARAMS: dict[str, Any] = {"k_sub": {"18-35": 0.5}}

_CASO_DIGESTIVO = Scenario(
    key="caso_digestivo",
    title="Caso Digestivo",
    domain="reuma",
    description=(
        "Guion de la demo guiada: cinco semanas de línea base de un "
        "servicio, un lote con cambio en la población atendida y el lote "
        "posterior a las medidas correctivas."
    ),
    phases=_CASO_DIGESTIVO_PHASES,
    default_params=_TIMELINE_DEFAULT_PARAMS,
    umbrales_calidad=_CASO_DIGESTIVO_UMBRALES_CALIDAD,
    human_params=_CASO_DIGESTIVO_HUMAN_PARAMS,
)

SCENARIOS: dict[str, Scenario] = {
    _TIMELINE_COMPLETO.key: _TIMELINE_COMPLETO,
    _CONSEJERIA_REGIONAL.key: _CONSEJERIA_REGIONAL,
    _CASO_DIGESTIVO.key: _CASO_DIGESTIVO,
}


# ---------------------------------------------------------------------------
# Registro y materialización
# ---------------------------------------------------------------------------


# Alias de lectura: una demo guardada con una clave antigua se
# reconoce por su huella (sha256 de la clave); la clave antigua se lee y nunca
# se escribe, ni se guarda su literal en el código.
_ALIAS_POR_HUELLA: dict[str, str] = {
    "c85069e45f4b3d4d548e98d975502f24d56c378c834ec62e86872c8f19170cfb": "consejeria_regional",
}


def clave_vigente(key: str) -> str:
    """Clave vigente de un guion: la misma si existe; la nueva si es una clave antigua conocida."""
    if key in SCENARIOS:
        return key
    return _ALIAS_POR_HUELLA.get(hashlib.sha256(key.encode("utf-8")).hexdigest(), key)


def get_scenario(key: str) -> Scenario:
    key = clave_vigente(key)
    try:
        return SCENARIOS[key]
    except KeyError as exc:
        claves = ", ".join(sorted(SCENARIOS))
        raise KeyError(f"guion {key!r} no existe; claves válidas: {claves}") from exc


def list_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "key": s.key,
            "title": s.title,
            "n_phases": len(s.phases),
            "description": s.description,
        }
        for s in SCENARIOS.values()
    ]


def phase_sequence(scenario: Scenario) -> list[tuple[int, Phase]]:
    return list(enumerate(scenario.phases))


def baseline_phase(scenario: Scenario, version: str) -> Phase | None:
    for p in scenario.phases:
        if p.model_version == version and p.freeze_baseline:
            return p
    return None


def _df_from_feedback(feedback: dict[str, Any]) -> pd.DataFrame:
    """Reconstruye `df_scored` desde un dict de feedback.

    Mismas columnas y mismo orden de filas que el feedback, más
    `PREDICTION`/`PROBABILITIES` (copias de `_original_prediction` y
    `_original_probability`) para que el frame quede puntuado.
    """
    df = pd.DataFrame(feedback["values"], columns=feedback["fields"])
    df["PREDICTION"] = df["_original_prediction"]
    df["PROBABILITIES"] = df["_original_probability"]
    return df


def _materialize_canned(phase: Phase, data_dir: Path | None) -> PhaseData:
    if phase.canned is None:
        raise ValueError(f"la fase {phase.key!r} no tiene datos enlatados (canned=None)")
    base = data_dir if data_dir is not None else demo_data_dir()
    payload_path = base / phase.canned[0]
    feedback_path = base / phase.canned[1]
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    feedback = json.loads(feedback_path.read_text(encoding="utf-8"))
    df_scored = _df_from_feedback(feedback)
    return PhaseData(
        phase=phase,
        df_scored=df_scored,
        payload=payload,
        feedback=feedback,
        permutation=None,
        source="canned",
    )


def _materialize_generate(phase: Phase, params_override: dict[str, Any] | None) -> PhaseData:
    params = {**phase.params, **(params_override or {})}
    seed = params.get("seed")
    generador = _GENERATORS[phase.generator]
    resultado = generador(**params)

    ground_truth_override: np.ndarray | None = None
    if phase.generator == "e1_event":
        df_scored, _is_young = resultado
    elif phase.generator == "e2_event":
        df_scored, ground_truth, _mask_new, _chosen_diags = resultado
        ground_truth_override = ground_truth
    else:
        df_scored = resultado

    payload = ser.payload_dict(df_scored)

    fb_kwargs: dict[str, Any] = {"seed": seed}
    if ground_truth_override is not None:
        fb_kwargs["ground_truth_override"] = ground_truth_override
    elif phase.label_accuracy is not None:
        fb_kwargs["accuracy_target"] = phase.label_accuracy
    feedback = ser.feedback_dict(df_scored, **fb_kwargs)

    permutation: np.ndarray | None = None
    if phase.orden_manipulado:
        reorder_params = dict(phase.reorder or {})
        permutation = ser.reorder_last_window(df_scored, **reorder_params)
        payload, feedback = ser.permute_dicts(payload, feedback, permutation)

    df_final = _df_from_feedback(feedback)
    return PhaseData(
        phase=phase,
        df_scored=df_final,
        payload=payload,
        feedback=feedback,
        permutation=permutation,
        source="generate",
    )


def materialize_phase(
    phase: Phase,
    *,
    source: Literal["canned", "generate"] = "canned",
    params_override: dict[str, Any] | None = None,
    data_dir: Path | None = None,
) -> PhaseData:
    if source == "canned":
        return _materialize_canned(phase, data_dir)
    if source == "generate":
        return _materialize_generate(phase, params_override)
    raise ValueError(f"source desconocido: {source!r} (usa 'canned' o 'generate')")


def fecha_simulada_fase(phase: Phase, *, ahora: datetime | None = None) -> str | None:
    """Fecha ISO de la fase con historia semanal, o `None` si no aplica.

    Solo las fases que declaran `semanas_atras` (`caso_digestivo`: `b1` seis
    semanas atrás … `e1_recovery` hoy) tienen fecha simulada; los guiones
    antiguos no lo declaran y sus lotes/evaluaciones siguen con `now_iso()`
    real, sin pasar por aquí. Es una función pura (sin sesión ni modelos de
    `app`, para que tanto `demo_player` como `demo_adoptar` la usen sin
    crear un ciclo de import entre ellos): siete llamadas seguidas en la
    misma reproducción real (segundos) producen siete fechas separadas por
    semanas completas porque `semanas_atras` cambia por fase, no porque el
    reloj avance. `ahora` solo existe para tests deterministas.
    """
    if phase.semanas_atras is None:
        return None
    base = ahora if ahora is not None else datetime.now(UTC)
    return (base - timedelta(weeks=phase.semanas_atras)).isoformat(timespec="microseconds")
