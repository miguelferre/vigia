"""Seguridad, área mcp_llm (parte a): destino del backend ollama y entorno del LLM.

Cada test comprueba un control seguro; el nombre lleva la huella abreviada.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vigia.app.main import create_app
from vigia.app.settings import Settings
from vigia.human import llm_env
from vigia.human._vendor.interaction_review import llm as vendor_llm

HUELLAS = {
    "test_ollama_url_remota_exige_control": "llm-ollama-base-url-sin-validar-ni-confirmar",
    "test_ollama_patch_texto_plano_rechazado": "llm-ollama-base-url-sin-validar-ni-confirmar",
    "test_ollama_rotulo_ui_no_afirma_local_sin_comprobar": "llm-ollama-base-url-sin-validar-ni-confirmar",
    "test_llm_env_carrera_vista_propia_intacta": "human.llm-environment-process-global-race",
    "test_llm_env_carrera_entorno_limpio_al_salir": "human.llm-environment-process-global-race",
}

RAIZ = Path(__file__).resolve().parents[2]
ACTOR = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}
VARIABLES = ("LLM_BACKEND", "GEN_MODEL", "GEN_TEMPERATURE", "ANTHROPIC_API_KEY", "OLLAMA_BASE_URL")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    datos = tmp_path / "vigia-datos"
    datos.mkdir()
    ajustes = Settings(
        data_dir=datos, host="127.0.0.1", port_start=8765, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )
    app = create_app(ajustes)
    app.state.port = 8765
    app.state.shutdown_token = "test-token"
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _patch_llm(client: TestClient, llm: dict, **kw):
    cuerpo = {"actor": "miguel", "motivo": "prueba de seguridad", "values": {"llm": llm}}
    return client.patch("/api/settings", json=cuerpo, headers=ACTOR, **kw)


def _url_guardada(client: TestClient) -> str:
    return client.get("/api/settings?reveal=true").json()["llm"]["base_url"]


@pytest.mark.parametrize("remota", ["http://evil.example:11434", "https://evil.example"], ids=["http", "https"])
def test_ollama_url_remota_exige_control(client: TestClient, remota: str):
    """llm-ollama-base-url-sin-validar-ni-confirmar: un host que no es local no se acepta sin confirmación."""
    local = _patch_llm(client, {"backend": "ollama", "base_url": "http://127.0.0.1:11434"})
    assert local.status_code == 200, local.text  # control positivo: el caso normal funciona
    resp = _patch_llm(client, {"backend": "ollama", "base_url": remota})
    assert resp.status_code not in (404, 405), resp.text
    assert 400 <= resp.status_code < 500, f"se aceptó {remota} sin confirmación: {resp.status_code}"
    assert _url_guardada(client) != remota


def test_ollama_patch_texto_plano_rechazado(client: TestClient):
    """llm-ollama-base-url-sin-validar-ni-confirmar: el PATCH de ajustes no acepta un cuerpo text/plain."""
    cuerpo = '{"actor":"miguel","motivo":"t","values":{"llm":{"backend":"ollama","base_url":"http://127.0.0.1:11434"}}}'
    resp = client.patch(
        "/api/settings", content=cuerpo, headers={**ACTOR, "Content-Type": "text/plain"}
    )
    assert resp.status_code not in (404, 405), resp.text
    assert resp.status_code in (415, 422), resp.status_code
    assert client.get("/api/settings").json()["llm"]["backend"] == "none"


def test_ollama_rotulo_ui_no_afirma_local_sin_comprobar():
    """llm-ollama-base-url-sin-validar-ni-confirmar (variante de declaraciones): el rótulo «en este equipo» depende del host."""
    fuente = (RAIZ / "frontend/src/pages/ajustes/ajustes-llm.tsx").read_text(encoding="utf-8")
    assert "base_url" in fuente  # el fichero es el de ajustes del LLM
    afirma_local = "en este equipo" in fuente
    comprueba_host = re.search(r"new URL\(|hostname|loopback|esLocal|es_local", fuente)
    assert (not afirma_local) or comprueba_host


def _escenario_carrera(monkeypatch) -> dict[str, object]:
    """Un trabajo con modelo (A) y otro rápido sin modelo (B) abren el entorno a la vez; B sale el último."""
    originales = {k: os.environ.get(k) for k in VARIABLES}
    for k in VARIABLES:
        monkeypatch.delenv(k, raising=False)
    a_dentro, a_mira, b_dentro, b_libera = (threading.Event() for _ in range(4))
    visto: dict[str, object] = {}

    def trabajo_a():
        with llm_env.llm_environment(backend="anthropic", model="m", base_url="", api_key="K-prueba"):
            a_dentro.set()
            a_mira.wait(10)
            visto["clave"] = os.environ.get("ANTHROPIC_API_KEY")
            visto["backend_env"] = os.environ.get("LLM_BACKEND")
            visto["backend_paquete"] = vendor_llm.backend()

    def trabajo_b():
        with llm_env.llm_environment(backend="none", model="", base_url="", api_key=""):
            b_dentro.set()
            b_libera.wait(10)

    try:
        ta = threading.Thread(target=trabajo_a)
        tb = threading.Thread(target=trabajo_b)
        ta.start()
        assert a_dentro.wait(10)
        tb.start()
        b_dentro.wait(1.0)  # con un cerrojo, B espera y no entra: no es un fallo
        a_mira.set()
        ta.join(10)
        b_libera.set()
        tb.join(10)
        visto["despues"] = {k: os.environ.get(k) for k in VARIABLES}
    finally:
        for k, v in originales.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    assert not ta.is_alive() and not tb.is_alive()
    return visto


def test_llm_env_carrera_vista_propia_intacta(monkeypatch):
    """human.llm-environment-process-global-race: un trabajo en curso conserva su clave y su backend aunque otro abra el entorno."""
    visto = _escenario_carrera(monkeypatch)
    assert visto["clave"] == "K-prueba"
    assert visto["backend_env"] == "anthropic"
    assert visto["backend_paquete"] == "anthropic"


def test_llm_env_carrera_entorno_limpio_al_salir(monkeypatch):
    """human.llm-environment-process-global-race: al acabar los dos trabajos no queda clave ni backend en el entorno."""
    visto = _escenario_carrera(monkeypatch)
    despues = visto["despues"]
    assert despues["ANTHROPIC_API_KEY"] is None
    assert despues["LLM_BACKEND"] is None
