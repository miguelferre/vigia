"""Corrección tras la revisión: los defectos de la regresión que se arreglaron y
los tests que les faltaban."""
from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import vigia.core.engine as motor
from vigia.core.calibration import (
    _MARGEN_RELATIVO,
    _percentil_de_cobertura,
    umbrales_linea_base_regresion,
)
from vigia.core.drift import evaluate_drift
from vigia.core.engine import MonitorSettings, evaluate_batch
from vigia.core.fairness import evaluate_fairness
from vigia.core.fairness_regresion import _intervalo_cociente, prediccion_por_grupo
from vigia.core.loaders import avisos_regresion, to_canonical
from vigia.core.predict_onnx import (
    ModeloEjecutableInvalido,
    coincidencia_valor,
    validar_coincidencia_valor,
)
from vigia.core.quality import _medida_regresion, evaluate_quality
from vigia.core.quality_regresion import (
    MOTIVO_R2_SIN_VARIANZA,
    MOTIVO_SIN_PARES,
    metricas_regresion,
    varianza_nula,
)
from vigia.core.schema import (
    CLAVES_CALIDAD_REGRESION,
    COL_GROUP,
    COL_LABEL_VALUE,
    COL_PREDICTION_VALUE,
    DatosNoValidos,
    DriftConfig,
    FairnessConfig,
    MonitorThresholds,
    MonitorType,
    QualityConfig,
    State,
    Threshold,
    ThresholdKind,
)
from vigia.core.states import classify_with_motivo, decimales_para
from vigia.core.thresholds import defaults_regresion

from ._datos_regresion import crudo, historia, mapeo, tarea

TAMANO_LOTE = 500
NUCLEO = Path(__file__).resolve().parents[2] / "src" / "vigia" / "core"


def _base(n=2000, seed=0, **kw):
    return to_canonical(crudo(n, seed=seed, **kw), mapeo(), task=tarea())


def _evaluar_calidad(frame, t, thresholds=None):
    return evaluate_quality(
        frame,
        batch_seq=0,
        config=QualityConfig(),
        thresholds=thresholds or MonitorThresholds(),
        task=t,
    )


def _por_clave(resultado):
    return {(m.metric_key, m.group_code): m for m in resultado.measurements}


# --------------------------------------------------------------------------
# Contrato 1 (media): R² con valor real constante pero inexacto en coma flotante
# --------------------------------------------------------------------------


@pytest.mark.parametrize("constante", [3.3, 7.7, 1_000_000.1, 0.1, 42.0])
def test_con_valor_real_constante_inexacto_da_sin_datos_nunca_un_numero_enorme(constante):
    df = crudo(300)
    df["y"] = constante
    h, t = historia([df])
    assert metricas_regresion(h.frame())["r2"] is None
    medida = {m.metric_key: m for m in _evaluar_calidad(h.frame(), t).measurements}["r2"]
    assert medida.value is None and medida.state == State.sin_datos
    assert medida.motivo == MOTIVO_R2_SIN_VARIANZA


@pytest.mark.parametrize("constante", [3.3, 7.7, 1_000_000.1])
def test_una_linea_base_con_valor_real_constante_inexacto_no_emite_umbral_de_r2(constante):
    base = _base(2000)
    base[COL_LABEL_VALUE] = constante
    claves = {u.metric_key for u in umbrales_linea_base_regresion(base, tarea(), tamano_lote=300)}
    assert "r2" not in claves


def test_poca_variacion_real_no_se_toma_por_varianza_nula():
    # 1e6 con un recorrido de 0,5: la variación es real, aunque pequeña frente a la magnitud
    rng = np.random.default_rng(0)
    y = 1_000_000.0 + rng.uniform(-0.25, 0.25, 300)
    assert not varianza_nula(y)
    assert varianza_nula(np.full(10, 3.3)) and varianza_nula(np.array([])) and varianza_nula(np.zeros(4))
    df = crudo(300)
    df["y"] = y
    df["p"] = y + rng.normal(0, 0.1, 300)
    h, _t = historia([df])
    r2 = metricas_regresion(h.frame())["r2"]
    assert r2 is not None and math.isfinite(r2) and r2 < 1.0


