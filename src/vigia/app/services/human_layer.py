"""Diario de uso y alertas cruzadas.

Ingesta del CSV de uso, evaluación cruzada (`vigia.human.cross_alerts`)
con calibración la primera vez por versión y vigilancia después, y exportación. El
deskilling y el dossier viven en otros servicios.

`interaction_review.telemetry.REQUIRED_COLUMNS` fija las columnas obligatorias del
CSV (`date`, `human_decision`, `model_output`, `ground_truth`); esos tres últimos
campos aceptan tanto las etiquetas del harness (`refer`/`no-refer`) como enteros
(`1`/`0`) y se guardan siempre como entero en `usage_log`. `evaluate_cross` exige las
etiquetas textuales del harness (compara literalmente con `"refer"`), así que
`usage_frame` hace el camino de vuelta al reconstruir el frame para el motor.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from datetime import date as date_cls
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from vigia import __version__ as APP_VERSION
from vigia.app.bus import EventBus
from vigia.app.errores import no_encontrado
from vigia.app.events import ACTOR_MODELO, Actor, record_event
from vigia.app.jobs import JobContext
from vigia.app.models import (
    Alert,
    Batch,
    Dataset,
    Evaluation,
    Measurement,
    ModelVersion,
    Monitor,
    Project,
    Record,
    UsageLog,
    now_iso,
)
from vigia.app.schemas.human import ComprobacionCodificacion, ValorFavorable
from vigia.app.schemas.monitors import claves_fuera_de_rango
from vigia.app.services import alerting
from vigia.app.services import tarea as tarea_service
from vigia.app.services.fechas import FORMATOS_FECHA
from vigia.app.services.usage_log_avisos import aviso_fechas_sin_lote
from vigia.app.services.usage_log_clases import (
    MENSAJE_VALOR_FAVORABLE,
    etiqueta_de_fila,
    favorables_del_proyecto,
    parse_clase,
    tarea_de_uso,
)
from vigia.core import CORE_VERSION
from vigia.core.loaders import (
    LIMITE_FILAS_LOTE,
    contar_filas_csv,
    mensaje_limite_filas,
    read_csv_smart,
)
from vigia.core.schema import USAGE_LOG_COLUMNS, DatosNoValidos, State, TaskSpec, clave_clase
from vigia.human import ir_adapter
from vigia.human._vendor.interaction_review.telemetry import REQUIRED_COLUMNS
from vigia.human.cross_alerts import (
    CrossAlertResult,
    CrossConfig,
    CrossReference,
    DeskillingInput,
    evaluate_cross,
)

__all__ = [
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "comprobar_codificacion",
    "cross_latest",
    "evaluate_cross_for_project",
    "export_usage_csv",
    "ingest_usage_log",
    "run_cross_evaluation_job",
    "usage_frame",
]

OPTIONAL_COLUMNS = ("clinician_pseudonym", "subgroup", "record_seq", "model_version")

_LABEL_TO_INT = {"refer": 1, "no-refer": 0}
_INT_TO_LABEL = {1: "refer", 0: "no-refer"}

_ORDEN_ESTADOS = (State.alerta, State.inestable, State.aviso, State.sin_datos, State.ok)

# La fecha del diario de uso se normaliza a ISO en la subida,
# nunca en `ir_adapter.py` (que solo se defiende, no valida): ISO
# (`aaaa-mm-dd`), `dd/mm/aaaa` (la fecha española) y
# `dd-mm-aaaa`. Cualquier otra cosa da 422 con la fila.
_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FECHA_DMY_BARRA_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_FECHA_DMY_GUION_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
# intervalo plausible de las fechas del diario. El banco y los datos de
# demostración van de enero a junio de 2026; el intervalo los admite con margen.
FECHA_USO_MIN = date_cls(2000, 1, 1)
FECHA_USO_MAX = date_cls(2049, 12, 31)


def _normalize_date(raw: Any, *, fila_n: int) -> str:
    """Normaliza la fecha del diario de uso a ISO.

    Admite ISO (`aaaa-mm-dd`), `dd/mm/aaaa` y `dd-mm-aaaa`; cualquier otro
    formato da 422 con el número de fila (1 para la primera fila de datos,
    igual que `outcomes._parse_value`)."""
    texto = str(raw).strip()
    fecha: date_cls | None = None
    try:
        if _FECHA_ISO_RE.match(texto):
            fecha = date_cls.fromisoformat(texto)
        elif _FECHA_DMY_BARRA_RE.match(texto):
            d, m, a = texto.split("/")
            fecha = date_cls(int(a), int(m), int(d))
        elif _FECHA_DMY_GUION_RE.match(texto):
            d, m, a = texto.split("-")
            fecha = date_cls(int(a), int(m), int(d))
    except ValueError:
        fecha = None
    if fecha is not None:
        # una fecha fuera de un intervalo plausible estira las ventanas del
        # deskilling hasta dejar todas las filas reales en una sola.
        if not FECHA_USO_MIN <= fecha <= FECHA_USO_MAX:
            raise HTTPException(
                422,
                f"la fecha de la fila {fila_n} ({texto}) queda fuera del intervalo admitido, "
                f"de {FECHA_USO_MIN.isoformat()} a {FECHA_USO_MAX.isoformat()}: revisa el año",
            )
        return fecha.isoformat()
    raise HTTPException(
        422,
        f"la fecha de la fila {fila_n} no se lee ({raw!r}): escríbela como {FORMATOS_FECHA}",
    )


def _parse_decision(valor: str | None) -> int | None:
    """Acepta `refer`/`no-refer` (el vocabulario del harness) o `1`/`0`. `None` si está en blanco."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    normalizado = texto.casefold()
    if normalizado in _LABEL_TO_INT:
        return _LABEL_TO_INT[normalizado]
    if texto in ("1", "0"):
        return int(texto)
    try:
        entero = int(float(texto))
    except ValueError as exc:
        raise HTTPException(
            422,
            f"el valor de decisión {valor!r} no se reconoce: usa refer/no-refer o 1/0",
        ) from exc
    if entero not in (0, 1):
        raise HTTPException(422, f"el valor de decisión {valor!r} no vale: usa refer/no-refer o 1/0")
    return entero


# en regresión el registro de uso trae cifras, no `refer`/`no-refer`. El MCP repite
# esta frase solo si valida antes de subir; si no, deja pasar el 422 de la API.
MENSAJE_REGISTRO_CIFRAS = "en regresión el registro trae las cifras"
MENSAJE_VALOR_FAVORABLE_REGRESION = (
    f"En un modelo de regresión el registro de uso no se recodifica con valor_favorable: "
    f"{MENSAJE_REGISTRO_CIFRAS} de human_decision, model_output y ground_truth, como números "
    "con punto decimal y sin unidad. Quita valor_favorable y sube el registro con las cifras"
)
MOTIVO_CODIFICACION_REGRESION = (
    "no aplica en regresión: el registro trae las cifras y no hay codificación que invertir"
)
_CIFRA_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_COMA_DECIMAL_RE = re.compile(r"[+-]?[0-9]+,[0-9]+")


