"""cross_alerts — Alertas cruzadas sobre el diario de uso (`usage_logs`).

Dos modos:

  - `calibracion`: fija la referencia del servicio (tasas de override y de
    error del modelo, globales, por subgrupo y por profesional) sobre una
    ventana sin alertas del modelo. Sin alertas.
  - `vigilancia`: aplica las reglas CX-1, CX-5 y CX-6 sobre la ventana
    recibida, cada subgrupo comparado contra su complemento (nunca contra
    la población entera). CX-2 a CX-4 (contra la referencia) son.

Ventana esperada: el diario de uso ACUMULADO de la versión activa (todas
las filas registradas hasta el momento con esa versión del modelo), no una
fase suelta. Motivo: con `min_group`/`min_positives` del orden de
30/20 filas, una sola fase corta (por ejemplo el evento E1, 450 filas) no
siempre reúne la potencia estadística para que la disparidad cruce los
umbrales, aunque el sesgo humano exista y sea real; verificado con datos
(2026-09-08): la ventana de override en jóvenes con `k_sub=0,25` da z=-1,74
sobre el evento solo y z=-5,16 sobre el evento acumulado con cinco
baselines previos de la misma versión (2700 filas). El motor de
orquestación (+) le pasa a `evaluate_cross` ese acumulado, no un batch
aislado.

Reglas implementadas aquí:
  - CX-1 (convergencia silenciosa): el subgrupo `g` sigue al modelo
    significativamente más que el resto (`z_override <= -z_alert`) Y el
    modelo yerra significativamente más en `g` sobre los casos que
    necesitaban la decisión favorable (`z_fnr >= model_error_z`, diferencia de tasa de
    falsos negativos). La tasa de error global no sirve como condición de
    modelo: con una etiqueta que aplica ruido de flip no estratificado por
    subgrupo (`feedback_dict`), el error global es idéntico en todos los
    subgrupos por construcción (verificado con datos); la FNR sí
    capta el daño real (0,806 en 18-35 frente a 0,122 en el resto, en el
    evento E1).
  - CX-5 (heterogeneidad por profesional): chi-cuadrado de override x profesional
    (solo profesionales con `n >= min_clinician`); vista de gestor, nunca nombra
    a un profesional concreto.
  - CX-6 (heterogeneidad por subgrupo sin alerta del modelo): `g` se aparta
    del resto en override (`|z_override| >= z_alert`) pero el monitor del
    modelo no lo ha señalado (`g not in model_alert_groups`); si el modelo
    ya alertó sobre `g`, CX-1 puede emitirse pero no CX-6 (redundante).
    Exclusión en cascada: el complemento de CX-6 deja fuera los
    grupos que el modelo ya señaló; con un atributo de dos grupos queda uno solo
    y CX-6 da `sin_datos`, con tres o más compara los que quedan.
    Una alerta por pareja: si CX-6 compara solo dos grupos, el z
    es simétrico y queda una alerta anclada en el grupo con menos override.
    Sin CX-6 donde hay CX-1: tras esa reducción, CX-6 se quita
    de los grupos con CX-1 disparada en la evaluación o ya viva (`cx1_alert_groups`).
  - CX-2 (automation disuse): la calidad del modelo está en `alerta`
    (`quality_state`, resuelto por el llamador sobre la última evaluación de
    `quality` de la versión activa) y el override global de la ventana está
    muy por encima de la referencia del servicio (`z_override_global >=
    z_alert`, dos proporciones sobre `CrossReference.override_rate`). Abre
    alerta severidad alta.
  - CX-3 (modelo sin aporte): la calidad está en `ok`, el override
    global está por encima de la referencia (mismo `z_override_global >=
    z_alert`) y el rescate (entre las filas donde el modelo se equivoca,
    fracción en que el profesional acierta) cae por debajo de la referencia
    (`z_rescue <= -z_alert`). Nunca abre alerta: se publica como
    `Measurement` en `state=aviso`, visible en la tarjeta de cruzadas y en
    `/capa-humana`, fuera de `/alertas`.
  - CX-4 (deskilling): dispara si `deskilling.fired` (la señal la
    calcula `human/ir_adapter.deskilling_view`, sobre la misma
    versión activa, `clinician=None, subgroup=None`; este módulo no importa
    `interaction_review`/§8.2: recibe `DeskillingInput`, una forma
    propia y desacoplada) O si `deskilling.level_z >= config.z_alert`
    (dos proporciones, como CX-2/CX-3, entre la tasa de
    acuerdo humano-modelo de la ventana de vigilancia y la de la
    referencia de calibración; lo calcula `evaluate_cross` con
    `_agreement_level_z`, no el llamador). Hace falta el disparo por nivel
    porque `deskilling.fired` es puramente de tendencia (pendiente OLS
    entre las ventanas del paquete): con un sesgo de automatización alto
    la convergencia ya está saturada dentro de la primera ventana (medido:
    barrido de 0 a 12 en `tests/human/test_cross_alerts.py`), la pendiente
    entre ventanas deja de verse y la tasa de disparo cae a 0 justo donde
    la erosión de criterio es mayor (la "campana"). Salvo que se
    cumpla el bloqueo por mejora real del modelo, que se
    aplica igual a los dos caminos: el modelo mejora de verdad
    (`model_accuracy_slope > eps`, `eps = 0.02`, mismo valor que
    `ir_adapter.EPS`) sin que el rescate haya caído (`rescue_slope is None
    or rescue_slope >= -eps`). Abre alerta severidad alta si dispara; nunca
    abre alerta en `sin_datos` (sin ninguna de las dos señales: tendencia
    Y nivel, `deskilling.agreement_slope is None and deskilling.level_z is
    None`, o sin señal en absoluto, `deskilling is None`).
  - `human_review_zero`: la tasa de override de la ventana de
    vigilancia está por debajo de `HUMAN_REVIEW_ZERO_THRESHOLD` (1 %) con
    `n` suficiente (`HUMAN_REVIEW_ZERO_MIN_N`, ver su justificación). Nunca
    abre `Alert` (mismo patrón que CX-3): se publica como
    `Measurement` en `state=aviso` con el motivo «ningún profesional ha
    corregido al modelo en N decisiones», distinto de `sin_datos` (`n`
    insuficiente). Sin referencia: es un umbral absoluto, no comparado con
    la calibración del servicio.
"""
from __future__ import annotations

