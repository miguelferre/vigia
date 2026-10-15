from __future__ import annotations

from pathlib import Path

from vigia.sim import generators, serialize


def _masked_bytes(path: Path) -> bytes:
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return serialize.mask_ids(text).encode("utf-8")


def _assert_bytes_equal_masked(actual: Path, expected: Path) -> None:
    assert _masked_bytes(actual) == _masked_bytes(expected), f"{actual.name} no coincide byte a byte"


def test_e1_baseline_byte_a_byte(tmp_path, e1_dir):
    df = generators.generate_e1_baseline()
    payload_path = serialize.save_payload_json(df, tmp_path / "01_baseline_payload.json")
    feedback_path = serialize.save_feedback_json(
        df, tmp_path / "01_baseline_feedback.json", seed=7000, accuracy_target=0.88
    )
    _assert_bytes_equal_masked(payload_path, e1_dir / "01_baseline_payload.json")
    _assert_bytes_equal_masked(feedback_path, e1_dir / "01_baseline_feedback.json")


def test_e1_evento_byte_a_byte(tmp_path, e1_dir):
    df, _is_young = generators.generate_e1_event()
    payload_path = serialize.save_payload_json(df, tmp_path / "02_evento_payload.json")
    feedback_path = serialize.save_feedback_json(
        df, tmp_path / "02_evento_feedback.json", seed=1001, accuracy_target=0.86
    )
    _assert_bytes_equal_masked(payload_path, e1_dir / "02_evento_payload.json")
    _assert_bytes_equal_masked(feedback_path, e1_dir / "02_evento_feedback.json")


def test_e1_recovery_byte_a_byte(tmp_path, e1_dir):
    df = generators.generate_e1_recovery()
    payload_path = serialize.save_payload_json(df, tmp_path / "03_recovery_payload.json")
    feedback_path = serialize.save_feedback_json(
        df, tmp_path / "03_recovery_feedback.json", seed=7003, accuracy_target=0.88
    )
    _assert_bytes_equal_masked(payload_path, e1_dir / "03_recovery_payload.json")
    _assert_bytes_equal_masked(feedback_path, e1_dir / "03_recovery_feedback.json")


def test_e2_evento_byte_a_byte(tmp_path, e2_dir):
    df, ground_truth, _mask_new, _chosen_diags = generators.generate_e2_event()
    payload = serialize.payload_dict(df)
    feedback = serialize.feedback_dict(df, seed=3003, ground_truth_override=ground_truth)
    perm = serialize.reorder_last_window(df, seed=3003)
    payload, feedback = serialize.permute_dicts(payload, feedback, perm)

    payload_path = serialize.dump_json(payload, tmp_path / "02_evento_payload.json", indent=None)
    feedback_path = serialize.dump_json(feedback, tmp_path / "02_evento_feedback.json", indent=None)

    _assert_bytes_equal_masked(payload_path, e2_dir / "02_evento_payload.json")
    _assert_bytes_equal_masked(feedback_path, e2_dir / "02_evento_feedback.json")


def test_e2_evento_sin_reorder_no_coincide(e2_dir):
    """Sanity: sin aplicar reorder_last_window, el orden de filas difiere."""
    import json

    df, _ground_truth, _mask_new, _chosen_diags = generators.generate_e2_event()
    payload_sin_reorder = serialize.payload_dict(df)
    ages_sin_reorder = [row[payload_sin_reorder["input_data"][0]["fields"].index("Age")]
                        for row in payload_sin_reorder["input_data"][0]["values"][:50]]

    with open(e2_dir / "02_evento_payload.json", encoding="utf-8") as f:
        expected = json.load(f)
    fields = expected["input_data"][0]["fields"]
    ages_expected = [row[fields.index("Age")] for row in expected["input_data"][0]["values"][:50]]

    assert ages_sin_reorder != ages_expected


def test_e2_recovery_byte_a_byte(tmp_path, e2_dir):
    df = generators.generate_e2_recovery()
    payload = serialize.payload_dict(df)
    feedback = serialize.feedback_dict(df, seed=7777, accuracy_target=0.92)
    perm = serialize.reorder_last_window(df, seed=7777)
    payload, feedback = serialize.permute_dicts(payload, feedback, perm)

    payload_path = serialize.dump_json(payload, tmp_path / "03_recovery_payload.json", indent=None)
    feedback_path = serialize.dump_json(feedback, tmp_path / "03_recovery_feedback.json", indent=None)

    _assert_bytes_equal_masked(payload_path, e2_dir / "03_recovery_payload.json")
    _assert_bytes_equal_masked(feedback_path, e2_dir / "03_recovery_feedback.json")


def test_apply_permutation_reordena_y_resetea_indice():
    df = generators.generate_e1_baseline(seed=1, n_total=10)
    perm = list(range(9, -1, -1))
    out = serialize.apply_permutation(df, perm)
    assert out.index.tolist() == list(range(10))
    assert out["Patient_Id"].tolist() == df["Patient_Id"].tolist()[::-1]


def test_mask_ids_sustituye_patrones():
    text = "PAT_0123456789 y EP_0123456789ab siguen"
    masked = serialize.mask_ids(text)
    assert "PAT_XXXXXXXXXX" in masked
    assert "EP_XXXXXXXXXXXX" in masked
