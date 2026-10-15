"""Tests de `vigia.human.cross_alerts`: sensibilidad y especificidad.

La sensibilidad se mide sobre la ventana ACUMULADA de la versión activa:
cinco baselines E1 más el evento E1, no una fase suelta. Ver el
docstring de `cross_alerts.py` para el porqué (potencia estadística).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from sqlmodel import Session, SQLModel, create_engine

from vigia.app.models import ModelVersion, Monitor, Project, UsageLog
from vigia.app.services.human_layer import cross_latest, evaluate_cross_for_project
from vigia.human import ir_adapter
from vigia.human._vendor.interaction_review.telemetry import Record as TelemetryRecord
from vigia.human._vendor.interaction_review.telemetry import (
    compute_trends,
    compute_windows,
    deskilling_signal,
)
from vigia.human.cross_alerts import (
    HUMAN_REVIEW_ZERO_MIN_N,
    CrossConfig,
    DeskillingInput,
    build_reference,
    evaluate_cross,
)
from vigia.sim.generators import (
    generate_baseline,
    generate_e1_baseline,
    generate_e1_event,
    score_dataframe,
)
from vigia.sim.human import HumanParams, simulate_decisions
from vigia.sim.serialize import feedback_dict

START = date(2026, 1, 5)


def _labeled(df_scored: pd.DataFrame, seed: int, accuracy_target: float) -> pd.DataFrame:
    df_scored = df_scored.reset_index(drop=True)
    fb = feedback_dict(df_scored, seed=seed, accuracy_target=accuracy_target)
    idx = fb["fields"].index("Has_Referral_in_Window")
    df_scored["Has_Referral_in_Window"] = [row[idx] for row in fb["values"]]
    return df_scored


def _baseline_usage(seed: int, n: int = 450) -> pd.DataFrame:
    df = score_dataframe(generate_baseline(n=n, seed=seed), seed=seed)
    df = _labeled(df, seed=seed, accuracy_target=0.88)
    return simulate_decisions(df, seed=seed, params=HumanParams(), start_date=START)


def _usage_con_sesgo(seed: int, bias: float, *, n: int = 900, days: int = 140) -> pd.DataFrame:
    """Diario de uso con `automation_bias=bias`: más días y más
    filas que `_baseline_usage` para que `compute_windows` (span de
    calendario, no de recuento) tenga ventanas con verdad de terreno de
    sobra incluso a sesgo alto."""
    df = score_dataframe(generate_baseline(n=n, seed=seed), seed=seed)
    df = _labeled(df, seed=seed, accuracy_target=0.88)
    return simulate_decisions(
        df, seed=seed, params=HumanParams(automation_bias=bias), start_date=START, days=days
    )


def _deskilling_input_from_df(df: pd.DataFrame, *, n_windows: int = 4) -> DeskillingInput:
    """Reconstruye `DeskillingInput` desde un diario en memoria por el mismo
    camino que `ir_adapter.deskilling_view` (ventanas, tendencias, señal de
    `interaction_review.telemetry`), sin base de datos: `level_z` se queda
    en `None`, lo rellena `evaluate_cross`."""
    records = [
        TelemetryRecord(
            date=date.fromisoformat(str(row["date"])),
            human=row["human_decision"],
            model=row["model_output"],
            truth=row["ground_truth"],
        )
        for _, row in df.iterrows()
    ]
    windows = compute_windows(records, n_windows=n_windows)
    trends = compute_trends(windows)
    signal = deskilling_signal(trends, eps=ir_adapter.EPS)
    return DeskillingInput(
        fired=signal.fired,
        agreement_slope=trends.agreement_slope,
        model_accuracy_slope=trends.model_accuracy_slope,
        rescue_slope=trends.rescue_slope,
        reason=signal.reason,
    )


def _sin_override(df: pd.DataFrame) -> pd.DataFrame:
    """Mismo diario, pero `human_decision` copia siempre `model_output`
    (cero overrides): fixture de `human_review_zero`."""
    d = df.copy()
    d["human_decision"] = d["model_output"]
    return d


def _e1_ventana_acumulada(params: HumanParams) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ventana acumulada E1: cinco baselines (el mismo batch
    `generate_e1_baseline()` etiquetado una vez, simulado con cinco
    semillas de decisión distintas sobre tramos horarios sucesivos) más el
    evento E1. Devuelve `(acumulado, usage_primer_baseline)`.
    """
    df_base = _labeled(generate_e1_baseline(), seed=7000, accuracy_target=0.88)
    frames: list[pd.DataFrame] = []
    primer_baseline: pd.DataFrame | None = None
    for i in range(5):
        usage = simulate_decisions(
            df_base,
            seed=10 + i,
            params=params,
            t_start=i / 6,
            t_end=(i + 1) / 6,
            start_date=START + timedelta(days=7 * i),
        )
        if i == 0:
            primer_baseline = usage
        frames.append(usage)

    df_event, _ = generate_e1_event()
    df_event = _labeled(df_event, seed=1001, accuracy_target=0.86)
    usage_event = simulate_decisions(
        df_event,
        seed=1,
        params=params,
        t_start=5 / 6,
        t_end=1.0,
        start_date=START + timedelta(days=35),
    )
    frames.append(usage_event)
    assert primer_baseline is not None
    return pd.concat(frames, ignore_index=True), primer_baseline


