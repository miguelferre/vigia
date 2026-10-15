"""Tras reiniciar un proyecto, la huella del dossier
coincide con su contenido sin telemetría (se anula el resumen de uso)."""

from __future__ import annotations

from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from tests.seguridad import _base_proyecto as _base
from vigia.app.models import Dossier, DossierReview, Event
from vigia.app.services.dossiers import plantillas_preguntas
from vigia.human import dossier_adapter

app, client, session, settings = _base.app, _base.client, _base.session, _base.settings

PERFIL = {"purpose": "triaje de derivaciones"}


def _huella(telemetria: str | None) -> str:
    return dossier_adapter.assemble_markdown(
        profile=PERFIL,
        experience={},
        inventory={},
        telemetry_text=telemetria,
        preguntas_por_formulario=plantillas_preguntas(),
    ).sha256


def test_reiniciar_proyecto_recalcula_la_huella_del_dossier(client, session: Session):
    resp = client.post(
        "/api/projects",
        json={"name": "huella-279a", "domain": "reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    con_telemetria = _huella("resumen de uso")
    assert con_telemetria != _huella(None)
    session.add(
        Dossier(
            project_id=pid,
            system_name="s",
            profile_json=PERFIL,
            telemetry_included=True,
            telemetry_text="resumen de uso",
            sha256=con_telemetria,
        )
    )
    session.commit()
    dossier_id = session.exec(select(Dossier).where(Dossier.project_id == pid)).one().id
    session.add(DossierReview(dossier_id=dossier_id, dossier_sha256=con_telemetria))
    session.commit()

    resp = client.post(
        f"/api/projects/{pid}/reset",
        json={"actor": "miguel", "motivo": "prueba del control", "confirm": True},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    dossier = session.exec(select(Dossier).where(Dossier.project_id == pid)).one()
    assert dossier.telemetry_text is None and dossier.telemetry_included is False
    assert dossier.sha256 == _huella(None)
    # La revisión es registro de lo que se revisó: conserva su huella.
    revision = session.exec(select(DossierReview).where(DossierReview.dossier_id == dossier.id)).one()
    assert revision.dossier_sha256 == con_telemetria
    assert session.exec(select(Event).where(Event.action == "proyecto.reiniciado")).one()
