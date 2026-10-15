"""`human/dossier_adapter.py`: línea base del proyecto como referencia del
dossier (opcional hasta que `services/dossiers.py` -fuera de
esta frontera- la pase desde `ProjectState.first_batch`)."""

from __future__ import annotations

from unittest.mock import patch

from vigia.human.dossier_adapter import DossierMarkdown, _referencia_linea_base, assemble_dossier


def test_referencia_linea_base_con_etiqueta():
    texto = _referencia_linea_base({"id": 1, "seq": 0, "phase_label": "b0"})
    assert texto == "Línea base: lote #0 · b0."


def test_referencia_linea_base_sin_etiqueta():
    texto = _referencia_linea_base({"id": 1, "seq": 3, "phase_label": None})
    assert texto == "Línea base: lote #3."


def test_assemble_dossier_sin_baseline_batch_no_toca_el_resumen():
    md = DossierMarkdown(
        profile_md="perfil", experience_md="experiencia", inventory_md="inventario", sha256="x"
    )
    with patch("vigia.human.dossier_adapter.build_dossier") as build_dossier_mock:
        assemble_dossier(
            md, telemetry_text=None, system_name="Vigía", domain="digestivo", summary="resumen humano"
        )
    assert build_dossier_mock.call_args.kwargs["summary"] == "resumen humano"


def test_assemble_dossier_con_baseline_batch_antepone_la_referencia():
    md = DossierMarkdown(
        profile_md="perfil", experience_md="experiencia", inventory_md="inventario", sha256="x"
    )
    with patch("vigia.human.dossier_adapter.build_dossier") as build_dossier_mock:
        assemble_dossier(
            md,
            telemetry_text=None,
            system_name="Vigía",
            domain="digestivo",
            summary="resumen humano",
            baseline_batch={"id": 7, "seq": 2, "phase_label": "e1_evento"},
        )
    resumen = build_dossier_mock.call_args.kwargs["summary"]
    assert resumen == "Línea base: lote #2 · e1_evento.\n\nresumen humano"


def test_assemble_dossier_con_baseline_batch_y_sin_resumen_previo():
    md = DossierMarkdown(
        profile_md="perfil", experience_md="experiencia", inventory_md="inventario", sha256="x"
    )
    with patch("vigia.human.dossier_adapter.build_dossier") as build_dossier_mock:
        assemble_dossier(
            md,
            telemetry_text=None,
            system_name="Vigía",
            domain="digestivo",
            baseline_batch={"id": 7, "seq": 2, "phase_label": None},
        )
    assert build_dossier_mock.call_args.kwargs["summary"] == "Línea base: lote #2."


# --- importar el `dossier.json` del paquete ----------------

import json
from pathlib import Path

import pytest

from vigia.human.dossier_adapter import (
    DossierInvalido,
    assemble_markdown,
    reconstruir_respuestas,
    validar_dossier_importado,
)
from vigia.human.dossier_import import (
    CLAVE_RESUMEN,
    CLAVE_SIN_ENCAJE,
    agrupar_fuentes,
    clave_fuente,
)
from vigia.human.dossier_markdown import _es_linea_estructural

_CASOS = sorted(Path(__file__).resolve().parents[1].glob("fixtures/casos-externos/*/dossier.json"))

_PEQUENO = {
    "system_name": "Triaje de ejemplo",
    "domain": "urgencias",
    "summary": "Resumen del sistema.\n- **Punto en negrita**",
    "sources": [
        {"id": "doc-1", "kind": "document", "label": "Ficha", "content": "Ficha técnica.\n# Título interno\nfin"},
        {"id": "tec-1", "kind": "technician", "label": "Proveedor", "content": "Lo mantiene el proveedor ✍ siempre."},
        {"id": "usr-1", "kind": "end_user", "label": "Médico", "content": "Acepto casi todo.\n> cita\n\nOtro párrafo."},
        {"id": "usr-2", "kind": "end_user", "label": "Médico", "content": "Otro médico."},
        {"id": "oth-1", "kind": "other", "label": "Prensa", "content": "Noticia."},
        {"id": "doc-2", "kind": "document", "label": "Vacío", "content": "no"},
        {"id": "doc-3", "kind": "document", "label": "Sin texto", "content": "  "},
    ],
}


def _norm(texto: str) -> str:
    r"""Contenido comparable: sin el escape `\` del saneado, ✍ como ✎ y sin
    espacios sobrantes ni líneas en blanco (el parser recorta cada línea)."""
    lineas = []
    for linea in texto.replace("✍️", "✎").replace("✍", "✎").splitlines():
        linea = linea.strip()
        if linea.startswith("\\") and _es_linea_estructural(linea[1:]):
            linea = linea[1:]
        if linea:
            lineas.append(linea)
    return "\n".join(lineas)


