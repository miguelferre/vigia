"""Prueba por stdio real. Un `vigia serve` en un puerto libre y
`vigia mcp --url` como subproceso, con una `ClientSession` por stdio de verdad.
Los tests en memoria no ven el bucle de eventos ni el arranque del proceso."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Subprocesos reales; pyproject.toml registra el marcador `slow` en pyproject.toml.
pytestmark = pytest.mark.slow

TOOLS_ESPERADAS = 39

SRC = Path(__file__).resolve().parents[2] / "src"


def _entorno() -> dict[str, str]:
    """Entorno de los subprocesos: `src` de ESTE árbol de trabajo delante en PYTHONPATH,
    para que `vigia mcp` y `vigia serve` no carguen el `vigia` de otro checkout (una
    copia de trabajo con el `.venv` enlazado importaría el principal)."""
    previo = os.environ.get("PYTHONPATH")
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(SRC) + (os.pathsep + previo if previo else "")}


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _parar(proc: subprocess.Popen) -> None:
    """Apaga `vigia serve` y su árbol (el venv de Windows lanza un hijo)."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def backend(tmp_path: Path) -> Iterator[str]:
    puerto = _puerto_libre()
    data_dir = tmp_path / "datos-stdio"
    data_dir.mkdir()
    proc = subprocess.Popen(
        [sys.executable, "-m", "vigia", "serve", "--no-browser", "--port", str(puerto), "--data-dir", str(data_dir)],
        env=_entorno(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{puerto}"
    try:
        limite = time.monotonic() + 45
        while True:
            if proc.poll() is not None:
                pytest.fail("vigia serve terminó antes de responder")
            try:
                if httpx.get(f"{url}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > limite:
                pytest.fail("vigia serve no respondió en 45 s")
            time.sleep(0.3)
        yield url
    finally:
        _parar(proc)


def _datos(resultado) -> object:
    import json

    if getattr(resultado, "structuredContent", None) is not None:
        return resultado.structuredContent
    return json.loads(resultado.content[0].text)


async def test_mcp_por_stdio_real(backend: str):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vigia", "mcp", "--url", backend, "--actor", "claude-stdio-test"],
        env=_entorno(),
    )
    async with stdio_client(params) as (leer, escribir), ClientSession(leer, escribir) as sesion:
        await sesion.initialize()
        # El `vigia` del subproceso sale de este árbol: si no, contaría las tools de otro checkout.
        import vigia.mcp

        assert SRC in Path(vigia.mcp.__file__).resolve().parents
        listado = await sesion.list_tools()
        assert len(listado.tools) == TOOLS_ESPERADAS

        proyectos = await sesion.call_tool("list_projects", {})
        assert not proyectos.isError, proyectos
        assert _datos(proyectos)["total"] == 0

        creado = await sesion.call_tool("create_project", {"name": "Proyecto por stdio", "deployment_stage": "desarrollo"})
        assert not creado.isError, creado
        proyecto = _datos(creado)
        assert proyecto["name"] == "Proyecto por stdio"

        # List_versions por stdio real, con la v1 activa del proyecto recién creado.
        versiones = await sesion.call_tool("list_versions", {"project_id": proyecto["id"]})
        assert not versiones.isError, versiones
        lista = _datos(versiones)
        assert lista["active_version_id"] == proyecto["active_version_id"]
        assert [v["id"] for v in lista["versions"]] == [proyecto["active_version_id"]]

        eventos = await sesion.call_tool(
            "get_events", {"object_type": "project", "object_id": proyecto["id"], "actor_kind": "agente"}
        )
        assert not eventos.isError, eventos
        items = _datos(eventos)["items"]
        creacion = next(e for e in items if e["action"].startswith("proyecto.") and e["actor_kind"] == "agente")
        assert creacion["actor_id"] == "claude-stdio-test"
        # El alta de proyecto guarda el `correlation_id` de la llamada.
        assert uuid.UUID(creacion["correlation_id"])
        por_correlacion = await sesion.call_tool("get_events", {"correlation_id": creacion["correlation_id"]})
        assert creacion["id"] in {e["id"] for e in _datos(por_correlacion)["items"]}
        riesgo = await sesion.call_tool(
            "create_risk",
            {
                "project_id": proyecto["id"],
                "title": "Riesgo por stdio",
                "motivo": "prueba stdio",
                "impact_level": 2,
                "probability_level": 2,
            },
        )
        assert not riesgo.isError, riesgo
        eventos_riesgo = await sesion.call_tool(
            "get_events", {"object_type": "risk", "object_id": _datos(riesgo)["id"], "actor_kind": "agente"}
        )
        alta = _datos(eventos_riesgo)["items"][0]
        assert alta["actor_id"] == "claude-stdio-test"
        assert uuid.UUID(alta["correlation_id"])  # el UUID de esa llamada

        # El correlation_id es el de la llamada: filtrar por él devuelve el mismo evento.
        mismo = await sesion.call_tool("get_events", {"correlation_id": alta["correlation_id"]})
        assert alta["id"] in {e["id"] for e in _datos(mismo)["items"]}

        # Un error de la API llega con el código por delante, también por stdio.
        error = await sesion.call_tool("get_alert", {"alert_id": 999999})
        assert error.isError
        assert error.content[0].text.startswith("404:")


USAGE_CSV = Path(__file__).resolve().parents[2] / "data" / "demo" / "usage_logs_demo.csv"


async def test_arreglos_por_stdio_real(backend: str, tmp_path: Path):
    """Contra un subproceso `vigia mcp` con su backend: el aviso de
    calibración de `evaluate_cross`, el diario acotado de `export_report` y la
    plantilla de mapeo heredada por `upload_dataset`."""
    import asyncio

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vigia", "mcp", "--url", backend, "--actor", "claude-stdio-r3"],
        env=_entorno(),
    )
    async with stdio_client(params) as (leer, escribir), ClientSession(leer, escribir) as sesion:
        await sesion.initialize()
        proyecto = _datos(await sesion.call_tool("create_project", {"name": "Arreglos por stdio", "deployment_stage": "desarrollo"}))

        # La primera evaluación cruzada es de calibración y el agente lo sabe.
        subida = await sesion.call_tool(
            "upload_usage_log",
            {"project_id": proyecto["id"], "file_path": str(USAGE_CSV), "valor_favorable": "refer"},
        )
        assert not subida.isError, subida
        primera = await asyncio.wait_for(
            sesion.call_tool("evaluate_cross", {"project_id": proyecto["id"]}), timeout=60
        )
        assert not primera.isError, primera
        job = _datos(primera)
        assert job["status"] == "terminado", job
        assert job["result"]["mode"] == "calibracion"
        assert "calibración" in job["aviso"] and "evaluate_cross" in job["aviso"]
        segunda = _datos(
            await asyncio.wait_for(sesion.call_tool("evaluate_cross", {"project_id": proyecto["id"]}), timeout=60)
        )
        assert segunda["status"] == "terminado", segunda
        assert segunda["result"]["mode"] != "calibracion"
        assert "aviso" not in segunda

        # El diario sale acotado, con el total y si se truncó.
        corto = await sesion.call_tool("export_report", {"kind": "diario", "limit": 2})
        assert not corto.isError, corto
        diario = _datos(corto)
        assert diario["devueltos"] == 2 and diario["limit"] == 2
        assert diario["total"] > 2 and diario["truncado"] is True
        assert [e["ts"] for e in diario["eventos"]] == sorted(e["ts"] for e in diario["eventos"])
        completo = _datos(await sesion.call_tool("export_report", {"kind": "diario"}))
        assert completo["limit"] == 200
        assert completo["devueltos"] == min(completo["total"], 200)
        assert completo["truncado"] is (completo["total"] > 200)
        assert completo["eventos"][-2:] == diario["eventos"]  # los más recientes
        # `since` sigue acotando igual: solo desde el penúltimo evento.
        desde = _datos(
            await sesion.call_tool("export_report", {"kind": "diario", "since": diario["eventos"][0]["ts"]})
        )
        assert desde["total"] >= 2 and desde["truncado"] is False

        # Sin `mapping` y sin plantilla, error claro antes de subir nada.
        csv = tmp_path / "plantilla.csv"
        csv.write_bytes(b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n")
        args = {"project_id": proyecto["id"], "file_path": str(csv), "kind": "combined", "role": "production"}
        sin = await asyncio.wait_for(sesion.call_tool("upload_dataset", args), timeout=30)
        assert sin.isError
        assert sin.content[0].text.startswith("422:")
        assert "set_mapping_template" in sin.content[0].text

        # Con plantilla fijada, la hereda y lo dice.
        plantilla = {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "feature_cols": ["Age"],
        }
        fijada = await sesion.call_tool(
            "set_mapping_template",
            {"project_id": proyecto["id"], "mapping_template": plantilla, "actor": "stdio", "motivo": "prueba"},
        )
        assert not fijada.isError, fijada
        con = await asyncio.wait_for(sesion.call_tool("upload_dataset", args), timeout=60)
        assert not con.isError, con
        datos = _datos(con)
        assert datos["mapping_origen"] == "plantilla_proyecto"
        assert datos["mapping_aplicado"]["prediction_col"] == "prediction"
        assert datos["ingest_job"]["status"] == "terminado", datos


async def test_upload_dataset_sin_mapeo_no_cuelga_por_stdio(backend: str, tmp_path: Path):
    """La primera espera por stdio importaba el backend y no volvía. Ahora
    la tool devuelve en menos de `timeout_s` el error de la ingesta."""
    import asyncio

    csv = tmp_path / "sin_mapeo.csv"
    csv.write_bytes(b"id,prediction,label,Age\n1,1,1,30\n2,0,0,45\n")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vigia", "mcp", "--url", backend],
        env=_entorno(),
    )
    async with stdio_client(params) as (leer, escribir), ClientSession(leer, escribir) as sesion:
        await sesion.initialize()
        creado = _datos(await sesion.call_tool("create_project", {"name": "sin-mapeo", "deployment_stage": "desarrollo"}))
        res = await asyncio.wait_for(
            sesion.call_tool(
                "upload_dataset",
                {
                    "project_id": creado["id"],
                    "file_path": str(csv),
                    "kind": "combined",
                    "role": "production",
                    "timeout_s": 10,
                },
            ),
            timeout=30,
        )
    assert res.isError
    assert res.content[0].text.startswith("422:")
    assert "mapeo" in res.content[0].text


async def test_set_monitor_fusiona_por_stdio_real(backend: str):
    """Por stdio real, `set_monitor` con un umbral cambia ese y
    conserva los demás del monitor de calidad."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vigia", "mcp", "--url", backend, "--actor", "claude-stdio-d176"],
        env=_entorno(),
    )
    async with stdio_client(params) as (leer, escribir), ClientSession(leer, escribir) as sesion:
        await sesion.initialize()
        proyecto = _datos(await sesion.call_tool("create_project", {"name": "Umbrales por stdio", "deployment_stage": "desarrollo"}))
        async with httpx.AsyncClient(base_url=backend, timeout=10) as http:
            monitores = (await http.get(f"/api/projects/{proyecto['id']}/monitors")).json()["items"]
        calidad = next(m for m in monitores if m["type"] == "quality")
        antes = calidad["thresholds"]["thresholds"]
        assert len(antes) >= 2
        nuevo = {"metric_key": antes[0]["metric_key"], "kind": antes[0]["kind"], "value": 0.81,
                 "origen": "criterio_clinico"}
        res = await sesion.call_tool(
            "set_monitor",
            {"monitor_id": calidad["id"], "actor": "claude-stdio-d176", "motivo": "ficha",
             "thresholds": {"thresholds": [nuevo]}},
        )
        assert not res.isError, res
    async with httpx.AsyncClient(base_url=backend, timeout=10) as http:
        despues = (await http.get(f"/api/monitors/{calidad['id']}")).json()["thresholds"]["thresholds"]
    assert despues[0] == nuevo
    assert despues[1:] == antes[1:]


async def test_get_settings_instancia_y_actor_por_stdio_real(backend: str):
    """Por stdio real: `get_settings` dice a qué instancia habla (el
    `puerto_en_uso` es el del backend, no el preferido) y una escritura con un `actor`
    de texto libre sale en el diario con el `--actor` de la entrada."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vigia", "mcp", "--url", backend, "--actor", "claude-stdio-m1"],
        env=_entorno(),
    )
    async with stdio_client(params) as (leer, escribir), ClientSession(leer, escribir) as sesion:
        await sesion.initialize()
        ajustes = _datos(await sesion.call_tool("get_settings", {}))
        instancia = ajustes["instancia"]
        assert instancia["url_base"] == backend
        assert instancia["puerto_en_uso"] == int(backend.rsplit(":", 1)[1])
        assert instancia["data_dir"] and instancia["version"]
        proyecto = _datos(await sesion.call_tool("create_project", {"name": "Actor por stdio", "deployment_stage": "desarrollo"}))
        riesgo = _datos(
            await sesion.call_tool(
                "create_risk",
                {
                    "project_id": proyecto["id"],
                    "title": "Riesgo de prueba",
                    "motivo": "prueba",
                    "impact_level": 2,
                    "probability_level": 2,
                    "actor": "Claude (por encargo del usuario)",
                },
            )
        )
    async with httpx.AsyncClient(base_url=backend, timeout=10) as http:
        eventos = (
            await http.get("/api/events", params={"object_type": "risk", "object_id": riesgo["id"]})
        ).json()["items"]
    alta = next(e for e in eventos if e["actor_kind"] == "agente")
    assert alta["actor_id"] == "claude-stdio-m1"
    assert alta["after"]["actor_detalle"] == "Claude (por encargo del usuario)"