import math
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field
from scipy.stats import chi2_contingency

from vigia.core.schema import CrossAlert, CrossAlertResult, Measurement, State


class CrossConfig(BaseModel):
    z_alert: float = 3.0
    model_error_z: float = 2.0
    min_group: int = 30
    min_clinician: int = 30
    min_positives: int = 20
    chi2_p: float = 1e-3
    min_expected: float = 5.0


class DeskillingInput(BaseModel):
    """Entrada de CX-4 (deskilling): la resuelve el llamador
    (`services/human_layer.py`) a partir de `human/ir_adapter.deskilling_view`,
    sobre la versión activa, `clinician=None, subgroup=None` (misma partición
    por versión que el resto de cruzadas). Forma propia, sin tipos de
    `interaction_review`: mantiene la frontera de imports de §8.2 (confinados
    a `ir_adapter.py`).

    `agreement_slope: None` (ventanas insuficientes con verdad de terreno
    para estimar una tendencia, `telemetry.deskilling_signal`) ya no basta
    por sí solo para `sin_datos`: con `level_z` calculable,
    `evaluate_cross` sigue pudiendo publicar `cx4_deskilling` en `ok` o
    `alerta` por nivel aunque no haya tendencia. Solo sin ninguna de las
    dos señales es `sin_datos`: ausencia de dato, no ausencia de señal.

    `level_z`: z de dos proporciones (como CX-2/CX-3) entre la
    tasa de acuerdo humano-modelo de la ventana de vigilancia y la de la
    referencia de calibración. `None` en la entrada que construye el
    llamador (`services/human_layer._deskilling_input_for_cx4`, que solo
    conoce la tendencia de `ir_adapter`); `evaluate_cross` lo rellena con
    `_agreement_level_z` justo antes de evaluar CX-4, porque ahí es donde
    viven `df_usage` (la ventana) y `CrossReference` (la referencia) a la
    vez."""

    fired: bool
    agreement_slope: float | None
    model_accuracy_slope: float | None
    rescue_slope: float | None
    reason: str
    level_z: float | None = None


class CrossReference(BaseModel):
    n: int
    override_rate: float | None
    model_error_rate: float | None
    # `rescue_rate` global de la referencia: `None` por
    # defecto para que un `ModelVersion.cross_reference_json` guardado antes
    # (sin esta clave) siga deserializando; CX-3 lo trata como
    # "sin referencia de rescate" (`sin_datos`), no como `0.0`.
    rescue_rate: float | None = None
    by_subgroup: dict[str, dict[str, float]] = Field(default_factory=dict)
    by_clinician: dict[str, dict[str, float]] = Field(default_factory=dict)


def two_proportion_z(k1: float, n1: float, k2: float, n2: float) -> float | None:
    """z de dos proporciones con pool (`None` si algún `n` es 0 o la varianza es 0)."""
    if n1 <= 0 or n2 <= 0:
        return None
    p1 = k1 / n1
    p2 = k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    var = p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)
    if var <= 0:
        return None
    return (p1 - p2) / math.sqrt(var)


MOTIVO_SIN_CONJUNTO_FAVORABLE = "sin conjunto favorable: solo calidad por grupo"


def _positivos(df: pd.DataFrame) -> pd.Series:
    """Máscara de los casos que necesitaban la decisión favorable (CX-1).

    Binario: `ground_truth == "refer"`. Multiclase: el diario trae
    además `truth_fav`, el 0/1 de pertenencia al conjunto favorable de la
    verdad; positivo es la verdad dentro del conjunto."""
    if "truth_fav" in df.columns:
        return df["truth_fav"] == 1
    return df["ground_truth"] == "refer"


def _fallos_del_modelo(df: pd.DataFrame) -> pd.Series:
    """Máscara de las filas en que el modelo no dio la decisión favorable.
    Multiclase: la salida fuera del conjunto favorable (`model_fav == 0`)."""
    if "model_fav" in df.columns:
        return df["model_fav"] == 0
    return df["model_output"] == "no-refer"


def _errores_del_modelo(df: pd.DataFrame) -> pd.Series:
    """Máscara de las filas con verdad registrada en que el modelo falla
    (`model_output != ground_truth`). Una fila sin verdad no es un error del
    modelo: la verdad puede llegar más tarde que la decisión."""
    return df["ground_truth"].notna() & (df["model_output"] != df["ground_truth"])


def _sin_conjunto_favorable(df: pd.DataFrame) -> bool:
    """Multiclase sin conjunto favorable: el diario trae la columna
    `conjunto_favorable` y es falsa. Nada que lea la pertenencia se puede
    calcular."""
    return (
        "conjunto_favorable" in df.columns
        and len(df) > 0
        and not bool(df["conjunto_favorable"].astype(bool).any())
    )