def _reconstruir(dossier: dict) -> dict[str, str]:
    """`{clave: respuesta}` de todo lo que el revisor vería tras importar."""
    ag = agrupar_fuentes(summary=dossier.get("summary", ""), sources=dossier["sources"])
    md = assemble_markdown(
        profile=ag.profile, experience=ag.experience, inventory=ag.inventory, telemetry_text=None
    )
    vistas: dict[str, str] = {}
    for markdown in (md.profile_md, md.experience_md, md.inventory_md):
        for pregunta, respuesta in reconstruir_respuestas(markdown):
            vistas[pregunta] = respuesta
    return vistas


def _comprobar_sin_perdidas(dossier: dict) -> None:
    vistas = _reconstruir(dossier)
    assert validar_dossier_importado(dossier) is not None
    if dossier.get("summary", "").strip():
        assert _norm(vistas[CLAVE_RESUMEN]) == _norm(dossier["summary"])
    sin_encaje = _norm(vistas.get(CLAVE_SIN_ENCAJE, ""))
    for fuente in dossier["sources"]:
        clave = clave_fuente(fuente["label"], fuente["id"])
        # El paquete lee el inventario como `[x] <documento>`.
        clave = clave if clave in vistas else f"[x] {clave}"
        esperado = _norm(fuente["content"])
        if clave in vistas and _norm(vistas[clave]):
            assert _norm(vistas[clave]) == esperado, fuente["id"]
        else:
            assert fuente["id"] in sin_encaje, fuente["id"]
            assert esperado in sin_encaje or not esperado, fuente["id"]


def test_importar_dossier_pequeno_no_pierde_contenido():
    _comprobar_sin_perdidas(_PEQUENO)


def test_agrupar_fuentes_por_kind_y_clave_propia():
    ag = agrupar_fuentes(summary=_PEQUENO["summary"], sources=_PEQUENO["sources"])
    assert next(iter(ag.profile)) == CLAVE_RESUMEN
    assert clave_fuente("Proveedor", "tec-1") in ag.profile
    assert set(ag.experience) == {"Médico [usr-1]", "Médico [usr-2]"}
    assert set(ag.inventory) == {"Ficha [doc-1]"}
    # `other`, «no» y el contenido en blanco van a la clave propia.
    assert ag.sin_encaje == ["oth-1", "doc-2", "doc-3"]
    assert "[other] Prensa [oth-1]: Noticia." in ag.profile[CLAVE_SIN_ENCAJE]
    assert "(sin contenido)" in ag.profile[CLAVE_SIN_ENCAJE]


def test_dossier_invalido_dice_el_campo_en_espanol():
    malo = {**_PEQUENO, "sources": [{**_PEQUENO["sources"][0], "kind": "inventado"}]}
    with pytest.raises(DossierInvalido) as exc:
        validar_dossier_importado(malo)
    texto = str(exc.value)
    assert "sources[0].kind" in texto and "valor no admitido" in texto


def test_dossier_sin_fuentes_es_invalido():
    with pytest.raises(DossierInvalido) as exc:
        validar_dossier_importado({**_PEQUENO, "sources": []})
    assert "al menos una fuente" in str(exc.value)


@pytest.mark.parametrize("ruta", _CASOS, ids=lambda p: p.parent.name)
def test_dossier_externo_se_reconstruye_sin_perder_contenido(ruta: Path):
    """Sobre cada `tests/fixtures/casos-externos/<caso>/dossier.json`."""
    _comprobar_sin_perdidas(json.loads(ruta.read_text(encoding="utf-8")))


def test_agrupar_fuentes_bordes_no_pierden_nada():
    fuentes = [
        {"id": "a", "kind": "end_user", "label": "Médico", "content": "uno"},
        {"id": "a", "kind": "end_user", "label": "Médico", "content": "dos"},
        {"id": "d1", "kind": "document", "label": "Ficha", "content": "No"},
        {"id": "t1", "kind": "technician", "label": "Prov", "content": "  "},
    ]
    ag = agrupar_fuentes(summary="", sources=fuentes)
    assert sorted(ag.experience.values()) == ["dos", "uno"]
    assert ag.inventory == {}
    assert ag.sin_encaje == ["d1", "t1"]
    texto = next(iter(ag.profile.values()))
    assert "Ficha [d1]" in texto and "(sin contenido)" in texto
