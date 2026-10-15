"""Ajustes: validación, secretos enmascarados y mcp_token."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.models import Event, Setting


def test_get_settings_valores_por_defecto_y_mcp_token_generado(client: TestClient):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tema"] == "miguel"
    assert body["modo_color"] == "sistema"
    assert body["idioma"] == "es"
    assert body["llm"]["backend"] == "none"
    assert body["mcp_token"]
    assert "*" in body["mcp_token"]

    # Segunda llamada: el mismo token (idempotente), sigue enmascarado.
    resp2 = client.get("/api/settings")
    assert resp2.json()["mcp_token"] == body["mcp_token"]


def test_mcp_token_reveal_muestra_el_token_completo(client: TestClient):
    enmascarado = client.get("/api/settings").json()["mcp_token"]
    revelado = client.get("/api/settings?reveal=true").json()["mcp_token"]
    assert revelado != enmascarado
    assert "*" not in revelado
    assert len(revelado) > len(enmascarado.replace("*", ""))


def test_patch_tema_invalido_422(client: TestClient):
    resp = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "cambio de tema", "values": {"tema": "no-existe"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


def test_patch_tema_valido_y_evento_con_motivo(client: TestClient, session: Session):
    resp = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "prueba de tema", "values": {"tema": "miguel"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tema"] == "miguel"

    evento = session.exec(select(Event).where(Event.action == "ajuste.cambiado")).one()
    assert evento.motivo == "prueba de tema"
    assert evento.after_json == {"tema": "miguel"}
    assert evento.actor_id == "miguel"


def test_patch_sin_motivo_422(client: TestClient):
    resp = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "", "values": {"tema": "miguel"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


def test_patch_con_motivo_solo_espacios_422(client: TestClient):
    resp = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "   ", "values": {"tema": "miguel"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


def test_llm_api_key_nunca_aparece_en_get_ni_en_el_evento_ni_con_reveal(
    client: TestClient, session: Session
):
    resp = client.patch(
        "/api/settings",
        json={
            "actor": "miguel",
            "motivo": "configuro anthropic",
            "values": {
                "llm": {
                    "backend": "anthropic",
                    "model": "modelo-uno",
                    "base_url": "",
                    "api_key": "sk-secreta-de-verdad",
                    "confirmacion_no_local": "los formularios no llevan datos de personas afectadas",
                }
            },
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["llm"]["api_key"] == "***"

    resp_get = client.get("/api/settings")
    assert resp_get.json()["llm"]["api_key"] == "***"

    evento = session.exec(
        select(Event).where(Event.action == "ajuste.cambiado", Event.motivo == "configuro anthropic")
    ).one()
    assert evento.after_json["llm"]["api_key"] == "***"
    assert "sk-secreta-de-verdad" not in str(evento.after_json)

    # A diferencia de `mcp_token`, `?reveal=true` no revela `llm.api_key`: no hay
    # excepción para ella.
    resp_reveal = client.get("/api/settings?reveal=true")
    assert resp_reveal.json()["llm"]["api_key"] == "***"

    # El valor real sigue guardado (lo confirma solo la base de datos, no la API).
    fila = session.get(Setting, "llm")
    assert fila.value_json["api_key"] == "sk-secreta-de-verdad"


def test_patch_llm_parcial_conserva_api_key_previa(client: TestClient, session: Session):
    client.patch(
        "/api/settings",
        json={
            "actor": "miguel",
            "motivo": "configuro anthropic",
            "values": {
                "llm": {
                    "backend": "anthropic",
                    "model": "modelo-uno",
                    "base_url": "https://api.anthropic.com",
                    "api_key": "sk-real-secret",
                    "confirmacion_no_local": "los formularios no llevan datos de personas afectadas",
                }
            },
        },
        headers=actor_headers("miguel"),
    )

    # PATCH parcial: solo cambia backend, no reenvía model/base_url/api_key.
    resp = client.patch(
        "/api/settings",
        json={
            "actor": "miguel",
            "motivo": "cambio backend",
            "values": {"llm": {"backend": "ollama"}},
        },
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["llm"]["backend"] == "ollama"
    assert resp.json()["llm"]["api_key"] == "***"

    # `reveal=true` sigue sin mostrar api_key: se comprueba que se conservó mirando
    # directamente el valor guardado, no la respuesta de la API.
    resp_reveal = client.get("/api/settings?reveal=true")
    llm = resp_reveal.json()["llm"]
    assert llm["backend"] == "ollama"
    assert llm["model"] == "modelo-uno"
    assert llm["base_url"] == ""  # La URL base de otro backend no se arrastra
    assert llm["api_key"] == "***"

    fila = session.get(Setting, "llm")
    assert fila.value_json["api_key"] == "sk-real-secret"


def test_patch_llm_roundtrip_get_no_pisa_api_key_con_mascara(client: TestClient, session: Session):
    client.patch(
        "/api/settings",
        json={
            "actor": "miguel",
            "motivo": "configuro anthropic",
            "values": {
                "llm": {
                    "backend": "anthropic",
                    "model": "modelo-uno",
                    "base_url": "",
                    "api_key": "sk-real-secret",
                    "confirmacion_no_local": "los formularios no llevan datos de personas afectadas",
                }
            },
        },
        headers=actor_headers("miguel"),
    )

    # Patrón típico de UI: GET (api_key llega enmascarado) y se reenvía tal cual
    # tras editar otro campo.
    leido = client.get("/api/settings").json()
    leido["llm"]["model"] = "modelo-dos"
    resp = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "cambio modelo", "values": {"llm": leido["llm"]}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    resp_reveal = client.get("/api/settings?reveal=true")
    llm = resp_reveal.json()["llm"]
    assert llm["model"] == "modelo-dos"
    assert llm["api_key"] == "***"

    fila = session.get(Setting, "llm")
    assert fila.value_json["api_key"] == "sk-real-secret"


def test_patch_data_dir_409_y_puerto_fuera_de_rango_422(client: TestClient):
    resp = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "cambio ruta", "values": {"data_dir": "/otra/ruta"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 409

    resp2 = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "cambio puerto", "values": {"puerto": 80}},
        headers=actor_headers("miguel"),
    )
    assert resp2.status_code == 422


def test_patch_mcp_token_es_de_solo_lectura_422(client: TestClient):
    resp = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "intento", "values": {"mcp_token": "lo-que-sea"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422


def test_patch_rol_auditor_200_y_admin_422(client: TestClient):
    """`auditor` sustituye a `admin` en el catálogo de roles."""
    resp = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "pruebo auditor", "values": {"rol": "auditor"}},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["rol"] == "auditor"

    resp2 = client.patch(
        "/api/settings",
        json={"actor": "miguel", "motivo": "intento admin", "values": {"rol": "admin"}},
        headers=actor_headers("miguel"),
    )
    assert resp2.status_code == 422


def test_patch_llm_anthropic_sin_confirmacion_422_y_con_confirmacion_deja_evento(
    client: TestClient, session: Session
):
    """Activar `anthropic` (no local) sin `confirmacion_no_local` es 422;
    con ella, deja `ajuste.cambiado` y además `ajuste.llm_confirmado`."""
    sin_confirmacion = client.patch(
        "/api/settings",
        json={
            "actor": "miguel",
            "motivo": "activo anthropic",
            "values": {
                "llm": {"backend": "anthropic", "model": "", "base_url": "", "api_key": ""}
            },
        },
        headers=actor_headers("miguel"),
    )
    assert sin_confirmacion.status_code == 422

    con_confirmacion = client.patch(
        "/api/settings",
        json={
            "actor": "miguel",
            "motivo": "activo anthropic con confirmación",
            "values": {
                "llm": {
                    "backend": "anthropic",
                    "model": "",
                    "base_url": "",
                    "api_key": "",
                    "confirmacion_no_local": "los formularios no llevan datos de personas afectadas",
                }
            },
        },
        headers=actor_headers("miguel"),
    )
    assert con_confirmacion.status_code == 200, con_confirmacion.text

    evento = session.exec(select(Event).where(Event.action == "ajuste.llm_confirmado")).one()
    assert evento.after_json == {
        "backend": "anthropic",
        "confirmacion": "los formularios no llevan datos de personas afectadas",
    }
    assert evento.actor_id == "miguel"

    # Un segundo PATCH que ya viene de `anthropic` (no cambia de backend) no
    # exige de nuevo `confirmacion_no_local`.
    sin_re_confirmar = client.patch(
        "/api/settings",
        json={
            "actor": "miguel",
            "motivo": "cambio modelo",
            "values": {
                "llm": {
                    "backend": "anthropic",
                    "model": "modelo-dos",
                    "base_url": "",
                    "api_key": "",
                }
            },
        },
        headers=actor_headers("miguel"),
    )
    assert sin_re_confirmar.status_code == 200, sin_re_confirmar.text


def test_tema_guardado_que_el_build_no_admite_cae_al_personal(client: TestClient, session: Session):
    session.add(Setting(key="tema", value_json="tema-que-no-existe"))
    session.commit()
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["tema"] == "miguel"