def _block(df: pd.DataFrame) -> dict[str, float | None]:
    """Bloque de referencia: tasas globales más `fnr`/`positives`/`rescue_rate`
    (informativo): `positives` son las filas con `ground_truth`
    favorable ("refer") y `fnr` la fracción de ellas predichas "no-refer".
    `rescue_rate` (CX-3): de las filas donde el modelo se equivoca
    (`model_output != ground_truth`), la fracción en que el profesional
    acierta (`human_decision == ground_truth`; mismo patrón que
    `interaction_review.telemetry.rescue_rate`, pero sobre el diario de uso,
    no sobre `Record`). `fnr` y `rescue_rate` son `nan` (no `None`) si no hay
    filas que los definan, para que el bloque siga siendo un
    `dict[str, float]` válido; CX-4 (deskilling) no usa este bloque, vive en
    `human/ir_adapter.py`.
    """
    n = len(df)
    if n == 0:
        return {
            "n": 0,
            "override_rate": None,
            "model_error_rate": None,
            "fnr": float("nan"),
            "positives": 0,
            "rescue_rate": float("nan"),
        }
    override = float((df["human_decision"] != df["model_output"]).mean())
    wrong_df = df[_errores_del_modelo(df)]
    model_error = float(len(wrong_df) / n)
    positives_df = df[_positivos(df)]
    positives = len(positives_df)
    fnr = (
        float(_fallos_del_modelo(positives_df).mean())
        if positives
        else float("nan")
    )
    rescue_rate = (
        float((wrong_df["human_decision"] == wrong_df["ground_truth"]).mean())
        if len(wrong_df)
        else float("nan")
    )
    return {
        "n": n,
        "override_rate": override,
        "model_error_rate": model_error,
        "fnr": fnr,
        "positives": positives,
        "rescue_rate": rescue_rate,
    }


def _sin_nan(valor: float) -> float | None:
    """`None` si `valor` es `nan`: los bloques de `_block` guardan
    `nan` para que el `dict` siga siendo homogéneo, pero `CrossReference`
    (y las funciones que la consumen) esperan `None` en el hueco."""
    return None if math.isnan(valor) else valor


def build_reference(df_usage: pd.DataFrame) -> CrossReference:
    """Referencia del servicio (modo calibración): tasas globales, por
    subgrupo y por profesional, sobre `df_usage`.
    """
    top = _block(df_usage)
    by_subgroup = {str(g): _block(gdf) for g, gdf in df_usage.groupby("subgroup")}
    by_clinician = {
        str(c): _block(cdf) for c, cdf in df_usage.groupby("clinician_pseudonym")
    }
    return CrossReference(
        n=int(top["n"]),
        override_rate=top["override_rate"],
        model_error_rate=top["model_error_rate"],
        rescue_rate=_sin_nan(top["rescue_rate"]),
        by_subgroup=by_subgroup,
        by_clinician=by_clinician,
    )


def _counts(df: pd.DataFrame) -> tuple[int, int, int]:
    """(n, k_override, k_error) de `df`."""
    n = len(df)
    k_override = int((df["human_decision"] != df["model_output"]).sum())
    k_error = int(_errores_del_modelo(df).sum())
    return n, k_override, k_error


def _fnr_counts(df: pd.DataFrame) -> tuple[int, int]:
    """(positivos, falsos_negativos) de `df`.

    Positivos = filas con `ground_truth` favorable ("refer"); falsos
    negativos = de esas, las que el modelo predijo "no-refer". Base de la
    condición de modelo de CX-1: diferencia de FNR, no de error
    global.
    """
    positives_df = df[_positivos(df)]
    pos = len(positives_df)
    fn = int(_fallos_del_modelo(positives_df).sum())
    return pos, fn


def _motivo_grupo_insuficiente(n_g: int, n_comp: int, minimo: int) -> str:
    """Motivo en lenguaje llano del `sin_datos` por decisiones insuficientes.

    Sin códigos internos: mínimos y lo alcanzado, no `min_group` ni el
    nombre del subgrupo en crudo (ya va aparte en `group_code`).
    """
    partes = []
    if n_g < minimo:
        partes.append(f"{n_g} decisiones registradas en el subgrupo de las {minimo} necesarias")
    if n_comp < minimo:
        partes.append(f"{n_comp} decisiones registradas en el resto de las {minimo} necesarias")
    return "; ".join(partes) if partes else f"menos de {minimo} decisiones por grupo"


def _motivo_positivos_insuficientes(pos_g: int, pos_comp: int, minimo: int) -> str:
    """Motivo del `sin_datos` de CX-1 cuando faltan casos que necesitaban la decisión favorable."""
    partes = []
    if pos_g < minimo:
        partes.append(
            f"{pos_g} casos que necesitaban la decisión favorable en el subgrupo "
            f"de los {minimo} necesarios"
        )
    if pos_comp < minimo:
        partes.append(
            f"{pos_comp} casos que necesitaban la decisión favorable en el resto "
            f"de los {minimo} necesarios"
        )
    return (
        "; ".join(partes)
        if partes
        else f"menos de {minimo} casos que necesitaban la decisión favorable por grupo"
    )


MOTIVO_CX6_UN_SOLO_GRUPO = "un solo grupo tras excluir el señalado por el modelo"