def test_cx1_dispara_ventana_acumulada_jovenes_con_sesgo():
    usage_acumulado, usage_primer_baseline = _e1_ventana_acumulada(
        HumanParams(k_sub={"18-35": 0.25})
    )
    reference = build_reference(usage_primer_baseline)

    resultado = evaluate_cross(
        usage_acumulado,
        reference=reference,
        mode="vigilancia",
        model_alert_groups={"18-35"},
    )
    reglas = {(a.rule, a.group) for a in resultado.alerts}
    assert ("CX-1", "18-35") in reglas
    assert ("CX-6", "18-35") not in reglas

    resultado_sin_modelo = evaluate_cross(
        usage_acumulado,
        reference=reference,
        mode="vigilancia",
        model_alert_groups=set(),
    )
    reglas_sin_modelo = {(a.rule, a.group) for a in resultado_sin_modelo.alerts}
    # Sin la exclusion del modelo, CX-6 se dispararia en 18-35 por
    # override, pero el grupo ya tiene CX-1 en esta evaluacion y CX-6 se calla ahi.
    assert ("CX-1", "18-35") in reglas_sin_modelo
    assert ("CX-6", "18-35") not in reglas_sin_modelo
    medida = next(
        m for m in resultado_sin_modelo.measurements if m.metric_key == "cx6_override_z:18-35"
    )
    assert medida.state.value == "ok"
    assert medida.extra["cubierta_por"] == "CX-1"


def test_cx1_no_dispara_ventana_acumulada_sin_sesgo_humano():
    """Mismo montaje, `HumanParams()` por defecto: la condición de FNR se
    cumple igual (el modelo sigue fallando más en 18-35) pero la de
    override no (sin sesgo humano no hay convergencia silenciosa) — CX-1 y
    CX-6 no disparan para ese grupo (z de override acumulado -1,31).
    """
    usage_acumulado, usage_primer_baseline = _e1_ventana_acumulada(HumanParams())
    reference = build_reference(usage_primer_baseline)

    resultado = evaluate_cross(
        usage_acumulado,
        reference=reference,
        mode="vigilancia",
        model_alert_groups={"18-35"},
    )
    reglas = {a.rule for a in resultado.alerts if a.group == "18-35"}
    assert "CX-1" not in reglas
    assert "CX-6" not in reglas


def test_cx1_evento_solo_no_dispara_pero_fnr_ya_es_alta():
    """Evento E1 solo (450 filas), `k_sub=0,25`: el override no acumula
    potencia suficiente (z = -1,74, no cruza -3.0) aunque la FNR ya
    muestre el daño real (z = 7,99). Deja constancia de por qué la ventana
    de CX-1 es la acumulada y no una fase suelta.
    """
    df_event, _ = generate_e1_event()
    df_event = _labeled(df_event, seed=1001, accuracy_target=0.86)
    usage_event = simulate_decisions(
        df_event, seed=1, params=HumanParams(k_sub={"18-35": 0.25}), start_date=START
    )
    df_base = _labeled(generate_e1_baseline(), seed=7000, accuracy_target=0.88)
    usage_base = simulate_decisions(df_base, seed=1, params=HumanParams(), start_date=START)
    reference = build_reference(usage_base)

    resultado = evaluate_cross(usage_event, reference=reference, mode="vigilancia")
    reglas = {a.rule for a in resultado.alerts if a.group == "18-35"}
    assert "CX-1" not in reglas

    medidas = {m.metric_key: m for m in resultado.measurements}
    override_z = medidas["cx1_override_z:18-35"]
    fnr_z = medidas["cx1_model_fnr_z:18-35"]
    assert override_z.value == pytest.approx(-1.74, abs=0.05)
    assert fnr_z.value == pytest.approx(7.99, abs=0.05)
    # Ambas condiciones son computables (n y positivos por encima de los
    # mínimos) pero CX-1 no dispara en conjunto: estado `ok`, no `alerta`.
    assert override_z.state == "ok"
    assert fnr_z.state == "ok"


