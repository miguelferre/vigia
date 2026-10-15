"""Texto de seguridad de la 1.0: lo que `SEGURIDAD.md` dice que no protege.

Cada test comprueba que el límite está escrito donde lo lee quien usa Vigía, en el
punto que le corresponde de la sección «Qué no protege y qué hacer». Los controles que
faltan no se arreglan aquí: se declaran.
"""

from __future__ import annotations

from pathlib import Path

from vigia.app.seguridad_http import CABECERAS_SEGURIDAD

RAIZ = Path(__file__).resolve().parents[2]

HUELLAS = {
    "test_seguridad_dice_version_1_0_y_nombra_las_auditorias": "version-and-audits",
    "test_seguridad_declara_el_tipo_de_contenido_y_las_cabeceras": "content-type-and-headers",
    "test_seguridad_declara_onnx_de_varias_clases_y_regresion": "onnx-classes-and-regression",
    "test_seguridad_declara_la_copia_previa_a_toda_migracion": "backup-before-migration",
    "test_seguridad_no_deja_los_permisos_como_pendientes": "permissions-not-pending",
    "test_seguridad_declara_la_huella_en_otro_canal": "checksum-other-channel",
    "test_seguridad_declara_las_dependencias_de_build": "build-dependencies",
    "test_seguridad_dice_como_avisar_de_un_fallo": "how-to-report",
    "test_limite_rutas_y_enlaces": "paths-and-links",
    "test_limite_revision_con_modelo": "model-review",
    "test_limite_retencion": "retention",
    "test_limite_ficheros_subidos_y_limpieza_incompleta": "uploaded-files-and-incomplete-cleanup",
    "test_limite_pickle_en_el_proceso": "pickle-in-process",
    "test_limite_disponibilidad": "availability",
    "test_limite_categoricas_y_borrados_en_marcha": "unaudited-surface",
    "test_limite_origin_sin_puerto": "origin-without-port",
}


def _texto() -> str:
    return (RAIZ / "SEGURIDAD.md").read_text(encoding="utf-8")


def _seccion(titulo: str) -> str:
    texto = _texto()
    inicio = texto.index(f"## {titulo}")
    fin = texto.find("\n## ", inicio + 1)
    return texto[inicio : fin if fin > 0 else None]


def _punto(seccion: str, clave: str) -> str:
    """El punto de la lista (`- **...`) cuyo encabezado contiene `clave`."""
    for punto in seccion.split("\n- **")[1:]:
        if clave.lower() in punto.split("**", 1)[0].lower():
            return " ".join(punto.lower().split())
    raise AssertionError(f"la sección no tiene un punto «{clave}»")


def test_seguridad_dice_version_1_0_y_nombra_las_auditorias():
    """El documento habla de la versión 1.0 y dice que pasó tres auditorías estáticas."""
    texto = _texto()
    bajo = texto.lower()
    assert "versión 1.0" in texto
    assert "versión 0.9" not in texto
    assert "tres auditorías" in bajo and "estátic" in bajo


def test_seguridad_declara_el_tipo_de_contenido_y_las_cabeceras():
    """«Qué hace» nombra el tipo de contenido estricto, las cuatro cabeceras y la ausencia de /docs."""
    punto = _punto(_seccion("Qué hace Vigía"), "tipo de contenido")
    assert "strict_content_type" in punto
    for nombre, _ in CABECERAS_SEGURIDAD:
        assert nombre.decode() in punto, nombre
    assert "/docs" in punto and "/redoc" in punto and "/openapi.json" in punto


def test_seguridad_declara_onnx_de_varias_clases_y_regresion():
    """El consejo de origen del modelo vale también para varias clases y regresión."""
    punto = _punto(_seccion("Qué hace Vigía"), "pickle o joblib")
    assert "ficheros aparte" in punto
    assert "varias clases" in punto and "regres" in punto and "conoces su origen" in punto


