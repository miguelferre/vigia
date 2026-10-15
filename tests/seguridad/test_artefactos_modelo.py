"""Artefactos de modelo (subida, apertura y huella).

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import hashlib
import struct
import threading
from pathlib import Path

import onnx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from onnx import TensorProto, helper
from onnx.external_data_helper import set_external_data
from sqlmodel import Session

from tests.api.test_model_artifacts import (
    _entrenar_pipeline,
    _onnx_bytes,
    _preparar_proyecto_con_baseline,
    _subir_artefacto,
)
from tests.seguridad import _base_proyecto as _base
from vigia.app.events import Actor
from vigia.app.models import ModelVersion
from vigia.app.services import model_registry
from vigia.app.services.onnx_entradas_double import mensaje_si_entradas_double

# Fixtures compartidas (carpeta de datos temporal y cliente con `base_url` local).
app, client, session, settings = _base.app, _base.client, _base.session, _base.settings

HUELLAS = {
    "test_subidas_solapadas_dejan_el_hash_del_fichero_activo": (
        "model-registry/temporal-nuevo-compartido-entre-subidas-concurrentes"
    ),
    "test_mensaje_de_entradas_double_no_abre_un_modelo_con_datos_externos": (
        "onnx/mensaje-doble-reabre-fichero-rechazado-por-datos-externos"
    ),
    "test_prediccion_rechaza_un_onnx_cambiado_en_disco": "model-file-hash",
}


def _variante(contenido: bytes, marca: str) -> bytes:
    """El mismo modelo con otra marca en el documento: bytes distintos, mismo grafo."""
    modelo = onnx.load_from_string(contenido)
    modelo.doc_string = marca
    return modelo.SerializeToString()


def test_subidas_solapadas_dejan_el_hash_del_fichero_activo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Dos subidas de la misma versión y el mismo nombre no comparten el temporal:
    el hash guardado es siempre el del fichero que queda activo y ninguna acaba
    en un error sin tratar (en Windows, el temporal compartido lo mantiene abierto
    la sesión de onnxruntime de la otra subida)."""
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "s1c-subidas")
    base = _onnx_bytes(_entrenar_pipeline())
    contenidos = {"a": _variante(base, "a"), "b": _variante(base, "b")}
    real = model_registry.validate_and_load
    a_valido, b_empieza = threading.Event(), threading.Event()
    llamadas = []

    def validar(temporal, *args, **kwargs):
        llamadas.append(temporal)
        es_a = len(llamadas) == 1
        if not es_a:
            b_empieza.set()
        resultado = real(temporal, *args, **kwargs)
        if es_a:
            a_valido.set()
            b_empieza.wait(timeout=2)  # sin cerrojo, B escribe aquí su temporal
        return resultado

    monkeypatch.setattr(model_registry, "validate_and_load", validar)
    engine = client.app.state.engine
    data_dir = Path(client.app.state.settings.data_dir)
    resultados: dict[str, object] = {}

    def subir(clave: str) -> None:
        with Session(engine) as s:
            try:
                version = s.get(ModelVersion, version_id)
                resultados[clave] = model_registry.upload_artifact(
                    s,
                    version,
                    file_bytes=contenidos[clave],
                    filename="modelo.onnx",
                    artifact_kind="onnx",
                    confirmacion_pickle=False,
                    data_dir=data_dir,
                    actor=Actor(kind="humano", id="miguel"),
                )
            except Exception as exc:  # noqa: BLE001
                resultados[clave] = exc

    hilo_a = threading.Thread(target=subir, args=("a",))
    hilo_a.start()
    assert a_valido.wait(timeout=30)
    hilo_b = threading.Thread(target=subir, args=("b",))
    hilo_b.start()
    hilo_a.join(timeout=60)
    hilo_b.join(timeout=60)
    assert set(resultados) == {"a", "b"}
    sin_control = [r for r in resultados.values() if isinstance(r, Exception) and not isinstance(r, HTTPException)]
    assert sin_control == [], sin_control

    with Session(engine) as s:
        version = s.get(ModelVersion, version_id)
        en_disco = hashlib.sha256(Path(version.artifact_path).read_bytes()).hexdigest()
        assert version.artifact_sha256 == en_disco
    assert not list(data_dir.rglob("*.nuevo"))


def _onnx_double_con_datos_externos(ruta: Path) -> None:
    peso = helper.make_tensor("w", TensorProto.DOUBLE, [1], struct.pack("<d", 1.0), raw=True)
    set_external_data(peso, location="otro.bin")
    peso.ClearField("raw_data")
    entrada = helper.make_tensor_value_info("X", TensorProto.DOUBLE, [None, 1])
    salida = helper.make_tensor_value_info("Y", TensorProto.DOUBLE, [None, 1])
    nodo = helper.make_node("Add", ["X", "w"], ["Y"])
    grafo = helper.make_graph([nodo], "g", [entrada], [salida], initializer=[peso])
    ruta.write_bytes(helper.make_model(grafo).SerializeToString())


def test_mensaje_de_entradas_double_no_abre_un_modelo_con_datos_externos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Un ONNX con pesos en ficheros externos no se abre con onnxruntime ni para
    elegir el texto del error: se rechaza antes de abrirlo."""
    ruta = tmp_path / "m.onnx"
    _onnx_double_con_datos_externos(ruta)
    llamadas: list[str] = []
    import onnxruntime

    monkeypatch.setattr(
        onnxruntime, "InferenceSession", lambda *a, **k: llamadas.append(str(a)) or object()
    )
    assert mensaje_si_entradas_double(ruta) is None
    assert llamadas == []


def test_prediccion_rechaza_un_onnx_cambiado_en_disco(client: TestClient):
    """La función de predicción recomprueba el hash del ONNX como el del pickle:
    si el fichero cambió desde la subida, 409 sin abrirlo."""
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "s1c-onnx-hash")
    base = _onnx_bytes(_entrenar_pipeline())
    assert _subir_artefacto(client, version_id, contenido=base).status_code == 200
    with Session(client.app.state.engine) as s:
        version = s.get(ModelVersion, version_id)
        assert callable(model_registry.get_predict_fn(version))
        Path(version.artifact_path).write_bytes(_variante(base, "otro"))
        with pytest.raises(HTTPException) as exc:
            model_registry.get_predict_fn(version)
    assert exc.value.status_code == 409