def test_especificidad_20_semillas_sin_alertas():
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref)

    total_alertas = 0
    for s in range(1, 21):
        usage = _baseline_usage(seed=s)
        resultado = evaluate_cross(usage, reference=reference, mode="vigilancia")
        total_alertas += len(resultado.alerts)
    assert total_alertas == 0


# --- CX-2 y CX-3 contra la referencia del servicio -------
#
# La especificidad de CX-2/CX-3 se comprueba en un test propio, no ampliando
# `test_especificidad_20_semillas_sin_alertas`, porque ese test no conoce el
# estado de `quality` (aquí se pasa explícitamente `quality_state`, sin el
# cual ninguna de las dos reglas puede disparar). CX-4 (deskilling)
# tiene su propio bloque de tests más abajo: no
# depende de `df_usage` (solo de `n = len(df_usage)` para `CrossAlert.n`), así
# que su especificidad ya queda cubierta por
# `test_especificidad_20_semillas_sin_alertas` (deskilling por defecto es
# `None`, sin_datos, nunca alerta).


def test_especificidad_20_semillas_cx2_cx3_sin_alertas():
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref)

    falsos_cx2 = 0
    falsos_cx3 = 0
    for s in range(1, 21):
        usage = _baseline_usage(seed=s)
        resultado_alerta = evaluate_cross(
            usage, reference=reference, mode="vigilancia", quality_state="alerta"
        )
        falsos_cx2 += sum(1 for a in resultado_alerta.alerts if a.rule == "CX-2")

        resultado_ok = evaluate_cross(
            usage, reference=reference, mode="vigilancia", quality_state="ok"
        )
        medidas = {m.metric_key: m for m in resultado_ok.measurements}
        if medidas["cx3_override_z"].state == "aviso":
            falsos_cx3 += 1
    assert falsos_cx2 == 0
    assert falsos_cx3 == 0


def test_cx2_dispara_con_calidad_en_alerta_y_override_muy_por_encima_de_la_referencia():
    df = score_dataframe(generate_baseline(n=600, seed=31), seed=31)
    df = _labeled(df, seed=31, accuracy_target=0.88)
    usage_ref = simulate_decisions(df, seed=31, params=HumanParams(), start_date=START)
    reference = build_reference(usage_ref)

    usage_ventana = simulate_decisions(
        df, seed=32, params=HumanParams(override_base=0.35), start_date=START
    )

    resultado_alerta = evaluate_cross(
        usage_ventana, reference=reference, mode="vigilancia", quality_state="alerta"
    )
    assert any(a.rule == "CX-2" for a in resultado_alerta.alerts)

    # Con calidad `ok` no dispara aunque el override sea idéntico: falta la
    # primera condición (calidad en `alerta`).
    resultado_ok = evaluate_cross(
        usage_ventana, reference=reference, mode="vigilancia", quality_state="ok"
    )
    assert not any(a.rule == "CX-2" for a in resultado_ok.alerts)


def test_cx3_aviso_con_calidad_ok_override_alto_y_rescate_bajo_nunca_abre_alerta():
    df = score_dataframe(generate_baseline(n=1200, seed=41), seed=41)
    df = _labeled(df, seed=41, accuracy_target=0.88)
    usage_ref = simulate_decisions(
        df, seed=41, params=HumanParams(rescue_skill=8.0), start_date=START
    )
    reference = build_reference(usage_ref)

    usage_ventana = simulate_decisions(
        df, seed=42, params=HumanParams(override_base=0.30, rescue_skill=0.2), start_date=START
    )

    resultado_ok = evaluate_cross(
        usage_ventana, reference=reference, mode="vigilancia", quality_state="ok"
    )
    medidas = {m.metric_key: m for m in resultado_ok.measurements}
    assert medidas["cx3_override_z"].state == "aviso"
    assert medidas["cx3_rescue_z"].state == "aviso"
    assert medidas["cx3_rescue_z"].value < 0
    # CX-3 nunca abre `Alert`, tampoco cuando dispara.
    assert not any(a.rule == "CX-3" for a in resultado_ok.alerts)

    # Con calidad en `alerta` no dispara (falta la condición de calidad `ok`);
    # con el mismo montaje puede disparar CX-2, que sí es de este ámbito.
    resultado_alerta = evaluate_cross(
        usage_ventana, reference=reference, mode="vigilancia", quality_state="alerta"
    )
    medidas_alerta = {m.metric_key: m for m in resultado_alerta.measurements}
    assert medidas_alerta["cx3_override_z"].state != "aviso"


