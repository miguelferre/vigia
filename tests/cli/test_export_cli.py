"""Tests de `vigia export events` y `vigia export openapi`."""

from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session, select

from vigia.app.db import init_db, make_engine, session_scope
from vigia.app.events import record_event
from vigia.app.models import Event
from vigia.cli import main


def _crear_db_con_eventos(data_dir: Path) -> None:
    db_path = data_dir / "vigia.db"
    engine = make_engine(db_path)
    init_db(engine, db_path)
    with session_scope(engine) as session:
        record_event(
            session,
            actor_kind="humano",
            actor_id="miguel",
            action="proyecto.crear",
            object_type="project",
            object_id=1,
            project_id=1,
            motivo="alta del proyecto de prueba",
        )
        record_event(
            session,
            actor_kind="modelo",
            actor_id="vigia.core",
            action="evaluacion.ejecutar",
            object_type="evaluation",
            object_id=1,
            project_id=1,
        )
    engine.dispose()


def test_export_events_json_escribe_los_eventos_y_respeta_since_until(tmp_path):
    data_dir = tmp_path / "vigia-datos"
    data_dir.mkdir()
    _crear_db_con_eventos(data_dir)

    db_path = data_dir / "vigia.db"
    engine = make_engine(db_path)
    with Session(engine) as session:
        eventos = list(session.exec(select(Event).order_by(Event.id)))
        assert len(eventos) == 2
        ts_primero, ts_segundo = eventos[0].ts, eventos[1].ts
    engine.dispose()

    salida = tmp_path / "eventos.json"
    codigo = main(
        [
            "export",
            "events",
            "--since",
            "2000-01-01T00:00:00+00:00",
            "--out",
            str(salida),
            "--data-dir",
            str(data_dir),
        ]
    )
    assert codigo == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert len(datos) == 2
    acciones = {e["action"] for e in datos}
    assert acciones == {"proyecto.crear", "evaluacion.ejecutar"}

    # since = justo el ts del segundo evento: solo debe quedar ese.
    salida_since = tmp_path / "eventos_since.json"
    codigo = main(
        [
            "export",
            "events",
            "--since",
            ts_segundo,
            "--out",
            str(salida_since),
            "--data-dir",
            str(data_dir),
        ]
    )
    assert codigo == 0
    datos_since = json.loads(salida_since.read_text(encoding="utf-8"))
    assert len(datos_since) == 1
    assert datos_since[0]["action"] == "evaluacion.ejecutar"

    # until = justo el ts del primer evento: solo debe quedar ese.
    salida_until = tmp_path / "eventos_until.json"
    codigo = main(
        [
            "export",
            "events",
            "--since",
            "2000-01-01T00:00:00+00:00",
            "--until",
            ts_primero,
            "--out",
            str(salida_until),
            "--data-dir",
            str(data_dir),
        ]
    )
    assert codigo == 0
    datos_until = json.loads(salida_until.read_text(encoding="utf-8"))
    assert len(datos_until) == 1
    assert datos_until[0]["action"] == "proyecto.crear"


def test_export_events_html_contiene_titulo_y_filas(tmp_path):
    data_dir = tmp_path / "vigia-datos"
    data_dir.mkdir()
    _crear_db_con_eventos(data_dir)

    salida = tmp_path / "eventos.html"
    codigo = main(
        [
            "export",
            "events",
            "--since",
            "2000-01-01T00:00:00+00:00",
            "--format",
            "html",
            "--out",
            str(salida),
            "--data-dir",
            str(data_dir),
        ]
    )
    assert codigo == 0
    html = salida.read_text(encoding="utf-8")
    assert "Evidencias Vigía" in html
    assert "proyecto.crear" in html
    assert "evaluacion.ejecutar" in html
    assert "<table>" in html