# --------------------------------------------------------------------------
# Los umbrales de hoy sobre la pertenencia, en el motor
# --------------------------------------------------------------------------


def test_con_rango_los_umbrales_de_hoy_alertan_sobre_la_pertenencia_y_rate_unpriv_es_la_media():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, recorte=15.0), crudo(400, seed=2)])
    umbrales = defaults_regresion(MonitorType.fairness, con_rango=True)

    def evaluar(lote):
        return _por_clave(
            evaluate_fairness(
                h.frame(),
                batch_seq=lote,
                config=FairnessConfig(),
                thresholds=umbrales,
                model_version="v1",
                interval_method="lote",
                task=t,
            )
        )

    cortado = evaluar(1)
    fila = h.batch(1)
    media_a = float(fila[fila[COL_GROUP] == 0]["prediction"].mean())
    assert cortado[("rate_unpriv", "unpriv")].value == pytest.approx(media_a, abs=1e-9)
    # el recorte de 15 unidades lleva la tasa del grupo bajo el 20 % de la del otro
    assert cortado[("fairness_value", None)].state in (State.alerta, State.inestable)
    sano = evaluar(2)
    assert sano[("fairness_value", None)].state in (State.ok, State.aviso)


def test_con_defaults_de_regresion_en_los_cuatro_monitores_nada_espera_ni_sobra():
    h, t = historia([crudo(400, seed=0), crudo(400, seed=1, desplazamiento=8.0)])
    ajustes = MonitorSettings(
        thresholds={
            m.value: defaults_regresion(m, con_rango=True)
            for m in (MonitorType.quality, MonitorType.fairness, MonitorType.drift, MonitorType.explain)
        }
    )
    r = evaluate_batch(h, 1, ajustes, task=t)
    calidad = {m.metric_key: m for m in r["quality"].measurements}
    for clave in CLAVES_CALIDAD_REGRESION:
        assert calidad[clave].state == State.sin_datos
        assert calidad[clave].extra["umbral_pendiente"] is True
    deriva = {m.metric_key: m for m in r["drift"].measurements}
    assert "confidence_drift_score" not in deriva
    assert deriva["prediction_drift_score"].state == State.sin_datos
    assert deriva["prediction_drift_score"].extra["umbral_pendiente"] is True
    assert deriva["prediction_drift_score"].extra["valor_calculado"] > 0.2  # el desplazamiento se ve


# --------------------------------------------------------------------------
# Las reglas de equidad a mano, las diez
# --------------------------------------------------------------------------


def _remuestreos_a_mano(base, *, semilla, tamano_lote, n_remuestreos=200, min_group=20):
    """Reproduce el orden de sorteos de `umbrales_linea_base_regresion`: un
    `rng.integers` por remuestreo y, después, dos `rng.choice` por par para el KS."""
    from scipy import stats as sps

    rng = np.random.default_rng(semilla)
    y = base[COL_LABEL_VALUE].to_numpy(dtype=float)
    pred = base[COL_PREDICTION_VALUE].to_numpy(dtype=float)
    error = pred - y
    grupo = base[COL_GROUP].to_numpy()
    m: dict[str, list[float]] = {
        c: []
        for c in (
            "mean_absolute_error", "root_mean_squared_error", "r2", "mean_error",
            "mean_error_difference", "mean_absolute_error_difference", "mean_absolute_error_ratio",
        )
    }
    for _ in range(n_remuestreos):
        idx = rng.integers(0, len(base), size=tamano_lote)
        e, yy, gg = error[idx], y[idx], grupo[idx]
        m["mean_absolute_error"].append(float(np.abs(e).mean()))
        m["root_mean_squared_error"].append(float(np.sqrt((e**2).mean())))
        m["mean_error"].append(float(e.mean()))
        m["r2"].append(float(1.0 - (e**2).sum() / ((yy - yy.mean()) ** 2).sum()))
        a, b = gg == 0, gg == 1
        if a.sum() >= min_group and b.sum() >= min_group:
            mae_a, mae_b = np.abs(e[a]).mean(), np.abs(e[b]).mean()
            m["mean_absolute_error_difference"].append(float(mae_a - mae_b))
            m["mean_absolute_error_ratio"].append(float(mae_a / mae_b))
            m["mean_error_difference"].append(float(e[a].mean() - e[b].mean()))
    ks = [
        float(sps.ks_2samp(rng.choice(pred, size=tamano_lote), rng.choice(pred, size=tamano_lote)).statistic)
        for _ in range(n_remuestreos)
    ]
    return m, ks


