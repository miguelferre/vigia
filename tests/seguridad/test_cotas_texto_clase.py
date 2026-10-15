"""Cotas de texto en los textos libres que no tienen módulo propio
y nombre de clase acotado en el núcleo común a mapeo, plantilla y alta.

Cada test comprueba un control; ver `HUELLAS`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vigia.app.schemas.datasets import IngestBody
from vigia.app.schemas.dossiers import DossierCreateBody, DossierImportBody
from vigia.app.schemas.monitors import MonitorPatch, MonitorProtocolStepBody
from vigia.app.schemas.risks import RiskCreateBody
from vigia.core.schema import MAX_LARGO_CLASE, _normalizar_clases

TEXTO_SIN_TOPE = "resource/free-text-unbounded-persisted-append-only-and-amplified-per-class"

HUELLAS = {
    "test_el_nombre_de_clase_tiene_tope_en_el_nucleo": TEXTO_SIN_TOPE,
    "test_el_titulo_y_la_descripcion_de_un_riesgo_tienen_tope": TEXTO_SIN_TOPE,
    "test_los_textos_del_protocolo_de_un_monitor_tienen_tope": TEXTO_SIN_TOPE,
    "test_el_nombre_del_sistema_de_un_dossier_tiene_tope": TEXTO_SIN_TOPE,
    "test_la_fase_y_el_motivo_de_una_ingesta_tienen_tope": TEXTO_SIN_TOPE,
}

BASE = {"actor": "miguel", "motivo": "prueba"}


def test_el_nombre_de_clase_tiene_tope_en_el_nucleo():
    assert _normalizar_clases(["a" * MAX_LARGO_CLASE, "b"]) == ["a" * MAX_LARGO_CLASE, "b"]
    with pytest.raises(ValueError, match="como mucho"):
        _normalizar_clases(["a" * (MAX_LARGO_CLASE + 1), "b"])


def test_el_titulo_y_la_descripcion_de_un_riesgo_tienen_tope():
    RiskCreateBody(**BASE, title="t" * 200, description="d" * 2000)
    with pytest.raises(ValidationError):
        RiskCreateBody(**BASE, title="t" * 201)
    with pytest.raises(ValidationError):
        RiskCreateBody(**BASE, title="t", description="d" * 2001)


def test_los_textos_del_protocolo_de_un_monitor_tienen_tope():
    MonitorProtocolStepBody(key="k", titulo="t", descripcion="d" * 2000, entregables=["e" * 2000])
    with pytest.raises(ValidationError):
        MonitorProtocolStepBody(key="k", titulo="t" * 201)
    with pytest.raises(ValidationError):
        MonitorProtocolStepBody(key="k", titulo="t", entregables=["e" * 2001])
    with pytest.raises(ValidationError):
        MonitorPatch(**BASE, protocolo_md="p" * 20_001)


def test_el_nombre_del_sistema_de_un_dossier_tiene_tope():
    DossierCreateBody(**BASE, system_name="s" * 200, domain="d" * 2000)
    with pytest.raises(ValidationError):
        DossierCreateBody(**BASE, system_name="s" * 201)
    with pytest.raises(ValidationError):
        DossierImportBody(**BASE, system_name="s", domain="d" * 2001)


def test_la_fase_y_el_motivo_de_una_ingesta_tienen_tope():
    IngestBody(phase_label="f" * 200, motivo_manipulacion="m" * 2000)
    with pytest.raises(ValidationError):
        IngestBody(phase_label="f" * 201)
    with pytest.raises(ValidationError):
        IngestBody(motivo_manipulacion="m" * 2001)
