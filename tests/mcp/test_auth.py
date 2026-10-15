"""401 del middleware de `mcp_token`. `POST /projects` depende
de `get_actor`, a diferencia de las lecturas: es el endpoint mínimo para
probar el middleware sin montar todo un proyecto."""

from __future__ import annotations

_CUERPO = {"name": "Proyecto de prueba de auth"}


async def test_agente_sin_token_da_401(cliente_http):
    resp = await cliente_http.post(
        "/api/projects",
        json=_CUERPO,
        headers={"X-Vigia-Actor-Kind": "agente", "X-Vigia-Actor": "test"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "X-Vigia-Token inválido o ausente para actor_kind=agente"


async def test_agente_con_token_incorrecto_da_401(cliente_http):
    resp = await cliente_http.post(
        "/api/projects",
        json=_CUERPO,
        headers={
            "X-Vigia-Actor-Kind": "agente",
            "X-Vigia-Actor": "test",
            "X-Vigia-Token": "no-es-el-token",
        },
    )
    assert resp.status_code == 401


async def test_agente_con_token_valido_pasa(cliente_http):
    token = (await cliente_http.get("/api/settings", params={"reveal": "true"})).json()["mcp_token"]
    resp = await cliente_http.post(
        "/api/projects",
        json=_CUERPO,
        headers={"X-Vigia-Actor-Kind": "agente", "X-Vigia-Actor": "test", "X-Vigia-Token": token},
    )
    assert resp.status_code == 200


async def test_humano_sin_token_sigue_funcionando(cliente_http):
    resp = await cliente_http.post(
        "/api/projects",
        json=_CUERPO,
        headers={"X-Vigia-Actor-Kind": "humano", "X-Vigia-Actor": "miguel"},
    )
    assert resp.status_code == 200