def test_las_diez_reglas_a_mano_con_p1_p99_y_margen():
    """Cada umbral contra su fórmula: máximo `p99 + 0,2 w` (MAE, RMSE, diferencia de
    MAE), mínimo `p1 - 0,2 w` (R²), los dos lados con signo (sesgo y diferencia de
    sesgo), `p99 x 1,2` (cociente y KS). Si cambia el orden de los sorteos de
    `umbrales_linea_base_regresion`, este test se reescribe con el nuevo orden; las
    fórmulas son las que fija."""
    base = _base(2000)
    u = {(x.metric_key, x.kind): x.value for x in umbrales_linea_base_regresion(
        base, tarea(), tamano_lote=TAMANO_LOTE, semilla=0)}
    m, ks = _remuestreos_a_mano(base, semilla=0, tamano_lote=TAMANO_LOTE)
    p_bajo = _percentil_de_cobertura(ThresholdKind.lower_limit, 0.99)
    p_alto = _percentil_de_cobertura(ThresholdKind.upper_limit, 0.99)

    def p1_p99_w(valores):
        p1, p99 = float(np.percentile(valores, p_bajo)), float(np.percentile(valores, p_alto))
        return p1, p99, p99 - p1

    esperado: dict[tuple[str, ThresholdKind], float] = {}
    for clave in ("mean_absolute_error", "root_mean_squared_error", "mean_absolute_error_difference"):
        _p1, p99, w = p1_p99_w(m[clave])
        esperado[(clave, ThresholdKind.upper_limit)] = p99 + _MARGEN_RELATIVO * w
    p1, _p99, w = p1_p99_w(m["r2"])
    esperado[("r2", ThresholdKind.lower_limit)] = min(p1 - _MARGEN_RELATIVO * w, 1.0)
    for clave in ("mean_error", "mean_error_difference"):
        p1, p99, w = p1_p99_w(m[clave])
        esperado[(clave, ThresholdKind.lower_limit)] = p1 - _MARGEN_RELATIVO * w
        esperado[(clave, ThresholdKind.upper_limit)] = p99 + _MARGEN_RELATIVO * w
    esperado[("mean_absolute_error_ratio", ThresholdKind.upper_limit)] = (
        p1_p99_w(m["mean_absolute_error_ratio"])[1] * (1 + _MARGEN_RELATIVO)
    )
    esperado[("prediction_drift_score", ThresholdKind.upper_limit)] = (
        float(np.percentile(ks, p_alto)) * (1 + _MARGEN_RELATIVO)
    )
    assert set(u) == set(esperado)
    for clave, valor in esperado.items():
        assert u[clave] == pytest.approx(valor, abs=2e-6), clave


# --------------------------------------------------------------------------
# La frontera del 99 %
# --------------------------------------------------------------------------


def _modelo_que_acierta(esperado, aciertos):
    fallo = np.arange(len(esperado)) >= aciertos
    return lambda _x: np.where(fallo, esperado + 100.0, esperado)


def test_de_200_coinciden_y_pasa_197_de_200_no():
    esperado = np.arange(200, dtype=float)
    X = pd.DataFrame({"a": np.arange(200)})
    assert coincidencia_valor(_modelo_que_acierta(esperado, 198), X, esperado) == pytest.approx(0.99)
    assert validar_coincidencia_valor(_modelo_que_acierta(esperado, 198), X, esperado) == pytest.approx(0.99)
    with pytest.raises(ModeloEjecutableInvalido, match="no reproduce"):
        validar_coincidencia_valor(_modelo_que_acierta(esperado, 197), X, esperado)


