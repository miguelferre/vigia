"""Contrato de respuestas de la API: `response_model` en todas las rutas.

Reproduce el guion `timeline_completo` con capa humana, calcula una explicación
global y recorre **todas** las rutas GET del OpenAPI con ids reales. Como los
modelos de `app/schemas/respuestas_*.py` cierran con `extra="forbid"`, cualquier
clave que un serializador devuelva y el modelo no declare rompe la respuesta con
un 500: ese fallo es el contrato.

El segundo bloque mira el OpenAPI publicado y falla si alguna ruta JSON se queda
sin esquema de respuesta o si algún esquema de respuesta admite claves extra.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.conftest import actor_headers

# Rutas que no devuelven JSON modelable: los dos flujos SSE, las tres descargas
# con `Content-Disposition` y el comodín que sirve el frontend estático.
RUTAS_SIN_MODELO = {
    "/api/events/stream",
    "/api/jobs/{job_id}/stream",
    "/api/events/export",
    "/api/projects/{project_id}/usage-logs/export.csv",
    # CSV combinado de una fase de demo enlatada: misma razón
    # que las dos descargas de arriba.
    "/api/demo/scenarios/{key}/files/{phase}",
    # El informe de una revisión es `text/html`
    # para un `<iframe sandbox>`, no JSON.
    "/api/reviews/{review_id}/report",
    # Ejemplo descargable del registro de uso, `text/csv`.
    "/api/content/registro-uso/ejemplo.csv",
    # Las cinco plantillas de la guía de datos, `text/csv`.
    "/api/content/plantillas/{tipo}.csv",
    "/{full_path}",
}

# Rutas GET que exigen dos versiones del modelo: el guion de demo trae una
# sola. Su contrato lo prueban `tests/api/test_comparacion*.py`.
RUTAS_CON_DOS_VERSIONES = {"/api/projects/{project_id}/versions/compare"}

# Esquemas de respuesta heredados, anteriores a esta enmienda.
ESQUEMAS_ABIERTOS_HEREDADOS = {"JobAccepted", "UsageLogUploadResponse"}

# Parámetros de consulta obligatorios de las rutas que los exigen.
CONSULTA_OBLIGATORIA: dict[str, dict[str, str]] = {
    "/api/projects/{project_id}/timeline": {
        "monitor_type": "fairness",
        "metric_key": "fairness_value",
    },
    # La vista propia exige el pseudónimo del
    # profesional; `clin-01` es el primero que genera `sim.human`.
    "/api/projects/{project_id}/overrides/me": {"clinician": "clin-01"},
}


def _reproducir_demo(client: TestClient) -> dict[str, int]:
    """Guion `timeline_completo` con capa humana más una explicación global.

    Devuelve un id real por cada parámetro de ruta de la API.
    """
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
    assert reproducida.json()["status"] == "terminado", reproducida.text

    project_id = run["project_id"]
    version_id = client.get(f"/api/projects/{project_id}").json()["active_version_id"]

    explicada = client.post(
        f"/api/model-versions/{version_id}/explain/global", json={}, headers=cab
    )
    assert explicada.status_code == 200, explicada.text

    # Un dossier con su revisión `b0` y un riesgo nacido
    # de la primera alerta, para que las rutas nuevas tengan id real y
    # sus listas no vengan vacías.
    dossier = client.post(
        f"/api/projects/{project_id}/dossiers",
        json={
            "profile": {"sc-0-1": "Vigía demo", "sc-1-1": "Sugiere si derivar o no"},
            "include_telemetry": True,
            "actor": "miguel",
            "role": "auditor",
            "motivo": "contrato de la API",
        },
        headers=cab,
    )
    assert dossier.status_code == 200, dossier.text
    revision = client.post(
        f"/api/dossiers/{dossier.json()['id']}/reviews",
        json={"approach": "b0", "actor": "miguel", "role": "auditor", "motivo": "contrato"},
        headers=cab,
    )
    assert revision.status_code == 200, revision.text
    assert revision.json()["status"] == "terminado", revision.text
    review_id = client.get(f"/api/dossiers/{dossier.json()['id']}").json()["reviews"][0]["id"]

    def primero(ruta: str) -> dict[str, Any]:
        respuesta = client.get(ruta, params={"limit": 500})
        assert respuesta.status_code == 200, respuesta.text
        items = respuesta.json()["items"]
        assert items, f"{ruta} no ha devuelto ningún elemento"
        return items[0]

    evaluaciones = client.get(
        f"/api/projects/{project_id}/evaluations", params={"limit": 500}
    ).json()["items"]
    equidad = next(e for e in evaluaciones if e["monitor_type"] == "fairness")

    alert_id = primero(f"/api/projects/{project_id}/alerts")["id"]
    riesgo = client.post(
        f"/api/projects/{project_id}/risks",
        json={
            "origin_alert_id": alert_id,
            "title": "Riesgo del contrato",
            "actor": "miguel",
            "role": "auditor",
            "motivo": "contrato de la API",
        },
        headers=cab,
    )
    assert riesgo.status_code == 200, riesgo.text

    return {
        "project_id": project_id,
        "version_id": version_id,
        "dataset_id": primero(f"/api/projects/{project_id}/datasets")["id"],
        "batch_id": primero(f"/api/projects/{project_id}/batches")["id"],
        "monitor_id": primero(f"/api/projects/{project_id}/monitors")["id"],
        "evaluation_id": equidad["id"],
        "alert_id": alert_id,
        "dossier_id": dossier.json()["id"],
        "review_id": review_id,
        "risk_id": riesgo.json()["id"],
        "explanation_id": primero(f"/api/model-versions/{version_id}/explanations")["id"],
        "job_id": primero("/api/jobs")["id"],
        "run_id": run["id"],
    }


def _caminos_get(spec: dict[str, Any]) -> list[str]:
    """Rutas GET del OpenAPI que sí devuelven JSON modelable."""
    return sorted(
        camino
        for camino, operaciones in spec["paths"].items()
        if "get" in operaciones
        and camino not in RUTAS_SIN_MODELO
        and camino not in RUTAS_CON_DOS_VERSIONES
    )


def test_rutas_sin_modelo_existen_de_verdad_en_el_openapi(app: FastAPI):
    """Cada entrada de `RUTAS_SIN_MODELO` es un camino real que declara algún
    router: una cadena escrita a mano (como la descarga de demo) que
    no coincidiera con el decorador se quedaría fuera del contrato en vez de
    fallar aquí."""
    spec = app.openapi()
    faltan = sorted(RUTAS_SIN_MODELO - set(spec["paths"]))
    assert not faltan, f"RUTAS_SIN_MODELO con caminos que no existen en el OpenAPI: {faltan}"


def test_todas_las_rutas_get_responden_con_cuerpo(client: TestClient):
    """Cada GET de la API responde 200 con un cuerpo que valida contra su modelo."""
    ids = _reproducir_demo(client)
    caminos = _caminos_get(client.app.openapi())
    assert len(caminos) >= 20, f"el inventario de rutas GET se ha quedado corto: {caminos}"

    for plantilla in caminos:
        camino = plantilla
        for nombre, valor in ids.items():
            camino = camino.replace("{" + nombre + "}", str(valor))
        assert "{" not in camino, f"parámetro sin id real en {plantilla}"

        respuesta = client.get(camino, params=dict(CONSULTA_OBLIGATORIA.get(plantilla, {})))
        assert respuesta.status_code == 200, f"{camino}: {respuesta.text}"
        cuerpo = respuesta.json()
        assert cuerpo, f"{camino} ha devuelto un cuerpo vacío"
        if isinstance(cuerpo, dict) and "items" in cuerpo:
            assert cuerpo["items"], f"{camino} ha devuelto una lista vacía"
            assert cuerpo["total"] >= len(cuerpo["items"])

    # Las rutas con más riesgo de desincronizarse se han recorrido de verdad.
    for imprescindible in (
        "/api/batches/{batch_id}/composition",
        "/api/batches/{batch_id}/records",
        "/api/evaluations/{evaluation_id}",
        "/api/alerts/{alert_id}",
        "/api/explanations/{explanation_id}",
        "/api/projects/{project_id}/state",
        "/api/projects/{project_id}/timeline",
        "/api/jobs/{job_id}",
        "/api/events",
        "/api/settings",
        "/api/health",
    ):
        assert imprescindible in caminos


def test_records_con_features_siguen_validando(client: TestClient):
    """`?with_features=true` añade `features` sin romper el modelo `Record`."""
    ids = _reproducir_demo(client)
    respuesta = client.get(
        f"/api/batches/{ids['batch_id']}/records",
        params={"limit": 3, "with_features": True},
    )
    assert respuesta.status_code == 200, respuesta.text
    primero = respuesta.json()["items"][0]
    assert isinstance(primero["features"], dict) and primero["features"]
    assert "group_label" in primero


def test_el_openapi_declara_esquema_de_respuesta_200_en_cada_ruta(app: FastAPI):
    """Ninguna ruta devuelve `dict` sin modelo."""
    spec = app.openapi()
    sin_esquema = []
    for camino, operaciones in spec["paths"].items():
        if camino in RUTAS_SIN_MODELO:
            continue
        for metodo, operacion in operaciones.items():
            respuestas = operacion.get("responses", {})
            if "204" in respuestas:  # los borrados no devuelven cuerpo
                continue
            esquema = (
                respuestas.get("200", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            # El `$ref` puede estar en la raíz (`response_model=Modelo`) o bajo
            # `additionalProperties` (`response_model=dict[str, Modelo]`, que es
            # como sirve `/content/*` su mapa por clave). `textos-pantalla`
            # es dos niveles de mapa a texto libre (`dict[str, dict[str, str]]`):
            # sin `$ref`, pero tampoco `Any` (un `dict[str, Any]` deja
            # `additionalProperties: true`, un booleano, no un esquema); un
            # `additionalProperties` que es a su vez un esquema con `$ref` o
            # `type` cuenta como modelado.
            # Una unión de modelos (`response_model=A | B`, como `GET /overrides`,
            # que devuelve dos formas según `by`) sale como `anyOf`
            # de `$ref`: cuenta como modelada si todas sus ramas lo están.
            union = esquema.get("anyOf") or esquema.get("oneOf")
            union_modelada = bool(union) and all(
                isinstance(rama, dict) and "$ref" in rama for rama in union
            )
            anidado = esquema.get("additionalProperties")
            anidado_doble = anidado.get("additionalProperties") if isinstance(anidado, dict) else None
            tiene_ref = (
                "$ref" in esquema
                or union_modelada
                or (isinstance(anidado, dict) and "$ref" in anidado)
                or (
                    isinstance(anidado, dict)
                    and anidado.get("type") == "object"
                    and isinstance(anidado_doble, dict)
                    and ("$ref" in anidado_doble or "type" in anidado_doble)
                )
            )
            if not tiene_ref:
                sin_esquema.append(f"{metodo.upper()} {camino}")
    assert not sin_esquema, f"rutas sin esquema de respuesta en el OpenAPI: {sin_esquema}"


def _refs(nodo: Any) -> set[str]:
    """Nombres de componente referenciados en cualquier profundidad de un nodo JSON."""
    encontrados: set[str] = set()
    if isinstance(nodo, dict):
        ref = nodo.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            encontrados.add(ref.rsplit("/", 1)[1])
        for valor in nodo.values():
            encontrados |= _refs(valor)
    elif isinstance(nodo, list):
        for valor in nodo:
            encontrados |= _refs(valor)
    return encontrados


def test_los_esquemas_de_respuesta_prohiben_claves_extra(app: FastAPI):
    """Todo esquema alcanzable desde una respuesta 200 cierra con `extra="forbid"`."""
    spec = app.openapi()
    componentes = spec["components"]["schemas"]

    pendientes = set()
    for camino, operaciones in spec["paths"].items():
        if camino in RUTAS_SIN_MODELO:
            continue
        for operacion in operaciones.values():
            pendientes |= _refs(operacion.get("responses", {}).get("200", {}))

    vistos: set[str] = set()
    abiertos: list[str] = []
    while pendientes:
        nombre = pendientes.pop()
        if nombre in vistos:
            continue
        vistos.add(nombre)
        esquema = componentes[nombre]
        pendientes |= _refs(esquema) - vistos
        if esquema.get("type") != "object" or nombre in ESQUEMAS_ABIERTOS_HEREDADOS:
            continue
        if esquema.get("additionalProperties") is not False:
            abiertos.append(nombre)

    assert len(vistos) >= 25, f"pocos esquemas de respuesta alcanzados: {sorted(vistos)}"
    assert not abiertos, f"esquemas de respuesta que admiten claves extra: {sorted(abiertos)}"


@pytest.mark.parametrize("formato", ["json", "html"])
def test_las_dos_descargas_del_diario_siguen_sirviendo(client: TestClient, formato: str):
    """Las rutas fuera del contrato JSON (descargas) siguen respondiendo."""
    respuesta = client.get("/api/events/export", params={"format": formato})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.content
    assert "attachment" in respuesta.headers["content-disposition"]