def _parse_cifra(valor: Any, tarea: TaskSpec, *, fila_n: int, columna: str) -> float | None:
    """Cifra de una celda del registro de uso de una regresión. `None` si está en
    blanco. `refer`/`no-refer`, texto, una coma decimal, una unidad pegada o un valor no finito
    dan 422 con la fila, la columna y qué hacer."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    unidad = f" ({tarea.unidad})" if tarea.unidad else ""
    que_hacer = (
        f"Escribe la cifra{unidad} como número con punto decimal y sin unidad, por ejemplo 38.5"
    )
    if texto.casefold() in _LABEL_TO_INT:
        raise HTTPException(
            422,
            f"la fila {fila_n} trae {texto!r} en {columna}: refer y no-refer son de los modelos "
            f"binarios y {MENSAJE_REGISTRO_CIFRAS}. {que_hacer}",
        )
    if _CIFRA_RE.fullmatch(texto):
        numero = float(texto)
        if math.isfinite(numero):
            return numero
    pista = " La coma decimal no vale: usa el punto." if _COMA_DECIMAL_RE.fullmatch(texto) else ""
    raise HTTPException(
        422,
        f"la fila {fila_n} trae {texto!r} en {columna}, que no es una cifra: "
        f"{MENSAJE_REGISTRO_CIFRAS}.{pista} {que_hacer}",
    )


def _decisiones_regresion(fila: Any, tarea: TaskSpec, *, fila_n: int) -> dict[str, Any]:
    """Columnas de `usage_log` de una fila de regresión: la cifra en
    `human_value`/`model_value`/`truth_value` y el 0/1 de pertenencia al rango favorable
    (`TaskSpec.en_rango`) en los enteros de siempre, nulo si la cifra es nula. Las clases
    quedan nulas."""
    columnas = (
        ("human_decision", "human_decision", "human_value"),
        ("model_output", "model_output", "model_value"),
        ("ground_truth", "ground_truth", "truth_value"),
    )
    decisiones: dict[str, Any] = {}
    for columna, entero, cifra in columnas:
        numero = _parse_cifra(fila.get(columna), tarea, fila_n=fila_n, columna=columna)
        decisiones[cifra] = numero
        dentro = None if numero is None else tarea.en_rango(numero)
        decisiones[entero] = None if dentro is None else int(dentro)
    return decisiones


def _safe_filename(name: str) -> str:
    limpio = "".join(c if c.isalnum() or c in ".-_" else "_" for c in name)
    return limpio or "usage_log.csv"


def _read_usage_csv(file_bytes: bytes) -> pd.DataFrame:
    """Lee el CSV de uso con la detección de los datasets:
    `sniff_csv_dialect` de `core.loaders` (`,`, `;` o tabulador; UTF-8 con y
    sin BOM o cp1252). Todo se lee como texto: la normalización de fecha y de
    decisión es de `ingest_usage_log`."""
    try:
        df, _dialecto = read_csv_smart(file_bytes, como_texto=True)
    except DatosNoValidos as exc:
        raise HTTPException(422, str(exc)) from exc
    faltantes = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if faltantes:
        raise HTTPException(
            422,
            f"faltan columnas obligatorias en el registro de uso: {', '.join(faltantes)}; "
            f"la cabecera necesita al menos {', '.join(REQUIRED_COLUMNS)}",
        )
    return df


_VALORES_FAVORABLE = ("refer", "no-refer", "1", "0")

# Regla medida con diarios sintéticos: solo se
# decide con un diario de 200 filas o más y con las predicciones del modelo
# suficientemente separadas del 50 %; el umbral de 0,15 se recalibra con el
# primer diario real.
COMPROBACION_MIN_N = 200
COMPROBACION_SEPARACION_MIN = 0.30
COMPROBACION_UMBRAL_DISTANCIA = 0.15


def _invertir(valor: int | None) -> int | None:
    return None if valor is None else 1 - valor


def _tasa_prediccion_favorable(
    session: Session, project: Project, version: ModelVersion
) -> tuple[float | None, int]:
    """`p`: tasa de predicción favorable (`Record.prediction == 1`, ya
    resuelta contra la clase favorable del mapeo) de los lotes de producción
    de la versión: todos sus lotes menos el de línea base. Es la media de las
    tasas por lote, (cada lote pesa igual).
    Devuelve `(p, n_registros)`; `(None, 0)` si no hay ninguno."""
    ids = [
        lote_id
        for lote_id, rol in session.exec(
            select(Batch.id, Dataset.role)
            .join(Dataset, Dataset.id == Batch.dataset_id, isouter=True)  # type: ignore[arg-type]
            .where(Batch.project_id == project.id, Batch.model_version_id == version.id)
        ).all()
        if lote_id != version.baseline_batch_id and rol != "baseline"
    ]
    if not ids:
        return None, 0
    por_lote = session.exec(
        select(func.count(Record.id), func.sum(Record.prediction))  # type: ignore[arg-type]
        .where(Record.batch_id.in_(ids))  # type: ignore[attr-defined]
        .group_by(Record.batch_id)
    ).all()
    tasas = [float(fav or 0) / float(n) for n, fav in por_lote if n]
    if not tasas:
        return None, 0
    return sum(tasas) / len(tasas), sum(int(n) for n, _ in por_lote)


MOTIVO_CODIFICACION_MULTICLASE = (
    "no aplica en multiclase: el registro trae nombres de clase validados contra las clases del modelo"
)


def comprobar_codificacion(
    *, r: float | None, p: float | None, n: int
) -> ComprobacionCodificacion:
    """Regla de la comprobación de codificación, función pura. `r`: tasa de `model_output`
    favorable del diario ya recodificado; `p`: tasa de predicción favorable
    del modelo en sus lotes de producción; `n`: filas del diario con salida del
    modelo. Decide solo con `n >= 200` y `|2p-1| >= 0,30`: `posible_inversion`
    si `|r-(1-p)| < |r-p|` y `|r-p| > 0,15`, `coherente` en otro caso;
    `inconcluso` (con motivo) cuando no se puede decidir. Es un aviso, nunca
    un rechazo."""
    redondeo = {
        "r": None if r is None else round(r, 4),
        "p": None if p is None else round(p, 4),
        "n": n,
    }
    if p is None:
        return ComprobacionCodificacion(
            estado="inconcluso",
            motivo=(
                "no hay lotes de producción de esta versión con los que comparar las "
                "decisiones del modelo: sube primero los lotes"
            ),
            **redondeo,
        )
    if r is None or n < COMPROBACION_MIN_N:
        return ComprobacionCodificacion(
            estado="inconcluso",
            motivo=(
                f"el registro tiene {n} decisiones del modelo y hacen falta al menos "
                f"{COMPROBACION_MIN_N} para comprobar la codificación"
            ),
            **redondeo,
        )
    separacion = abs(2 * p - 1)
    if separacion < COMPROBACION_SEPARACION_MIN:
        favorables = f"{p * 100:.0f}".replace(".", ",")
        desfavorables = f"{(1 - p) * 100:.0f}".replace(".", ",")
        valor = f"{separacion:.2f}".replace(".", ",")
        minimo = f"{COMPROBACION_SEPARACION_MIN:.2f}".replace(".", ",")
        return ComprobacionCodificacion(
            estado="inconcluso",
            motivo=(
                f"el modelo da un {favorables} % de decisiones favorables y un "
                f"{desfavorables} % de desfavorables: la separación |2p-1| ({valor}) "
                f"queda por debajo del {minimo} que hace falta para decidir si la "
                "codificación está al revés"
            ),
            **redondeo,
        )
    if abs(r - (1 - p)) < abs(r - p) and abs(r - p) > COMPROBACION_UMBRAL_DISTANCIA:
        return ComprobacionCodificacion(
            estado="posible_inversion",
            motivo=(
                "la tasa de decisiones favorables del registro se parece más a la tasa "
                "desfavorable del modelo: revisa qué valor del fichero es la decisión favorable"
            ),
            **redondeo,
        )
    return ComprobacionCodificacion(estado="coherente", **redondeo)


def _rechazar_registro_repetido(session: Session, project: Project, file_bytes: bytes) -> None:
    """409 si un registro de uso ya ingerido en el proyecto tiene la misma huella sha256.

    Subir dos veces el mismo fichero duplicaba las decisiones y falseaba
    el deskilling, los overrides y las reglas cruzadas. Tras reiniciar el proyecto el dataset
    ya no existe y el mismo fichero vuelve a entrar.
    """
    huella = hashlib.sha256(file_bytes).hexdigest()
    previo = session.exec(
        select(Dataset)
        .where(
            Dataset.project_id == project.id,
            Dataset.kind == "usage_log",
            Dataset.status == "ingerido",
            Dataset.sha256 == huella,
        )
        .order_by(Dataset.id)  # type: ignore[arg-type]
    ).first()
    if previo is None:
        return
    cuando = (previo.created_at or "")[:16].replace("T", " ")
    raise HTTPException(
        409,
        f"este registro de uso ya se subió el {cuando} (UTC) con el nombre "
        f"«{previo.name}»: no se suma dos veces. Si es otro registro, cambia su contenido; "
        "si quieres empezar de cero, reinicia el proyecto.",
    )


def ingest_usage_log(
    session: Session,
    project: Project,
    *,
    file_bytes: bytes,
    filename: str,
    model_version: ModelVersion,
    upload_dir: Path,
    actor: Actor,
    bus: EventBus | None = None,
    valor_favorable: ValorFavorable | None = None,
    correlation_id: str | None = None,
) -> tuple[Dataset, int, ComprobacionCodificacion, list[str]]:
    """Guarda el CSV subido, lo valida e inserta sus filas en `usage_log`.

    En una regresión con rango favorable las tres columnas llevan cifras
    (números con punto decimal y sin unidad); se guardan en `human_value`, `model_value` y
    `truth_value` y los enteros guardan la pertenencia al rango (0/1). `refer`/`no-refer` y
    `valor_favorable` con valor dan 422 con `MENSAJE_REGISTRO_CIFRAS`; sin rango, 422 con el
    motivo; la comprobación de codificación no corre. `valor_favorable` nulo es `refer` en
    clasificación.

    Registra el fichero como `Dataset(kind="usage_log")` bajo `upload_dir`
    (`data_dir/uploads/<project_id>/`) y deja un evento `usage_log.ingerido`.

    `date` se normaliza a ISO: ISO, `dd/mm/aaaa` o
    `dd-mm-aaaa`; cualquier otro formato da 422 con la fila (`_normalize_date`),
    antes de escribir ninguna `UsageLog` en la sesión.

    `human_decision`, `model_output` y `ground_truth` son `refer`/`no-refer`
    (o `1`/`0`): `refer` (o `1`) es la decisión favorable para la persona
    afectada, en el mismo sentido que la etiqueta favorable del modelo.
    En un modelo multiclase las tres columnas
    llevan nombres de clase y `refer`/`no-refer` dan 422; `valor_favorable`
    distinto de `refer` también (el `refer` explícito es el defecto y pasa).

    `valor_favorable` declara qué valor del fichero es la decisión
    favorable. Con `refer` o `1` (el defecto) no se toca nada; con `no-refer`
    o `0` se recodifican las tres columnas antes de guardar. La declaración
    queda en `Dataset.mapping_json` y en el evento. Tras guardar, se
    comprueba la codificación contra las predicciones de producción de la
    versión; es un aviso, nunca un rechazo, y se devuelve y se deja en
    el evento.

    Devuelve además `avisos`: filas con fecha posterior al último
    lote de producción de la versión. Aviso, no rechazo; también va al evento.
    """
    # una regresión sin rango favorable da 422 con el motivo; la subida nunca
    # cae al camino binario.
    tarea_service.guardia_capa_humana(project)
    match project.task_type:
        case "regression":
            # la inversión por `valor_favorable` no tiene sentido con cifras.
            if valor_favorable is not None:
                raise HTTPException(422, MENSAJE_VALOR_FAVORABLE_REGRESION)
        case "binary" | "multiclass":
            valor_favorable = valor_favorable or "refer"
            if valor_favorable not in _VALORES_FAVORABLE:
                raise HTTPException(
                    422,
                    f"el valor favorable {valor_favorable!r} no es válido: elige uno de "
                    f"{', '.join(_VALORES_FAVORABLE)}",
                )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    # En multiclase el registro trae nombres de clase; la
    # inversión por `valor_favorable` no tiene sentido y da 422.
    tarea = tarea_de_uso(session, project)
    match project.task_type:
        case "multiclass":
            if valor_favorable != "refer":
                raise HTTPException(422, MENSAJE_VALOR_FAVORABLE)
        case "binary" | "regression":
            pass
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    invertir = valor_favorable in ("no-refer", "0")
    # el tope de filas por lote vale también para el registro de uso; se cuenta
    # antes de leer el fichero.
    n_filas = contar_filas_csv(file_bytes)
    if n_filas > LIMITE_FILAS_LOTE:
        raise HTTPException(422, mensaje_limite_filas(n_filas))
    _rechazar_registro_repetido(session, project, file_bytes)
    df = _read_usage_csv(file_bytes)

    dataset = Dataset(
        project_id=project.id,
        name=filename,
        source="upload",
        kind="usage_log",
        role="production",
        format="csv",
        n_rows=len(df),
        columns_json=list(df.columns),
        status="subido",
        mapping_json={"valor_favorable": valor_favorable},
    )
    session.add(dataset)
    session.flush()

    destino = upload_dir / f"{dataset.id}_{_safe_filename(filename)}"

    filas: list[UsageLog] = []

    def _decision(valor: str | None) -> int | None:
        entero = _parse_decision(valor)
        return _invertir(entero) if invertir else entero

    for posicion, (_, fila) in enumerate(df.iterrows(), start=1):
        record_seq_raw = fila.get("record_seq", "") if "record_seq" in df.columns else ""
        record_seq_texto = str(record_seq_raw).strip()
        if record_seq_texto:
            try:
                record_seq = int(float(record_seq_texto))
            except ValueError as exc:
                raise HTTPException(
                    422,
                    f"el número de registro {record_seq_raw!r} de la fila {posicion} no es un número",
                ) from exc
        else:
            record_seq = None
        fecha = _normalize_date(fila.get("date", ""), fila_n=posicion)
        match project.task_type:
            case "binary":
                decisiones: dict[str, Any] = {
                    "human_decision": _decision(fila.get("human_decision")),
                    "model_output": _decision(fila.get("model_output")),
                    "ground_truth": _decision(fila.get("ground_truth")),
                }
            case "regression":
                decisiones = _decisiones_regresion(fila, tarea, fila_n=posicion)
            case "multiclass":
                decisiones = {}
                for columna, entero, nombre in (
                    ("human_decision", "human_decision", "human_class"),
                    ("model_output", "model_output", "model_class"),
                    ("ground_truth", "ground_truth", "truth_class"),
                ):
                    clase, miembro = parse_clase(
                        fila.get(columna), tarea, fila_n=posicion, columna=columna
                    )
                    decisiones[nombre] = clase
                    # Sin conjunto favorable los enteros quedan en 0.
                    decisiones[entero] = None if clase is None else int(miembro or 0)
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
        filas.append(
            UsageLog(
                project_id=project.id,
                dataset_id=dataset.id,
                model_version_id=model_version.id,
                record_seq=record_seq,
                date=fecha,
                clinician_pseudonym=(str(fila.get("clinician_pseudonym", "")).strip() or None),
                subgroup=(str(fila.get("subgroup", "")).strip() or None),
                **decisiones,
            )
        )
    # El fichero se guarda solo cuando todas las filas ya son válidas; si algo
    # falla después, se borra: una subida rechazada no deja nada en `uploads/`.
    upload_dir.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(file_bytes)
    try:
        return _cerrar_ingesta_uso(
            session, project, dataset, filas, destino, file_bytes,
            model_version=model_version, actor=actor, bus=bus,
            valor_favorable=valor_favorable, correlation_id=correlation_id,
        )
    except BaseException:
        destino.unlink(missing_ok=True)
        raise


def _cerrar_ingesta_uso(
    session: Session,
    project: Project,
    dataset: Dataset,
    filas: list[UsageLog],
    destino: Path,
    file_bytes: bytes,
    *,
    model_version: ModelVersion,
    actor: Actor,
    bus: EventBus | None,
    valor_favorable: ValorFavorable | None,
    correlation_id: str | None,
) -> tuple[Dataset, int, ComprobacionCodificacion, list[str]]:
    """Guarda las filas ya validadas, comprueba la codificación y deja el evento."""
    dataset.file_path = str(destino)
    dataset.sha256 = hashlib.sha256(file_bytes).hexdigest()
    session.add_all(filas)
    dataset.status = "ingerido"
    session.add(dataset)
    session.flush()

    salidas = [f.model_output for f in filas if f.model_output is not None]
    match project.task_type:
        case "multiclass":
            # en multiclase `model_output` es la pertenencia al conjunto favorable de una
            # clase validada contra las clases del proyecto: no hay codificación que invertir.
            # `r` sería solo la proporción de salidas favorables de la semana.
            comprobacion = ComprobacionCodificacion(
                estado="inconcluso", r=None, p=None, n=len(salidas), motivo=MOTIVO_CODIFICACION_MULTICLASE
            )
        case "binary":
            tasa_diario = (sum(salidas) / len(salidas)) if salidas else None
            tasa_modelo, _n_registros = _tasa_prediccion_favorable(session, project, model_version)
            comprobacion = comprobar_codificacion(r=tasa_diario, p=tasa_modelo, n=len(salidas))
        case "regression":
            # el registro trae cifras y no hay inversión posible; la comprobación de
            # codificación no corre en regresión.
            comprobacion = ComprobacionCodificacion(
                estado="inconcluso", r=None, p=None, n=len(salidas), motivo=MOTIVO_CODIFICACION_REGRESION
            )
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    avisos = aviso_fechas_sin_lote(session, model_version, (f.date for f in filas))

    record_event(
        session,
        actor_kind=actor.kind,
        actor_id=actor.id,
        role=actor.role,
        action="usage_log.ingerido",
        object_type="dataset",
        object_id=dataset.id,
        project_id=project.id,
        after={
            "n_rows": len(filas),
            "model_version_id": model_version.id,
            "valor_favorable": valor_favorable,
            "comprobacion_codificacion": comprobacion.model_dump(mode="json"),
            "avisos": avisos,
        },
        correlation_id=correlation_id,
        bus=bus,
    )
    session.commit()
    session.refresh(dataset)
    return dataset, len(filas), comprobacion, avisos


def usage_frame(session: Session, project: Project, version: ModelVersion) -> pd.DataFrame:
    """Diario de uso ACUMULADO de `version`, con las etiquetas que espera `evaluate_cross`."""
    filas = session.exec(
        select(UsageLog).where(
            UsageLog.project_id == project.id,
            UsageLog.model_version_id == version.id,
        )
    ).all()
    # Multiclase: `human_decision`, `model_output` y `ground_truth` llevan
    # los nombres de clase, así que CX-2, CX-3, CX-5 y CX-6 comparan clases. CX-1
    # lee `truth_fav` y `model_fav`, el 0/1 del conjunto favorable (nulos, con
    # `conjunto_favorable` en falso, si el proyecto no tiene conjunto favorable).
    match project.task_type:
        case "multiclass":
            multiclase = True
        case "binary":
            multiclase = False
        case "regression":
            # con rango, los enteros del diario ya son la decisión derivada
            # (dentro o fuera del rango) y CX-1 a CX-6 la leen como `refer`/`no-refer`. Sin
            # rango no hay diario que leer: las cruzadas dan `sin_datos`.
            if tarea_service.motivo_capa_humana(project) is not None:
                return pd.DataFrame([], columns=list(USAGE_LOG_COLUMNS))
            multiclase = False
        case _:
            raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")
    favorables = favorables_del_proyecto(session, project) if multiclase else []
    con_conjunto = bool(favorables)
    claves_favorables = {clave_clase(c) for c in favorables}

    def _pertenencia(clase: str | None) -> int | None:
        # la pertenencia sale de la clase guardada (`truth_class`, `model_class`) y del
        # conjunto de hoy. Los enteros `ground_truth` y `model_output` guardan el 0/1 de cuando
        # se subió la fila: sin conjunto eran 0 de relleno y un conjunto fijado después no
        # los corrige.
        return None if clase is None else int(clave_clase(clase) in claves_favorables)

    registros = []
    for f in filas:
        registro = {
            "date": f.date,
            "clinician_pseudonym": f.clinician_pseudonym,
            "subgroup": f.subgroup,
            "human_decision": etiqueta_de_fila(f.human_decision, f.human_class, _INT_TO_LABEL),
            "model_output": etiqueta_de_fila(f.model_output, f.model_class, _INT_TO_LABEL),
            "ground_truth": etiqueta_de_fila(f.ground_truth, f.truth_class, _INT_TO_LABEL),
            "record_seq": f.record_seq,
            "model_version": version.label,
        }
        # el motor de cruzadas compara con `!=` y `==`, y en pandas un nulo
        # difiere de todo; una fila sin decisión o sin salida contaría como override.
        # Queda fuera, como en el deskilling (`ir_adapter._filtered_rows`) y en la
        # tabla de cambios. Una fila sin verdad (la verdad llega tarde) sí entra: el
        # motor solo la excluye de las medidas que leen la verdad (`cross_alerts`).
        if registro["human_decision"] is None or registro["model_output"] is None:
            continue
        if multiclase:
            registro["truth_fav"] = _pertenencia(f.truth_class) if con_conjunto else None
            registro["model_fav"] = _pertenencia(f.model_class) if con_conjunto else None
            registro["conjunto_favorable"] = con_conjunto
        registros.append(registro)
    columnas = list(USAGE_LOG_COLUMNS) + (
        ["truth_fav", "model_fav", "conjunto_favorable"] if multiclase else []
    )
    return pd.DataFrame(registros, columns=columnas)


def _worst_state(measurements: list[Any]) -> str:
    estados = {m.state for m in measurements}
    for estado in _ORDEN_ESTADOS:
        if estado in estados:
            return estado.value
    return State.sin_datos.value


# Estados de una alerta que cuentan como viva: ni cerrada ni retirada.
ESTADOS_ALERTA_VIVOS: tuple[str, ...] = ("abierta", "reconocida", "en_observacion")


def _alertas_vivas(
    session: Session, project: Project, *, monitor_type: str, metric_key: str | None = None
) -> list[Alert]:
    """`Alert` vivas del proyecto (`ESTADOS_ALERTA_VIVOS`) de un `monitor_type`.

    La fila de una alerta no es de una versión (su clave es proyecto, monitor,
    métrica y grupo), y `last_evaluation_id` no se mueve si la alerta ya estaba
    en `en_observacion`: no sirve para acotar por versión. Quien llama acota
    exigiendo además que la señal se haya dado en la versión activa.
    """
    consulta = select(Alert).where(
        Alert.project_id == project.id,
        Alert.monitor_type == monitor_type,
        Alert.status.in_(ESTADOS_ALERTA_VIVOS),  # type: ignore[attr-defined]
    )
    if metric_key is not None:
        consulta = consulta.where(Alert.metric_key == metric_key)
    return list(session.exec(consulta).all())


def _equidad_senalada_en_version(session: Session, project: Project) -> bool:
    """Alguna evaluación de `fairness` de la versión activa llegó a `alerta` o `inestable`."""
    if project.active_version_id is None:
        return False
    fila = session.exec(
        select(Evaluation.id)
        .join(Monitor, Monitor.id == Evaluation.monitor_id)  # type: ignore[arg-type]
        .where(
            Evaluation.project_id == project.id,
            Evaluation.model_version_id == project.active_version_id,
            Monitor.type == "fairness",
            Evaluation.worst_state.in_((State.alerta.value, State.inestable.value)),  # type: ignore[union-attr]
        )
    ).first()
    return fila is not None


def _cx1_alert_groups(session: Session, project: Project) -> set[str]:
    """Grupos con una alerta CX-1 viva señalada en la versión activa.

    Viva = `abierta`, `reconocida` o `en_observacion` (`ESTADOS_ALERTA_VIVOS`), y
    CX-1 tiene que haber disparado en ese grupo en alguna evaluación cruzada de la
    versión activa (medida `cx1_override_z:<g>` en `alerta`). `evaluate_cross` no
    emite CX-6 en esos grupos. Efecto aceptado: (una alerta nunca se
    cierra sola) la supresión es pegajosa; CX-6 sigue callada en ese grupo hasta
    que una persona cierre o retire la CX-1. `core/engine.run_scenario` lo refleja.
    """
    if project.active_version_id is None:
        return set()
    vivas = {
        a.group_code
        for a in _alertas_vivas(session, project, monitor_type="cross", metric_key="CX-1")
        if a.group_code is not None
    }
    if not vivas:
        return set()
    disparadas = session.exec(
        select(Measurement.group_code)
        .join(Evaluation, Evaluation.id == Measurement.evaluation_id)  # type: ignore[arg-type]
        .where(
            Measurement.project_id == project.id,
            Measurement.metric_key.startswith("cx1_override_z:"),  # type: ignore[attr-defined]
            Measurement.state == State.alerta.value,
            Evaluation.model_version_id == project.active_version_id,
        )
        .distinct()
    ).all()
    return vivas & {g for g in disparadas if g is not None}


def _model_alert_groups(session: Session, project: Project) -> set[str]:
    """Etiquetas de los grupos no privilegiados en alerta de fairness (§9.1).

    Reproduce `engine.run_scenario`: si la última evaluación de `fairness` de la
    versión activa tiene `worst_state` en `{alerta, inestable}`, el conjunto son las
    etiquetas de los grupos no privilegiados del mapeo del dataset origen del último
    batch del proyecto (`alerting.last_batch_mapping`); si no, conjunto vacío. Sin
    referencia al dominio del proyecto.

    UNION con un segundo camino. Si alguna evaluación de `fairness`
    de la versión activa llegó a `alerta` o `inestable` y sigue viva una `Alert` de
    `fairness` (`ESTADOS_ALERTA_VIVOS`, incluida `en_observacion`), el conjunto
    también son esas etiquetas, aunque la última evaluación ya esté en `ok`: la
    alerta sigue ahí hasta que una persona la cierre. El camino por
    `worst_state` se queda porque `inestable` puede no abrir fila en `Alert`.
    `core/engine.run_scenario` lo refleja (sin personas, ninguna alerta se cierra).
    """
    if project.active_version_id is None:
        return set()
    ultima = session.exec(
        select(Evaluation)
        .join(Monitor, Monitor.id == Evaluation.monitor_id)  # type: ignore[arg-type]
        .where(
            Evaluation.project_id == project.id,
            Evaluation.model_version_id == project.active_version_id,
            Monitor.type == "fairness",
        )
        .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())  # type: ignore[union-attr]
    ).first()
    por_estado = ultima is not None and ultima.worst_state in (
        State.alerta.value,
        State.inestable.value,
    )
    if not por_estado and not (
        _equidad_senalada_en_version(session, project)
        and _alertas_vivas(session, project, monitor_type="fairness")
    ):
        return set()
    mapping = alerting.last_batch_mapping(session, project)
    return set(alerting.group_labels(mapping))


def _quality_state(session: Session, project: Project) -> str | None:
    """`worst_state` de la última evaluación de `quality` de la versión activa.

    `None` si no hay versión activa o ninguna evaluación de `quality` todavía: CX-2 y
    CX-3 (`cross_alerts.evaluate_cross`) tratan eso como dato insuficiente y no disparan.
    """
    if project.active_version_id is None:
        return None
    ultima = session.exec(
        select(Evaluation)
        .join(Monitor, Monitor.id == Evaluation.monitor_id)  # type: ignore[arg-type]
        .where(
            Evaluation.project_id == project.id,
            Evaluation.model_version_id == project.active_version_id,
            Monitor.type == "quality",
        )
        .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())  # type: ignore[union-attr]
    ).first()
    return ultima.worst_state if ultima is not None else None


def _deskilling_input_for_cx4(session: Session, project: Project) -> DeskillingInput | None:
    """Señal de deskilling para CX-4: reutiliza
    `human.ir_adapter.deskilling_view` sobre la versión activa del proyecto
    (`clinician=None, subgroup=None`, la señal es del servicio entero, misma
    partición por versión que el resto de cruzadas). No duplica el
    pipeline de `interaction_review.telemetry` (§8.2): llama al adaptador ya
    existente, no lo reimplementa.

    `None` si no hay versión activa, versión sin fila en `ModelVersion` o
    diario de uso: `cross_alerts._cx4` lo traduce a `sin_datos`.

    `reason` pasa por `ir_adapter.deskilling_reason_es` (corrección,
    hallazgo 2): `resultado.signal.reason` es texto de librería en inglés
    (`interaction_review.telemetry`); `GET /deskilling` lo enseña tal cual a
    propósito (se traduce en el frontend), pero `DeskillingInput.reason`
    alimenta el `motivo` de la alerta CX-4 (`cross_alerts._cx4`), que sí tiene
    que ir en español sin texto de librería.
    """
    if project.active_version_id is None:
        return None
    version = session.get(ModelVersion, project.active_version_id)
    if version is None:
        return None
    resultado = ir_adapter.deskilling_view(session, project.id, version)
    if resultado.sin_datos or resultado.signal is None or resultado.trends is None:
        return None
    return DeskillingInput(
        fired=resultado.signal.fired,
        agreement_slope=resultado.trends.agreement_slope,
        model_accuracy_slope=resultado.trends.model_accuracy_slope,
        rescue_slope=resultado.trends.rescue_slope,
        reason=ir_adapter.deskilling_reason_es(resultado.signal.reason),
    )


def _titulo_revision_cero(tasa: Any, n: int) -> str:
    """Título de `human_review_zero`: con tasa 0 dice que nadie ha
    corregido; con tasa mayor que 0 dice cuánto, con coma decimal, para no negar
    correcciones que existen. `alerting._titulo_actual` sustituye lo que va antes
    de «: » por la etiqueta de `metricas-ayuda.json` («Tasa de correcciones del modelo»):
    el resto tiene que leerse solo."""
    if not isinstance(tasa, (int, float)) or math.isnan(tasa) or tasa <= 0:
        return f"Nadie ha corregido al modelo en {n} decisiones"
    pct = f"{tasa * 100:.1f}"
    if pct == "0.0":
        pct = f"{tasa * 100:.2f}"
    return f"Tasa de correcciones del modelo: solo el {pct.replace('.', ',')} % de {n} decisiones corrigió al modelo"


def _candidato_revision_cero(m: Any) -> dict[str, Any]:
    """Candidato de `human_review_zero`. Solo el estado `aviso` abre
    alerta (como `inestable`, severidad `media`); el título lleva las decisiones
    de la ventana (`extra["n"]`)."""
    extra = m.extra if isinstance(getattr(m, "extra", None), dict) else {}
    n = extra.get("n")
    candidato: dict[str, Any] = {
        "metric_key": "human_review_zero",
        "group_code": m.group_code,
        "state": State.inestable if m.state == State.aviso else m.state,
        "value": m.value,
        "motivo": m.motivo,
    }
    if isinstance(n, (int, float)):
        candidato["title"] = _titulo_revision_cero(m.value, int(n))
        n_override = extra.get("n_override")
        if isinstance(n_override, (int, float)) and n_override > 0:
            candidato["motivo"] = (
                f"solo {int(n_override)} de {int(n)} decisiones se apartaron del modelo"
            )
    return candidato


def _cross_candidates(resultado: CrossAlertResult) -> list[dict[str, Any]]:
    """Candidatos de `sync_candidates` (§9.2) para las reglas CX-1, CX-2, CX-5 y CX-6.

    `resultado.measurements` trae el estado de cada regla por grupo (incluidas las que
    no disparan y las que quedan `sin_datos`), lo que basta para que `alerting.sync_candidates`
    abra, actualice, reabra u observe las alertas cruzadas sin un paso aparte para las
    reglas que dejan de disparar. `resultado.alerts` (solo las disparadas) aporta el
    valor, la referencia y el motivo de cada una.

    CX-3 (`cx3_override_z`/`cx3_rescue_z`) no entra en el `if/elif`: nunca se convierte
    en candidato, por diseño (`cross_alerts.py`, nunca abre `Alert`). CX-4
    (`cx4_deskilling`) sí entra: abre alerta severidad alta igual que CX-2.
    `human_review_zero` sí entra: en `aviso`
    es candidata de alerta con severidad `media` y título «Nadie ha corregido
    al modelo en N decisiones» (tasa 0) o «Tasa de correcciones del modelo: solo el X %
    de N decisiones corrigió al modelo» (tasa mayor que 0); `sync_candidates` solo abre con `alerta` o
    `inestable` y asigna `media` al segundo, así que el candidato lleva
    `inestable` (la medida del monitor sigue en `aviso`). Con `ok` o
    `sin_datos` no abre, y si ya había una abierta la pasa a observación como
    las demás cruzadas.
    """
    disparadas = {(a.rule, a.group): a for a in resultado.alerts}
    candidatos: list[dict[str, Any]] = []
    for m in resultado.measurements:
        if m.metric_key == "human_review_zero":
            candidatos.append(_candidato_revision_cero(m))
            continue
        if m.metric_key == "cx5_chi2_p":
            regla = "CX-5"
        elif m.metric_key.startswith("cx1_override_z:"):
            regla = "CX-1"
        elif m.metric_key.startswith("cx6_override_z:"):
            regla = "CX-6"
        elif m.metric_key == "cx2_override_z":
            regla = "CX-2"
        elif m.metric_key == "cx4_deskilling":
            regla = "CX-4"
        else:
            continue
        disparada = disparadas.get((regla, m.group_code))
        if disparada is not None:
            candidatos.append(
                {
                    "metric_key": regla,
                    "group_code": m.group_code,
                    "state": State.alerta,
                    "value": disparada.value,
                    "threshold_high": disparada.reference,
                    "motivo": disparada.motivo,
                    "title": alerting.titulo_cruzada(
                        regla,
                        m.group_code,
                        value=disparada.value,
                        reference=disparada.reference,
                        z=disparada.z,
                        n=disparada.n,
                    ),
                }
            )
        else:
            candidatos.append(
                {
                    "metric_key": regla,
                    "group_code": m.group_code,
                    "state": m.state,
                    "value": m.value,
                    "motivo": m.motivo,
                }
            )
    return candidatos


def _config_cruzadas_sana(config: dict[str, Any] | None) -> dict[str, Any]:
    """Configuración guardada de las cruzadas sin las claves fuera de rango o no finitas.

    Una fila de antes de las cotas (`schemas/monitors.RANGOS_CONFIG`) vuelve al
    valor de fábrica de esa clave, igual que `settings_for` con los otros monitores."""
    config = config or {}
    malas = set(claves_fuera_de_rango(config))
    return {k: v for k, v in config.items() if k not in malas}


def evaluate_cross_for_project(
    session: Session,
    project: Project,
    *,
    version: ModelVersion,
    trigger: str = "manual",
    job: JobContext | None = None,
    bus: EventBus | None = None,
) -> Evaluation | None:
    """Calibra (primera vez por versión) o vigila las alertas cruzadas de `project`/`version`.

    Devuelve `None` si el monitor `cross` está deshabilitado o no hay diario de uso.
    No hace `commit`: pensado para correr dentro de un trabajo (`JobManager` hace el
    commit al terminar).

    `Project.calibration_until` gobierna cuándo se fija la referencia:
    mientras no sea `None` y no haya vencido, el proyecto se queda en modo `calibracion`
    (acumula, sin alertas) en cada corrida, sin tocar `version.cross_reference_json`; al
    vencer (o con `calibration_until is None`, comportamiento actual), la primera
    corrida sin referencia todavía la fija y las siguientes vigilan.
    """
    if tarea_service.motivo_capa_humana(project) is not None:
        # una regresión no pasa por el camino binario de las cruzadas.
        return None
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "cross")
    ).first()
    if monitor is None or not monitor.enabled:
        return None

    df = usage_frame(session, project, version)
    if df.empty:
        return None

    config = CrossConfig(**_config_cruzadas_sana(monitor.config_json))

    calibrando_por_fecha = (
        project.calibration_until is not None and now_iso() < project.calibration_until
    )
    if calibrando_por_fecha:
        # Acumula sin fijar la referencia mientras `calibration_until` no venza
        #: a diferencia de la primera calibración de más abajo, esta
        # corrida no toca `version.cross_reference_json` ni emite el evento
        # `version.referencia_cruzadas`.
        resultado = evaluate_cross(df, config=config, mode="calibracion")
    elif version.cross_reference_json is None:
        # Primera evaluación de la versión (calibration_until nulo, o ya
        # vencido y todavía sin fijar): fija la referencia sobre el
        # acumulado hasta este momento (como siempre).
        resultado = evaluate_cross(df, config=config, mode="calibracion")
        version.cross_reference_json = resultado.reference
        session.add(version)
        session.flush()
        record_event(
            session,
            actor_kind=ACTOR_MODELO[0],
            actor_id=ACTOR_MODELO[1],
            action="version.referencia_cruzadas",
            object_type="model_version",
            object_id=version.id,
            project_id=project.id,
            after={"n": resultado.reference.get("n")},
            correlation_id=job.correlation_id if job else None,
            job_id=job.job_id if job else None,
            bus=bus,
        )
    else:
        referencia = CrossReference(**version.cross_reference_json)
        grupos_alerta = _model_alert_groups(session, project)
        estado_calidad = _quality_state(session, project)
        deskilling = _deskilling_input_for_cx4(session, project)
        resultado = evaluate_cross(
            df,
            reference=referencia,
            config=config,
            model_alert_groups=grupos_alerta,
            quality_state=estado_calidad,
            deskilling=deskilling,
            mode="vigilancia",
            cx1_alert_groups=_cx1_alert_groups(session, project),
        )

    worst = _worst_state(resultado.measurements)
    evaluation = Evaluation(
        monitor_id=monitor.id,
        project_id=project.id,
        model_version_id=version.id,
        batch_id=None,
        trigger=trigger,
        window_json={"kind": "acumulado_version", "n": len(df), "model_version_id": version.id},
        config_snapshot_json=config.model_dump(mode="json"),
        app_version=APP_VERSION,
        core_version=CORE_VERSION,
        status="ok",
        worst_state=worst,
        result_json=resultado.to_dict(),
        job_id=job.job_id if job else None,
    )
    session.add(evaluation)
    session.flush()

    for m in resultado.measurements:
        session.add(
            Measurement(
                evaluation_id=evaluation.id,
                project_id=project.id,
                monitor_type="cross",
                metric_key=m.metric_key,
                value=m.value,
                state=m.state.value,
                group_code=m.group_code,
                motivo=m.motivo,
                extra_json=m.extra,
            )
        )
    session.flush()

    record_event(
        session,
        actor_kind=ACTOR_MODELO[0],
        actor_id=ACTOR_MODELO[1],
        action="evaluacion.completada",
        object_type="evaluation",
        object_id=evaluation.id,
        project_id=project.id,
        after={"monitor_type": "cross", "mode": resultado.mode, "n_alertas": len(resultado.alerts)},
        correlation_id=job.correlation_id if job else None,
        job_id=job.job_id if job else None,
        bus=bus,
    )

    alerting.sync_candidates(
        session,
        project,
        monitor,
        evaluation,
        _cross_candidates(resultado),
        correlation_id=job.correlation_id if job else None,
        job_id=job.job_id if job else None,
        bus=bus,
    )

    session.flush()
    return evaluation


def run_cross_evaluation_job(
    ctx: JobContext,
    session: Session,
    *,
    project_id: int,
    version_id: int,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Función de trabajo (`kind="cruzadas"`, cola `rapida`): evalúa cruzadas y resume el resultado."""
    project = session.get(Project, project_id)
    if project is None:
        raise no_encontrado("modelo", project_id, "modelos")
    version = session.get(ModelVersion, version_id)
    if version is None:
        raise no_encontrado("versión", version_id, "versiones")
    ctx.progress(0.1, "evaluando alertas cruzadas")
    evaluation = evaluate_cross_for_project(session, project, version=version, trigger=trigger, job=ctx)
    ctx.progress(1.0, "cruzadas evaluadas")
    if evaluation is None:
        motivo = tarea_service.motivo_capa_humana(project)
        return {
            "evaluation_id": None,
            "mode": None,
            "n_alerts": 0,
            **({"motivo": motivo} if motivo is not None else {}),
        }
    resultado = evaluation.result_json or {}
    return {
        "evaluation_id": evaluation.id,
        "mode": resultado.get("mode"),
        "n_alerts": len(resultado.get("alerts") or []),
    }