def test_seguridad_declara_la_copia_previa_a_toda_migracion():
    """La copia en `backups\\` se hace antes de cualquier migración pendiente, no solo de las últimas."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "copia previa")
    assert "migraciones 12 a 15" in punto and "base nueva" in punto
    assert "*.bak" in punto and "clave de api" in punto and "a mano" in punto


def test_seguridad_no_deja_los_permisos_como_pendientes():
    """El texto dice que otra cuenta de Windows puede escribir en las carpetas, y qué hacer."""
    texto = _texto()
    assert "pendiente antes de la 1.0" not in texto
    punto = _punto(_seccion("Qué no protege y qué hacer"), "permisos de carpetas")
    assert "otra cuenta de windows" in punto and "tu perfil" in punto


def test_seguridad_declara_la_huella_en_otro_canal():
    """La huella va también en el texto de la release, y sigue sin firma."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "huella")
    assert "texto de la release" in punto and "no está firmada" in punto


def test_seguridad_declara_las_dependencias_de_build():
    """El build usa `uv export --locked` y `npm ci`; lo que queda fuera del `lock` se nombra."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "dependencias de tiempo de build")
    for clave in ("uv export --locked", "npm ci --ignore-scripts", "node", "terceros.txt", "lock"):
        assert clave in punto, clave


def test_seguridad_dice_como_avisar_de_un_fallo():
    """La sección de avisos manda al aviso privado de GitHub y no a una incidencia abierta."""
    seccion = _seccion("Cómo avisar de un fallo").lower()
    assert "aviso privado de seguridad de github" in seccion
    assert "incidencia abierta" in seccion
    assert "cuando el repositorio tenga" not in seccion


def test_limite_rutas_y_enlaces():
    """«Qué no protege y qué hacer» dice que la API enseña las rutas y que un enlace precarga texto."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "ruta de tus carpetas")
    assert "/api/health" in punto and "ajustes" in punto and "carpeta de datos" in punto
    assert "?demo=anotar" in punto and "motivo" in punto


def test_limite_revision_con_modelo():
    """La revisión con modelo no distingue «vacío» de «limpio» ni comprueba la evidencia."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "revisión con modelo")
    assert "apagada por defecto" in punto and "clave" in punto
    assert "sin hallazgos" in punto and "evidencia" in punto and "con criterio" in punto


def test_limite_retencion():
    """Dice qué no se poda, qué sí retira un reinicio y qué hace `secure_delete`."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "poda nada")
    assert "diario" in punto and "outcomes" in punto and "vigia.log" in punto
    assert "secure_delete" in punto and ".bak" in punto and "a mano" in punto
    assert "v1.1" not in punto


def test_limite_ficheros_subidos_y_limpieza_incompleta():
    """Los ficheros subidos quedan en `uploads\\`; los que no se retiran se anotan."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "ficheros que subes")
    assert ".privado.csv" in punto and "registro de uso" in punto
    assert "limpieza_incompleta" in punto and "al arrancar" in punto


def test_limite_pickle_en_el_proceso():
    """Un pickle se carga en el proceso de Vigía, sin subproceso y con un plazo que no lo detiene."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "dentro del proceso")
    assert "sin subproceso" in punto and "60 s" in punto and "no detiene" in punto
    assert "has generado tú" in punto


def test_limite_disponibilidad():
    """Tres rutas no acotan su coste: la demo con proyecto, la explicación y el ONNX."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "no acotan su coste")
    assert "project_id" in punto and "sin deduplicar" in punto and "onnx" in punto
    assert "reinicia vigía" in punto and "plazo" in punto


def test_limite_categoricas_y_borrados_en_marcha():
    """Dice que Vigía no acota las variables categóricas enormes ni bloquea el borrado en marcha."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "variables categóricas enormes")
    assert "categóricas" in punto and "lote" in punto and "dataset" in punto
    assert "no acota" in punto


def test_limite_origin_sin_puerto():
    """La comprobación de `Origin` no mira el puerto, y el texto lo dice."""
    punto = _punto(_seccion("Qué no protege y qué hacer"), "no mira el puerto")
    assert "localhost" in punto and "127.0.0.1" in punto and "otro puerto" in punto
