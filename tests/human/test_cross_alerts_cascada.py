"""CX-6 con exclusión en cascada .

El grupo que el modelo ya señaló sale del complemento de CX-6. Con un
atributo de dos grupos, el complemento del otro queda vacío y CX-6 da
`sin_datos`: el complementario de un par no es una comparación. Con tres o más
grupos, CX-6 compara contra los que quedan.
"""
from __future__ import annotations

import pandas as pd

from vigia.human.cross_alerts import (
    MOTIVO_CX6_UN_SOLO_GRUPO,
    build_reference,
    evaluate_cross,
    two_proportion_z,
)

N = 200


def _grupo(nombre: str, overrides: int, offset: int) -> pd.DataFrame:
    """`N` decisiones del subgrupo; las primeras `overrides` corrigen al modelo."""
    modelo = ["no-refer"] * N
    humano = ["refer"] * overrides + ["no-refer"] * (N - overrides)
    return pd.DataFrame(
        {
            "date": ["2026-01-05"] * N,
            "clinician_pseudonym": [f"clin-{nombre}"] * N,
            "subgroup": [nombre] * N,
            "human_decision": humano,
            "model_output": modelo,
            "ground_truth": ["no-refer"] * N,
            "record_seq": list(range(offset, offset + N)),
            "model_version": ["v1"] * N,
        }
    )


def _usage(**overrides_por_grupo: int) -> pd.DataFrame:
    frames = [
        _grupo(nombre, ov, i * N) for i, (nombre, ov) in enumerate(overrides_por_grupo.items())
    ]
    return pd.concat(frames, ignore_index=True)


def _cx6(resultado, grupo: str):
    return next(m for m in resultado.measurements if m.metric_key == f"cx6_override_z:{grupo}")


def _cx6_alertas(resultado):
    return {a.group for a in resultado.alerts if a.rule == "CX-6"}


def test_dos_grupos_sin_exclusion_una_alerta_por_pareja():
    """El z es simétrico; una alerta, anclada en el de menos override."""
    df = _usage(A=100, B=20)
    r = evaluate_cross(df, reference=build_reference(df), mode="vigilancia")
    assert _cx6_alertas(r) == {"B"}
    alerta = next(a for a in r.alerts if a.rule == "CX-6")
    assert "B y A difieren en override (0.10 frente a 0.50" in alerta.motivo
    pareja = _cx6(r, "A")
    assert pareja.state.value == "ok"
    assert pareja.value == two_proportion_z(100, N, 20, N)
    assert pareja.extra["pareja_de"] == "B"


def test_dos_grupos_iguales_no_dan_alerta():
    df = _usage(A=40, B=40)
    r = evaluate_cross(df, reference=build_reference(df), mode="vigilancia")
    assert _cx6_alertas(r) == set()
    assert _cx6(r, "A").state.value == "ok"
    assert "pareja_de" not in _cx6(r, "A").extra


def test_dos_grupos_con_el_senalado_excluido_cx6_da_sin_datos():
    df = _usage(A=100, B=20)
    r = evaluate_cross(
        df, reference=build_reference(df), mode="vigilancia", model_alert_groups={"A"}
    )
    complementario = _cx6(r, "B")
    assert complementario.state.value == "sin_datos"
    assert complementario.value is None
    assert complementario.motivo == MOTIVO_CX6_UN_SOLO_GRUPO
    assert complementario.motivo == "un solo grupo tras excluir el señalado por el modelo"
    # Ningún disparo de CX-6, ni en el señalado ni en el complementario.
    assert _cx6_alertas(r) == set()


def test_tres_grupos_compara_los_que_quedan():
    df = _usage(A=100, B=20, C=80)
    r = evaluate_cross(
        df, reference=build_reference(df), mode="vigilancia", model_alert_groups={"A"}
    )
    esperado_b = two_proportion_z(20, N, 80, N)
    medida_b = _cx6(r, "B")
    assert medida_b.motivo is None
    assert medida_b.value == esperado_b
    # B se compara solo con C (200 filas), no con A y C juntos (400).
    assert medida_b.extra["n_complemento"] == N
    assert _cx6(r, "C").value == two_proportion_z(80, N, 20, N)
    # Quedan dos grupos tras la cascada: una alerta por pareja.
    assert _cx6_alertas(r) == {"B"}
    assert _cx6(r, "C").extra["pareja_de"] == "B"


def test_cuatro_grupos_con_uno_excluido_no_colapsa():
    df = _usage(A=190, B=20, C=20, D=120)
    r = evaluate_cross(
        df, reference=build_reference(df), mode="vigilancia", model_alert_groups={"A"}
    )
    # Quedan tres: cada uno contra los otros dos, sin pareja.
    assert "D" in _cx6_alertas(r)
    assert all("pareja_de" not in m.extra for m in r.measurements if m.metric_key.startswith("cx6"))


def test_tres_grupos_el_senalado_no_dispara_aunque_se_aparte():
    df = _usage(A=190, B=40, C=40)
    r = evaluate_cross(
        df, reference=build_reference(df), mode="vigilancia", model_alert_groups={"A"}
    )
    # B y C son iguales entre si: nada que avisar; A esta senalado por el modelo.
    assert _cx6_alertas(r) == set()
    assert _cx6(r, "B").state.value == "ok"
    assert _cx6(r, "A").state.value == "ok"


def test_senalado_ausente_de_los_datos_no_cambia_nada():
    df = _usage(A=100, B=20)
    r = evaluate_cross(
        df, reference=build_reference(df), mode="vigilancia", model_alert_groups={"Z"}
    )
    assert _cx6_alertas(r) == {"B"}
    assert _cx6(r, "B").value == two_proportion_z(20, N, 100, N)
    assert _cx6(r, "B").motivo is None


def test_cx1_no_cambia_con_la_cascada():
    df = _usage(A=100, B=20)
    ref = build_reference(df)
    sin = evaluate_cross(df, reference=ref, mode="vigilancia")
    con = evaluate_cross(df, reference=ref, mode="vigilancia", model_alert_groups={"A"})
    def cx1(r):
        return [(m.metric_key, m.value, m.state) for m in r.measurements if "cx1" in m.metric_key]
    assert cx1(sin) == cx1(con)
