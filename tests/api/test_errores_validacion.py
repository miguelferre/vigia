"""Manejadores globales de errores en español.

Mini app con los tipos de error de pydantic que enumera el contrato, más una
muestra contra la app real (forma de la respuesta intacta: `loc`, `msg`, `type`).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

import pytest
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vigia.app.errores import (
    TEXTO_ERROR_INTERNO,
    registrar_manejadores,
    traducir_validacion,
)


class Color(str, Enum):
    rojo = "rojo"
    verde = "verde"


class Cuerpo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entero: int = 0
    real: float = 0.0
    activo: bool = True
    modo: Literal["a", "b", "c"] = "a"
    color: Color = Color.rojo
    nombre: str = Field(default="xx", min_length=2, max_length=5)
    minimo: int = Field(default=5, ge=3)
    maximo: int = Field(default=1, le=9)
    obligatorio: str = "x"
    texto: str = "t"
    valida: str = "ok"

    @field_validator("valida")
    @classmethod
    def _solo_ok(cls, v: str) -> str:
        if v != "ok":
            raise ValueError("solo se admite «ok»")
        return v


class CuerpoObligatorio(BaseModel):
    campo: str


def _app() -> FastAPI:
    app = FastAPI()
    registrar_manejadores(app)

    @app.post("/m")
    def m(cuerpo: Cuerpo) -> dict:
        return {"ok": True}

    @app.post("/o")
    def o(cuerpo: CuerpoObligatorio) -> dict:
        return {"ok": True}

    @app.get("/q")
    def q(n: int) -> dict:
        return {"n": n}

    @app.get("/lista")
    def lista(cuerpo: Annotated[list[int], Body()]) -> dict:
        return {}

    @app.get("/solo-get")
    def solo_get() -> dict:
        return {}

    @app.get("/roto")
    def roto() -> dict:
        raise RuntimeError("fallo con texto interno de la libreria")

    return app


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(_app(), base_url="http://127.0.0.1:8765", raise_server_exceptions=False)


def _un_error(cliente: TestClient, cuerpo: dict) -> dict:
    resp = cliente.post("/m", json=cuerpo)
    assert resp.status_code == 422, resp.text
    errores = resp.json()["detail"]
    assert len(errores) == 1, errores
    return errores[0]


@pytest.mark.parametrize(
    ("cuerpo", "tipo", "fragmentos"),
    [
        ({"entero": "abc"}, "int_parsing", ["«entero»", "número entero"]),
        ({"real": "abc"}, "float_parsing", ["«real»", "número"]),
        ({"activo": "quizás"}, "bool_parsing", ["«activo»", "verdadero o falso"]),
        ({"zzz": 1}, "extra_forbidden", ["«zzz»", "no existe"]),
        ({"modo": "z"}, "literal_error", ["«modo»", "a, b o c"]),
        ({"color": "azul"}, "enum", ["«color»", "rojo o verde"]),
        ({"nombre": "a"}, "string_too_short", ["«nombre»", "al menos 2"]),
        ({"nombre": "demasiado"}, "string_too_long", ["«nombre»", "como máximo 5"]),
        ({"minimo": 1}, "greater_than_equal", ["«minimo»", "menor que 3"]),
        ({"maximo": 99}, "less_than_equal", ["«maximo»", "mayor que 9"]),
        ({"valida": "no"}, "value_error", ["solo se admite «ok»"]),
    ],
)
def test_422_por_tipo_en_espanol_y_con_la_forma_de_siempre(cliente, cuerpo, tipo, fragmentos):
    error = _un_error(cliente, cuerpo)
    assert error["type"] == tipo
    assert error["loc"][0] == "body"
    for fragmento in fragmentos:
        assert fragmento in error["msg"], error["msg"]
    assert "Value error" not in error["msg"]
    # nada del texto inglés de pydantic
    for ingles in ("Input should", "Field required", "Extra inputs", "String should"):
        assert ingles not in error["msg"]


def test_422_missing_nombra_el_campo(cliente):
    resp = cliente.post("/o", json={})
    assert resp.status_code == 422
    error = resp.json()["detail"][0]
    assert error["type"] == "missing"
    assert error["loc"] == ["body", "campo"]
    assert error["msg"] == "falta el campo «campo»: es obligatorio"


def test_422_json_roto(cliente):
    resp = cliente.post("/o", content=b'{"campo": ', headers={"content-type": "application/json"})
    assert resp.status_code == 422
    error = resp.json()["detail"][0]
    assert error["type"] == "json_invalid"
    assert "no es un JSON válido" in error["msg"]


def test_422_de_parametro_de_consulta(cliente):
    resp = cliente.get("/q", params={"n": "x"})
    error = resp.json()["detail"][0]
    assert error["loc"] == ["query", "n"]
    assert error["msg"] == "«n» debe ser un número entero"


def test_tipo_sin_traduccion_da_valor_no_valido_en_el_campo():
    fuera = [{"type": "tipo_raro", "loc": ("body", "cosa"), "msg": "Strange thing", "input": 1}]
    traducido = traducir_validacion(fuera)
    assert traducido[0]["msg"] == "valor no válido en cosa"
    assert traducido[0]["type"] == "tipo_raro" and traducido[0]["loc"] == ("body", "cosa")
    assert fuera[0]["msg"] == "Strange thing"  # copia: no toca el original


def test_405_en_json_y_en_espanol(cliente):
    resp = cliente.post("/solo-get")
    assert resp.status_code == 405
    assert resp.headers["content-type"].startswith("application/json")
    detalle = resp.json()["detail"]
    assert "Method Not Allowed" not in detalle
    assert "no admite esa operación" in detalle
    assert "GET" in resp.headers.get("allow", "")


def test_500_en_json_en_espanol_y_con_traza_en_el_registro(cliente, caplog):
    with caplog.at_level("ERROR", logger="vigia.app.errores"):
        resp = cliente.get("/roto")
    assert resp.status_code == 500
    assert resp.json() == {"detail": TEXTO_ERROR_INTERNO}
    assert "fallo con texto interno" not in resp.text
    assert any("fallo con texto interno" in (r.exc_text or "") or r.exc_info for r in caplog.records)


def test_app_real_mantiene_la_forma_del_422(client: TestClient):
    resp = client.post("/api/projects", json={"domain": "reuma"})
    assert resp.status_code == 422
    error = resp.json()["detail"][0]
    assert set(error) >= {"loc", "msg", "type"}
    assert error["type"] == "missing"
    assert error["msg"].startswith("falta el campo")
    assert "Field required" not in resp.text


def test_app_real_405_y_ruta_inexistente(client: TestClient):
    resp = client.post("/api/health")
    assert resp.status_code == 405
    assert "no admite esa operación" in resp.json()["detail"]
