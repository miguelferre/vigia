"""CSV combinado de una fase de demo enlatada, para subirlo a mano.

`combined_csv_bytes` junta el payload y el feedback enlatados de la fase (ya
unidos en `PhaseData.df_scored` por `vigia.sim.scenarios.materialize_phase`,
que reconstruye el frame puntuado a partir del feedback) y los sirve con los
nombres reconocibles del formulario real: `id`, `timestamp`, `prediction`,
`probability` (escalar, el índice 1 de la lista de probabilidades) y `label`.
Las columnas clínicas viajan con su nombre original (`Age`, `Sex`,
`Previous_PC_episodes`, …), sin renombrar.

El mapeo automático de `services/ingest.py::_suggest_mapping` para un CSV
genérico no sirve para este fichero: nunca propone `feature_cols` y, si
detectara `Age` como atributo protegido, lo haría sin `unpriv_groups`/
`priv_groups` (el guardado del mapeo fallaría por grupos vacíos). En vez de
esconder `Age` renombrándola, `upload_mapping` calcula el mapeo real —el
mismo que usa el motor sobre el frame puntuado, con el atributo protegido y
sus grupos ya declarados— para que `GET /demo/scenarios` lo sirva y el
formulario de subida lo precargue: el usuario ve y confirma el grupo
supervisado (18 a 35 frente a 36 a 75) en vez de subir la línea base sin él.
"""

from __future__ import annotations

import io
from functools import lru_cache

import pandas as pd
from fastapi import HTTPException

from vigia.core.engine import _harness_scored_mapping
from vigia.sim.scenarios import Phase, Scenario, get_scenario, materialize_phase

__all__ = ["combined_csv_bytes", "upload_mapping"]

# Metadatos del harness que no aportan como columna del combinado: el id y la
# fecha ya salen bajo su propio nombre reconocible, y el resto son redundantes
# con `prediction`/`probability`/`label`.
_EXCLUIR = {
    "Patient_Id",
    "Episode_Window_Start",
    "Episode_Start_Date",
    "Episode_Id",
    "_original_prediction",
    "_original_probability",
    "Has_Referral_in_Window",
    "PREDICTION",
    "PROBABILITIES",
}


def _phase_for_download(scenario: Scenario, phase_key: str) -> Phase:
    for fase in scenario.phases:
        if fase.key == phase_key:
            if fase.canned is None:
                raise HTTPException(404, f"la fase {phase_key} no tiene fichero de ejemplo: elige otra fase")
            return fase
    claves = ", ".join(p.key for p in scenario.phases)
    raise HTTPException(
        404, f"la fase {phase_key} no existe en el guion {scenario.key}; las fases del guion son: {claves}"
    )


@lru_cache(maxsize=32)
def _combined_csv_cached(scenario_key: str, phase_key: str) -> bytes:
    try:
        scenario = get_scenario(scenario_key)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0] if exc.args else exc)) from exc
    phase = _phase_for_download(scenario, phase_key)
    phase_data = materialize_phase(phase, source="canned")
    df = phase_data.df_scored

    salida = pd.DataFrame(
        {
            "id": df["Episode_Id"],
            "timestamp": df["Episode_Start_Date"],
            "prediction": df["PREDICTION"].astype(int),
            "probability": [float(fila[1]) for fila in df["PROBABILITIES"]],
            "label": df["Has_Referral_in_Window"].astype(int),
        }
    )
    for columna in df.columns:
        if columna in _EXCLUIR:
            continue
        salida[columna] = df[columna].to_numpy()

    buffer = io.StringIO()
    salida.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def combined_csv_bytes(scenario_key: str, phase_key: str) -> bytes:
    """CSV combinado (bytes UTF-8) de la fase `phase_key` del guion `scenario_key`.

    404 si el guion o la fase no existen, o si la fase no tiene enlatado
    (`Phase.canned is None`, por ejemplo una fase de laboratorio). Cacheado en
    memoria por `(scenario_key, phase_key)` (`lru_cache`): es lectura pura,
    sin actor ni evento (§3.3). Los errores no se cachean, solo el resultado.
    """
    return _combined_csv_cached(scenario_key, phase_key)


def _combined_csv_columns(scenario_key: str, phase_key: str) -> list[str]:
    """Cabecera del CSV combinado ya servido (reutiliza la caché de `combined_csv_bytes`)."""
    contenido = _combined_csv_cached(scenario_key, phase_key)
    return list(pd.read_csv(io.BytesIO(contenido), nrows=0).columns)


def upload_mapping(scenario_key: str) -> dict:
    """Mapeo (forma de `core.schema.ColumnMapping`) que el formulario de subida
    debe precargar para el CSV combinado de la primera fase de `scenario_key`
    (ver docstring del módulo).

    Parte de `_harness_scored_mapping()` (el mapeo real que usa el motor sobre
    el frame puntuado: ya lleva `protected_attr_col="Age"` con sus grupos y
    los `feature_cols` del harness) y traduce las columnas de puntuación a las
    del CSV combinado: `prediction`, `probability` (escalar, índice 1),
    `label`, `id` y `timestamp`. `feature_cols` se filtra a las columnas que
    de verdad existen en ese CSV (hoy llegan las 41). El llamador
    (`GET /demo/scenarios`) solo invoca esto para guiones cuya primera fase
    tiene enlatado; con una fase sin enlatado, `_combined_csv_columns` propaga
    el 404 de `combined_csv_bytes`.
    """
    scenario = get_scenario(scenario_key)
    phase = scenario.phases[0]
    columnas = _combined_csv_columns(scenario_key, phase.key)
    base = _harness_scored_mapping()
    mapping = base.model_copy(
        update={
            "prediction_col": "prediction",
            "probability_col": "probability",
            "probability_format": "scalar",
            "probability_index": 1,
            "label_col": "label",
            "id_col": "id",
            "timestamp_col": "timestamp",
            "feature_cols": [c for c in base.feature_cols if c in columnas],
        }
    )
    return mapping.model_dump(mode="json")
