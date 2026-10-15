"""Dossier de auditoría y su revisión."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers
from vigia.human.dossier_markdown import render_form_markdown, render_inventory_markdown

_SYSTEM_NAME = "Vigía - Derivación de Digestivo <script>alert(1)</script>"
_PROFILE = {
    "sc-0-1": "Vigía - Derivación de Digestivo",
    "sc-0-2": "Cribado de derivación a digestivo",
    "sc-1-1": "Clasifica el riesgo de la derivación",
}
_EXPERIENCE = {
    "ue-1-1": "Enfermero de triaje: reviso las derivaciones antes de enviarlas",
}
_INVENTORY = {
    "di-0-1": "sí, las tiene el equipo de producto",
    "di-0-2": "no",
}


def _reproducir_demo(client: TestClient) -> dict:
    cab = actor_headers("miguel")
    creada = client.post(
        "/api/demo/runs", json={"scenario_key": "timeline_completo", "with_human": True}, headers=cab
    )
    assert creada.status_code == 200, creada.text
    run = creada.json()
    reproducida = client.post(f"/api/demo/runs/{run['id']}/play", headers=cab)
    assert reproducida.status_code == 200, reproducida.text
    assert reproducida.json()["status"] == "terminado", reproducida.text
    return run


def _crear_dossier(client: TestClient, project_id: int, **extra) -> dict:
    body = {
        "profile": _PROFILE,
        "experience": _EXPERIENCE,
        "inventory": _INVENTORY,
        "actor": "miguel",
        "role": "auditor",
        "motivo": "primer dossier del despliegue",
        **extra,
    }
    resp = client.post(
        f"/api/projects/{project_id}/dossiers", json=body, headers=actor_headers("miguel")
    )
    return resp


def test_get_plantillas_tres_formularios_con_id_seccion_texto(client: TestClient):
    resp = client.get("/api/content/dossier-plantillas")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for clave in ("system_card", "usage_experience", "document_inventory"):
        assert clave in body
        assert body[clave]["preguntas"], clave
        pregunta = body[clave]["preguntas"][0]
        assert {"id", "seccion", "texto", "original"} <= set(pregunta)


def test_b0_sin_llm_review_completa_y_report_escapado(client: TestClient):
    run = _reproducir_demo(client)
    project_id = run["project_id"]

    creado = _crear_dossier(client, project_id, include_telemetry=True, system_name=_SYSTEM_NAME)
    assert creado.status_code == 200, creado.text
    dossier = creado.json()
    assert dossier["telemetry_included"] is True
    assert len(dossier["sha256"]) == 64

    lanzada = client.post(
        f"/api/dossiers/{dossier['id']}/reviews",
        json={"approach": "b0", "corpus": "todas", "dedup": True, "crosswalk": True,
              "actor": "miguel", "role": "auditor", "motivo": "revisión de cierre del hito"},
        headers=actor_headers("miguel"),
    )
    assert lanzada.status_code == 200, lanzada.text
    job = lanzada.json()
    assert job["status"] == "terminado", job

    review_id = None
    leido_dossier = client.get(f"/api/dossiers/{dossier['id']}")
    assert leido_dossier.status_code == 200, leido_dossier.text
    reviews = leido_dossier.json()["reviews"]
    assert len(reviews) == 1
    review_id = reviews[0]["id"]
    assert reviews[0]["status"] == "terminada"

    detalle = client.get(f"/api/reviews/{review_id}")
    assert detalle.status_code == 200, detalle.text
    d = detalle.json()
    assert len(d["findings"]) > 0
    guidelines_total = len({gid for f in d["findings"] for gid in f["guideline_ids"]})
    assert guidelines_total == 32
    assert d["crosswalk"], "el crosswalk no debería estar vacío para al menos un marco"
    assert d["package_version"] == "0.1.0"
    assert len(d["corpus_hash"]) == 64
    assert len(d["dossier_sha256"]) == 64
    assert d["prompt_sha256"] is None

    report = client.get(f"/api/reviews/{review_id}/report")
    assert report.status_code == 200, report.text
    assert report.headers["content-type"].startswith("text/html")
    assert "&lt;script&gt;" in report.text
    assert "<script>alert" not in report.text

    listado = client.get(f"/api/projects/{project_id}/dossiers")
    assert listado.status_code == 200, listado.text
    assert listado.json()["total"] == 1

    # `dossier.creado` lleva `correlation_id` (contexto común, `get_correlation_id`).
    eventos_dossier = client.get(
        "/api/events", params={"object_type": "dossier", "object_id": dossier["id"]}
    )
    assert eventos_dossier.status_code == 200, eventos_dossier.text
    creado_evt = next(
        e for e in eventos_dossier.json()["items"] if e["action"] == "dossier.creado"
    )
    assert creado_evt["correlation_id"], creado_evt
    # Privacidad de `interaction_review`: el evento lleva
    # `system_name`, `domain` y `telemetry_included`, nunca una respuesta.
    assert set(creado_evt["after"]) == {"system_name", "domain", "telemetry_included"}
    texto_evento = json.dumps(creado_evt, ensure_ascii=False)
    for respuesta in (*_PROFILE.values(), *_EXPERIENCE.values(), *_INVENTORY.values()):
        # `sc-0-1` repite el nombre del sistema, que sí va en el evento; «no» es
        # demasiado corto para buscarlo como subcadena.
        if respuesta in _SYSTEM_NAME or len(respuesta) < 5:
            continue
        assert respuesta not in texto_evento, respuesta

    # `dossier.revision_lanzada` y `dossier.revision_terminada` llevan el
    # `job_id` del trabajo real, incluso con `jobs_inline=True`.
    eventos_review = client.get(
        "/api/events", params={"object_type": "dossier_review", "object_id": review_id}
    )
    assert eventos_review.status_code == 200, eventos_review.text
    por_accion = {e["action"]: e for e in eventos_review.json()["items"]}
    assert por_accion["dossier.revision_lanzada"]["job_id"] == job["id"]
    assert por_accion["dossier.revision_terminada"]["job_id"] == job["id"]


def test_dossier_tres_formularios_vacios_422(client: TestClient):
    run = _reproducir_demo(client)
    resp = _crear_dossier(client, run["project_id"], profile={}, experience={}, inventory={})
    assert resp.status_code == 422
    assert "rellena al menos una respuesta" in resp.json()["detail"]


def test_review_p3_sin_backend_llm_409(client: TestClient):
    run = _reproducir_demo(client)
    creado = _crear_dossier(client, run["project_id"])
    assert creado.status_code == 200, creado.text
    dossier_id = creado.json()["id"]

    resp = client.post(
        f"/api/dossiers/{dossier_id}/reviews",
        json={"approach": "p3", "actor": "miguel", "role": "auditor", "motivo": "revisión con LLM"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 409


def test_render_form_markdown_sanea_lineas_de_continuacion_y_marcador():
    """Una línea de continuación que empieza por un marcador estructural del
    parser de `interaction_review` (`extract_answers`) se escapa con `\\`, y
    cualquier ✍ dentro de la respuesta se sustituye por ✎: sin esto, el resto
    de la respuesta se pierde en silencio (encargo-D, hallazgos de fidelidad
    y contratos)."""
    respuesta = (
        "Primera linea.\n"
        "- **Un punto importante en negrita**\n"
        "Segunda parte de la respuesta con ✍ dentro."
    )
    md = render_form_markdown("Título", {"q1": respuesta}, preguntas=None)
    cuerpo = md.split("✍️ ", 1)[1]
    # La primera línea no se toca; la de continuación con `- **` va escapada.
    assert cuerpo.startswith("Primera linea.\n\\- **Un punto importante en negrita**")
    # El resto de la respuesta, tras la línea escapada, se conserva entera.
    assert "Segunda parte de la respuesta con ✎ dentro." in cuerpo
    # Ninguna línea de continuación queda sin escapar si empezaba por un marcador.
    assert "\n- **Un punto importante en negrita**" not in cuerpo


def test_render_inventory_markdown_sanea_respuesta_multilinea():
    respuesta = "sí, la tiene el equipo\n> Nota interna del equipo"
    md = render_inventory_markdown("Título", {"doc": respuesta}, preguntas=None)
    assert "\\> Nota interna del equipo" in md
    assert "\n> Nota interna del equipo" not in md


# --- POST /projects/{id}/dossiers/import -------------------

_DOSSIER_JSON = {
    "system_name": "Triaje de ejemplo",
    "domain": "urgencias",
    "summary": "Resumen del sistema importado.",
    "sources": [
        {"id": "doc-1", "kind": "document", "label": "Ficha", "content": "Ficha técnica del modelo."},
        {"id": "tec-1", "kind": "technician", "label": "Proveedor", "content": "Lo mantiene el proveedor."},
        {"id": "usr-1", "kind": "end_user", "label": "Médico", "content": "Acepto casi todo.\n> cita"},
        {"id": "oth-1", "kind": "other", "label": "Prensa", "content": "Noticia."},
    ],
}


def _importar(client: TestClient, project_id: int, dossier: dict, actor: str = "miguel", **extra):
    cuerpo = {**dossier, "actor": actor, "role": "auditor", "motivo": "dossier del caso externo", **extra}
    return client.post(
        f"/api/projects/{project_id}/dossiers/import", json=cuerpo, headers=actor_headers(actor)
    )


def test_importar_dossier_json_agrupa_por_kind_y_emite_el_evento_del_actor(client: TestClient):
    from vigia.human.dossier_import import CLAVE_RESUMEN, CLAVE_SIN_ENCAJE

    project_id = _reproducir_demo(client)["project_id"]
    resp = _importar(client, project_id, _DOSSIER_JSON, actor="ana")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["system_name"] == "Triaje de ejemplo"
    assert d["summary"] == "Resumen del sistema importado."
    assert len(d["sha256"]) == 64
    assert d["profile"]["Proveedor [tec-1]"] == "Lo mantiene el proveedor."
    assert d["experience"] == {"Médico [usr-1]": "Acepto casi todo.\n> cita"}
    assert d["inventory"] == {"Ficha [doc-1]": "Ficha técnica del modelo."}
    assert d["profile"][CLAVE_RESUMEN] == "Resumen del sistema importado."
    assert "Prensa [oth-1]" in d["profile"][CLAVE_SIN_ENCAJE]

    leido = client.get(f"/api/dossiers/{d['id']}")
    assert leido.status_code == 200, leido.text
    assert leido.json()["inventory"] == d["inventory"]

    eventos = client.get("/api/events", params={"object_type": "dossier", "object_id": d["id"]})
    creado = next(e for e in eventos.json()["items"] if e["action"] == "dossier.creado")
    assert creado["actor_id"] == "ana" and creado["correlation_id"]
    assert {"system_name", "domain", "telemetry_included"} <= set(creado["after"])
    assert "Ficha técnica del modelo." not in json.dumps(creado, ensure_ascii=False)


def test_dossier_importado_se_revisa_como_cualquier_otro(client: TestClient):
    project_id = _reproducir_demo(client)["project_id"]
    d = _importar(client, project_id, _DOSSIER_JSON).json()
    lanzada = client.post(
        f"/api/dossiers/{d['id']}/reviews",
        json={"approach": "b0", "actor": "miguel", "role": "auditor", "motivo": "revisión del importado"},
        headers=actor_headers("miguel"),
    )
    assert lanzada.status_code == 200, lanzada.text
    assert lanzada.json()["status"] == "terminado"
    assert client.get(f"/api/dossiers/{d['id']}").json()["reviews"][0]["status"] == "terminada"


def test_importar_dossier_invalido_422_en_espanol_con_el_campo(client: TestClient):
    project_id = _reproducir_demo(client)["project_id"]

    kind_malo = {**_DOSSIER_JSON, "sources": [{**_DOSSIER_JSON["sources"][0], "kind": "inventado"}]}
    resp = _importar(client, project_id, kind_malo)
    assert resp.status_code == 422, resp.text
    detalle = resp.json()["detail"]
    assert isinstance(detalle, str)
    assert "sources[0].kind" in detalle and "valor no admitido" in detalle

    sin_fuentes = _importar(client, project_id, {**_DOSSIER_JSON, "sources": []})
    assert sin_fuentes.status_code == 422
    assert "al menos una fuente" in sin_fuentes.json()["detail"]

    sin_contenido = {k: v for k, v in _DOSSIER_JSON["sources"][0].items() if k != "content"}
    falta = _importar(client, project_id, {**_DOSSIER_JSON, "sources": [sin_contenido]})
    assert falta.status_code == 422
    assert "sources[0].content: falta este campo" in falta.json()["detail"]

    sin_nombre = {k: v for k, v in _DOSSIER_JSON.items() if k != "system_name"}
    assert "system_name: falta este campo" in _importar(client, project_id, sin_nombre).json()["detail"]

    # Nada se guardó con los rechazos.
    assert client.get(f"/api/projects/{project_id}/dossiers").json()["total"] == 0


def test_importar_dossier_proyecto_inexistente_404(client: TestClient):
    assert _importar(client, 99999, _DOSSIER_JSON).status_code == 404


def test_importar_los_dossiers_de_los_casos_externos(client: TestClient):
    """Por la API: cada `tests/fixtures/casos-externos/<caso>/dossier.json`
    entra y vuelve entero (el parametrizado fino vive en `tests/human`)."""
    from pathlib import Path

    rutas = sorted(Path(__file__).resolve().parents[1].glob("fixtures/casos-externos/*/dossier.json"))
    if not rutas:
        import pytest

        pytest.skip("aún no hay fixtures de casos externos")
    project_id = _reproducir_demo(client)["project_id"]
    for ruta in rutas:
        dossier = json.loads(ruta.read_text(encoding="utf-8"))
        resp = _importar(client, project_id, dossier)
        assert resp.status_code == 200, (ruta.parent.name, resp.text)
        d = resp.json()
        n = sum(len(d[k]) for k in ("profile", "experience", "inventory"))
        assert n >= len(dossier["sources"]), ruta.parent.name