def _supera_umbral(regla: str, valor: float | None, z_alert: float) -> bool | None:
    """B3: ¿`valor` cruza el umbral de `regla` en el sentido en que alerta?

    Lee la condición de disparo de `human/cross_alerts.py`: CX-1 (`z_override <=
    -z_alert`) y CX-3 (`z_rescue <= -z_alert`) hacia abajo, CX-2 (`z >= z_alert`)
    hacia arriba y CX-6 (`|z| >= z_alert`) en las dos colas. Las demás reglas no
    llevan una desviación (CX-4 es una señal, CX-5 una probabilidad): `None`."""
    if valor is None or math.isnan(valor):
        return None
    match regla:
        case "CX-1" | "CX-3":
            return valor <= -z_alert
        case "CX-2":
            return valor >= z_alert
        case "CX-6":
            return abs(valor) >= z_alert
        case _:
            return None


def _cross_rules_from_measurements(
    measurements: list[Measurement], z_alert: float = CrossConfig().z_alert
) -> list[dict[str, Any]]:
    """Traduce las medidas de una evaluación `cross` en las reglas de
    `GET /projects/{id}/cross/latest` (§6.3): una entrada por regla y
    grupo, con el valor que decide si dispara (`z` de override en CX-1/CX-2/
    CX-6, `p` en CX-5, `z` de rescate en CX-3, `1.0`/`0.0` de `fired` en
    CX-4, tasa de override en `human_review_zero`). CX-3 no lleva su medida
    de override (precondición, no el valor que se enseña).

    `human_review_zero` entra con su propia clave, no como
    `rule` de una CX-N: es una señal nueva, no una de las seis cruzadas
    (el frontend y `checks_by_state` la conocen por su clave)."""
    reglas: list[dict[str, Any]] = []

    def regla(nombre: str, grupo: str | None, m: Measurement) -> dict[str, Any]:
        # `motivo` (la frase de la señal) y `n` (decisiones de la
        # ventana) salen de la medida si el motor los dejó.
        extra = m.extra_json if isinstance(m.extra_json, dict) else {}
        n = extra.get("n")
        return {
            "rule": nombre,
            "group": grupo,
            "state": m.state,
            "value": m.value,
            "motivo": m.motivo,
            "n": int(n) if isinstance(n, (int, float)) else None,
            "supera_umbral": _supera_umbral(nombre, m.value, z_alert),
        }

    for m in measurements:
        if m.metric_key.startswith("cx1_override_z:"):
            reglas.append(regla("CX-1", m.group_code, m))
        elif m.metric_key == "cx5_chi2_p":
            reglas.append(regla("CX-5", None, m))
        elif m.metric_key.startswith("cx6_override_z:"):
            reglas.append(regla("CX-6", m.group_code, m))
        elif m.metric_key == "cx2_override_z":
            reglas.append(regla("CX-2", None, m))
        elif m.metric_key == "cx3_rescue_z":
            reglas.append(regla("CX-3", None, m))
        elif m.metric_key == "cx4_deskilling":
            reglas.append(regla("CX-4", None, m))
        elif m.metric_key == "human_review_zero":
            reglas.append(regla("human_review_zero", None, m))
        # cx1_model_fnr_z, cx2/cx3 sin listar arriba: precondiciones, no reglas.
    return reglas


