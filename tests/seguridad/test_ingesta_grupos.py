"""Ingesta y mapeo: validación de los grupos protegidos y del índice de probabilidad.

Cada test comprueba el control seguro de una huella; ver `HUELLAS`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vigia.core.schema import ColumnMapping, MappingTemplate

_N10 = "mapping/protected-groups-shape-finiteness-overlap-unvalidated"
HUELLAS = {
    "test_los_grupos_protegidos_mal_formados_se_rechazan": _N10,
    "test_los_grupos_protegidos_solapados_se_rechazan": _N10,
    "test_un_intervalo_de_un_solo_valor_sigue_valiendo": _N10,
    "test_los_grupos_categoricos_sin_solape_valen": _N10,
    "test_el_indice_de_probabilidad_debe_caer_en_el_rango": _N10,
}

GRUPOS_MALOS = [
    [[1]],
    [[1, 2, 3]],
    [[float("nan"), 35]],
    [[18, float("inf")]],
    [[35, 18]],
]


@pytest.mark.parametrize("grupos", GRUPOS_MALOS)
def test_los_grupos_protegidos_mal_formados_se_rechazan(grupos):
    """Forma de pares, valores finitos y mínimo no mayor que el máximo, en el mapeo
    y en la plantilla."""
    base = {"protected_attr_col": "age", "priv_groups": [[40, 75]]}
    with pytest.raises(ValidationError, match="unpriv_groups"):
        ColumnMapping(unpriv_groups=grupos, **base)
    with pytest.raises(ValidationError, match="unpriv_groups"):
        MappingTemplate(unpriv_groups=grupos, **base)


def test_los_grupos_protegidos_solapados_se_rechazan():
    """Los intervalos (o las categorías) de los dos grupos no se solapan."""
    for clase in (ColumnMapping, MappingTemplate):
        with pytest.raises(ValidationError, match="solap"):
            clase(protected_attr_col="age", unpriv_groups=[[18, 35]], priv_groups=[[30, 75]])
        with pytest.raises(ValidationError, match="solap"):
            clase(
                protected_attr_col="sexo", protected_kind="categorical",
                unpriv_groups=["f", "x"], priv_groups=["x"],
            )


def test_un_intervalo_de_un_solo_valor_sigue_valiendo():
    """Un atributo codificado 0/1 se declara con intervalos de un solo valor."""
    m = ColumnMapping(protected_attr_col="sexo", unpriv_groups=[[0, 0]], priv_groups=[[1, 1]])
    assert m.unpriv_groups == [[0, 0]]
    MappingTemplate(protected_attr_col="sexo", unpriv_groups=[[0, 0]], priv_groups=[[1, 1]])


def test_los_grupos_categoricos_sin_solape_valen():
    """El camino legítimo de un atributo categórico sigue intacto."""
    m = ColumnMapping(
        protected_attr_col="sexo", protected_kind="categorical",
        unpriv_groups=["f"], priv_groups=["m", "otro"],
    )
    assert m.priv_groups == ["m", "otro"]


@pytest.mark.parametrize("indice", [-1, 2, 7])
def test_el_indice_de_probabilidad_debe_caer_en_el_rango(indice):
    """Con probabilidad en lista, el índice cae entre 0 y k-1."""
    with pytest.raises(ValidationError, match="probability_index"):
        ColumnMapping(probability_col="p", probability_format="list", probability_index=indice)
    assert ColumnMapping(probability_col="p", probability_format="list", probability_index=1)