def _cx1_cx6_for_group(
    g: str,
    df_g: pd.DataFrame,
    df_comp: pd.DataFrame,
    *,
    config: CrossConfig,
    model_alert_groups: set[str],
    df_comp_cx6: pd.DataFrame | None = None,
    sin_favorable: bool = False,
) -> tuple[list[Measurement], list[CrossAlert]]:
    """CX-1 y CX-6 de un subgrupo `g`.

    `df_comp_cx6` es el complemento de CX-6 tras la exclusión en
    cascada de los grupos que el modelo ya señaló; `None` es el complemento
    completo, como hasta ahora (CX-1 usa siempre el completo).
    """
    measurements: list[Measurement] = []
    alerts: list[CrossAlert] = []

    n_g, k_ov_g, _k_err_g = _counts(df_g)
    n_comp, k_ov_comp, _k_err_comp = _counts(df_comp)
    pos_g, fn_g = _fnr_counts(df_g)
    pos_comp, fn_comp = _fnr_counts(df_comp)

    computable = n_g >= config.min_group and n_comp >= config.min_group
    z_override = two_proportion_z(k_ov_g, n_g, k_ov_comp, n_comp) if computable else None

    fnr_computable = pos_g >= config.min_positives and pos_comp >= config.min_positives
    z_fnr = two_proportion_z(fn_g, pos_g, fn_comp, pos_comp) if fnr_computable else None

    fnr_group = (fn_g / pos_g) if pos_g else None
    fnr_complement = (fn_comp / pos_comp) if pos_comp else None

    override_rate_g = (k_ov_g / n_g) if n_g else None
    override_rate_comp = (k_ov_comp / n_comp) if n_comp else None

    # Sin conjunto favorable, CX-1 no se puede leer: ni el override ni
    # el FNR dicen nada de «derivar», y la medida da `sin_datos`, nunca un 0.
    if sin_favorable:
        computable = False
        fnr_computable = False
        z_override = None
        z_fnr = None

    cx1_fires = (
        computable
        and fnr_computable
        and z_override is not None
        and z_fnr is not None
        and z_override <= -config.z_alert
        and z_fnr >= config.model_error_z
    )
    state_override = State.sin_datos if not computable else (State.alerta if cx1_fires else State.ok)
    state_fnr = State.sin_datos if not fnr_computable else (State.alerta if cx1_fires else State.ok)

    measurements.append(
        Measurement(
            metric_key=f"cx1_override_z:{g}",
            value=z_override,
            state=state_override,
            group_code=g,
            motivo=(
                MOTIVO_SIN_CONJUNTO_FAVORABLE
                if sin_favorable
                else _motivo_grupo_insuficiente(n_g, n_comp, config.min_group)
                if not computable
                else None
            ),
            extra={"n": n_g, "n_complemento": n_comp},
        )
    )
    measurements.append(
        Measurement(
            metric_key=f"cx1_model_fnr_z:{g}",
            value=z_fnr,
            state=state_fnr,
            group_code=g,
            motivo=(
                MOTIVO_SIN_CONJUNTO_FAVORABLE
                if sin_favorable
                else _motivo_positivos_insuficientes(pos_g, pos_comp, config.min_positives)
                if not fnr_computable
                else None
            ),
            extra={
                "fnr_group": fnr_group,
                "fnr_complement": fnr_complement,
                "positives_group": pos_g,
                "positives_complement": pos_comp,
            },
        )
    )
    if cx1_fires:
        alerts.append(
            CrossAlert(
                rule="CX-1",
                group=g,
                value=override_rate_g,
                reference=override_rate_comp,
                z=z_override,
                n=n_g,
                state=State.alerta,
                motivo=(
                    f"el subgrupo {g} se aparta del modelo menos que el resto "
                    f"(z = {z_override:.1f}) mientras el modelo deja sin la decisión "
                    f"favorable a más de sus casos que la necesitaban "
                    f"(FNR {fnr_group:.2f} frente a {fnr_complement:.2f}, "
                    f"z = {z_fnr:.1f})"
                ),
            )
        )

    cascada = df_comp_cx6 is not None
    df_comp6 = df_comp_cx6 if cascada else df_comp
    n_comp6, k_ov_comp6, _k_err_comp6 = _counts(df_comp6)
    override_rate_comp6 = (k_ov_comp6 / n_comp6) if n_comp6 else None
    computable6 = n_g >= config.min_group and n_comp6 >= config.min_group
    z6 = two_proportion_z(k_ov_g, n_g, k_ov_comp6, n_comp6) if computable6 else None
    cx6_computable = computable6 and z6 is not None
    cx6_fires = cx6_computable and abs(z6) >= config.z_alert and g not in model_alert_groups
    state6 = State.sin_datos if not cx6_computable else (State.alerta if cx6_fires else State.ok)
    if cx6_computable:
        motivo6 = None
    elif cascada and n_comp6 == 0 and n_comp > 0:
        motivo6 = MOTIVO_CX6_UN_SOLO_GRUPO
    else:
        motivo6 = _motivo_grupo_insuficiente(n_g, n_comp6, config.min_group)
    measurements.append(
        Measurement(
            metric_key=f"cx6_override_z:{g}",
            value=z6,
            state=state6,
            group_code=g,
            motivo=motivo6,
            extra={"n": n_g, "n_complemento": n_comp6},
        )
    )
    if cx6_fires:
        alerts.append(
            CrossAlert(
                rule="CX-6",
                group=g,
                value=override_rate_g,
                reference=override_rate_comp6,
                z=z6,
                n=n_g,
                state=State.alerta,
                motivo=(
                    f"el subgrupo {g} se aparta del resto en override "
                    f"(z = {z6:.1f}) sin que el monitor del modelo lo haya señalado"
                ),
            )
        )

    return measurements, alerts


def _cx6_una_por_pareja(measurements: list[Measurement], alerts: list[CrossAlert]) -> None:
    """Con un atributo de dos grupos, CX-6 es una alerta por pareja.

    Cada grupo se compara con el otro y el z es simétrico: si dispara uno, dispara
    el otro con el signo cambiado, y el estadístico no dice cuál de los dos es el
    problema. Se deja una sola alerta, anclada en el grupo con menos override, la
    dirección de riesgo de CX-1 y del deskilling (el que más se fía del modelo; el
    `group_code` tiene que ser un subgrupo real: lo usan el enlace a deskilling y la
    clave de `sync_candidates`), con las dos tasas en el motivo. La medida del otro
    grupo conserva su z y pasa a `ok` con un motivo que remite a la pareja, para que
    `human_layer._cross_candidates` no abra una segunda alerta espejo.
    """
    cx6 = [a for a in alerts if a.rule == "CX-6"]
    if len(cx6) != 2:
        return
    ancla, otra = sorted(cx6, key=lambda a: (a.value or 0.0, a.group))
    motivo_pareja = f"comparación simétrica con {ancla.group}: la alerta de la pareja va en ese grupo"
    for i, m in enumerate(measurements):
        if m.metric_key == f"cx6_override_z:{otra.group}":
            measurements[i] = m.model_copy(
                update={
                    "state": State.ok,
                    "motivo": motivo_pareja,
                    "extra": {**(m.extra or {}), "pareja_de": ancla.group},
                }
            )
    alerts.remove(otra)
    alerts[alerts.index(ancla)] = ancla.model_copy(
        update={
            "motivo": (
                f"{ancla.group} y {otra.group} difieren en override "
                f"({ancla.value:.2f} frente a {otra.value:.2f}, z = {abs(ancla.z or 0.0):.1f}) "
                "sin que el monitor del modelo lo haya señalado; con dos grupos la "
                "comparación es simétrica y no indica cuál de los dos es el problema"
            )
        }
    )


