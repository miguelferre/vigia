"""Datos y ayudas de los tests multiclase de la API.

Un moderador de contenido de 5 clases sintético: el modelo da una probabilidad
por clase (`prob_<clase>`), la predicción es el argmax y la etiqueta coincide
con la predicción en la mayoría de las filas.
"""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers

CLASES = ["permitido", "spam", "odio", "desnudez", "violencia"]
PREVALENCIA = [0.60, 0.15, 0.10, 0.08, 0.07]
IDIOMAS = ["es", "en", "otro"]


def filas_multiclase(
    n: int = 600,
    *,
    seed: int = 7,
    clases: list[str] | None = None,
    prevalencia: list[float] | None = None,
    prefijo_id: str = "m",
    etiquetas: bool = True,
) -> list[dict]:
    """Filas con id, prediction, label, `prob_<clase>`, idioma, longitud y enlaces."""
    clases = clases or CLASES
    prevalencia = prevalencia or PREVALENCIA
    rng = np.random.default_rng(seed)
    verdad = rng.choice(len(clases), size=n, p=np.array(prevalencia) / sum(prevalencia))
    filas = []
    for i, real in enumerate(verdad):
        ruido = rng.dirichlet(np.ones(len(clases)) * 0.6)
        probs = 0.55 * ruido
        probs[real] += 0.45
        probs = probs / probs.sum()
        pred = int(probs.argmax())
        fila = {
            "id": f"{prefijo_id}{i}",
            "prediction": clases[pred],
            "label": clases[int(real)] if etiquetas else "",
            **{f"prob_{c}": round(float(p), 6) for c, p in zip(clases, probs, strict=True)},
            "idioma": IDIOMAS[i % 3],
            "longitud": int(rng.integers(5, 400)),
            "enlaces": int(rng.integers(0, 6)),
        }
        filas.append(fila)
    return filas


def a_csv(filas: list[dict]) -> bytes:
    columnas = list(filas[0])
    lineas = [",".join(columnas)] + [",".join(str(f[c]) for c in columnas) for f in filas]
    return ("\n".join(lineas) + "\n").encode("utf-8")


def mapeo_multiclase(clases: list[str] | None = None, **extra) -> dict:
    clases = clases or CLASES
    mapeo = {
        "prediction_col": "prediction",
        "label_col": "label",
        "id_col": "id",
        "probability_cols": [f"prob_{c}" for c in clases],
        "classes": clases,
        "favorable_label": [clases[0]],
        "feature_cols": ["longitud", "enlaces"],
    }
    mapeo.update(extra)
    return mapeo


def crear_proyecto_multiclase(
    client: TestClient, nombre: str, *, clases: list[str] | None = None, **extra
) -> dict:
    cuerpo = {
        "name": nombre,
        "domain": "libre",
        "task_type": "multiclass",
        "classes": clases or CLASES,
        "store_features": True,
        "mapping_template": {"favorable_label": [(clases or CLASES)[0]]},
    }
    cuerpo.update(extra)
    resp = client.post("/api/projects", json=cuerpo, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def subir(client: TestClient, proyecto_id: int, contenido: bytes, *, rol: str = "baseline",
          kind: str = "combined", nombre: str = "datos.csv") -> dict:
    resp = client.post(
        f"/api/projects/{proyecto_id}/datasets/upload",
        files={"file": (nombre, contenido, "text/csv")},
        data={"kind": kind, "role": rol},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def mapear(client: TestClient, dataset_id: int, mapeo: dict):
    return client.put(
        f"/api/datasets/{dataset_id}/mapping",
        json={"mapping": mapeo},
        headers=actor_headers("miguel"),
    )


def ingerir(client: TestClient, dataset_id: int, version_id: int, *, evaluar: bool = False) -> dict:
    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": version_id, "evaluate": evaluar},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def linea_base_multiclase(
    client: TestClient, nombre: str, *, n: int = 600, evaluar: bool = False, **kw
) -> tuple[dict, dict, dict]:
    """Proyecto multiclase con la línea base subida, mapeada e ingerida (y
    congelada por la propia ingesta). Devuelve (proyecto, subida, trabajo)."""
    proyecto = crear_proyecto_multiclase(client, nombre, **kw)
    subida = subir(client, proyecto["id"], a_csv(filas_multiclase(n)))
    resp = mapear(client, subida["dataset"]["id"], mapeo_multiclase())
    assert resp.status_code == 200, resp.text
    trabajo = ingerir(client, subida["dataset"]["id"], proyecto["active_version_id"])
    assert trabajo["status"] == "terminado", trabajo
    if evaluar:
        resp = client.post(
            f"/api/batches/{trabajo['result']['batch_id']}/evaluate",
            json={},
            headers=actor_headers("miguel"),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "terminado", resp.json()
    return proyecto, subida, trabajo


# ---------------------------------------------------------------------------
# Un modelo de verdad (regresión logística multinomial) y filas coherentes con él
# ---------------------------------------------------------------------------


def modelo_y_filas(
    n: int = 300, *, clases: list[str] | None = None, seed: int = 11, prefijo_id: str = "z"
):
    """Entrena una regresión logística multinomial con dos variables numéricas y
    devuelve `(pipeline, filas)`: las filas llevan la predicción y las
    probabilidades del modelo, con las columnas `prob_<clase>` en el orden de
    `clases` (el declarado), no en el de `modelo.classes_` (alfabético)."""
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    clases = clases or CLASES
    rng = np.random.default_rng(seed)
    centros = {c: (30 + 70 * i, i % 3) for i, c in enumerate(clases)}
    verdad = rng.choice(len(clases), size=n)
    datos = pd.DataFrame(
        {
            "longitud": [centros[clases[v]][0] + rng.normal(0, 25) for v in verdad],
            "enlaces": [centros[clases[v]][1] + rng.normal(0, 0.6) for v in verdad],
        }
    )
    y = [clases[v] for v in verdad]
    pipe = Pipeline(
        [
            ("ct", ColumnTransformer([("num", StandardScaler(), ["longitud", "enlaces"])])),
            ("clf", LogisticRegression(max_iter=2000)),
        ]
    )
    pipe.fit(datos, y)
    probs = pipe.predict_proba(datos)
    orden_modelo = [str(c) for c in pipe.classes_]
    filas = []
    for i in range(n):
        por_clase = {c: float(probs[i][orden_modelo.index(c)]) for c in clases}
        filas.append(
            {
                "id": f"{prefijo_id}{i}",
                "prediction": max(por_clase, key=por_clase.get),
                "label": y[i],
                **{f"prob_{c}": round(por_clase[c], 6) for c in clases},
                "longitud": round(float(datos["longitud"][i]), 4),
                "enlaces": round(float(datos["enlaces"][i]), 4),
            }
        )
    return pipe, filas


def subir_modelo(client: TestClient, version_id: int, contenido: bytes, *, kind: str = "onnx",
                 confirmar: bool = False, nombre: str = "modelo.onnx"):
    return client.post(
        f"/api/model-versions/{version_id}/artifact",
        files={"file": (nombre, contenido, "application/octet-stream")},
        data={"artifact_kind": kind, "confirmacion_pickle": str(confirmar).lower()},
        headers=actor_headers("miguel"),
    )