# --- CX-4 (deskilling) ------
#
# CX-4 no toca `df_usage` más que para `n` (recuento informativo en el
# `CrossAlert`): la señal la pasa el llamador ya calculada (`DeskillingInput`,
# forma propia sin tipos de `interaction_review`, §8.2). Los valores de cada
# test reproducen el patrón del ejemplo de `deskilling_signal`
# (`telemetry.py:191-214`): `agreement_slope` por encima de `eps=0.02` con
# `rescue_slope` cayendo por debajo de `-eps` dispara; con
# `model_accuracy_slope` por encima de `eps` y sin caída de rescate, se
# Bloquea.


def test_cx4_dispara_con_convergencia_y_rescate_cayendo():
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref)
    usage = _baseline_usage(seed=1)

    deskilling = DeskillingInput(
        fired=True,
        agreement_slope=0.06,
        model_accuracy_slope=-0.01,
        rescue_slope=-0.05,
        reason="Human and model are converging while the rescue rate is falling",
    )
    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia", deskilling=deskilling)
    assert any(a.rule == "CX-4" for a in resultado.alerts)
    medidas = {m.metric_key: m for m in resultado.measurements}
    assert medidas["cx4_deskilling"].value == 1.0
    assert medidas["cx4_deskilling"].state == "alerta"


def test_cx4_no_dispara_si_la_senal_no_esta_fired():
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref)
    usage = _baseline_usage(seed=1)

    deskilling = DeskillingInput(
        fired=False,
        agreement_slope=0.01,
        model_accuracy_slope=0.0,
        rescue_slope=0.0,
        reason="Human and model are not converging over the period.",
    )
    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia", deskilling=deskilling)
    assert not any(a.rule == "CX-4" for a in resultado.alerts)
    medidas = {m.metric_key: m for m in resultado.measurements}
    assert medidas["cx4_deskilling"].value == 0.0
    assert medidas["cx4_deskilling"].state == "ok"


def test_cx4_bloqueado_por_mejora_real_del_modelo_sin_caida_de_rescate():
    """`model_accuracy_slope` positivo
    por encima de `eps` sin que el rescate caiga significa que la convergencia
    es una mejora real del modelo, no erosión de criterio: CX-4 no dispara
    pese a `deskilling.fired`."""
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref)
    usage = _baseline_usage(seed=1)

    deskilling = DeskillingInput(
        fired=True,
        agreement_slope=0.06,
        model_accuracy_slope=0.05,
        rescue_slope=0.0,
        reason="Human and model are converging while the human's own accuracy is not improving",
    )
    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia", deskilling=deskilling)
    assert not any(a.rule == "CX-4" for a in resultado.alerts)
    medidas = {m.metric_key: m for m in resultado.measurements}
    # El valor sigue reflejando la señal cruda (`fired`); el bloqueo decide si
    # abre alerta, no el número.
    assert medidas["cx4_deskilling"].value == 1.0
    assert medidas["cx4_deskilling"].state == "ok"


def test_cx4_sin_datos_sin_senal_de_deskilling():
    """`deskilling=None` (sin versión activa o sin diario, resuelto por
    `human_layer._deskilling_input_for_cx4`): `sin_datos`, nunca alerta."""
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref)
    usage = _baseline_usage(seed=1)

    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia")
    medidas = {m.metric_key: m for m in resultado.measurements}
    assert medidas["cx4_deskilling"].state == "sin_datos"
    assert not any(a.rule == "CX-4" for a in resultado.alerts)