MOTIVO_CX6_CUBIERTA_POR_CX1 = (
    "el grupo ya tiene una alerta CX-1 (convergencia silenciosa): "
    "la señal de override va en esa alerta"
)


def _cx6_suprimir_con_cx1(
    measurements: list[Measurement], alerts: list[CrossAlert], con_cx1: set[str]
) -> None:
    """Quita las alertas CX-6 de los grupos de `con_cx1`.

    Se llama tras `_cx6_una_por_pareja`. La medida `cx6_override_z:g` conserva su z
    y pasa a `ok` con el motivo propio y `extra["cubierta_por"] = "CX-1"`, para que
    `human_layer._cross_candidates` no abra ni mantenga CX-6 en ese grupo.
    """
    cubiertas = [a for a in alerts if a.rule == "CX-6" and a.group in con_cx1]
    for a in cubiertas:
        for i, m in enumerate(measurements):
            if m.metric_key == f"cx6_override_z:{a.group}":
                measurements[i] = m.model_copy(
                    update={
                        "state": State.ok,
                        "motivo": MOTIVO_CX6_CUBIERTA_POR_CX1,
                        "extra": {**(m.extra or {}), "cubierta_por": "CX-1"},
                    }
                )
            elif (m.extra or {}).get("pareja_de") == a.group:
                # La pareja remitía a la alerta de `a.group`, que ya no existe: el
                # motivo no puede seguir diciendo que la alerta va en ese grupo.
                measurements[i] = m.model_copy(
                    update={
                        "motivo": (
                            f"comparación simétrica con {a.group}: ese grupo ya tiene una "
                            "alerta CX-1 (convergencia silenciosa) y la señal de override va en ella"
                        )
                    }
                )
        alerts.remove(a)


def _cx5(df_usage: pd.DataFrame, *, config: CrossConfig) -> tuple[Measurement, CrossAlert | None]:
    counts = df_usage.groupby("clinician_pseudonym").size()
    qualifying = counts[counts >= config.min_clinician].index.tolist()

    if len(qualifying) < 2:
        return (
            Measurement(
                metric_key="cx5_chi2_p",
                value=None,
                state=State.sin_datos,
                motivo=(
                    f"{len(qualifying)} profesionales con al menos {config.min_clinician} "
                    "decisiones registradas; hacen falta al menos 2 para comparar"
                ),
                extra={"n_clinicos": len(qualifying)},
            ),
            None,
        )

    table = []
    for clin in qualifying:
        df_c = df_usage[df_usage["clinician_pseudonym"] == clin]
        _, k_ov, _ = _counts(df_c)
        table.append([k_ov, len(df_c) - k_ov])

    # Una columna a cero (0% o 100% de override en todos los clínicos
    # cualificados) hace que scipy calcule una frecuencia esperada nula y
    # lance ValueError antes de que podamos comprobar min_expected: se
    # descarta aquí, sin_datos, antes de llamar a chi2_contingency.
    col_totals = [sum(row[c] for row in table) for c in range(2)]
    if any(total == 0 for total in col_totals):
        return (
            Measurement(
                metric_key="cx5_chi2_p",
                value=None,
                state=State.sin_datos,
                motivo=(
                    f"los {len(qualifying)} profesionales cualificados coinciden en el override "
                    "(0 % o 100 % en todos): no hay variación que comparar"
                ),
                extra={"n_clinicos": len(qualifying)},
            ),
            None,
        )

    chi2_stat, p_value, _dof, expected = chi2_contingency(table)
    if expected.min() < config.min_expected:
        return (
            Measurement(
                metric_key="cx5_chi2_p",
                value=None,
                state=State.sin_datos,
                motivo=(
                    f"frecuencia esperada por celda por debajo de {config.min_expected:.0f} "
                    f"con {len(qualifying)} profesionales cualificados"
                ),
                extra={"n_clinicos": len(qualifying)},
            ),
            None,
        )

    fires = p_value < config.chi2_p
    measurement = Measurement(
        metric_key="cx5_chi2_p",
        value=float(p_value),
        state=State.alerta if fires else State.ok,
        extra={"n_clinicos": len(qualifying), "chi2": float(chi2_stat)},
    )
    alert = None
    if fires:
        alert = CrossAlert(
            rule="CX-5",
            group=None,
            value=float(p_value),
            reference=config.chi2_p,
            z=float(chi2_stat),
            n=len(df_usage),
            state=State.alerta,
            motivo=(
                f"{len(qualifying)} profesionales muestran patrones de override heterogéneos "
                f"(chi2, p = {p_value:.4f})"
            ),
        )
    return measurement, alert


def _reconstructed_count(rate: float | None, n: int | None) -> int | None:
    """`round(rate * n)` o `None` si falta cualquiera de los dos.

    La referencia (`CrossReference`) guarda tasas, no recuentos: para el `z`
    de dos proporciones de CX-2/CX-3 hace falta reconstruir el `k` del lado
    de la referencia a partir de la tasa que se fijó en la calibración
    (`rate` es exactamente `k / n` en ese momento, así que `round` recupera
    el entero salvo el redondeo de coma flotante, sin margen práctico).
    """
    if rate is None or n is None or n <= 0:
        return None
    return round(rate * n)