def _csv_multiclase(ruta: Path, n: int = 5000) -> list[str]:
    """Línea base de 5 clases (como `moderacion`) con una probabilidad por clase."""
    import numpy as np

    clases = ["permitido", "spam", "odio", "desnudez", "violencia"]
    rng = np.random.default_rng(7)
    verdad = rng.choice(5, size=n, p=[0.60, 0.15, 0.10, 0.08, 0.07])
    ruido = rng.dirichlet(np.ones(5) * 0.6, size=n) * 0.55
    ruido[np.arange(n), verdad] += 0.45
    probs = ruido / ruido.sum(axis=1, keepdims=True)
    lineas = ["id,prediction,label," + ",".join(f"prob_{c}" for c in clases) + ",longitud"]
    for i in range(n):
        lineas.append(
            f"m{i},{clases[int(probs[i].argmax())]},{clases[int(verdad[i])]},"
            + ",".join(f"{p:.6f}" for p in probs[i])
            + f",{int(rng.integers(5, 400))}"
        )
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return clases


async def test_get_threshold_proposal_multiclase_por_stdio_real_no_da_504(backend: str, tmp_path: Path):
    """La propuesta multiclase remuestrea en el servidor (unos 3 a 7 s) y el cliente del
    MCP esperaba 5 s. Con `get_threshold_proposal` a 60 s, la tool devuelve la propuesta.
    El test determinista del tiempo está en `test_multiclase_correcciones.py`; este prueba el camino
    completo por stdio real (bucle de eventos, subproceso, backend en un puerto)."""
    import asyncio

    csv = tmp_path / "base.csv"
    clases = _csv_multiclase(csv)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vigia", "mcp", "--url", backend, "--actor", "claude-stdio-221"],
        env=_entorno(),
    )
    async with stdio_client(params) as (leer, escribir), ClientSession(leer, escribir) as sesion:
        await sesion.initialize()
        proyecto = _datos(
            await sesion.call_tool(
                "create_project",
                {"name": "Propuesta multiclase por stdio", "deployment_stage": "validacion",
                 "task_type": "multiclass", "classes": clases, "favorable_label": ["permitido"]},
            )
        )
        subida = await sesion.call_tool(
            "upload_dataset",
            {
                "project_id": proyecto["id"], "file_path": str(csv), "kind": "combined", "role": "baseline",
                "mapping": {
                    "prediction_col": "prediction", "label_col": "label", "id_col": "id",
                    "classes": clases, "probability_cols": [f"prob_{c}" for c in clases],
                    "favorable_label": ["permitido"], "feature_cols": ["longitud"],
                },
            },
        )
        assert not subida.isError, subida
        propuesta = await asyncio.wait_for(
            sesion.call_tool("get_threshold_proposal", {"project_id": proyecto["id"]}), timeout=90
        )
        assert not propuesta.isError, propuesta
        por_monitor = {m["monitor_type"]: m["propuestas"] for m in _datos(propuesta)["monitors"]}
        assert {"quality", "drift", "fairness"} <= set(por_monitor)
        assert {"accuracy", "f1_measure", "area_under_roc"} <= {p["metric_key"] for p in por_monitor["quality"]}
