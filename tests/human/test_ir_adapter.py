"""Tests de `vigia.human.ir_adapter`: `records_from_db` filtra
antes de construir `telemetry.Record` y nunca mezcla `model_version_id`; el
signal de deskilling se afirma sobre diarios simulados con
`sim.human.simulate_decisions` (mismo patrón que `tests/human/test_cross_alerts.py`).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from vigia.app.models import UsageLog
from vigia.human._vendor.interaction_review.telemetry import (
    Trends,
    compute_trends,
    compute_windows,
    deskilling_signal,
)
from vigia.human.ir_adapter import _records_and_excluded, deskilling_reason_es, records_from_db
from vigia.sim.generators import generate_baseline, score_dataframe
from vigia.sim.human import HumanParams, simulate_decisions
from vigia.sim.serialize import feedback_dict

START = date(2026, 1, 5)

# Mismo mapeo entero/etiqueta que `human_layer._INT_TO_LABEL` (human_layer.py:59).
_LABEL_TO_INT = {"refer": 1, "no-refer": 0}


def _labeled(df_scored: pd.DataFrame, seed: int, accuracy_target: float) -> pd.DataFrame:
    df_scored = df_scored.reset_index(drop=True)
    fb = feedback_dict(df_scored, seed=seed, accuracy_target=accuracy_target)
    idx = fb["fields"].index("Has_Referral_in_Window")
    df_scored["Has_Referral_in_Window"] = [row[idx] for row in fb["values"]]
    return df_scored


def _usage_df(seed: int, params: HumanParams, *, n: int = 900, days: int = 140) -> pd.DataFrame:
    df = score_dataframe(generate_baseline(n=n, seed=seed), seed=seed)
    df = _labeled(df, seed=seed, accuracy_target=0.85)
    return simulate_decisions(df, seed=seed, params=params, start_date=START, days=days)


def _rows_from_usage_df(df: pd.DataFrame, *, project_id: int, model_version_id: int) -> list[UsageLog]:
    """Convierte el DataFrame de `simulate_decisions` (etiquetas del harness) en
    filas `UsageLog` (enteros), como hace `human_layer.ingest_usage_log`."""
    return [
        UsageLog(
            project_id=project_id,
            model_version_id=model_version_id,
            date=str(row["date"]),
            clinician_pseudonym=row["clinician_pseudonym"],
            subgroup=row["subgroup"],
            human_decision=_LABEL_TO_INT[row["human_decision"]],
            model_output=_LABEL_TO_INT[row["model_output"]],
            ground_truth=_LABEL_TO_INT[row["ground_truth"]],
            record_seq=int(row["record_seq"]),
        )
        for _, row in df.iterrows()
    ]


def test_signal_fired_true_con_convergencia_y_rescate_a_la_baja():
    """`override_base` y `automation_bias` altos: el humano deja de corregir al
    modelo a medida que avanza el periodo (converge) y el rescate cae."""
    params = HumanParams(override_base=0.3, automation_bias=3.0, rescue_skill=8.0)
    df = _usage_df(seed=42, params=params)
    filas = _rows_from_usage_df(df, project_id=1, model_version_id=1)

    records = records_from_db(filas)
    assert len(records) == len(filas)

    windows = compute_windows(records, n_windows=4)
    trends = compute_trends(windows)
    signal = deskilling_signal(trends)

    assert signal.fired is True
    assert trends.agreement_slope is not None and trends.agreement_slope > 0.02
    assert trends.rescue_slope is not None and trends.rescue_slope < 0


def test_signal_fired_false_con_datos_sin_tendencia():
    """`HumanParams()` por defecto: sin sesgo de automatización, no hay
    convergencia sistemática entre ventanas."""
    params = HumanParams()
    df = _usage_df(seed=1, params=params)
    filas = _rows_from_usage_df(df, project_id=1, model_version_id=1)

    records = records_from_db(filas)
    windows = compute_windows(records, n_windows=4)
    trends = compute_trends(windows)
    signal = deskilling_signal(trends)

    assert signal.fired is False


def test_records_from_db_nunca_ve_la_otra_version():
    """`records_from_db` no filtra por versión: quien llama ya ha limitado
    `rows` a una sola. Se comprueba pasando solo las filas de una
    versión, aunque el diario tenga dos, y afirmando la longitud exacta."""
    params = HumanParams()
    df_v1 = _usage_df(seed=5, params=params, n=40, days=20)
    df_v2 = _usage_df(seed=6, params=params, n=25, days=20)
    filas_v1 = _rows_from_usage_df(df_v1, project_id=1, model_version_id=1)
    filas_v2 = _rows_from_usage_df(df_v2, project_id=1, model_version_id=2)

    # El "diario" completo del proyecto mezcla las dos versiones; quien llama
    # (deskilling_view) ya filtra por `model_version_id` antes de invocar.
    solo_v1 = [f for f in (filas_v1 + filas_v2) if f.model_version_id == 1]
    assert len(solo_v1) == len(filas_v1)

    records = records_from_db(solo_v1)
    assert len(records) == len(filas_v1)


def test_records_from_db_filtra_por_clinician_y_subgroup():
    filas = [
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="2026-01-05",
            clinician_pseudonym="clin-01",
            subgroup="18-35",
            human_decision=1,
            model_output=1,
            ground_truth=1,
        ),
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="2026-01-06",
            clinician_pseudonym="clin-02",
            subgroup="36-75",
            human_decision=0,
            model_output=1,
            ground_truth=0,
        ),
    ]
    solo_clin01 = records_from_db(filas, clinician="clin-01")
    assert len(solo_clin01) == 1
    assert solo_clin01[0].human == "refer"

    solo_36_75 = records_from_db(filas, subgroup="36-75")
    assert len(solo_36_75) == 1
    assert solo_36_75[0].model == "refer"


def test_records_from_db_descarta_decisiones_nulas():
    filas = [
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="2026-01-05",
            human_decision=None,
            model_output=1,
            ground_truth=1,
        ),
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="2026-01-06",
            human_decision=1,
            model_output=None,
            ground_truth=1,
        ),
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="2026-01-07",
            human_decision=1,
            model_output=0,
            ground_truth=None,
        ),
    ]
    records = records_from_db(filas)
    assert len(records) == 1
    assert records[0].truth is None


def test_records_from_db_excluye_fecha_no_iso_en_vez_de_romper():
    """Antes, `date_cls.fromisoformat(f.date)` sin `try` daba
    `ValueError` crudo (500 en `GET /deskilling`). Defensa en profundidad:
    `POST /usage-logs/upload` ya normaliza la fecha a ISO (`services/
    human_layer._normalize_date`), así que esto solo cubre una fila que
    llegase a `usage_log` con una fecha que no lo sea (dato antiguo,
    importado por otra vía); se excluye, no rompe el resto del cálculo."""
    filas = [
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="2026-01-05",
            human_decision=1,
            model_output=1,
            ground_truth=1,
        ),
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="05/01/2026",  # fecha española, no ISO: no debería llegar
            # aquí desde la subida (se normaliza antes), pero si lo hace no
            # debe romper `records_from_db`.
            human_decision=1,
            model_output=0,
            ground_truth=1,
        ),
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="no es una fecha",
            human_decision=0,
            model_output=0,
            ground_truth=0,
        ),
    ]
    records = records_from_db(filas)
    assert len(records) == 1
    assert records[0].human == "refer"


def test_records_and_excluded_cuenta_las_filas_de_fecha_invalida():
    """`_records_and_excluded` (que usa `deskilling_view`) cuenta lo que
    `records_from_db` descarta en silencio, para que la API pueda decirlo
   ."""
    filas = [
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="2026-01-05",
            human_decision=1,
            model_output=1,
            ground_truth=1,
        ),
        UsageLog(
            project_id=1,
            model_version_id=1,
            date="fecha-mala",
            human_decision=1,
            model_output=0,
            ground_truth=1,
        ),
    ]
    records, excluidas = _records_and_excluded(filas, clinician=None, subgroup=None)
    assert len(records) == 1
    assert excluidas == 1


# --- Corrección, hallazgo 2: catálogo de `deskilling_reason_es` ------------


def test_deskilling_reason_es_traduce_las_seis_cadenas_del_catalogo_cerrado():
    """`_DESKILLING_REASON_ES` cubre todo lo que puede devolver
    `telemetry.deskilling_signal` (catálogo cerrado, `telemetry.py:189-211`):
    ninguna cadena traducida lleva texto en inglés y ninguna coincide con la
    original."""
    combinaciones_trends = [
        Trends(agreement_slope=None, human_accuracy_slope=0.0, model_accuracy_slope=0.0, rescue_slope=0.0),
        Trends(agreement_slope=0.1, human_accuracy_slope=-0.1, model_accuracy_slope=0.0, rescue_slope=0.0),
        Trends(agreement_slope=0.1, human_accuracy_slope=0.1, model_accuracy_slope=0.0, rescue_slope=-0.1),
        Trends(agreement_slope=0.1, human_accuracy_slope=-0.1, model_accuracy_slope=0.0, rescue_slope=-0.1),
        Trends(agreement_slope=-0.1, human_accuracy_slope=0.0, model_accuracy_slope=0.0, rescue_slope=0.0),
        Trends(agreement_slope=0.1, human_accuracy_slope=0.1, model_accuracy_slope=0.0, rescue_slope=0.1),
    ]
    for trends in combinaciones_trends:
        signal = deskilling_signal(trends, eps=0.02)
        traducido = deskilling_reason_es(signal.reason)
        assert traducido != signal.reason
        assert signal.reason not in traducido
        for fragmento_en in ("Human and model", "Investigate;", "Insufficient windows", "holds."):
            assert fragmento_en not in traducido


def test_deskilling_reason_es_no_deja_pasar_ingles_si_el_paquete_cambia_el_texto():
    """Defensa en profundidad: una cadena fuera del catálogo (paquete
    actualizado) da un motivo genérico en español, nunca la original."""
    generico = deskilling_reason_es("Some brand new english text from a future version.")
    assert "Some brand new english text" not in generico
    assert "revisar la versión" in generico
