"""Datos sintéticos y ayudas de los tests de regresión de la API.

Un modelo de regresión de «horas por semana»: dos variables, un grupo protegido
categórico y una predicción continua. Todo sintético.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from tests.api import _datos_multiclase as d
from tests.api.conftest import actor_headers

UNIDAD = "horas por semana"
RANGO = [[12.0, None]]  # «desde 12 horas por semana»: lo favorable es una atención alta


def filas_regresion(
    n: int = 600,
    *,
    semilla: int = 5,
    desplazar_grupo_b: float = 0.0,
    desplazar_todo: float = 0.0,
    prefijo: str = "r",
    con_etiqueta: bool = True,
    fecha: str = "2026-01-15",
) -> pd.DataFrame:
    """Líneas base o lotes: `label` = valor real; `prediction` = valor real más ruido
    pequeño. `desplazar_grupo_b` resta horas a la predicción del grupo B (un recorte,
    sesgo negativo); `desplazar_todo` suma horas a todas."""
    rng = np.random.default_rng(semilla)
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    grupo = np.where(rng.random(n) < 0.5, "A", "B")
    real = 12 + 3 * x1 + 2 * x2 + rng.normal(0, 1, n)
    pred = real + rng.normal(0, 0.8, n)
    pred = pred + desplazar_todo - np.where(grupo == "B", desplazar_grupo_b, 0.0)
    df = pd.DataFrame(
        {
            "id": [f"{prefijo}{i}" for i in range(n)],
            "date": [fecha] * n,
            "x1": np.round(x1, 4),
            "x2": np.round(x2, 4),
            "grupo": grupo,
            "prediction": np.round(pred, 4),
            "label": np.round(real, 4) if con_etiqueta else np.nan,
        }
    )
    return df


def a_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def mapeo_regresion(**extra: Any) -> dict[str, Any]:
    mapeo: dict[str, Any] = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "timestamp_col": "date",
        "feature_cols": ["x1", "x2"],
        "protected_attr_col": "grupo",
        "protected_kind": "categorical",
        "unpriv_groups": ["B"],
        "priv_groups": ["A"],
    }
    mapeo.update(extra)
    return mapeo


def crear_proyecto_regresion(
    client: TestClient, nombre: str, *, unidad: str | None = UNIDAD, rangos: Any = RANGO, **extra: Any
) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "name": nombre,
        "domain": "libre",
        "task_type": "regression",
        "store_features": True,
    }
    if unidad is not None:
        cuerpo["target_unit"] = unidad
    if rangos:
        cuerpo["favorable_ranges"] = rangos
    cuerpo.update(extra)
    resp = client.post("/api/projects", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def subir_e_ingerir(
    client: TestClient,
    proyecto: dict[str, Any],
    df: pd.DataFrame,
    *,
    rol: str = "baseline",
    mapeo: dict[str, Any] | None = None,
    evaluar: bool = False,
) -> dict[str, Any]:
    """Sube, mapea e ingiere un fichero; devuelve el trabajo terminado."""
    sub = d.subir(client, proyecto["id"], a_csv(df), rol=rol)
    resp = d.mapear(client, sub["dataset"]["id"], mapeo or mapeo_regresion())
    assert resp.status_code == 200, resp.text
    trabajo = d.ingerir(client, sub["dataset"]["id"], proyecto["active_version_id"], evaluar=evaluar)
    assert trabajo["status"] == "terminado", trabajo
    return trabajo


def linea_base_regresion(
    client: TestClient, nombre: str, *, n: int = 600, **kw: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Proyecto de regresión con su línea base ingerida (y congelada por la ingesta)."""
    proyecto = crear_proyecto_regresion(client, nombre, **kw)
    trabajo = subir_e_ingerir(client, proyecto, filas_regresion(n))
    return proyecto, trabajo


def evaluar_lote(client: TestClient, batch_id: int) -> dict[str, Any]:
    resp = client.post(
        f"/api/batches/{batch_id}/evaluate", json={}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminado", resp.json()
    return resp.json()


def evaluacion(client: TestClient, proyecto_id: int, batch_id: int, monitor: str) -> dict[str, Any]:
    """La última evaluación del monitor sobre el lote, con medidas y `result`."""
    resp = client.get(
        f"/api/projects/{proyecto_id}/evaluations",
        params={"monitor_type": monitor, "batch_id": batch_id, "order": "desc"},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items, f"sin evaluación de {monitor} para el lote {batch_id}"
    detalle = client.get(f"/api/evaluations/{items[0]['id']}")
    assert detalle.status_code == 200, detalle.text
    return detalle.json()


def medidas(client: TestClient, proyecto_id: int, batch_id: int, monitor: str) -> dict[str, list[dict[str, Any]]]:
    """Medidas de la evaluación, por `metric_key` (varias si hay grupos)."""
    por_clave: dict[str, list[dict[str, Any]]] = {}
    for m in evaluacion(client, proyecto_id, batch_id, monitor)["measurements"]:
        por_clave.setdefault(m["metric_key"], []).append(m)
    return por_clave
