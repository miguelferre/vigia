"""Mensaje propio para un ONNX con entradas `double` que no abre.

`skl2onnx` exporta un regresor de árboles (`RandomForestRegressor`,
`GradientBoostingRegressor`) con entradas `double` cuando las columnas son
`float64`, y `onnxruntime` no abre ese grafo. Solo se consulta cuando la
validación ya ha fallado: un ONNX que hoy carga no cambia.
"""

from __future__ import annotations

from pathlib import Path

from vigia.core.predict_onnx import tiene_datos_externos

MENSAJE_ENTRADAS_DOUBLE = (
    "el modelo ONNX espera entradas de tipo double (float64) y onnxruntime no lo abre "
    "con un regresor de árboles. Exporta el modelo con entradas float32: usa "
    "FloatTensorType en skl2onnx, por ejemplo initial_types=[(\"X\", FloatTensorType([None, n]))], "
    "y vuelve a subirlo"
)

_DOUBLE = 11  # onnx.TensorProto.DOUBLE


def mensaje_si_entradas_double(ruta: Path) -> str | None:
    """`MENSAJE_ENTRADAS_DOUBLE` si el fichero tiene entradas `double` y no abre con
    `onnxruntime`; `None` en cualquier otro caso (incluido no poder leerlo)."""
    try:
        import onnx
        import onnxruntime as ort

        proto = onnx.load(str(ruta), load_external_data=False)
        # Mismo control que `load_session`. Un modelo con pesos en
        # ficheros externos no se abre con onnxruntime, que los leería de la ruta
        # que dice el propio modelo; el rechazo ya lleva su mensaje.
        if tiene_datos_externos(proto):
            return None
        hay_double = any(
            entrada.type.HasField("tensor_type") and entrada.type.tensor_type.elem_type == _DOUBLE
            for entrada in proto.graph.input
        )
        if not hay_double:
            return None
        try:
            ort.InferenceSession(str(ruta), providers=["CPUExecutionProvider"])
        except Exception:  # noqa: BLE001  # justo el caso que se busca
            return MENSAJE_ENTRADAS_DOUBLE
    except Exception:  # noqa: BLE001  # sin onnx o fichero ilegible: queda el mensaje de siempre
        return None
    return None
