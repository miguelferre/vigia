"""Los avisos de la ingesta dicen qué hacer."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api import test_ingesta_formatos as r2
from tests.api.test_titulos_avisos_ingesta import _ingerir_csv


def test_un_grupo_protegido_que_no_esta_en_el_lote_avisa(client: TestClient):
    filas = ["id,prediction,label,grupo"] + [
        f"{i},{i % 2},{i % 2},{'A' if i % 2 else 'B'}" for i in range(10)
    ]
    resultado = _ingerir_csv(
        client,
        "r6-grupo-ausente",
        ("\n".join(filas) + "\n").encode(),
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "favorable_label": 1,
            "protected_attr_col": "grupo",
            "protected_kind": "categorical",
            "unpriv_groups": ["NoExiste"],
            "priv_groups": ["A", "B"],
        },
    )
    avisos = [a for a in resultado["avisos"] if "atributo protegido" in a]
    assert len(avisos) == 1
    assert "«NoExiste»" in avisos[0] and "revisa" in avisos[0] and "mapeo" in avisos[0]


def test_un_grupo_presente_no_avisa(client: TestClient):
    filas = ["id,prediction,label,grupo"] + [
        f"{i},{i % 2},{i % 2},{'A' if i % 2 else 'B'}" for i in range(10)
    ]
    resultado = _ingerir_csv(
        client,
        "r6-grupo-presente",
        ("\n".join(filas) + "\n").encode(),
        {
            "prediction_col": "prediction",
            "label_col": "label",
            "id_col": "id",
            "favorable_label": 1,
            "protected_attr_col": "grupo",
            "protected_kind": "categorical",
            "unpriv_groups": ["A"],
            "priv_groups": ["B"],
        },
    )
    assert not any("atributo protegido" in a for a in resultado["avisos"])


def test_los_ids_duplicados_y_las_tres_clases_dicen_que_hacer(client: TestClient):
    filas = ["id,prediction,label"] + [f"{i % 2},{i % 3 % 2},{i % 3}" for i in range(9)]
    resultado = _ingerir_csv(
        client,
        "r6-dup-tres-clases",
        ("\n".join(filas) + "\n").encode(),
        {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1},
    )
    duplicados = [a for a in resultado["avisos"] if "identificador que ya existía" in a]
    assert duplicados and "revisa la columna de identificador" in duplicados[0]
    clases = [a for a in resultado["avisos"] if "modelos binarios" in a]
    assert clases and "elige la columna correcta en el mapeo" in clases[0]


def test_etiquetas_tardias_sin_pareja_avisan(client: TestClient):
    proyecto = r2._crear_proyecto(client, "r6-feedback-sin-pareja")
    version_id = proyecto["active_version_id"]
    lote = r2._subir(
        client, proyecto["id"], filename="lote.csv", content=b"id,prediction,label\nE1,1,\nE2,0,\n"
    ).json()
    r2._mapear(
        client, lote["dataset"]["id"], {"prediction_col": "prediction", "label_col": "label", "id_col": "id", "favorable_label": 1}
    )
    r2._ingerir(client, lote["dataset"]["id"], model_version_id=version_id)
    fb = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("fb.csv", b"id,label\nE1,1\nZ9,0\nZ8,1\n", "text/csv")},
        data={"kind": "feedback", "role": "production"},
        headers=r2.actor_headers("miguel"),
    ).json()
    r2._mapear(client, fb["dataset"]["id"], {"label_col": "label", "id_col": "id", "favorable_label": 1})
    resultado = r2._ingerir(client, fb["dataset"]["id"], model_version_id=version_id)["result"]
    assert resultado["n_matched"] == 1 and resultado["n_unmatched"] == 2
    assert any(
        a.startswith("2 etiquetas no tienen pareja en ningún lote") and "identificador" in a
        for a in resultado["avisos"]
    )
