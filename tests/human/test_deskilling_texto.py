"""El texto del deskilling sale en español.

Se prueba contra `telemetry` del paquete vendorizado: el catálogo de motivos
tiene que cubrir lo que `deskilling_signal` puede producir, y el resumen en
español tiene que decir lo mismo (mismas cifras, mismas líneas) que el inglés."""

from __future__ import annotations

import re
from datetime import date

import pytest

pytest.importorskip("vigia.human._vendor.interaction_review")

from vigia.human._vendor.interaction_review import telemetry as tel
from vigia.human.deskilling_texto import MOTIVOS_ES, motivo_es, resumen_md_es

_INGLES = re.compile(
    r"\b(Usage|telemetry|Source|Windows|Events|Window|Dates|Agreement|accuracy|Human|Model|Rescue|"
    r"Trends|slope|Deskilling signal|no signal|Caution|events|ground truth|converging|diagnosis|"
    r"Aggregated|testimony|substitute|rising|win)\b"
)


def _senales():
    """Las salidas de `deskilling_signal` que alcanzan sus cuatro ramas."""
    def t(a, h, r):
        return tel.Trends(agreement_slope=a, human_accuracy_slope=h, model_accuracy_slope=0.0, rescue_slope=r)

    return [
        tel.deskilling_signal(t(None, None, None)),
        tel.deskilling_signal(t(0.1, -0.1, 0.1)),
        tel.deskilling_signal(t(0.1, 0.1, -0.1)),
        tel.deskilling_signal(t(0.1, -0.1, -0.1)),
        tel.deskilling_signal(t(-0.1, 0.0, 0.0)),
        tel.deskilling_signal(t(0.1, 0.1, 0.1)),
    ]


def test_el_catalogo_cubre_todas_las_salidas_del_paquete():
    senales = _senales()
    assert len({s.reason for s in senales}) == 6
    for s in senales:
        assert s.reason in MOTIVOS_ES, s.reason
        assert not _INGLES.search(motivo_es(s.reason))


def test_motivo_desconocido_no_deja_pasar_ingles():
    texto = motivo_es("A brand new reason from a newer package.")
    assert "revisar la versión" in texto
    assert "brand new" not in texto


def _ventanas():
    return [
        tel.WindowMetrics(date(2026, 3, 1), date(2026, 3, 8), 40, 40, 0.9, 0.8, 0.85, 0.5),
        tel.WindowMetrics(date(2026, 3, 8), date(2026, 3, 15), 10, 0, 0.95, None, None, None),
    ]


def test_resumen_es_conserva_cifras_y_estructura_del_paquete():
    ventanas = _ventanas()
    tendencias = tel.compute_trends(ventanas)
    senal = tel.deskilling_signal(tendencias)
    es = resumen_md_es(ventanas, tendencias, senal, min_n=30)
    en = tel.render_summary_md(ventanas, tendencias, senal, min_n=30)

    # Misma forma: mismo número de líneas, mismas filas de la tabla y mismas cifras.
    assert len(es.splitlines()) == len(en.splitlines())
    cifras = re.compile(r"[+-]?\d+\.\d+|\d{4}-\d\d-\d\d\.\.\d{4}-\d\d-\d\d")
    assert cifras.findall(es) == cifras.findall(en)
    assert es.count("|") == en.count("|")
    # Los avisos del paquete (pocas observaciones, sin verdad de referencia) salen en español.
    assert "Precaución: la ventana 2 tiene menos de 30 eventos" in es
    assert "Precaución: la ventana 2 no tiene verdad de referencia" in es


def test_resumen_es_no_tiene_ingles_y_es_determinista():
    ventanas = _ventanas()
    tendencias = tel.compute_trends(ventanas)
    senal = tel.deskilling_signal(tendencias)
    es = resumen_md_es(ventanas, tendencias, senal)
    assert not _INGLES.search(es), _INGLES.search(es)
    assert es == resumen_md_es(ventanas, tendencias, senal)
    assert "Señal de deskilling (IX-2): sin señal." in es


def test_resumen_es_con_senal_disparada():
    ventanas = [
        tel.WindowMetrics(date(2026, 3, 1), date(2026, 3, 8), 50, 50, 0.7, 0.9, 0.9, 0.6),
        tel.WindowMetrics(date(2026, 3, 8), date(2026, 3, 15), 50, 50, 0.9, 0.85, 0.9, 0.4),
    ]
    tendencias = tel.compute_trends(ventanas)
    senal = tel.deskilling_signal(tendencias)
    assert senal.fired
    es = resumen_md_es(ventanas, tendencias, senal)
    assert "Señal de deskilling (IX-2): SEÑAL." in es
    assert "erosión del criterio" in es
