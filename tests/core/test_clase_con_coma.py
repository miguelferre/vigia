"""Una clase con coma se rechaza en el esquema, con el mismo
patrón que «nan». Vigía usa la coma para separar listas de clases en
`group_code` y en las listas pedidas por la API."""

from __future__ import annotations

import pytest

from vigia.core.schema import MappingTemplate


@pytest.mark.parametrize("nombre", ["a,b", " spam,odio ", "alto,", ",bajo"])
def test_una_clase_con_coma_se_rechaza_en_el_alta(nombre):
    with pytest.raises(ValueError, match="lleva una coma") as exc:
        MappingTemplate(classes=[nombre, "spam", "odio"], favorable_label=["spam"])
    assert nombre.strip() in str(exc.value)


def test_una_clase_con_coma_no_afecta_a_las_demas():
    plantilla = MappingTemplate(classes=["a b", "c-d", "e/f"], favorable_label=["a b"])
    assert plantilla.classes == ["a b", "c-d", "e/f"]


def test_nan_sigue_rechazado_antes_que_la_coma():
    with pytest.raises(ValueError, match="«nan» no sirve como nombre de clase"):
        MappingTemplate(classes=["nan", "spam", "odio"], favorable_label=["spam"])
