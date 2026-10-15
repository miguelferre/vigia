"""Seguridad, área mcp_llm (parte b): puertas de confirmación y rutas de subida del MCP."""

from __future__ import annotations

import json
import pathlib
import pickle
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import joblib
import pytest
import pytest_asyncio
from mcp.shared.memory import create_connected_server_and_client_session

from vigia.app.main import create_app
from vigia.app.settings import Settings
from vigia.mcp.client import VigiaClient, set_client
from vigia.mcp.server import mcp

CSV = (
    "id,prediction,label,Age\n"
    + "".join(f"{i},{i % 2},{(i + (i % 3 == 0)) % 2},{30 + i}\n" for i in range(1, 41))
).encode()
MAPEO = {"prediction_col": "prediction", "label_col": "label", "id_col": "id",
         "feature_cols": ["Age"], "favorable_label": 1}
UNC = "\\\\127.0.0.1\\vigia-prueba\\datos"
ACTOR = {"X-Vigia-Actor": "miguel", "X-Vigia-Actor-Kind": "humano"}


@pytest_asyncio.fixture
async def cliente_http(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    datos = tmp_path / "vigia-datos"
    datos.mkdir()
    ajustes = Settings(
        data_dir=datos, host="127.0.0.1", port_start=8765, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )
    app = create_app(ajustes)
    app.state.port = 8765
    app.state.shutdown_token = "test-token"
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as http:
        yield http


@pytest_asyncio.fixture
async def sesion_mcp(cliente_http: httpx.AsyncClient):
    cliente = VigiaClient(url="http://vigia", actor="claude-code-tests", http=cliente_http)
    cliente._base_url = "http://vigia"
    await cliente.bootstrap()
    set_client(cliente)
    return create_connected_server_and_client_session(mcp._mcp_server)


async def _llamar(sesion, nombre: str, args: dict) -> tuple[bool, object]:
    r = await sesion.call_tool(nombre, args)
    if getattr(r, "structuredContent", None) is not None:
        return r.isError, r.structuredContent
    texto = r.content[0].text if r.content else ""
    try:
        return r.isError, json.loads(texto)
    except ValueError:
        return r.isError, texto


async def _proyecto_con_linea_base(sesion, tmp_path: Path) -> dict:
    csv = tmp_path / "base.csv"
    csv.write_bytes(CSV)
    error, proyecto = await _llamar(sesion, "create_project", {"name": "seg", "deployment_stage": "validacion"})
    assert not error, proyecto
    error, subida = await _llamar(
        sesion,
        "upload_dataset",
        {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined",
         "role": "baseline", "mapping": MAPEO},
    )
    assert not error, subida
    return proyecto


LIMITE_CONFIRM = (
    "Límite conocido (decisión de diseño): la aprobación por "
    "llamada es del host del MCP; SEGURIDAD.md lo declara"
)


@pytest.mark.xfail(strict=True, reason=LIMITE_CONFIRM)
async def test_confirm_pickle_no_basta_con_el_parametro(sesion_mcp, tmp_path, monkeypatch):
    """Subir un pickle no se aprueba solo con confirm_pickle=true del modelo."""
    cargas: list[object] = []

    def carga_inerte(ruta, *a, **k):
        cargas.append(ruta)
        raise ValueError("carga inerte de prueba")

    monkeypatch.setattr(joblib, "load", carga_inerte)
    inerte = tmp_path / "modelo.joblib"
    inerte.write_bytes(pickle.dumps({"inerte": 1}))
    async with sesion_mcp as sesion:
        proyecto = await _proyecto_con_linea_base(sesion, tmp_path)
        args = {"version_id": proyecto["active_version_id"], "file_path": str(inerte)}
        error, texto = await _llamar(sesion, "upload_model_artifact", args)  # control: sin confirmar, falla
        assert error and "Unknown tool" not in str(texto) and not cargas
        error, texto = await _llamar(sesion, "upload_model_artifact", {**args, "confirm_pickle": True})
    assert not cargas, f"se abrió el pickle solo con confirm_pickle=true (respuesta: {texto})"


@pytest.mark.xfail(strict=True, reason=LIMITE_CONFIRM)
async def test_reset_project_confirm_no_basta_con_el_parametro(sesion_mcp, cliente_http, tmp_path):
    """Reiniciar un proyecto no se aprueba solo con confirm=true del modelo."""
    async with sesion_mcp as sesion:
        proyecto = await _proyecto_con_linea_base(sesion, tmp_path)
        listado = f"/api/projects/{proyecto['id']}/datasets"
        antes = (await cliente_http.get(listado)).json()["items"]
        assert antes
        args = {"project_id": proyecto["id"], "motivo": "prueba de seguridad"}
        error, texto = await _llamar(sesion, "reset_project", args)  # control: sin confirmar, falla
        assert error and "Unknown tool" not in str(texto)
        assert (await cliente_http.get(listado)).json()["items"] == antes
        await _llamar(sesion, "reset_project", {**args, "confirm": True})
    despues = (await cliente_http.get(listado)).json()["items"]
    assert despues == antes, "el reinicio se ejecutó solo con confirm=true"


@pytest.fixture
def lecturas(monkeypatch):
    """Registra las lecturas de ficheros del MCP; las rutas UNC y el fichero enorme nunca llegan al sistema."""
    vistas: list[str] = []
    orig_bytes, orig_texto = pathlib.Path.read_bytes, pathlib.Path.read_text

    def lee_bytes(self):
        vistas.append(str(self))
        if str(self).startswith("\\\\") or self.name == "enorme.csv":
            raise FileNotFoundError(str(self))
        return orig_bytes(self)

    def lee_texto(self, *a, **k):
        vistas.append(str(self))
        if str(self).startswith("\\\\"):
            raise FileNotFoundError(str(self))
        return orig_texto(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_bytes", lee_bytes)
    monkeypatch.setattr(pathlib.Path, "read_text", lee_texto)
    return vistas


def _llamadas(proyecto: dict, ruta: str) -> dict[str, tuple[str, dict]]:
    pid, vid = proyecto["id"], proyecto["active_version_id"]
    return {
        "upload_dataset": ("upload_dataset", {"project_id": pid, "file_path": ruta, "kind": "combined",
                                              "role": "production", "mapping": MAPEO}),
        "upload_usage_log": ("upload_usage_log", {"project_id": pid, "file_path": ruta, "valor_favorable": "1"}),
        "upload_outcomes": ("upload_outcomes", {"project_id": pid, "file_path": ruta}),
        "upload_model_artifact": ("upload_model_artifact", {"version_id": vid, "file_path": ruta,
                                                            "artifact_kind": "onnx"}),
        "create_dossier": ("create_dossier", {"project_id": pid, "motivo": "prueba", "dossier_path": ruta}),
    }


@pytest.mark.parametrize(
    "tool",
    ["upload_dataset", "upload_usage_log", "upload_outcomes", "upload_model_artifact", "create_dossier"],
)
async def test_ruta_unc_rechazada_antes_de_abrir(sesion_mcp, lecturas, tmp_path, tool):
    """Una ruta UNC no se abre desde las tools de subida."""
    async with sesion_mcp as sesion:
        proyecto = await _proyecto_con_linea_base(sesion, tmp_path)
        lecturas.clear()
        nombre, args = _llamadas(proyecto, UNC + ".json")[tool]
        error, texto = await _llamar(sesion, nombre, args)
    assert error and "Unknown tool" not in str(texto) and "validation error" not in str(texto), texto
    intentos = [r for r in lecturas if r.startswith("\\\\")]
    assert not intentos, f"{tool} intentó abrir una ruta UNC: {intentos}"


def _fichero_de_1_gib(ruta: Path) -> Path:
    """1 GiB sin ocupar disco si el volumen admite ficheros dispersos."""
    ruta.write_bytes(b"x")
    subprocess.run(["fsutil", "sparse", "setflag", str(ruta)], check=False, capture_output=True)
    with ruta.open("r+b") as f:
        f.truncate(1024 * 1024 * 1024)
    return ruta


async def test_fichero_enorme_rechazado_antes_de_leer(sesion_mcp, lecturas, tmp_path):
    """Las subidas del MCP tienen tope de tamaño antes de leer el fichero."""
    grande = _fichero_de_1_gib(tmp_path / "enorme.csv")
    async with sesion_mcp as sesion:
        proyecto = await _proyecto_con_linea_base(sesion, tmp_path)
        lecturas.clear()
        error, texto = await _llamar(
            sesion, "upload_outcomes", {"project_id": proyecto["id"], "file_path": str(grande)}
        )
    assert "Unknown tool" not in str(texto) and "validation error" not in str(texto), texto
    assert error
    assert str(grande) not in lecturas, "se intentó leer entero en memoria un fichero de 1 GiB"