def _agreement_level_z(df_usage: pd.DataFrame, reference: CrossReference) -> float | None:
    """z de dos proporciones entre la tasa de acuerdo humano-modelo
    de `df_usage` y la de `reference` (`agreement = 1 - override`: reutiliza
    los mismos recuentos que `_cx2`/`_cx3`, con el complementario del
    override). `None` si no hay ventana o referencia suficiente, igual que
    `_cx2`."""
    n, k_ov, _k_err = _counts(df_usage)
    if n <= 0:
        return None
    n_ref = reference.n
    k_ov_ref = _reconstructed_count(reference.override_rate, n_ref)
    if k_ov_ref is None:
        return None
    return two_proportion_z(n - k_ov, n, n_ref - k_ov_ref, n_ref)


# HUMAN_REVIEW_ZERO_MIN_N: con una tasa real de override del 1 %
# (el umbral), `(1 - 0.01) ** n` es la probabilidad de ver CERO overrides por
# puro azar en una ventana de `n` decisiones. En n = 300, (0.99)**300 ≈ 4,9 %:
# por debajo de esa `n`, "cero correcciones" no distingue "nadie corrige" de
# "poca muestra" más de un 5 % de las veces; por encima, si la tasa real
# fuese 1 % o más, la ventana casi seguro habría visto al menos una
# corrección. Un diario normal (con overrides por encima del 1 %) no
# la dispara.
HUMAN_REVIEW_ZERO_THRESHOLD = 0.01
HUMAN_REVIEW_ZERO_MIN_N = 300


def _human_review_zero(df_usage: pd.DataFrame) -> Measurement:
    """Señal `human_review_zero`: la tasa de override de la
    ventana de vigilancia está por debajo de `HUMAN_REVIEW_ZERO_THRESHOLD`
    con `n` suficiente (`HUMAN_REVIEW_ZERO_MIN_N`, justificación arriba).
    `sin_datos` si `n` no llega. Se publica en `state=aviso` cuando dispara y,
    desde `_cross_candidates` de `services/human_layer.py` la
    convierte en alerta de severidad `media`; con `sin_datos` no abre nada."""
    n, k_ov, _k_err = _counts(df_usage)
    if n < HUMAN_REVIEW_ZERO_MIN_N:
        return Measurement(
            metric_key="human_review_zero",
            value=(k_ov / n) if n else None,
            state=State.sin_datos,
            motivo=f"n insuficiente para valorar la revisión humana ({n} de {HUMAN_REVIEW_ZERO_MIN_N})",
            extra={"n": n},
        )
    override_rate = k_ov / n
    fires = override_rate < HUMAN_REVIEW_ZERO_THRESHOLD
    return Measurement(
        metric_key="human_review_zero",
        value=override_rate,
        state=State.aviso if fires else State.ok,
        motivo=f"ningún profesional ha corregido al modelo en {n} decisiones" if fires else None,
        extra={"n": n, "n_override": k_ov},
    )


def _cx2(
    df_usage: pd.DataFrame,
    *,
    reference: CrossReference,
    config: CrossConfig,
    quality_state: str | None,
) -> tuple[Measurement, CrossAlert | None]:
    """CX-2, automation disuse: calidad en `alerta` y override global
    de la ventana significativamente por encima de `reference.override_rate`
    (dos proporciones, `z >= config.z_alert`, global, no por subgrupo)."""
    n, k_ov, _k_err = _counts(df_usage)
    n_ref = reference.n
    k_ov_ref = _reconstructed_count(reference.override_rate, n_ref)
    computable = n > 0 and k_ov_ref is not None
    z = two_proportion_z(k_ov, n, k_ov_ref, n_ref) if computable else None
    override_rate = (k_ov / n) if n else None

    quality_alerta = quality_state == State.alerta.value
    fires = computable and quality_alerta and z is not None and z >= config.z_alert
    state = State.sin_datos if not computable else (State.alerta if fires else State.ok)

    measurement = Measurement(
        metric_key="cx2_override_z",
        value=z,
        state=state,
        motivo=(
            "la referencia del servicio no tiene datos suficientes de override"
            if not computable
            else None
        ),
        extra={"n": n, "n_referencia": n_ref, "quality_state": quality_state},
    )
    alert = None
    if fires:
        assert z is not None and override_rate is not None
        alert = CrossAlert(
            rule="CX-2",
            group=None,
            value=override_rate,
            reference=reference.override_rate,
            z=z,
            n=n,
            state=State.alerta,
            motivo=(
                "la calidad del modelo está en alerta y, pese a ello, el profesional "
                f"sigue automatizando la decisión por encima de su patrón de referencia "
                f"(z = {z:.1f})"
            ),
        )
    return measurement, alert


