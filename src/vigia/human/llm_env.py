"""Entorno del paquete `interaction_review` durante un trabajo.

Sin imports del paquete: solo `os`. `human/dossier_adapter.py` lo reexporta y
`services/dossiers_review_job.py` lo abre alrededor de cada revisión.
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Iterator

__all__ = ["llm_environment"]

_CERROJO = threading.RLock()


@contextlib.contextmanager
def llm_environment(*, backend: str, model: str, base_url: str, api_key: str) -> Iterator[None]:
    """Fija `LLM_BACKEND`/`GEN_MODEL`/`GEN_TEMPERATURE`/clave/URL del entorno
    del proceso justo antes de invocar al paquete y restaura el valor previo (o
    lo borra) en un `finally`: nunca persisten fuera de la ejecución
    del job. Para `b0` se fija igualmente `LLM_BACKEND=none`."""
    claves: dict[str, str | None] = {
        "LLM_BACKEND": backend,
        "GEN_MODEL": model or None,
        "GEN_TEMPERATURE": "0",
        "ANTHROPIC_API_KEY": (api_key or None) if backend == "anthropic" else None,
        "OLLAMA_BASE_URL": (base_url or None) if backend == "ollama" else None,
        # Variables del SDK de Anthropic heredadas del entorno: dentro del trabajo no existen.
        "ANTHROPIC_BASE_URL": None,
        "ANTHROPIC_AUTH_TOKEN": None,
    }
    # El entorno es del proceso: un cerrojo hace que dos trabajos con modelo
    # no se pisen la clave, el backend ni la URL.
    with _CERROJO:
        previos = {k: os.environ.get(k) for k in claves}
        try:
            for clave, valor in claves.items():
                if valor is None:
                    os.environ.pop(clave, None)
                else:
                    os.environ[clave] = valor
            yield
        finally:
            for clave, valor in previos.items():
                if valor is None:
                    os.environ.pop(clave, None)
                else:
                    os.environ[clave] = valor
