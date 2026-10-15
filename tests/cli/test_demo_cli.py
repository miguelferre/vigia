"""Tests de `vigia demo run` y `vigia demo list` (ver `cmd_demo` en `vigia.cli`)."""
from __future__ import annotations

import json

from vigia.cli import main


def test_demo_run_timeline_completo_out_escribe_diez_ficheros(tmp_path):
    out_dir = tmp_path / "salida"
    code = main(["demo", "run", "timeline_completo", "--out", str(out_dir)])
    ficheros = sorted(p.name for p in out_dir.glob("*.json"))
    assert len(ficheros) == 10
    assert "timeline_completo-resumen.json" in ficheros
    for fase in ("b1", "b2", "b3", "b4", "b5", "e1_evento", "e1_recovery", "e2_evento", "e2_recovery"):
        assert f"timeline_completo-{fase}.json" in ficheros

    resumen = json.loads((out_dir / "timeline_completo-resumen.json").read_text(encoding="utf-8"))
    assert len(resumen) == 9
    assert resumen[0]["phase_key"] == "b1"

    # Todas las fases coinciden con expected: `aviso` cuenta como "sin
    # alerta" frente a un esperado "ok" (b1-b5 y e1_recovery tienen accuracy
    # 0,88 en la banda del 10 % sobre 0,80) y en fairness `inestable`
    # equivale a `alerta`.
    assert code == 0
    estados_por_fase = {fila["phase_key"]: fila["matches_expected"] for fila in resumen}
    assert estados_por_fase["b1"]["fairness"] is True
    assert estados_por_fase["e2_evento"]["fairness"] is True
    assert estados_por_fase["e2_recovery"]["fairness"] is True


def test_demo_run_guion_no_existe_codigo_2(capsys):
    code = main(["demo", "run", "no_existe"])
    assert code == 2
    err = capsys.readouterr().err
    assert "timeline_completo" in err
    assert "consejeria_regional" in err


def test_demo_list_lista_los_dos_guiones(capsys):
    code = main(["demo", "list"])
    assert code == 0
    salida = capsys.readouterr().out
    assert "timeline_completo" in salida
    assert "consejeria_regional" in salida


def test_demo_run_json_imprime_resumen(capsys):
    code = main(["demo", "run", "consejeria_regional", "--json"])
    salida = capsys.readouterr().out
    resumen = json.loads(salida)
    assert len(resumen) == 6
    assert code == 0


def test_demo_run_with_human_no_revienta():
    code = main(["demo", "run", "consejeria_regional", "--with-human", "--json"])
    assert code == 0
