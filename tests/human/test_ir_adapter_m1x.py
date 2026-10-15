"""M1x: las ventanas con menos de `MIN_N` decisiones no aportan
punto a la pendiente del deskilling. Siguen en la respuesta con su `n`.

El diario de lote pequeño de abajo es el patrón de concern-cds fase 2: dos
ventanas con n = 7 y 8 y dos con 40. Con todo el histórico las dos
pequeñas tiran de la pendiente y la señal dispara; con M1x solo cuentan las dos
grandes, con acuerdo plano, y no dispara. El oráculo es `build/validacion/medir_149.py`.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine

from vigia.app.models import UsageLog
from vigia.human._vendor.interaction_review.telemetry import (
    compute_trends,
    compute_windows,
    deskilling_signal,
)
from vigia.human.ir_adapter import (
    MIN_N,
    deskilling_view,
    records_from_db,
    ventanas_para_pendiente,
)

INICIO = date(2026, 1, 1)
VERSION = SimpleNamespace(id=1, label="v1")


def _filas(ventanas: list[tuple[int, float]]) -> list[UsageLog]:
    """Una ventana de calendario de 30 días por tupla `(n, acuerdo)`. Mitad de
    las filas con el modelo acertando y mitad errando (la verdad es 1); el
    profesional coincide con el modelo en la fracción `acuerdo` de cada mitad.
    Con el acuerdo subiendo, el rescate cae."""
    filas: list[UsageLog] = []
    for w, (n, acuerdo) in enumerate(ventanas):
        mitad = [(n + 1) // 2, n // 2]
        for paridad in (0, 1):
            coinciden = round(acuerdo * mitad[paridad])
            for k in range(mitad[paridad]):
                modelo = 1 if paridad == 0 else 0
                humano = modelo if k < coinciden else 1 - modelo
                dia = w * 30 + (k % 28)
                filas.append(
                    UsageLog(
                        project_id=1,
                        model_version_id=1,
                        date=(INICIO + timedelta(days=dia)).isoformat(),
                        human_decision=humano,
                        model_output=modelo,
                        ground_truth=1,
                    )
                )
    return filas


@pytest.fixture
def session() -> Session:
    motor = create_engine("sqlite://")
    SQLModel.metadata.create_all(motor)
    with Session(motor) as s:
        yield s


def _sembrar(session: Session, filas: list[UsageLog]) -> None:
    session.add_all(filas)
    session.commit()


# Ventanas de n = 7 y 8 con el acuerdo bajo y dos de 40 con el acuerdo alto y plano.
LOTE_PEQUENO = [(7, 0.3), (8, 0.25), (40, 0.75), (40, 0.75)]


def test_con_todo_el_historico_dispara_y_m1x_no(session: Session):
    filas = _filas(LOTE_PEQUENO)
    _sembrar(session, filas)

    # El paquete tal cual, con todas las ventanas: dispara.
    records = records_from_db(filas)
    ventanas = compute_windows(records, n_windows=4)
    assert [w.n for w in ventanas] == [7, 8, 40, 40]
    assert deskilling_signal(compute_trends(ventanas), eps=0.02).fired is True

    # M1x (la vista del adaptador): las ventanas de 7 y 8 salen de la pendiente.
    r = deskilling_view(session, 1, VERSION)
    assert r.sin_datos is False
    assert [w.n for w in r.windows] == [7, 8, 40, 40]  # siguen en la respuesta
    assert r.min_n == MIN_N == 30
    assert r.ventanas_excluidas == 2
    assert r.signal is not None and r.signal.fired is False
    assert r.trends is not None
    assert r.trends.agreement_slope == pytest.approx(0.0, abs=1e-9)
    # Las tasas de las ventanas pequeñas se enseñan: solo salen de la pendiente.
    assert r.windows[0].agreement_rate is not None


def test_ventanas_para_pendiente_conserva_la_posicion_de_cada_ventana(session: Session):
    """Excluir una ventana central no recorre el índice de la regresión: la
    pendiente es la de los puntos 0, 2 y 3, no la de 0, 1 y 2."""
    filas = _filas([(40, 0.2), (7, 0.9), (40, 0.4), (40, 0.5)])
    ventanas = compute_windows(records_from_db(filas), n_windows=4)
    validas = ventanas_para_pendiente(ventanas)
    assert [v.agreement_rate is None for v in validas] == [False, True, False, False]
    assert [v.n for v in validas] == [w.n for w in ventanas]
    pendiente = compute_trends(validas).agreement_slope
    # OLS sobre (0, .2), (2, .4), (3, .5)
    xs, ys = [0, 2, 3], [0.2, 0.4, 0.5]
    mx, my = sum(xs) / 3, sum(ys) / 3
    esperada = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sum((x - mx) ** 2 for x in xs)
    assert pendiente == pytest.approx(esperada)


def test_con_menos_de_dos_ventanas_validas_no_hay_pendiente_y_el_resumen_dice_por_que(
    session: Session,
):
    _sembrar(session, _filas([(7, 0.3), (8, 0.25), (6, 0.5), (40, 0.75)]))
    r = deskilling_view(session, 1, VERSION)
    assert r.sin_datos is False
    assert r.ventanas_excluidas == 3
    assert r.trends is not None
    assert r.trends.agreement_slope is None
    assert r.trends.human_accuracy_slope is None
    assert r.trends.rescue_slope is None
    assert r.signal is not None and r.signal.fired is False
    assert r.summary_md is not None
    assert "se excluyen 3 ventanas con menos de 30 eventos (las ventanas 1, 2, 3)" in r.summary_md
    assert "La pendiente no se calcula: queda 1 ventana con al menos 30 eventos y hacen falta 2." in r.summary_md


def test_el_resumen_nombra_la_ventana_excluida_en_singular(session: Session):
    _sembrar(session, _filas([(7, 0.3), (40, 0.5), (40, 0.5), (40, 0.5)]))
    r = deskilling_view(session, 1, VERSION)
    assert r.ventanas_excluidas == 1
    assert "se excluye 1 ventana con menos de 30 eventos (la ventana 1); sigue en la tabla" in r.summary_md
    assert "La pendiente no se calcula" not in r.summary_md


def test_sin_ventanas_pequenas_el_resultado_es_el_de_siempre(session: Session):
    _sembrar(session, _filas([(40, 0.3), (40, 0.4), (40, 0.5), (40, 0.6)]))
    r = deskilling_view(session, 1, VERSION)
    assert r.ventanas_excluidas == 0
    assert "se excluye" not in r.summary_md
    ventanas = compute_windows(records_from_db(_filas([(40, 0.3), (40, 0.4), (40, 0.5), (40, 0.6)])), 4)
    assert r.trends == compute_trends(ventanas)


def test_el_filtro_por_subgrupo_aplica_la_misma_exclusion(session: Session):
    """El mismo camino sirve a la lectura filtrada: un subgrupo con ventanas de
    n = 7 y 8 las excluye igual que el agregado."""
    filas = _filas(LOTE_PEQUENO)
    for f in filas:
        f.subgroup = "urgencias"
    _sembrar(session, filas)
    r = deskilling_view(session, 1, VERSION, subgroup="urgencias")
    assert r.ventanas_excluidas == 2
    assert r.signal is not None and r.signal.fired is False


def test_min_n_es_un_parametro_de_la_vista(session: Session):
    """Con `min_n` = 5 las ventanas de 7 y 8 ya cuentan y la señal dispara como con el paquete tal cual."""
    _sembrar(session, _filas(LOTE_PEQUENO))
    r = deskilling_view(session, 1, VERSION, min_n=5)
    assert r.ventanas_excluidas == 0
    assert r.signal is not None and r.signal.fired is True


def test_el_adaptador_pasa_nombres_de_clase_en_multiclase_y_refer_en_binario():
    """Una fila con clases va al paquete con los nombres de clase (que compara
    por igualdad); una fila binaria, con `refer`/`no-refer` desde los enteros."""
    multiclase = UsageLog(
        project_id=1, model_version_id=1, date="2026-01-05",
        human_decision=1, model_output=0, ground_truth=1,
        human_class="spam", model_class="ok", truth_class="odio",
    )
    sin_verdad = UsageLog(
        project_id=1, model_version_id=1, date="2026-01-06",
        human_decision=0, model_output=0, ground_truth=None,
        human_class="ok", model_class="ok", truth_class=None,
    )
    binaria = UsageLog(
        project_id=1, model_version_id=1, date="2026-01-07",
        human_decision=1, model_output=0, ground_truth=1,
    )
    a, b, c = records_from_db([multiclase, sin_verdad, binaria])
    assert (a.human, a.model, a.truth) == ("spam", "ok", "odio")
    assert (b.human, b.model, b.truth) == ("ok", "ok", None)
    assert (c.human, c.model, c.truth) == ("refer", "no-refer", "refer")


def test_con_menos_de_dos_validas_el_motivo_dice_la_celda_minima_no_la_verdad(session: Session):
    """Revisión D: `signal.reason` nombra la causa real (ventanas pequeñas), en
    español, tanto en la vista de la API como en el motivo de CX-4."""
    from vigia.human.deskilling_texto import motivo_es
    from vigia.human.ir_adapter import deskilling_reason_es

    _sembrar(session, _filas([(7, 0.3), (8, 0.25), (6, 0.5), (40, 0.75)]))
    r = deskilling_view(session, 1, VERSION)
    assert r.signal is not None
    assert "ventanas con eventos suficientes" in motivo_es(r.signal.reason)
    assert "verdad de referencia" not in motivo_es(r.signal.reason)
    assert "ventanas con eventos suficientes" in deskilling_reason_es(r.signal.reason)


def test_ninguna_ventana_valida_o_min_n_mayor_que_todas(session: Session):
    _sembrar(session, _filas([(7, 0.3), (8, 0.25), (6, 0.5), (9, 0.75)]))
    r = deskilling_view(session, 1, VERSION)
    assert r.ventanas_excluidas == 4
    assert r.trends is not None and r.trends.agreement_slope is None
    assert r.summary_md is not None and "quedan 0 ventanas" in r.summary_md
    r2 = deskilling_view(session, 1, VERSION, min_n=500)
    assert r2.ventanas_excluidas == 4


def test_cx4_con_m1x_no_dispara_con_ventanas_de_7_y_8(session: Session):
    """CX-4 lee la misma vista: con M1x el lote pequeño no abre la alerta."""
    from vigia.app.models import ModelVersion
    from vigia.app.services.human_layer import _deskilling_input_for_cx4

    session.add(ModelVersion(id=1, project_id=1, label="v1"))
    _sembrar(session, _filas(LOTE_PEQUENO))
    entrada = _deskilling_input_for_cx4(session, SimpleNamespace(id=1, active_version_id=1))  # type: ignore[arg-type]
    assert entrada is not None
    assert entrada.fired is False


def test_cambio_de_version_sigue_en_sin_datos_con_m1x(session: Session):
    _sembrar(session, _filas(LOTE_PEQUENO))
    r = deskilling_view(session, 1, SimpleNamespace(id=2, label="v2"))
    assert r.sin_datos is True
    assert r.motivo == "cambio de versión en el periodo"