def _cx3(
    df_usage: pd.DataFrame,
    *,
    reference: CrossReference,
    config: CrossConfig,
    quality_state: str | None,
) -> tuple[Measurement, Measurement]:
    """CX-3, modelo sin aporte: calidad en `ok`, override global por
    encima de la referencia (mismo `z_override_global >= config.z_alert`) y
    rescate por debajo de la referencia (`z_rescue <= -config.z_alert`).

    Nunca abre `Alert`: las dos medidas se publican en `state=aviso`
    cuando dispara, y `_cross_candidates` no las convierte en candidato (por
    diseño: `_ESTADOS_OBSERVACION` de `alerting.py` no incluye `aviso`, así
    que ninguna regla cruzada puede abrir alerta ahí).
    """
    n, k_ov, _k_err = _counts(df_usage)
    n_ref = reference.n
    k_ov_ref = _reconstructed_count(reference.override_rate, n_ref)
    computable_override = n > 0 and k_ov_ref is not None
    z_override = two_proportion_z(k_ov, n, k_ov_ref, n_ref) if computable_override else None

    n_wrong_ref = _reconstructed_count(reference.model_error_rate, n_ref)
    k_rescue_ref = _reconstructed_count(reference.rescue_rate, n_wrong_ref)

    wrong_df = df_usage[_errores_del_modelo(df_usage)]
    n_wrong = len(wrong_df)
    k_rescue = int((wrong_df["human_decision"] == wrong_df["ground_truth"]).sum()) if n_wrong else 0

    computable_rescue = n_wrong > 0 and k_rescue_ref is not None and (n_wrong_ref or 0) > 0
    z_rescue = (
        two_proportion_z(k_rescue, n_wrong, k_rescue_ref, n_wrong_ref) if computable_rescue else None
    )

    computable = computable_override and computable_rescue
    quality_ok = quality_state == State.ok.value
    fires = (
        computable
        and quality_ok
        and z_override is not None
        and z_override >= config.z_alert
        and z_rescue is not None
        and z_rescue <= -config.z_alert
    )
    state = State.sin_datos if not computable else (State.aviso if fires else State.ok)
    if not computable:
        motivo = "la referencia del servicio no tiene datos suficientes de override o de rescate"
    elif fires:
        motivo = (
            "el modelo acierta lo bastante (calidad en ok) pero, cuando falla, el "
            f"profesional ya no lo corrige más que antes (override z = {z_override:.1f}, "
            f"rescate z = {z_rescue:.1f})"
        )
    else:
        motivo = None

    extra_override = {"n": n, "n_referencia": n_ref, "quality_state": quality_state}
    extra_rescue = {"n_modelo_erroneo": n_wrong, "n_modelo_erroneo_referencia": n_wrong_ref}
    return (
        Measurement(metric_key="cx3_override_z", value=z_override, state=state, motivo=motivo, extra=extra_override),
        Measurement(metric_key="cx3_rescue_z", value=z_rescue, state=state, motivo=motivo, extra=extra_rescue),
    )


_CX4_EPS = 0.02  # Mismo valor que `human.ir_adapter.EPS` (deskilling_signal).


def _cx4(
    n: int,
    deskilling: DeskillingInput | None,
    *,
    config: CrossConfig,
) -> tuple[Measurement, CrossAlert | None]:
    """CX-4, erosión del criterio (deskilling): dispara por
    tendencia (`deskilling.fired`) O por nivel (`deskilling.level_z >=
    config.z_alert`), salvo que se cumpla el bloqueo de la revisión
    adversarial (problema 18): el modelo mejora de verdad
    (`model_accuracy_slope > eps`) sin que el rescate haya caído
    (`rescue_slope is None or rescue_slope >= -eps`). El bloqueo se aplica
    igual dispare por tendencia o por nivel: una mejora real del modelo sin
    caída de rescate no es erosión de criterio.

    El camino por nivel existe porque la tendencia sola tiene un punto
    ciego (medido con un barrido de sesgo de automatización de 0 a
    12): con un sesgo alto la convergencia ya satura dentro de la primera
    ventana del paquete, la pendiente entre ventanas deja de verse
    (`agreement_slope` cerca de 0, no `> eps`) y la tasa de disparo por
    tendencia cae justo donde la erosión es mayor. El nivel (acuerdo de la
    ventana frente a la referencia de calibración, dos proporciones como
    CX-2/CX-3) sigue siendo extremo ahí y lo capta.

    `sin_datos` (nunca abre alerta) si no hay señal en absoluto
    (`deskilling is None`, sin versión activa o sin diario, resuelto por el
    llamador) o si no hay NINGUNA de las dos señales (`agreement_slope is
    None and level_z is None`): sin ventanas suficientes con verdad de
    terreno para la tendencia Y sin ventana o referencia suficiente para el
    nivel.
    """
    if deskilling is None or (deskilling.agreement_slope is None and deskilling.level_z is None):
        return (
            Measurement(
                metric_key="cx4_deskilling",
                value=0.0,
                state=State.sin_datos,
                motivo=(
                    "sin señal de deskilling disponible (sin versión activa o sin diario de uso)"
                    if deskilling is None
                    else "ventanas insuficientes con verdad de terreno para estimar una tendencia o un nivel"
                ),
                extra={"reason": None if deskilling is None else deskilling.reason},
            ),
            None,
        )

    bloqueado = (
        deskilling.model_accuracy_slope is not None
        and deskilling.model_accuracy_slope > _CX4_EPS
        and (deskilling.rescue_slope is None or deskilling.rescue_slope >= -_CX4_EPS)
    )
    trend_fires = deskilling.fired
    level_fires = deskilling.level_z is not None and deskilling.level_z >= config.z_alert
    disparada = trend_fires or level_fires
    fires = disparada and not bloqueado
    measurement = Measurement(
        metric_key="cx4_deskilling",
        value=1.0 if disparada else 0.0,
        state=State.alerta if fires else State.ok,
        extra={
            "agreement_slope": deskilling.agreement_slope,
            "model_accuracy_slope": deskilling.model_accuracy_slope,
            "rescue_slope": deskilling.rescue_slope,
            "level_z": deskilling.level_z,
            "trend_fires": trend_fires,
            "level_fires": level_fires,
            "bloqueado": bloqueado,
            "reason": deskilling.reason,
        },
    )
    alert = None
    if fires:
        motivos = []
        if trend_fires:
            motivos.append(deskilling.reason)
        if level_fires:
            assert deskilling.level_z is not None
            motivos.append(
                "el acuerdo humano-modelo de la ventana se aparta de la referencia de "
                f"calibración (z = {deskilling.level_z:.1f})"
            )
        alert = CrossAlert(
            rule="CX-4",
            group=None,
            value=1.0,
            reference=None,
            z=deskilling.level_z,
            n=n,
            state=State.alerta,
            motivo=(
                "el profesional converge con el modelo sin que su propio criterio o el "
                f"rescate lo sostengan ({'; '.join(motivos)})"
            ),
        )
    return measurement, alert