def test_cx4_sin_tendencia_pero_con_nivel_computable_no_es_sin_datos():
    """`agreement_slope is None` (ventanas insuficientes con verdad
    de terreno, `telemetry.py:196-197`) ya no basta para `sin_datos` por sí
    solo, porque `evaluate_cross` calcula `level_z` con `df_usage` y
    `reference`, que aquí sí son computables. Con una ventana de vigilancia
    parecida a la referencia (misma distribución, `_baseline_usage` con
    semillas distintas) el nivel no dispara: `ok`, no `sin_datos`."""
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref)
    usage = _baseline_usage(seed=1)

    deskilling = DeskillingInput(
        fired=False,
        agreement_slope=None,
        model_accuracy_slope=None,
        rescue_slope=None,
        reason="Insufficient windows with ground truth to assess a trend.",
    )
    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia", deskilling=deskilling)
    medidas = {m.metric_key: m for m in resultado.measurements}
    assert medidas["cx4_deskilling"].state == "ok"
    assert not any(a.rule == "CX-4" for a in resultado.alerts)


def test_cx4_sin_datos_sin_tendencia_ni_nivel_computable():
    """`sin_datos` sigue existiendo cuando NINGUNA de las dos señales se puede
    calcular: sin ventanas con verdad de terreno (`agreement_slope is None`)
    Y sin referencia de override para el nivel (`reference.override_rate is
    None`, `_agreement_level_z` no puede reconstruir el `k` de la
    referencia)."""
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref).model_copy(update={"override_rate": None})
    usage = _baseline_usage(seed=1)

    deskilling = DeskillingInput(
        fired=False,
        agreement_slope=None,
        model_accuracy_slope=None,
        rescue_slope=None,
        reason="Insufficient windows with ground truth to assess a trend.",
    )
    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia", deskilling=deskilling)
    medidas = {m.metric_key: m for m in resultado.measurements}
    assert medidas["cx4_deskilling"].state == "sin_datos"
    assert not any(a.rule == "CX-4" for a in resultado.alerts)


def test_tasa_falsos_positivos_200_semillas():
    usage_ref = _baseline_usage(seed=0)
    reference = build_reference(usage_ref)

    conteo_por_regla: dict[str, int] = {}
    n_semillas = 200
    for s in range(1, n_semillas + 1):
        usage = _baseline_usage(seed=s)
        resultado = evaluate_cross(usage, reference=reference, mode="vigilancia")
        for a in resultado.alerts:
            conteo_por_regla[a.rule] = conteo_por_regla.get(a.rule, 0) + 1

    total_alertas = sum(conteo_por_regla.values())
    tasa = total_alertas / n_semillas
    print(f"[FPR] tasa={tasa:.4f} por_regla={conteo_por_regla}")
    assert tasa <= 0.02, f"tasa {tasa:.4f} por encima de 0.02; por regla: {conteo_por_regla}"


