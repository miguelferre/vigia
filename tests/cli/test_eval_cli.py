"""Tests de `vigia eval` (ver `cmd_eval` en `vigia.cli`)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vigia.cli import main

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_E1 = REPO_ROOT / "data" / "demo" / "escenario_1"

BASELINE_PAYLOAD = str(DATA_E1 / "01_baseline_payload.json")
BASELINE_FEEDBACK = str(DATA_E1 / "01_baseline_feedback.json")
EVENTO_PAYLOAD = str(DATA_E1 / "02_evento_payload.json")
EVENTO_FEEDBACK = str(DATA_E1 / "02_evento_feedback.json")


def test_eval_evento_con_baseline_codigo_3_o_4_y_fairness_value(tmp_path, capsys):
    out_file = tmp_path / "resultado.json"
    code = main(
        [
            "eval",
            "--payload",
            EVENTO_PAYLOAD,
            "--feedback",
            EVENTO_FEEDBACK,
            "--baseline-payload",
            BASELINE_PAYLOAD,
            "--baseline-feedback",
            BASELINE_FEEDBACK,
            "--out",
            str(out_file),
            "--quiet",
        ]
    )
    # fairness_value 19,50 (inestable) y FNRD 0,631 (alerta) hacen que
    # el peor estado sea alerta: código 3 (anotado en el informe del carril).
    assert code in (3, 4)

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert set(data) >= {"fairness", "quality", "drift", "core_version", "app_version"}

    medidas = {m["metric_key"]: m for m in data["fairness"]["measurements"]}
    assert medidas["fairness_value"]["value"] == pytest.approx(19.50, abs=0.05)

    salida = capsys.readouterr()
    assert salida.out == ""  # --quiet: nada de resumen, solo el JSON a --out


def test_eval_fichero_inexistente_codigo_1_sin_traza(capsys):
    code = main(
        [
            "eval",
            "--payload",
            EVENTO_PAYLOAD,
            "--feedback",
            str(DATA_E1 / "no_existe.json"),
            "--quiet",
        ]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "vigia eval" in err
    assert "Traceback" not in err


def test_eval_solo_evento_sin_baseline_drift_sin_datos():
    code = main(
        [
            "eval",
            "--payload",
            EVENTO_PAYLOAD,
            "--feedback",
            EVENTO_FEEDBACK,
            "--quiet",
        ]
    )
    assert code in (0, 3, 4)


def test_eval_con_mapping_end_to_end_fairness_value_cerca_de_19_50(tmp_path):
    from vigia.core.schema import HARNESS_FEEDBACK_MAPPING

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps(HARNESS_FEEDBACK_MAPPING.model_dump(), ensure_ascii=False),
        encoding="utf-8",
    )
    out_file = tmp_path / "resultado_mapping.json"
    code = main(
        [
            "eval",
            "--payload",
            EVENTO_PAYLOAD,
            "--feedback",
            EVENTO_FEEDBACK,
            "--mapping",
            str(mapping_path),
            "--quiet",
            "--out",
            str(out_file),
        ]
    )
    assert code in (3, 4)
    data = json.loads(out_file.read_text(encoding="utf-8"))
    medidas = {m["metric_key"]: m for m in data["fairness"]["measurements"]}
    assert medidas["fairness_value"]["value"] == pytest.approx(19.50, abs=0.5)


def test_eval_con_mapping_prediction_col_inexistente_codigo_1(tmp_path, capsys):
    from vigia.core.schema import HARNESS_FEEDBACK_MAPPING

    mapping_malo = HARNESS_FEEDBACK_MAPPING.model_copy(
        update={"prediction_col": "columna_que_no_existe"}
    )
    mapping_path = tmp_path / "mapping_malo.json"
    mapping_path.write_text(
        json.dumps(mapping_malo.model_dump(), ensure_ascii=False), encoding="utf-8"
    )
    code = main(
        [
            "eval",
            "--payload",
            EVENTO_PAYLOAD,
            "--feedback",
            EVENTO_FEEDBACK,
            "--mapping",
            str(mapping_path),
            "--quiet",
        ]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "vigia eval" in err
    assert "columna_que_no_existe" in err
    assert "Traceback" not in err


def test_eval_solo_evento_sin_baseline_drift_sin_datos_json(tmp_path):
    out_file = tmp_path / "solo_evento.json"
    main(
        [
            "eval",
            "--payload",
            EVENTO_PAYLOAD,
            "--feedback",
            EVENTO_FEEDBACK,
            "--out",
            str(out_file),
            "--quiet",
        ]
    )
    data = json.loads(out_file.read_text(encoding="utf-8"))
    estados_drift = {m["metric_key"]: m["state"] for m in data["drift"]["measurements"]}
    assert set(estados_drift.values()) == {"sin_datos"}
