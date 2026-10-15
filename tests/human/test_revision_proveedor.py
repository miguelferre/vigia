"""Clasificación de los fallos de proveedor tras vendorizar `interaction_review`.

`dossiers_review_job._es_fallo_de_proveedor` mira el primer segmento de
`__module__` de cada clase del MRO. Con el paquete externo, sus errores tenían
`interaction_review` como primer segmento y no contaban como de proveedor; con la
copia, su primer segmento es `vigia`. Estos tests fijan que no cambia nada:
un error de `anthropic` o de `httpx` sigue siendo de proveedor y uno de la copia
(el mismo `LLMNotConfigured` o un `RuntimeError` de `llm.py`) sigue sin serlo.
"""

from __future__ import annotations

import anthropic
import httpx

from vigia.app.services import dossiers_review_job as job
from vigia.human import dossier_adapter
from vigia.human._vendor.interaction_review import llm as ir_llm


def _peticion() -> httpx.Request:
    return httpx.Request("POST", "http://127.0.0.1:1/v1/messages")


def test_error_de_anthropic_es_de_proveedor():
    exc = anthropic.APIConnectionError(request=_peticion())
    assert job._es_fallo_de_proveedor(exc)


def test_error_de_httpx_es_de_proveedor():
    assert job._es_fallo_de_proveedor(httpx.ConnectError("sin conexión", request=_peticion()))
    assert job._es_fallo_de_proveedor(httpx.ReadTimeout("lento", request=_peticion()))


def test_error_de_red_del_sistema_es_de_proveedor():
    assert job._es_fallo_de_proveedor(ConnectionRefusedError("rechazada"))


def test_errores_de_la_copia_no_son_de_proveedor():
    """Como antes con `interaction_review`: no son de proveedor ni por tipo ni por módulo."""
    assert ir_llm.LLMNotConfigured.__module__.startswith("vigia.human._vendor.interaction_review")
    assert not job._es_fallo_de_proveedor(ir_llm.LLMNotConfigured("sin backend"))
    assert not job._es_fallo_de_proveedor(RuntimeError("The model did not return a tool_use block."))
    assert not job._es_fallo_de_proveedor(dossier_adapter.DossierInvalido("campo vacío"))


def test_texto_de_error_de_la_copia_no_atribuye_al_proveedor():
    texto = job._texto_error_revision(ir_llm.LLMNotConfigured("sin backend"), en_proveedor=True)
    assert "proveedor" not in texto
    texto = job._texto_error_revision(
        anthropic.APIConnectionError(request=_peticion()), en_proveedor=True
    )
    assert texto.startswith("el proveedor del modelo de lenguaje respondió:")
