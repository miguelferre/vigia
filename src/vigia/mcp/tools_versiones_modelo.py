"""Tools de artefacto de modelo y comparación de versiones."""

from __future__ import annotations

import os
from typing import Any

from vigia.mcp.client import get_client
from vigia.mcp.rutas import comprobar_ruta_de_subida

# Extensión del fichero a `artifact_kind` de la API; `joblib` es un pickle.
_KIND_POR_EXTENSION = {".onnx": "onnx", ".pkl": "pickle", ".pickle": "pickle", ".joblib": "pickle"}


def _kind_del_artefacto(file_path: str, artifact_kind: str | None) -> str:
    """`onnx` o `pickle` a partir del parámetro o, sin él, de la extensión."""
    if artifact_kind:
        kind = "pickle" if artifact_kind.lower() == "joblib" else artifact_kind.lower()
    else:
        kind = _KIND_POR_EXTENSION.get(os.path.splitext(file_path)[1].lower(), "")
    if kind not in ("onnx", "pickle"):
        raise ValueError(
            "no sé de qué tipo es el fichero del modelo: pasa artifact_kind='onnx' o "
            "artifact_kind='pickle' (un joblib es un pickle)"
        )
    return kind


def registrar(mcp) -> None:
    @mcp.tool()
    async def upload_model_artifact(
        version_id: int,
        file_path: str,
        artifact_kind: str | None = None,
        confirm_pickle: bool = False,
    ) -> dict[str, Any]:
        """Sube el modelo ejecutable de una versión desde un fichero local.

        Qué hace: manda el fichero que nombras (`POST /model-versions/{id}/artifact`),
        lo valida y deja la versión como ejecutable. Nunca escanea directorios.
        Qué devuelve: `artifact_kind`, `artifact_sha256`, `artifact_inputs` (las
        columnas de entrada) y `avisos`. Cuándo usarla: en una versión de modelo
        ejecutable, antes de subir sus lotes.

        `artifact_kind`: `onnx` o `pickle`; sin él se deduce de la extensión (`.onnx`,
        `.pkl`, `.pickle`, `.joblib`). Un pickle o un joblib ejecuta código al abrirse:
        la tool exige `confirm_pickle=true` y falla antes de llamar a la API si falta;
        pásalo solo si el fichero lo generaste tú o te lo dio quien lo generó. El modelo
        rellena `confirm_pickle`: la aprobación por llamada es del host del MCP, no de Vigía.

        Proyecto MULTICLASE: el modelo (ONNX o pickle) tiene que dar una
        probabilidad por clase, `(n, k)` con `k` igual al número de clases del proyecto.
        Vigía lee el orden de las clases del grafo ONNX (o de `classes_` del pickle) y lo
        compara con las clases declaradas del proyecto: si es el mismo conjunto en otro
        orden, reordena las columnas solo; si no, o si la clase de mayor probabilidad no
        coincide con la predicción de la línea base en el 99 % de 200 filas, falla con
        422 y el mensaje cita el «Orden de clases que lee Vigía en el modelo» y el «Orden
        declarado en el proyecto»: corrige `classes` (en el alta o la plantilla) al orden
        del modelo, o sube el modelo correcto. La línea base tiene que estar subida antes
        (la validación la usa). Plazo de 60 s: solo lo tienen la predicción de validación de un
        pickle o un joblib y la comparación de clases de un modelo multiclase; si se pasa, 422
        por tiempo. Un ONNX binario o de regresión no tiene plazo en la validación.

        Proyecto de REGRESIÓN: el modelo tiene que dar UNA cifra por fila,
        `(n,)` o `(n, 1)`, en la unidad del proyecto. Un ONNX con más de una columna de
        salida, con `ZipMap` o con etiquetas de clase da 422 con «es un clasificador»; en un
        proyecto de clasificación, un regresor da 422 con «es un regresor». Vigía compara
        las cifras del modelo con las de la línea base en 200 filas (tolerancia relativa de
        1e-4, en al menos el 99 %); si no coinciden, el 422 da la mediana de la
        diferencia: revisa que el modelo es el que generó la línea base. La línea base tiene
        que estar subida antes. La tool pasa estos mensajes tal cual."""
        comprobar_ruta_de_subida(file_path)
        kind = _kind_del_artefacto(file_path, artifact_kind)
        if kind == "pickle" and not confirm_pickle:
            raise ValueError(
                "un pickle o un joblib ejecuta código al abrirse: pasa confirm_pickle=true "
                "solo si el fichero lo generaste tú o lo generó quien te lo ha dado"
            )
        campos = {"artifact_kind": kind, "confirmacion_pickle": "true" if confirm_pickle else "false"}
        return await get_client().upload(
            f"/model-versions/{version_id}/artifact", file_path=file_path, fields=campos
        )

    @mcp.tool()
    async def compare_versions(
        project_id: int,
        a: int | None = None,
        b: int | None = None,
        ventana: str = "ultimo",
    ) -> dict[str, Any]:
        """Compara dos versiones de modelo, métrica a métrica, cada una contra su línea base.

        Qué hace: solo lee (`GET /projects/{id}/versions/compare`). Compara por
        evaluaciones, con los umbrales del proyecto; no compara alertas, porque las
        alertas son del proyecto y no de una versión. Qué devuelve: `version_a` y
        `version_b` (lo que se comparó), `filas` (por monitor, métrica y grupo: el
        valor de cada lado, `diferencia`, `direccion` en `mejora`, `empeora`, `igual` o
        `sin_datos`, y `motivo` con la regla), `alertas_vivas` con la versión de su
        última medida y `nota_alertas`. Cuándo usarla: tras subir lotes a dos
        versiones, para decidir si la nueva mejora a la anterior; con la pantalla de
        comparación abierta, el resultado es el mismo.

        `a` es la versión de referencia y `b` la comparada; sin ellas, la activa
        anterior y la activa. `ventana`: `ultimo` (último lote de producción evaluado
        de cada versión) o `todos` (media de todos sus lotes evaluados). Un 404 dice
        que el proyecto o una versión no existe: `list_versions` da los ids."""
        params: dict[str, Any] = {"ventana": ventana}
        if a is not None:
            params["a"] = a
        if b is not None:
            params["b"] = b
        return await get_client().get(f"/projects/{project_id}/versions/compare", params=params)
