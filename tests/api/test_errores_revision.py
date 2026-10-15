"""`fila.error` de la revisión de dossier, por tipo de fallo."""

from __future__ import annotations

import contextlib

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.test_dossiers import _crear_dossier, _reproducir_demo
from vigia.app.models import DossierReview
from vigia.app.services import dossiers_review_job as job_mod
from vigia.human import dossier_adapter


def _fila_nueva(client: TestClient, session: Session, approach: str) -> int:
    run = _reproducir_demo(client)
    dossier = _crear_dossier(client, run["project_id"]).json()
    fila = DossierReview(
        dossier_id=dossier["id"],
        approach=approach,
        status="pendiente",
        actor="miguel",
        role="auditor",
        motivo="prueba de los textos de error",
    )
    session.add(fila)
    session.commit()
    return fila.id


def _correr(session: Session, review_id: int, approach: str) -> DossierReview:
    resultado = job_mod.ejecutar_review(
        session,
        review_id,
        approach=approach,
        corpus="todas",
        dedup=True,
        incluir_crosswalk=True,
        backend="local",
        llm_conf={},
        correlation_id="prueba-c53",
        job_id=0,
        bus=None,
    )
    assert resultado["status"] == "error"
    session.expire_all()
    fila = session.get(DossierReview, review_id)
    assert fila is not None and fila.status == "error"
    return fila


@pytest.fixture
def entorno_falso(monkeypatch):
    monkeypatch.setattr(dossier_adapter, "llm_environment", lambda **_: contextlib.nullcontext())


def test_fallo_del_proveedor_lleva_el_prefijo(
    client: TestClient, session: Session, monkeypatch, entorno_falso
):
    review_id = _fila_nueva(client, session, "p3")

    def _falla(*_a, **_k):
        raise ConnectionError("tiempo de espera agotado")

    monkeypatch.setattr(dossier_adapter, "run_review", _falla)
    fila = _correr(session, review_id, "p3")
    assert fila.error == "el proveedor del modelo de lenguaje respondió: tiempo de espera agotado"


def test_error_interno_en_la_revision_no_se_atribuye_al_proveedor(
    client: TestClient, session: Session, monkeypatch, entorno_falso
):
    review_id = _fila_nueva(client, session, "p3")

    def _falla(*_a, **_k):
        raise KeyError("campo_interno")

    monkeypatch.setattr(dossier_adapter, "run_review", _falla)
    fila = _correr(session, review_id, "p3")
    assert "proveedor" not in fila.error and "campo_interno" not in fila.error


def test_fallo_del_proveedor_sin_texto_usa_el_nombre_del_tipo(
    client: TestClient, session: Session, monkeypatch, entorno_falso
):
    review_id = _fila_nueva(client, session, "p3")

    def _falla(*_a, **_k):
        raise TimeoutError()

    monkeypatch.setattr(dossier_adapter, "run_review", _falla)
    fila = _correr(session, review_id, "p3")
    assert fila.error == "el proveedor del modelo de lenguaje respondió: TimeoutError"


def test_dossier_invalido_dice_su_motivo_tal_cual(
    client: TestClient, session: Session, monkeypatch, entorno_falso
):
    review_id = _fila_nueva(client, session, "b0")

    def _falla(*_a, **_k):
        raise dossier_adapter.DossierInvalido("falta la sección «perfil del sistema»")

    monkeypatch.setattr(dossier_adapter, "assemble_dossier", _falla)
    fila = _correr(session, review_id, "b0")
    assert fila.error == "falta la sección «perfil del sistema»"


def test_otro_fallo_da_el_texto_generico_sin_texto_de_libreria(
    client: TestClient, session: Session, monkeypatch, entorno_falso
):
    review_id = _fila_nueva(client, session, "b0")

    def _falla(*_a, **_k):
        raise KeyError("columna_secreta")

    monkeypatch.setattr(dossier_adapter, "assemble_dossier", _falla)
    fila = _correr(session, review_id, "b0")
    assert (
        fila.error
        == "error interno al revisar el dossier: el registro del servidor tiene el detalle"
    )
    assert "columna_secreta" not in fila.error
