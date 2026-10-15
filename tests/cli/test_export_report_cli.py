"""Tests de `vigia export report`: envuelve
`DossierReview.report_html` sin arrancar el servidor, patrón de
`test_export_cli.py::test_export_events_*`."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.app.main import create_app
from vigia.app.settings import Settings
from vigia.cli import main


def _reproducir_dossier_b0(client: TestClient) -> dict[str, int]:
    """Guion mínimo con un dossier y una revisión `b0` (termina en línea)."""
    cab = actor_headers("miguel")
    creada = client.post(
        "/api/demo/runs",
        json={"scenario_key": "timeline_completo", "with_human": True},
        headers=cab,
    )
    assert creada.status_code == 200, creada.text
    run = creada.json()
    reproducida = client.post(f"/api/demo/runs/{run['id']}/play", headers=cab)
    assert reproducida.status_code == 200, reproducida.text

    project_id = run["project_id"]
    dossier = client.post(
        f"/api/projects/{project_id}/dossiers",
        json={
            "profile": {"sc-0-1": "Vigía demo", "sc-1-1": "Sugiere si derivar o no"},
            "include_telemetry": True,
            "actor": "miguel",
            "role": "auditor",
            "motivo": "test cli export report",
        },
        headers=cab,
    )
    assert dossier.status_code == 200, dossier.text
    revision = client.post(
        f"/api/dossiers/{dossier.json()['id']}/reviews",
        json={"approach": "b0", "actor": "miguel", "role": "auditor", "motivo": "test"},
        headers=cab,
    )
    assert revision.status_code == 200, revision.text
    assert revision.json()["status"] == "terminado", revision.text
    review_id = client.get(f"/api/dossiers/{dossier.json()['id']}").json()["reviews"][0]["id"]
    return {"project_id": project_id, "review_id": review_id}


def test_export_report_sin_base_de_datos_devuelve_1(tmp_path, capsys):
    data_dir = tmp_path / "vigia-datos-vacia"
    data_dir.mkdir()

    codigo = main(
        [
            "export",
            "report",
            "--review",
            "1",
            "--out",
            str(tmp_path / "informe.html"),
            "--data-dir",
            str(data_dir),
        ]
    )

    assert codigo == 1
    assert "no existe la base de datos" in capsys.readouterr().err


def test_export_report_revision_inexistente_devuelve_1(tmp_path, capsys):
    data_dir = tmp_path / "vigia-datos"
    data_dir.mkdir()
    settings = Settings(data_dir=data_dir, open_browser=False, jobs_inline=True)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8765"):
        pass  # solo para crear vigia.db con el lifespan; ninguna revisión creada

    codigo = main(
        [
            "export",
            "report",
            "--review",
            "999",
            "--out",
            str(tmp_path / "informe.html"),
            "--data-dir",
            str(data_dir),
        ]
    )

    assert codigo == 1
    assert "no encontrada o sin informe" in capsys.readouterr().err


def test_export_report_con_revision_terminada_escribe_el_mismo_html_que_la_api(tmp_path, capsys):
    data_dir = tmp_path / "vigia-datos"
    data_dir.mkdir()
    settings = Settings(data_dir=data_dir, open_browser=False, jobs_inline=True)
    app = create_app(settings)

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        ids = _reproducir_dossier_b0(client)
        resp_api = client.get(f"/api/reviews/{ids['review_id']}/report")
        assert resp_api.status_code == 200, resp_api.text
        bytes_api = resp_api.content

    salida = tmp_path / "informe.html"
    codigo = main(
        [
            "export",
            "report",
            "--review",
            str(ids["review_id"]),
            "--out",
            str(salida),
            "--data-dir",
            str(data_dir),
        ]
    )

    assert codigo == 0
    assert "informe de la revisión" in capsys.readouterr().out
    assert salida.read_bytes() == bytes_api
