"""Título y ayuda de `human_review_zero`, guía del modelo, límite del rango y plantilla de unidad y rango."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vigia.app.services.human_layer import _titulo_revision_cero

PROHIBIDO = ("paciente", "el clínico", "clínic", "derivar", "cribado", "—", "NaN", "undefined")


@pytest.mark.parametrize(
    ("tasa", "n", "esperado"),
    [
        (0.008, 7150, "Tasa de correcciones del modelo: solo el 0,8 % de 7150 decisiones corrigió al modelo"),
        (0.0, 7150, "Nadie ha corregido al modelo en 7150 decisiones"),
        (None, 400, "Nadie ha corregido al modelo en 400 decisiones"),
        (0.0004, 5000, "Tasa de correcciones del modelo: solo el 0,04 % de 5000 decisiones corrigió al modelo"),
    ],
)
def test_el_titulo_no_niega_correcciones_que_existen(tasa, n, esperado):
    assert _titulo_revision_cero(tasa, n) == esperado


def test_el_titulo_del_candidato_usa_la_tasa():
    from types import SimpleNamespace

    from vigia.app.services.human_layer import _candidato_revision_cero
    from vigia.core.schema import State

    m = SimpleNamespace(
        metric_key="human_review_zero", group_code=None, state=State.aviso, value=0.008,
        motivo="x", extra={"n": 7150},
    )
    assert _candidato_revision_cero(m)["title"] == (
        "Tasa de correcciones del modelo: solo el 0,8 % de 7150 decisiones corrigió al modelo"
    )


def test_el_titulo_servido_se_lee_tras_cambiar_la_etiqueta():
    """Regresión: `_titulo_actual` cambia la base por la etiqueta de la ayuda;
    el título servido debe seguir diciendo qué es el porcentaje."""
    from types import SimpleNamespace

    from vigia.app.services.alerting import _titulo_actual

    alerta = SimpleNamespace(
        title="Tasa de correcciones del modelo: solo el 0,6 % de 11150 decisiones corrigió al modelo",
        metric_key="human_review_zero", monitor_type="cross", group_code=None, project_id=1,
    )
    assert _titulo_actual(None, alerta) == alerta.title  # type: ignore[arg-type]


def test_human_review_zero_tiene_ayuda_y_bloque_de_regresion(client: TestClient):
    metricas = client.get("/api/content/metricas").json()
    entrada = metricas["human_review_zero"]
    assert entrada["monitor"] == "cross"
    for campo in ("que_mide", "formula", "como_se_lee"):
        assert entrada[campo], campo
    texto = " ".join(str(entrada[c]) for c in ("etiqueta", "que_mide", "formula", "como_se_lee"))
    assert "1 %" in texto and "300" in texto
    regresion = entrada["regresion"]
    assert "cruza el rango favorable" in regresion["que_mide"]
    for valor in (entrada, regresion):
        assert not [p for p in PROHIBIDO if p in " ".join(str(v) for v in valor.values())]


def test_la_guia_del_modelo_pide_float32(client: TestClient):
    guia = client.get("/api/content/guia-datos").json()
    modelo = next(s for s in guia["secciones"] if s["id"] == "modelo")
    assert any("float32" in nota and "regresor" in nota for nota in modelo["notas"])


def test_la_guia_de_datos_de_regresion_manda_fijar_unidad_y_rango_en_la_plantilla(client: TestClient):
    guia = client.get("/api/content/guia-datos").json()
    regresion = next(s for s in guia["secciones"] if s["id"] == "regresion")
    assert any("set_mapping_template" in n and "antes de congelar" in n for n in regresion["notas"])


def test_la_guia_de_uso_declara_el_limite_del_rango(client: TestClient):
    entradas = client.get("/api/content/guia-uso").json()["entradas"]
    capa = next(e for e in entradas if e["titulo"] == "Capa humana")
    limite = [p for p in capa["pasos"] if "En regresión, fija el rango favorable" in p]
    assert len(limite) == 1
    assert "antes de subir el registro de uso" in limite[0]