def test_export_events_sin_base_de_datos_falla_con_mensaje_claro(tmp_path, capsys):
    data_dir = tmp_path / "vigia-datos-vacia"
    data_dir.mkdir()

    codigo = main(
        [
            "export",
            "events",
            "--since",
            "2000-01-01T00:00:00+00:00",
            "--out",
            str(tmp_path / "eventos.json"),
            "--data-dir",
            str(data_dir),
        ]
    )
    assert codigo == 1
    assert "no existe la base de datos" in capsys.readouterr().err


def test_export_openapi_tiene_las_diecisiete_etiquetas(tmp_path):
    """Las diecisiete etiquetas (las doce básicas, `contenido`, `auditoria`, `riesgos`, `esquema` y `modelo`) son las declaradas en `router = APIRouter(tags=[...])`
    de cada módulo de `routers/*.py` (vía `ALL_ROUTERS`). No se comprueban a través de los
    `paths` del esquema: mientras otros carriles no hayan añadido rutas a su router, FastAPI
    no emite esas etiquetas en ninguna operación, aunque el router ya las declare.
    """
    from vigia.app.routers import ALL_ROUTERS

    etiquetas_esperadas = {
        "salud",
        "ajustes",
        "proyectos",
        "datos",
        "monitores",
        "evaluaciones",
        "alertas",
        "explicabilidad",
        "demo",
        "capa-humana",
        "diario",
        "jobs",
        # El router de contenido de ayuda.
        "contenido",
        # Dossier de auditoría y matriz de riesgos.
        "auditoria",
        # Artefacto del modelo ejecutable.
        "modelo",
        "riesgos",
        # `GET /schema/tables`, introspección para el resource
        # `schema://tables` del servidor MCP.
        "esquema",
    }
    etiquetas_reales: set[str] = set()
    for modulo in ALL_ROUTERS:
        etiquetas_reales.update(modulo.router.tags)
    assert etiquetas_esperadas == etiquetas_reales, etiquetas_reales

    salida = tmp_path / "openapi.json"
    codigo = main(["export", "openapi", "--out", str(salida)])
    assert codigo == 0

    esquema = json.loads(salida.read_text(encoding="utf-8"))
    assert esquema["info"]["title"] == "Vigía"

    # No se crea ninguna base de datos: la carpeta temporal usada por el CLI ya no existe.
    assert not salida.parent.joinpath("vigia.db").exists()


def test_export_events_html_paridad_api_y_cli(tmp_path):
    """§9.4: el HTML de `GET /events/export` y el de `vigia export events` son idénticos
    para los mismos eventos (mismo `services/evidence.py` en los dos caminos)."""
    from fastapi.testclient import TestClient

    from vigia.app.main import create_app
    from vigia.app.settings import Settings

    data_dir = tmp_path / "vigia-datos"
    data_dir.mkdir()
    _crear_db_con_eventos(data_dir)

    # El arranque de la app deja su propio evento `sistema.arranque`: los dos exports
    # se hacen con la app ya arrancada, sobre el mismo estado de la BD, para comparar
    # de verdad "los mismos eventos" y no una BD con un evento más en un lado.
    settings = Settings(data_dir=data_dir, open_browser=False, jobs_inline=True)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        resp = client.get(
            "/api/events/export", params={"since": "2000-01-01T00:00:00+00:00", "format": "html"}
        )
        assert resp.status_code == 200
        html_api = resp.text

        salida_cli = tmp_path / "eventos_cli.html"
        codigo = main(
            [
                "export",
                "events",
                "--since",
                "2000-01-01T00:00:00+00:00",
                "--format",
                "html",
                "--out",
                str(salida_cli),
                "--data-dir",
                str(data_dir),
            ]
        )
        assert codigo == 0
        html_cli = salida_cli.read_text(encoding="utf-8")

    assert html_cli == html_api


def test_export_events_dispatch_no_afecta_a_export_sin_subcomando():
    """`export` sin subcomando lo captura argparse antes de llegar a `cmd_export`."""
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        main(["export"])
    assert exc_info.value.code == 2