def evaluate_cross(
    df_usage: pd.DataFrame,
    *,
    reference: CrossReference | None = None,
    config: CrossConfig | None = None,
    model_alert_groups: set[str] | None = None,
    quality_state: str | None = None,
    deskilling: DeskillingInput | None = None,
    mode: Literal["calibracion", "vigilancia"] | None = None,
    cx1_alert_groups: set[str] | None = None,
) -> CrossAlertResult:
    """Evalúa las alertas cruzadas sobre `df_usage` (ventana de diario de uso).

    `cx1_alert_groups` son los grupos con una alerta CX-1 viva de
    la versión activa; los resuelve el llamador (`services/human_layer.py`), este
    módulo no toca la base de datos. CX-6 no se emite en un grupo que ya tiene
    CX-1, ni porque CX-1 dispare en esta evaluación ni porque esté viva ya: la
    señal de override del grupo va en la alerta de convergencia silenciosa. La
    supresión se aplica DESPUÉS de la reducción por pareja (`_cx6_una_por_pareja`);
    antes, con dos grupos quedaría una sola alerta CX-6 en el grupo con más
    override y la reducción no actuaría (alerta espejo en el grupo equivocado).
    Efecto aceptado: (una alerta nunca se cierra sola) la supresión es
    pegajosa; CX-6 sigue callada en ese grupo hasta que una persona cierre o
    retire la CX-1.

    `quality_state` es el `worst_state` de la última evaluación del monitor
    `quality` de la versión activa (CX-2/CX-3); lo resuelve el
    llamador (`services/human_layer.py`), este módulo no toca la base de
    datos. `None` (versión sin evaluación de `quality` todavía) hace que
    ni CX-2 ni CX-3 disparen, sin romper el cálculo.

    `deskilling` (CX-4) es la señal ya resuelta por el llamador desde
    `human/ir_adapter.deskilling_view`; `None` si no hay versión
    activa o diario de uso. Este módulo nunca importa `interaction_review`
    (§8.2): recibe `DeskillingInput`, forma propia.
    """
    config = config or CrossConfig()
    model_alert_groups = model_alert_groups or set()
    if mode is None:
        mode = "calibracion" if reference is None else "vigilancia"

    if mode == "calibracion":
        ref = build_reference(df_usage)
        measurements = [
            Measurement(
                metric_key=f"override_rate:{g}",
                value=block["override_rate"],
                state=State.ok,
                group_code=g,
                extra={"n": block["n"]},
            )
            for g, block in ref.by_subgroup.items()
        ]
        return CrossAlertResult(
            mode="calibracion",
            alerts=[],
            measurements=measurements,
            reference=ref.model_dump(),
        )

    assert reference is not None
    measurements: list[Measurement] = []
    alerts: list[CrossAlert] = []

    sin_favorable = _sin_conjunto_favorable(df_usage)
    for g, df_g in df_usage.groupby("subgroup"):
        df_comp = df_usage[df_usage["subgroup"] != g]
        # CX-6 compara contra los grupos que quedan tras excluir
        # los que el modelo ya señaló. Sin exclusiones, el complemento de
        # siempre; con un par, queda un solo grupo y CX-6 da `sin_datos`.
        excluidos = {str(x) for x in model_alert_groups}
        df_comp_cx6 = (
            df_comp[~df_comp["subgroup"].astype(str).isin(excluidos)] if excluidos else None
        )
        m, a = _cx1_cx6_for_group(
            str(g),
            df_g,
            df_comp,
            config=config,
            model_alert_groups=model_alert_groups,
            df_comp_cx6=df_comp_cx6,
            sin_favorable=sin_favorable,
        )
        measurements.extend(m)
        alerts.extend(a)

    # Si CX-6 compara solo dos grupos (dos en el atributo, o dos
    # que quedan tras la cascada), la comparación es simétrica: una alerta por pareja.
    comparados = set(df_usage["subgroup"].astype(str)) - {str(x) for x in model_alert_groups}
    if len(comparados) == 2:
        _cx6_una_por_pareja(measurements, alerts)

    # CX-6 se calla en los grupos con CX-1 (disparada ahora o viva).
    _cx6_suprimir_con_cx1(
        measurements,
        alerts,
        {a.group for a in alerts if a.rule == "CX-1" and a.group is not None}
        | {str(x) for x in (cx1_alert_groups or set())},
    )

    m5, a5 = _cx5(df_usage, config=config)
    measurements.append(m5)
    if a5 is not None:
        alerts.append(a5)

    m2, a2 = _cx2(df_usage, reference=reference, config=config, quality_state=quality_state)
    measurements.append(m2)
    if a2 is not None:
        alerts.append(a2)

    m3_override, m3_rescue = _cx3(
        df_usage, reference=reference, config=config, quality_state=quality_state
    )
    measurements.append(m3_override)
    measurements.append(m3_rescue)

    if deskilling is not None:
        # `level_z` se calcula aquí, no en el llamador: es donde
        # viven `df_usage` (la ventana) y `reference` (la calibración) a la
        # vez; `services/human_layer._deskilling_input_for_cx4` solo conoce
        # la tendencia de `ir_adapter`.
        deskilling = deskilling.model_copy(
            update={"level_z": _agreement_level_z(df_usage, reference)}
        )
    m4, a4 = _cx4(len(df_usage), deskilling, config=config)
    measurements.append(m4)
    if a4 is not None:
        alerts.append(a4)

    measurements.append(_human_review_zero(df_usage))

    if reference.override_rate is not None:
        window_override = _block(df_usage)["override_rate"]
        delta = (
            None
            if window_override is None
            else window_override - reference.override_rate
        )
        measurements.append(
            Measurement(metric_key="override_rate_delta", value=delta, state=State.ok)
        )

    return CrossAlertResult(
        mode="vigilancia",
        alerts=alerts,
        measurements=measurements,
        reference=reference.model_dump(),
    )
