"""`GET /overrides` (gestor, agregado), `/overrides/clinicians` y
`/overrides/me` (vista propia). Datos con `vigia.sim.human.simulate_decisions`,
como `tests/human/test_cross_alerts.py`, insertados directamente en `usage_log`."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.conftest import actor_headers
from vigia.app.models import Batch, UsageLog
from vigia.sim.generators import generate_baseline, score_dataframe
from vigia.sim.human import HumanParams, simulate_decisions
from vigia.sim.serialize import feedback_dict

START = date(2026, 1, 5)


def _crear_proyecto(client: TestClient, name: str = "reuma-overrides") -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "domain": "reuma"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _labeled(df_scored: pd.DataFrame, seed: int, accuracy_target: float) -> pd.DataFrame:
    df_scored = df_scored.reset_index(drop=True)
    fb = feedback_dict(df_scored, seed=seed, accuracy_target=accuracy_target)
    idx = fb["fields"].index("Has_Referral_in_Window")
    df_scored["Has_Referral_in_Window"] = [row[idx] for row in fb["values"]]
    return df_scored


def _usage_df(seed: int, params: HumanParams, n: int = 450, start_date: date = START) -> pd.DataFrame:
    df = score_dataframe(generate_baseline(n=n, seed=seed), seed=seed)
    df = _labeled(df, seed=seed, accuracy_target=0.88)
    return simulate_decisions(df, seed=seed, params=params, start_date=start_date)


def _volcar_usage_log(
    session: Session,
    project_id: int,
    model_version_id: int,
    df_usage: pd.DataFrame,
    batch_id: int | None = None,
) -> None:
    """Vuelca un frame de `simulate_decisions` a filas de `UsageLog` (`human_decision`/`model_output`/`ground_truth` como entero, no como etiqueta)."""
    label_a_entero = {"refer": 1, "no-refer": 0}
    for i, fila in df_usage.reset_index(drop=True).iterrows():
        session.add(
            UsageLog(
                project_id=project_id,
                model_version_id=model_version_id,
                batch_id=batch_id,
                record_seq=int(fila["record_seq"]) if pd.notna(fila["record_seq"]) else i,
                date=str(fila["date"]),
                clinician_pseudonym=fila["clinician_pseudonym"],
                subgroup=fila["subgroup"],
                human_decision=label_a_entero[fila["human_decision"]],
                model_output=label_a_entero[fila["model_output"]],
                ground_truth=label_a_entero[fila["ground_truth"]],
            )
        )
    session.commit()


def test_by_subgroup_sesgado_tiene_override_rate_mas_alto(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    # Con 450 filas el subgrupo 18-35 tiene 16 y queda bajo la celda mínima
    # (el test de abajo lo comprueba); con 1200 llega a la celda mínima.
    df_usage = _usage_df(seed=1, params=HumanParams(k_sub={"18-35": 4.0}), n=1200)
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    resp = client.get(f"/api/projects/{proyecto['id']}/overrides?by=subgroup")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["by"] == "subgroup"
    assert body["n_total"] == len(df_usage)
    grupos = {g["group"]: g for g in body["groups"]}
    assert "18-35" in grupos
    assert grupos["18-35"]["n"] >= body["min_n"]
    otros = [g for nombre, g in grupos.items() if nombre != "18-35" and g["tasa"] is not None]
    assert otros, "hace falta al menos otro subgrupo con tasa para comparar"
    assert all(grupos["18-35"]["tasa"] > g["tasa"] for g in otros)


def test_celda_minima_en_subgrupo_y_fase_da_tasa_nula_con_su_n(client: TestClient, session: Session):
    """Una celda con menos de `min_n` decisiones da la tasa como
    `null` y conserva su `n`; las celdas con `n >= min_n` siguen con su tasa."""
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    df_usage = _usage_df(seed=1, params=HumanParams(k_sub={"18-35": 4.0}))
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    body = client.get(f"/api/projects/{proyecto['id']}/overrides?by=subgroup").json()
    assert body["min_n"] == 30
    grupos = {g["group"]: g for g in body["groups"]}
    pequeno = grupos["18-35"]
    assert pequeno["n"] == 16 < body["min_n"]
    assert pequeno["tasa"] is None
    # La fila de grupo solo lleva `tasa`; `override_rate` se retiró.
    assert "override_rate" not in pequeno
    grande = grupos["36-75"]
    assert grande["n"] >= body["min_n"]
    assert grande["tasa"] is not None and "override_rate" not in grande

    # Por fase: filas sueltas sin lote van a `sin_fase`, con 450 filas pasan la celda.
    por_fase = client.get(f"/api/projects/{proyecto['id']}/overrides?by=phase").json()
    assert por_fase["min_n"] == 30
    assert all((g["tasa"] is None) == (g["n"] < 30) for g in por_fase["groups"])


def test_celda_minima_configurable_en_la_funcion_de_servicio(client: TestClient, session: Session):
    from vigia.app.services import overrides as overrides_service

    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    df_usage = _usage_df(seed=1, params=HumanParams(k_sub={"18-35": 4.0}))
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    bajo = overrides_service.overrides_by_group(session, proyecto["id"], version_id, "subgroup", min_n=10)
    assert bajo["min_n"] == 10
    assert {g["group"]: g for g in bajo["groups"]}["18-35"]["tasa"] is not None
    alto = overrides_service.overrides_by_group(session, proyecto["id"], version_id, "subgroup", min_n=400)
    assert next(g for g in alto["groups"] if g["group"] == "36-75")["tasa"] is None


def test_by_phase_agrupa_por_phase_label_del_lote_y_sin_fase_para_filas_sueltas(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    lote = Batch(
        project_id=proyecto["id"],
        model_version_id=version_id,
        phase_label="E1 evento",
        n_rows=10,
    )
    session.add(lote)
    session.commit()
    session.refresh(lote)

    df_usage = _usage_df(seed=2, params=HumanParams())
    mitad = len(df_usage) // 2
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage.iloc[:mitad], batch_id=lote.id)
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage.iloc[mitad:], batch_id=None)

    resp = client.get(f"/api/projects/{proyecto['id']}/overrides?by=phase")
    assert resp.status_code == 200, resp.text
    grupos = {g["group"]: g for g in resp.json()["groups"]}
    assert grupos["E1 evento"]["n"] == mitad
    assert grupos["sin_fase"]["n"] == len(df_usage) - mitad


def test_by_clinician_nunca_lleva_fila_por_pseudonimo_y_bins_suman_qualified(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    df_usage = _usage_df(seed=3, params=HumanParams(n_clinicians=10), n=900)
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    resp = client.get(f"/api/projects/{proyecto['id']}/overrides?by=clinician")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["by"] == "clinician"
    assert "groups" not in body
    texto = resp.text
    for i in range(1, 11):
        assert f"clin-{i:02d}" not in texto
    # n=900 entre 10 clínicos (`_usage_df`, seed=3) deja al menos 73 filas por
    # clínico, muy por encima de `min_clinician=30`: los 10 cualifican siempre
    # y `distribution` nunca es `None` aquí.
    assert body["n_qualified"] == 10
    assert body["distribution"] is not None
    assert sum(body["distribution"]["bin_counts"]) == body["n_qualified"]
    assert body["n_clinicians"] <= 10


def test_by_clinician_con_menos_de_dos_cualificados_distribution_null_con_motivo(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    # Muy pocas filas: ningún profesional llega a `min_clinician` (30).
    df_usage = _usage_df(seed=4, params=HumanParams(), n=10)
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    resp = client.get(f"/api/projects/{proyecto['id']}/overrides?by=clinician")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["distribution"] is None
    assert body["motivo"]


def test_by_fuera_del_catalogo_422(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client)
    resp = client.get(f"/api/projects/{proyecto['id']}/overrides?by=nope")
    assert resp.status_code == 422


def test_sin_filas_para_model_version_id_devuelve_groups_vacio_no_404(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client)
    resp = client.get(
        f"/api/projects/{proyecto['id']}/overrides"
        f"?by=subgroup&model_version_id={proyecto['active_version_id']}"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_total"] == 0
    assert body["groups"] == []


def test_overrides_clinicians_lista_alfabetica(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    df_usage = _usage_df(seed=5, params=HumanParams(n_clinicians=4), n=40)
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    resp = client.get(f"/api/projects/{proyecto['id']}/overrides/clinicians")
    assert resp.status_code == 200, resp.text
    clinicians = resp.json()["clinicians"]
    assert clinicians == sorted(clinicians)
    assert len(clinicians) >= 1


def test_overrides_me_pseudonimo_inexistente_404(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    df_usage = _usage_df(seed=6, params=HumanParams(), n=40)
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    resp = client.get(
        f"/api/projects/{proyecto['id']}/overrides/me?clinician=no-existe"
    )
    assert resp.status_code == 404


def test_overrides_me_coherente_con_overrides_by_clinician_para_ese_profesional(
    client: TestClient, session: Session
):
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    frames = []
    for i in range(4):
        frames.append(
            _usage_df(
                seed=100 + i,
                params=HumanParams(n_clinicians=6),
                n=200,
                start_date=START + timedelta(days=10 * i),
            )
        )
    df_usage = pd.concat(frames, ignore_index=True)
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    clinician = df_usage["clinician_pseudonym"].iloc[0]
    resp = client.get(
        f"/api/projects/{proyecto['id']}/overrides/me?clinician={clinician}"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["clinician"] == clinician
    assert body["n_windows"] == 4
    suma_mine = sum(w["mine"]["n"] for w in body["windows"])
    n_esperado = int((df_usage["clinician_pseudonym"] == clinician).sum())
    assert suma_mine == n_esperado


def test_celda_minima_configurable_por_la_api(client: TestClient, session: Session):
    proyecto = _crear_proyecto(client)
    version_id = proyecto["active_version_id"]
    df_usage = _usage_df(seed=1, params=HumanParams(k_sub={"18-35": 4.0}))
    _volcar_usage_log(session, proyecto["id"], version_id, df_usage)

    url = f"/api/projects/{proyecto['id']}/overrides?by=subgroup"
    bajo = client.get(url + "&min_n=10").json()
    assert bajo["min_n"] == 10
    assert {g["group"]: g for g in bajo["groups"]}["18-35"]["tasa"] is not None
    assert client.get(url + "&min_n=0").status_code == 422


def test_celda_minima_cuenta_las_decisiones_con_override_calculable():
    """Revisión D: una celda con n >= min_n pero pocas filas con override
    calculable no da tasa ni cuartiles."""
    import pandas as pd

    from vigia.app.services.overrides import _by_group

    filas = [{"subgroup": "a", "phase": "p", "clinician_pseudonym": f"c{i % 3}", "override": 1.0 if i % 2 else 0.0} for i in range(10)]
    filas += [{"subgroup": "a", "phase": "p", "clinician_pseudonym": "c0", "override": None} for _ in range(40)]
    df = pd.DataFrame(filas)
    g = _by_group(df, "subgroup", 1, len(df), min_n=30)["groups"][0]
    assert g["n"] == 50
    assert g["tasa"] is None and "override_rate" not in g
    assert g["p25"] is None and g["median"] is None and g["p75"] is None