# --------------------------------------------------------------------------
# Distingue sin rango de con rango
# --------------------------------------------------------------------------


def test_el_motor_pasa_la_tasa_de_etiqueta_solo_con_rango(monkeypatch):
    capturadas: list[float | None] = []
    original = motor.evaluate_quality

    def espia(*args, **kwargs):
        capturadas.append(kwargs["baseline_label_rate"])
        return original(*args, **kwargs)

    monkeypatch.setattr(motor, "evaluate_quality", espia)
    h, t = historia([crudo(300, seed=0), crudo(300, seed=1)], rangos=[])
    evaluate_batch(h, 1, MonitorSettings.defaults(), task=t)
    assert capturadas == [None]
    h2, t2 = historia([crudo(300, seed=0), crudo(300, seed=1)])
    evaluate_batch(h2, 1, MonitorSettings.defaults(), task=t2)
    assert capturadas[1] == pytest.approx(h2.label_rate_baseline("v1")) and 0.0 < capturadas[1] < 1.0


# --------------------------------------------------------------------------
# Contrato 6 (baja): el intervalo del cociente y la razón no definida
# --------------------------------------------------------------------------


def test_el_intervalo_del_cociente_es_el_metodo_delta_en_escala_log():
    rng = np.random.default_rng(3)
    a, b = np.abs(rng.normal(4, 2, 80)), np.abs(rng.normal(3, 1.5, 90))
    bajo, alto = _intervalo_cociente(a, b)
    se = math.sqrt(a.var(ddof=1) / (80 * a.mean() ** 2) + b.var(ddof=1) / (90 * b.mean() ** 2))
    razon = a.mean() / b.mean()
    assert bajo == pytest.approx(razon * math.exp(-1.959963984540054 * se), rel=1e-6)
    assert alto == pytest.approx(razon * math.exp(1.959963984540054 * se), rel=1e-6)
    assert bajo < razon < alto
    assert _intervalo_cociente(np.zeros(5), b) is None  # media no positiva
    assert _intervalo_cociente(a[:1], b) is None  # una sola fila


def test_con_error_cero_en_el_grupo_de_referencia_la_razon_no_esta_definida():
    df = crudo(400, seed=1)
    df.loc[df["g"] == "b", "p"] = df["y"]  # error exactamente 0 en el grupo de referencia
    h, t = historia([crudo(400, seed=0), df])
    umbrales = MonitorThresholds(
        thresholds=[Threshold(metric_key="mean_absolute_error_ratio", kind=ThresholdKind.upper_limit,
                              value=1.5, origen="linea_base")]
    )
    r = evaluate_fairness(
        h.frame(), batch_seq=1, config=FairnessConfig(), thresholds=umbrales,
        model_version="v1", interval_method="lote", task=t,
    )
    razon = _por_clave(r)[("mean_absolute_error_ratio", None)]
    assert razon.value is None and razon.state == State.sin_datos
    assert "la razón no está definida" in razon.motivo


# --------------------------------------------------------------------------
# Contrato 7 (baja): todo `match` por tipo del motor termina en `case _: raise`
# --------------------------------------------------------------------------

_SUJETOS = {"tipo", "task.task_type", "_tipo(task)"}
_GUARDAS = {"_columnas_objetivo"}  # lanza ante un tipo desconocido antes de los `match` que le siguen


def _match_por_tipo(funcion: ast.AST) -> list[ast.Match]:
    """Los `match` sobre el tipo de la función, sin entrar en las funciones anidadas."""
    hallados: list[ast.Match] = []

    def visita(nodo: ast.AST) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(hijo, ast.Match) and ast.unparse(hijo.subject) in _SUJETOS:
                hallados.append(hijo)
            visita(hijo)

    visita(funcion)
    return sorted(hallados, key=lambda n: n.lineno)


def _llama_a_guarda_antes(funcion: ast.AST, linea: int) -> bool:
    for nodo in ast.walk(funcion):
        if (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Name)
            and nodo.func.id in _GUARDAS
            and nodo.lineno < linea
        ):
            return True
    return False