def test_cx1_sin_positivos_no_divide_por_cero():
    """Un grupo sin filas `ground_truth == 'refer'` (0 positivos) no debe
    romper con `ZeroDivisionError`: la condición de FNR es `sin_datos` y
    CX-1 no dispara para ese grupo.
    """
    n = 40
    grupo = pd.DataFrame(
        {
            "date": ["2026-01-05"] * n,
            "clinician_pseudonym": ["clin-01"] * n,
            "subgroup": ["18-35"] * n,
            "human_decision": ["no-refer"] * n,
            "model_output": ["no-refer"] * n,
            "ground_truth": ["no-refer"] * n,
            "record_seq": list(range(n)),
            "model_version": ["v1"] * n,
        }
    )
    complemento = pd.DataFrame(
        {
            "date": ["2026-01-05"] * n,
            "clinician_pseudonym": ["clin-02"] * n,
            "subgroup": ["36-75"] * n,
            "human_decision": ["refer"] * (n // 2) + ["no-refer"] * (n - n // 2),
            "model_output": ["no-refer"] * (n // 2) + ["refer"] * (n - n // 2),
            "ground_truth": ["refer"] * n,
            "record_seq": list(range(n, 2 * n)),
            "model_version": ["v1"] * n,
        }
    )
    df = pd.concat([grupo, complemento], ignore_index=True)

    resultado = evaluate_cross(df, reference=build_reference(df), mode="vigilancia")
    medidas = {m.metric_key: m for m in resultado.measurements}
    assert medidas["cx1_model_fnr_z:18-35"].state == "sin_datos"
    assert medidas["cx1_model_fnr_z:18-35"].value is None
    assert not any(a.rule == "CX-1" and a.group == "18-35" for a in resultado.alerts)


def test_cx5_dispara_con_k_clin_override_y_no_por_defecto():
    df = score_dataframe(generate_baseline(n=2000, seed=11), seed=11)
    df = _labeled(df, seed=11, accuracy_target=0.88)

    usage_sesgada = simulate_decisions(
        df, seed=11, params=HumanParams(k_clin_override={"clin-03": 4.0}), start_date=START
    )
    resultado_sesgado = evaluate_cross(usage_sesgada, reference=build_reference(usage_sesgada))
    assert any(a.rule == "CX-5" for a in resultado_sesgado.alerts)

    usage_normal = simulate_decisions(df, seed=11, params=HumanParams(), start_date=START)
    resultado_normal = evaluate_cross(usage_normal, reference=build_reference(usage_normal))
    assert not any(a.rule == "CX-5" for a in resultado_normal.alerts)


def test_calibracion_sin_alertas_con_referencia():
    usage = _baseline_usage(seed=1)
    resultado = evaluate_cross(usage, reference=None)
    assert resultado.mode == "calibracion"
    assert resultado.alerts == []
    assert "by_subgroup" in resultado.reference
    assert resultado.reference["by_subgroup"]


def test_grupos_pequenos_dan_sin_datos():
    df = score_dataframe(generate_baseline(n=30, seed=21), seed=21)
    df = _labeled(df, seed=21, accuracy_target=0.88)
    usage = simulate_decisions(df, seed=21, params=HumanParams(), start_date=START)
    reference = build_reference(usage)

    resultado = evaluate_cross(
        usage, reference=reference, mode="vigilancia", config=CrossConfig(min_group=1000)
    )
    assert resultado.alerts == []
    estados = {m.state for m in resultado.measurements if m.metric_key.startswith("cx1_")}
    assert "sin_datos" in estados


# --- motivo en lenguaje llano del `sin_datos` ------------


def test_sin_datos_cx1_override_lleva_motivo_con_minimo_y_alcanzado():
    df = score_dataframe(generate_baseline(n=30, seed=21), seed=21)
    df = _labeled(df, seed=21, accuracy_target=0.88)
    usage = simulate_decisions(df, seed=21, params=HumanParams(), start_date=START)
    reference = build_reference(usage)
    config = CrossConfig(min_group=1000)

    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia", config=config)
    medidas_override = [
        m for m in resultado.measurements if m.metric_key.startswith("cx1_override_z:")
    ]
    assert medidas_override
    for medida in medidas_override:
        assert medida.state == "sin_datos"
        assert medida.motivo is not None
        assert str(config.min_group) in medida.motivo
        assert "decisiones registradas" in medida.motivo
        # Sin código interno: ni la clave de la métrica ni "min_group"
        assert medida.metric_key not in medida.motivo
        assert "min_group" not in medida.motivo


def test_sin_datos_cx1_fnr_lleva_motivo_con_casos_que_necesitaban_derivacion():
    """Reproduce el grupo sin positivos de `test_cx1_sin_positivos_no_divide_por_cero`
    y comprueba que el `sin_datos` de la condición FNR explica el mínimo y lo alcanzado."""
    n = 40
    grupo = pd.DataFrame(
        {
            "date": ["2026-01-05"] * n,
            "clinician_pseudonym": ["clin-01"] * n,
            "subgroup": ["18-35"] * n,
            "human_decision": ["no-refer"] * n,
            "model_output": ["no-refer"] * n,
            "ground_truth": ["no-refer"] * n,
            "record_seq": list(range(n)),
            "model_version": ["v1"] * n,
        }
    )
    complemento = pd.DataFrame(
        {
            "date": ["2026-01-05"] * n,
            "clinician_pseudonym": ["clin-02"] * n,
            "subgroup": ["36-75"] * n,
            "human_decision": ["refer"] * (n // 2) + ["no-refer"] * (n - n // 2),
            "model_output": ["no-refer"] * (n // 2) + ["refer"] * (n - n // 2),
            "ground_truth": ["refer"] * n,
            "record_seq": list(range(n, 2 * n)),
            "model_version": ["v1"] * n,
        }
    )
    df = pd.concat([grupo, complemento], ignore_index=True)

    resultado = evaluate_cross(df, reference=build_reference(df), mode="vigilancia")
    medida = next(m for m in resultado.measurements if m.metric_key == "cx1_model_fnr_z:18-35")
    assert medida.state == "sin_datos"
    assert medida.motivo is not None
    assert "necesitaban la decisión favorable" in medida.motivo
    assert str(CrossConfig().min_positives) in medida.motivo
    assert "0 casos" in medida.motivo  # el subgrupo no tiene positivos


def test_sin_datos_cx5_lleva_motivo_sin_codigo_interno():
    usage = _baseline_usage(seed=1)
    resultado = evaluate_cross(usage, reference=build_reference(usage), mode="vigilancia")
    medida = next(m for m in resultado.measurements if m.metric_key == "cx5_chi2_p")
    assert medida.state == "sin_datos"
    assert medida.motivo is not None
    assert "profesionales" in medida.motivo
    assert "min_clinician" not in medida.motivo


# --- `Project.calibration_until` y `GET /projects/{id}/cross/latest` ---

_ETIQUETA_A_ENTERO = {"refer": 1, "no-refer": 0}


def _bd_con_proyecto_cross(
    usage: pd.DataFrame, *, calibration_until: str | None = None
) -> tuple[Session, Project, ModelVersion]:
    """BD SQLite en memoria con un proyecto, su versión activa, el monitor
    `cross` y el diario de uso de `usage` ya cargado. Evita levantar la app
    FastAPI entera: solo hace falta `human_layer` sobre una sesión."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    project = Project(name="test-cross-h3", calibration_until=calibration_until)
    session.add(project)
    session.flush()
    version = ModelVersion(project_id=project.id, label="v1", is_active=True)
    session.add(version)
    session.flush()
    project.active_version_id = version.id
    session.add(project)
    session.add(Monitor(project_id=project.id, type="cross", enabled=True))
    for _, fila in usage.reset_index(drop=True).iterrows():
        valor_fecha = fila["date"]
        session.add(
            UsageLog(
                project_id=project.id,
                model_version_id=version.id,
                record_seq=int(fila["record_seq"]),
                date=valor_fecha.isoformat() if hasattr(valor_fecha, "isoformat") else str(valor_fecha),
                clinician_pseudonym=fila.get("clinician_pseudonym"),
                subgroup=fila.get("subgroup"),
                human_decision=_ETIQUETA_A_ENTERO.get(fila["human_decision"]),
                model_output=_ETIQUETA_A_ENTERO.get(fila["model_output"]),
                ground_truth=_ETIQUETA_A_ENTERO.get(fila["ground_truth"]),
            )
        )
    session.flush()
    session.commit()
    return session, project, version


def test_cross_latest_sin_datos_antes_de_evaluar_y_con_las_claves_del_contrato_despues():
    """Antes de la primera evaluación responde `estado`
    `sin_datos` (ya no 404), con `rules`, `calibration_until` y `worst_state`
    después de una."""
    usage = _baseline_usage(seed=2)
    session, project, version = _bd_con_proyecto_cross(usage)
    try:
        vacio = cross_latest(session, project)
        assert vacio["estado"] == "sin_datos"
        assert vacio["rules"] == []
        assert vacio["evaluation_id"] is None
        assert vacio["worst_state"] == "sin_datos"

        evaluacion = evaluate_cross_for_project(session, project, version=version)
        session.commit()
        assert evaluacion is not None

        cuerpo = cross_latest(session, project)
        assert cuerpo["estado"] == "con_datos"
        assert set(cuerpo) == {
            "estado",
            "evaluation_id",
            "mode",
            "worst_state",
            "model_version_id",
            "evaluated_at",
            "rules",
            "calibration_until",
        }
        assert cuerpo["evaluation_id"] == evaluacion.id
        assert cuerpo["mode"] == "calibracion"
        assert cuerpo["worst_state"] == evaluacion.worst_state
        assert cuerpo["calibration_until"] is None
        assert isinstance(cuerpo["rules"], list)
    finally:
        session.close()


def test_calibrando_por_fecha_acumula_sin_fijar_referencia_hasta_vencer():
    """`calibration_until` en el futuro: modo `calibracion` en cada corrida,
    sin fijar `version.cross_reference_json` (a diferencia del `None`, que
    la fija en la primera corrida)."""
    usage = _baseline_usage(seed=3)
    session, project, version = _bd_con_proyecto_cross(usage, calibration_until="2099-01-01")
    try:
        primera = evaluate_cross_for_project(session, project, version=version)
        session.commit()
        assert primera is not None
        assert primera.result_json["mode"] == "calibracion"
        session.refresh(version)
        assert version.cross_reference_json is None

        segunda = evaluate_cross_for_project(session, project, version=version)
        session.commit()
        assert segunda.result_json["mode"] == "calibracion"
        session.refresh(version)
        assert version.cross_reference_json is None
    finally:
        session.close()


def test_calibration_until_vencido_fija_la_referencia_en_la_primera_corrida():
    """`calibration_until` en el pasado (ya vencido, no `None`): la primera
    corrida sin referencia todavía la fija, igual que con `calibration_until`
    nulo (comportamiento anterior)."""
    usage = _baseline_usage(seed=4)
    session, project, version = _bd_con_proyecto_cross(usage, calibration_until="2020-01-01")
    try:
        evaluacion = evaluate_cross_for_project(session, project, version=version)
        session.commit()
        assert evaluacion is not None
        assert evaluacion.result_json["mode"] == "calibracion"
        session.refresh(version)
        assert version.cross_reference_json is not None
        assert version.cross_reference_json.get("n") > 0
    finally:
        session.close()


# --- Barrido de sesgo de automatización -------------------


def test_cx4_tasa_de_disparo_no_cae_a_cero_en_el_barrido_de_sesgo():
    """Con solo la tendencia, la convergencia satura dentro de la
    primera ventana del paquete a sesgo alto (`exp(-automation_bias * t)`
    decae casi entero antes de que acabe la ventana 1), la pendiente entre
    ventanas deja de superar `eps` y la tasa de disparo caía a 0 justo donde
    la erosión de criterio es mayor (la "campana"). Con el nivel
    (`level_z`, dos proporciones contra la referencia de calibración) la
    tasa no cae a 0 en los valores altos del barrido (0 a 12)."""
    reference = build_reference(_baseline_usage(seed=0, n=450))

    sesgos = (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
    disparos: dict[float, bool] = {}
    for bias in sesgos:
        disparo = False
        for seed in (101, 202, 303):
            usage = _usage_con_sesgo(seed, bias)
            deskilling = _deskilling_input_from_df(usage)
            resultado = evaluate_cross(
                usage, reference=reference, mode="vigilancia", deskilling=deskilling
            )
            if any(a.rule == "CX-4" for a in resultado.alerts):
                disparo = True
                break
        disparos[bias] = disparo

    altos = [b for b in sesgos if b >= 8.0]
    assert any(disparos[b] for b in altos), disparos


# --- señal `human_review_zero` ---------------------------------


def test_human_review_zero_dispara_con_override_cero_y_n_suficiente():
    """Diario de vigilancia con cero overrides y `n >= HUMAN_REVIEW_ZERO_MIN_N`:
    `aviso` con el texto exacto del contrato, distinto de `sin_datos`."""
    reference = build_reference(_baseline_usage(seed=0))
    n = HUMAN_REVIEW_ZERO_MIN_N + 10
    usage = _sin_override(_baseline_usage(seed=5, n=n))

    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia")
    medidas = {m.metric_key: m for m in resultado.measurements}
    medida = medidas["human_review_zero"]
    assert medida.state == "aviso"
    assert medida.motivo == f"ningún profesional ha corregido al modelo en {n} decisiones"
    # nunca abre `Alert` (mismo patrón que CX-3).
    assert not any(a.rule == "human_review_zero" for a in resultado.alerts)


def test_human_review_zero_sin_datos_con_n_insuficiente():
    """Por debajo de `HUMAN_REVIEW_ZERO_MIN_N`, `sin_datos`, no `aviso`, aunque
    el override sea cero: con poca `n` cero overrides no distingue "nadie
    corrige" de "poca muestra"."""
    reference = build_reference(_baseline_usage(seed=0))
    usage = _sin_override(_baseline_usage(seed=5, n=HUMAN_REVIEW_ZERO_MIN_N - 10))

    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia")
    medidas = {m.metric_key: m for m in resultado.measurements}
    medida = medidas["human_review_zero"]
    assert medida.state == "sin_datos"


def test_human_review_zero_no_dispara_en_diario_normal():
    """Un diario normal (`HumanParams()` por defecto, `override_base=0.05`,
    muy por encima del umbral del 1 %) no la dispara."""
    reference = build_reference(_baseline_usage(seed=0))
    usage = _baseline_usage(seed=6, n=HUMAN_REVIEW_ZERO_MIN_N + 50)

    resultado = evaluate_cross(usage, reference=reference, mode="vigilancia")
    medidas = {m.metric_key: m for m in resultado.measurements}
    medida = medidas["human_review_zero"]
    assert medida.state == "ok"