def cross_latest(session: Session, project: Project) -> dict[str, Any]:
    """`GET /projects/{id}/cross/latest` (§6.3): última evaluación del
    monitor `cross` del proyecto, con sus reglas. Sin monitor `cross` o sin
    ninguna evaluación todavía (proyecto nuevo o sin diario de uso) responde
    200 con `estado="sin_datos"` y el resto vacío (no un 404, que el
    navegador contaría como error de consola)."""
    monitor = session.exec(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.type == "cross")
    ).first()
    evaluation = (
        session.exec(
            select(Evaluation)
            .where(Evaluation.project_id == project.id, Evaluation.monitor_id == monitor.id)
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())  # type: ignore[union-attr]
        ).first()
        if monitor is not None
        else None
    )
    if evaluation is None:
        return {
            "estado": "sin_datos",
            "evaluation_id": None,
            "mode": None,
            "worst_state": "sin_datos",
            "model_version_id": None,
            "evaluated_at": None,
            "rules": [],
            "calibration_until": project.calibration_until,
            # el motivo de una regresión; nulo en clasificación.
            "motivo": tarea_service.motivo_capa_humana(project),
        }
    medidas = session.exec(
        select(Measurement).where(Measurement.evaluation_id == evaluation.id)
    ).all()
    return {
        "estado": "con_datos",
        "evaluation_id": evaluation.id,
        "mode": (evaluation.result_json or {}).get("mode"),
        "worst_state": evaluation.worst_state or "sin_datos",
        "model_version_id": evaluation.model_version_id,
        "evaluated_at": evaluation.created_at,
        "rules": _cross_rules_from_measurements(
            medidas, CrossConfig(**_config_cruzadas_sana(monitor.config_json if monitor else None)).z_alert
        ),
        "calibration_until": project.calibration_until,
    }