def _cierra_con_raise(m: ast.Match) -> bool:
    for caso in m.cases:
        if isinstance(caso.pattern, ast.MatchAs) and caso.pattern.pattern is None:
            return any(isinstance(n, ast.Raise) for s in caso.body for n in ast.walk(s))
    return False


def _sin_guarda(funcion: ast.AST, guardada: bool, fichero: str, fallos: list[str]) -> None:
    """Dentro de una función, el primer `match` por tipo (si nada lo guardó antes ni
    ninguna función que la envuelve) debe cerrar con `case _: raise`."""
    mis_match = _match_por_tipo(funcion)
    if mis_match and not guardada:
        primero = mis_match[0]
        if not _llama_a_guarda_antes(funcion, primero.lineno) and not _cierra_con_raise(primero):
            fallos.append(f"{fichero}:{primero.lineno}")
    guardada_aqui = guardada or (bool(mis_match) and _cierra_con_raise(mis_match[0]))
    for hijo in ast.walk(funcion):
        if hijo is funcion:
            continue
        if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)) and _padre_directo(funcion, hijo):
            _sin_guarda(hijo, guardada_aqui, fichero, fallos)


def _padre_directo(funcion: ast.AST, hijo: ast.AST) -> bool:
    """`hijo` es una función cuyo ámbito inmediato es `funcion`."""
    pila = list(ast.iter_child_nodes(funcion))
    while pila:
        nodo = pila.pop()
        if nodo is hijo:
            return True
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        pila.extend(ast.iter_child_nodes(nodo))
    return False