def export_usage_csv(session: Session, project: Project) -> str:
    """CSV del diario de uso del proyecto: cabecera de `REQUIRED_COLUMNS` primero."""
    columnas = list(REQUIRED_COLUMNS) + list(OPTIONAL_COLUMNS)
    filas = session.exec(
        select(UsageLog).where(UsageLog.project_id == project.id).order_by(UsageLog.id)  # type: ignore[arg-type]
    ).all()
    etiquetas_version = {
        v.id: v.label
        for v in session.exec(select(ModelVersion).where(ModelVersion.project_id == project.id)).all()
    }

    def decisiones(f: UsageLog) -> list[str]:
        match project.task_type:
            case "regression":
                # en regresión el diario devuelve las cifras, no la pertenencia.
                return [_cifra_csv(f.human_value), _cifra_csv(f.model_value), _cifra_csv(f.truth_value)]
            case "binary" | "multiclass":
                return [
                    _celda_clase_csv_segura(
                        etiqueta_de_fila(f.human_decision, f.human_class, _INT_TO_LABEL) or ""
                    ),
                    _celda_clase_csv_segura(
                        etiqueta_de_fila(f.model_output, f.model_class, _INT_TO_LABEL) or ""
                    ),
                    _celda_clase_csv_segura(
                        etiqueta_de_fila(f.ground_truth, f.truth_class, _INT_TO_LABEL) or ""
                    ),
                ]
            case _:
                raise ValueError(f"tipo de tarea no reconocido: {project.task_type!r}")

    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(columnas)
    for f in filas:
        escritor.writerow(
            [
                f.date,
                *decisiones(f),
                _celda_csv_segura(f.clinician_pseudonym or ""),
                _celda_csv_segura(f.subgroup or ""),
                f.record_seq if f.record_seq is not None else "",
                _celda_csv_segura(etiquetas_version.get(f.model_version_id, "")),
            ]
        )
    return buffer.getvalue()


def _cifra_csv(valor: float | None) -> str:
    """Cifra de una regresión en el CSV de exportación: sin `.0` sobrante, con punto decimal."""
    if valor is None:
        return ""
    texto = repr(float(valor))
    return texto.removesuffix(".0")


_INICIOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _celda_csv_segura(texto: str) -> str:
    """Prefija con `'` el texto que una hoja de cálculo leería como fórmula."""
    return f"'{texto}" if texto.startswith(_INICIOS_DE_FORMULA) else texto


_NUMERO_SIMPLE_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")


def _celda_clase_csv_segura(texto: str) -> str:
    """igual que `_celda_csv_segura` para las columnas de decisión, donde en
    multiclase el texto es el nombre de clase que eligió quien declaró las clases. Una
    clase que es un número simple (`-1`, `2`) se deja tal cual: una hoja de cálculo
    la lee como número, no como fórmula, y así la ida y vuelta del CSV no cambia."""
    return texto if _NUMERO_SIMPLE_RE.fullmatch(texto) else _celda_csv_segura(texto)