def test_cada_funcion_de_core_que_decide_por_tipo_cierra_con_case_raise():
    fallos: list[str] = []
    for ruta in sorted(NUCLEO.glob("*.py")):
        if ruta.name in ("schema.py", "thresholds.py"):
            continue  # los módulos de tipo y la tabla de monitores, fuera del despacho del motor
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _sin_guarda(nodo, False, ruta.name, fallos)
            elif isinstance(nodo, ast.ClassDef):
                for met in nodo.body:
                    if isinstance(met, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        _sin_guarda(met, False, ruta.name, fallos)
    assert fallos == [], f"`match` por tipo sin `case _: raise`: {fallos}"


def test_el_detector_de_despacho_caza_un_match_sin_raise():
    malo = ast.parse("def f(task):\n    match task.task_type:\n        case 'binary':\n            pass\n")
    fallos: list[str] = []
    _sin_guarda(malo.body[0], False, "x.py", fallos)  # type: ignore[arg-type]
    assert fallos == ["x.py:2"]
    bueno = ast.parse(
        "def f(task):\n    match task.task_type:\n        case 'binary':\n            pass\n"
        "        case _:\n            raise ValueError('no')\n"
    )
    fallos = []
    _sin_guarda(bueno.body[0], False, "x.py", fallos)  # type: ignore[arg-type]
    assert fallos == []


# --------------------------------------------------------------------------
# Contrato 9 (baja): `prediccion_por_grupo` con un grupo pequeño
# --------------------------------------------------------------------------


def test_un_grupo_pequeno_lleva_solo_n_y_motivo_en_la_prediccion_por_grupo():
    df = crudo(400, seed=1)
    pequeno = pd.concat([df[df["g"] == "b"], df[df["g"] == "a"].head(10)], ignore_index=True)
    h, _t = historia([crudo(400, seed=0), pequeno])
    ppg = prediccion_por_grupo(h.batch(1), min_group=20)
    assert set(ppg["unpriv"]) == {"n", "motivo"} and ppg["unpriv"]["n"] == 10
    assert set(ppg["priv"]) == {"cuantiles", "media", "n", "histograma"}


# --------------------------------------------------------------------------
# Contrato 10 (baja): unidades pequeñas
# --------------------------------------------------------------------------


def test_con_una_salida_de_escala_1e_7_los_umbrales_no_se_redondean_a_cero():
    base = _base(2000)
    base[COL_PREDICTION_VALUE] = base[COL_PREDICTION_VALUE] * 1e-7
    base[COL_LABEL_VALUE] = base[COL_LABEL_VALUE] * 1e-7
    u = {x.metric_key: x.value for x in umbrales_linea_base_regresion(base, tarea(), tamano_lote=300)
         if x.kind == ThresholdKind.upper_limit}
    assert 1e-8 < u["mean_absolute_error"] < 1e-6
    assert 1e-8 < u["root_mean_squared_error"] < 1e-6


def test_el_motivo_de_una_regresion_de_escala_pequena_no_se_pinta_con_ceros():
    assert decimales_para(0.0004, None, 0.0003) == 6
    assert decimales_para(12.5, None, 20.0) is None  # unidades normales: los decimales de siempre
    umbrales = MonitorThresholds(
        thresholds=[Threshold(metric_key="mean_absolute_error", kind=ThresholdKind.upper_limit,
                              value=0.0003, origen="linea_base")]
    )
    medida = _medida_regresion(
        "mean_absolute_error", 0.0004, umbrales, titular=True, motivo_nulo=None
    )
    assert medida.state == State.alerta
    assert "0.000400" in medida.motivo and "0.000300" in medida.motivo
    # el binario y el multiclase no cambian: los decimales de siempre
    assert classify_with_motivo(0.0004, None, 0.0003)[1] == (
        "valor 0.000 por encima del umbral superior 0.000"
    )


# --------------------------------------------------------------------------
# Contrato 11 (baja): faltan las columnas de valor en deriva y equidad
# --------------------------------------------------------------------------


@pytest.mark.parametrize("rangos", [[[55, None]], []], ids=["con_rango", "sin_rango"])
def test_a_la_equidad_de_regresion_sin_prediction_value_se_le_dice_en_espanol(rangos):
    h, t = historia([crudo(300, seed=0), crudo(300, seed=1)], rangos=rangos)
    frame = h.frame().drop(columns=[COL_PREDICTION_VALUE])
    with pytest.raises(DatosNoValidos, match="falta el valor de la predicción"):
        evaluate_fairness(
            frame, batch_seq=1, config=FairnessConfig(), thresholds=MonitorThresholds(),
            model_version="v1", interval_method="lote", task=t,
        )


def test_a_la_deriva_de_regresion_sin_prediction_value_se_le_dice_en_espanol():
    h, t = historia([crudo(300, seed=0), crudo(300, seed=1)])
    base, actual = h.baseline_for("v1"), h.batch(1)
    with pytest.raises(DatosNoValidos, match="falta el valor de la predicción"):
        evaluate_drift(
            base.drop(columns=[COL_PREDICTION_VALUE]), actual.drop(columns=[COL_PREDICTION_VALUE]),
            config=DriftConfig(), thresholds=MonitorThresholds(), feature_cols=["x"], task=t,
        )


# --------------------------------------------------------------------------
# Un lote sano nunca sale `aviso`
# --------------------------------------------------------------------------


def _umbrales_por_monitor(base, tamano_lote):
    por_monitor: dict[str, list[Threshold]] = {"quality": [], "fairness": [], "drift": []}
    for u in umbrales_linea_base_regresion(base, tarea(), tamano_lote=tamano_lote):
        monitor = {
            "mean_absolute_error": "quality", "root_mean_squared_error": "quality", "r2": "quality",
            "mean_error": "quality", "prediction_drift_score": "drift",
        }.get(u.metric_key, "fairness")
        por_monitor[monitor].append(u)
    return {k: MonitorThresholds(thresholds=v) for k, v in por_monitor.items()}


@pytest.mark.parametrize("desplazamiento", [0.0, -5.0], ids=["sesgo_nulo", "sesgo_de_la_linea_base"])
@pytest.mark.parametrize("tamano", [1000, 200])
def test_un_lote_estable_remuestreado_de_la_linea_base_no_sale_en_aviso_ni_en_alerta(
    desplazamiento, tamano
):
    base = crudo(3000, seed=0, desplazamiento=desplazamiento)
    lotes = [base] + [base.sample(tamano, random_state=s, replace=True) for s in (1, 2, 3)]
    h, t = historia(lotes)
    ajustes = MonitorSettings.defaults()
    ajustes.thresholds.update(_umbrales_por_monitor(h.baseline_for("v1"), tamano))
    for seq in (1, 2, 3):
        r = evaluate_batch(h, seq, ajustes, task=t, fairness_interval_method="ventanas")
        claves = {"mean_absolute_error", "root_mean_squared_error", "r2", "mean_error",
                  "prediction_drift_score", "mean_error_difference", "mean_absolute_error_difference",
                  "mean_absolute_error_ratio"}
        for monitor in ("quality", "drift", "fairness"):
            for m in r[monitor].measurements:
                con_umbral = m.threshold_low is not None or m.threshold_high is not None
                if m.metric_key in claves and con_umbral:
                    assert m.state in (State.ok, State.sin_datos), (monitor, m.metric_key, m.state, m.motivo)


# --------------------------------------------------------------------------
# El consejo cuenta la causa
# --------------------------------------------------------------------------


def _con_prediccion_de_texto(valor):
    df = crudo(40)
    df["p"] = df["p"].map(valor)
    return df


def _error_de_ingesta(df):
    with pytest.raises(DatosNoValidos) as exc:
        to_canonical(df, mapeo(), task=tarea())
    return str(exc.value)


def test_una_coma_decimal_en_la_prediccion_dice_que_se_use_el_punto():
    texto = _error_de_ingesta(_con_prediccion_de_texto(lambda v: f"{v:.1f}".replace(".", ",")))
    assert "separador decimal" in texto and "unidad pegada" not in texto


def test_una_unidad_pegada_dice_que_se_quite_la_unidad():
    texto = _error_de_ingesta(_con_prediccion_de_texto(lambda v: f"{v:.1f} h"))
    assert "unidad pegada" in texto and "separador decimal" not in texto


def test_pocas_clases_de_texto_dicen_que_parece_de_clasificacion():
    rng = np.random.default_rng(0)
    df = crudo(40)
    df["p"] = rng.choice(["a", "b", "c"], 40)
    texto = _error_de_ingesta(df)
    assert "crea un proyecto de clasificación" in texto and "«a»" in texto
    assert "unidad pegada" not in texto


def test_un_infinito_no_enseña_el_tipo_interno_de_numpy():
    df = crudo(40)
    df.loc[0, "p"] = np.inf
    texto = _error_de_ingesta(df)
    assert "np.float64" not in texto and "inf" in texto and "infinitos" in texto


def test_una_etiqueta_con_coma_decimal_dice_la_causa_y_que_se_pierden_todas():
    df = crudo(40)
    df["y"] = df["y"].map(lambda v: f"{v:.1f}".replace(".", ","))
    avisos = avisos_regresion(df, mapeo(), tarea())
    assert len(avisos) == 1
    assert "no traen un número" in avisos[0] and "separador decimal" in avisos[0]
    assert "Ninguna fila conserva etiqueta" in avisos[0]


def test_una_columna_de_booleanos_no_es_una_prediccion_numerica():
    df = crudo(40)
    df["p"] = [i % 2 == 0 for i in range(40)]
    assert "de texto" in _error_de_ingesta(df)


# --------------------------------------------------------------------------
# Revisión de regresión, B4: ninguna fila con el par completo
# --------------------------------------------------------------------------


def test_sin_ninguna_fila_con_el_par_numerico_el_motivo_no_habla_de_varianza():
    h, t = historia([crudo(200)])
    frame = h.frame().copy()
    frame[COL_PREDICTION_VALUE] = np.nan
    m = metricas_regresion(frame)
    assert m["n"] == 0 and m["motivo_r2"] == MOTIVO_SIN_PARES
    r = _por_clave(_evaluar_calidad(frame, t))
    assert r[("r2", None)].state == State.sin_datos and r[("r2", None)].motivo == MOTIVO_SIN_PARES
    assert r[("mean_absolute_error", None)].motivo == MOTIVO_SIN_PARES
