"""Tests en seco de `build/humo_zip.py` : funciones puras y la ejecución con pasos simulados.

El humo en sí (marcar, extraer, arrancar, imports, demo) lo ejecuta el script del cierre contra el
zip; aquí se prueban el entorno limpio, la lectura del puerto, el parseo del stream de
zona, la clasificación de un import lento frente a un bloqueo 4551 y la fecha de la
carpeta de datos. `build/humo_zip.py` es una herramienta del árbol de trabajo: si no
está (árbol público), el módulo entero se salta.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HUMO = REPO_ROOT / "build" / "humo_zip.py"

if not HUMO.is_file():
    pytest.skip("build/humo_zip.py no está en este árbol", allow_module_level=True)


def _cargar():
    spec = importlib.util.spec_from_file_location("vigia_humo_zip", HUMO)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


hz = _cargar()


# --------------------------------------------------------------------------
# stream Zone.Identifier
# --------------------------------------------------------------------------


def test_contenido_de_la_marca_de_la_web():
    texto = hz.contenido_zone_identifier()
    assert texto == "[ZoneTransfer]\r\nZoneId=3\r\n"
    assert hz.parse_zone_identifier(texto) == 3


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("[ZoneTransfer]\r\nZoneId=3\r\nReferrerUrl=x\r\n", 3),
        ("[ZoneTransfer]\nZoneId=4", 4),
        ("[ZoneTransfer]\nZoneId = 2\n", 2),
        ("[ZoneTransfer]\n", None),
        ("", None),
        (None, None),
        ("ZoneId=abc", None),
    ],
)
def test_parse_zone_identifier(texto, esperado):
    assert hz.parse_zone_identifier(texto) == esperado


def test_parse_salida_zonas_y_hay_marca():
    salida = (
        "ZONA|C:\\x\\Vigia.cmd|3\r\n"
        "ZONA|C:\\x\\runtime\\_ssl.pyd|3\r\n"
        "ZONA|C:\\x\\runtime\\a.pyd|\r\n"
        "ruido que no es una línea de zona\r\n"
    )
    zonas = hz.parse_salida_zonas(salida)
    assert zonas == {
        "C:\\x\\Vigia.cmd": 3,
        "C:\\x\\runtime\\_ssl.pyd": 3,
        "C:\\x\\runtime\\a.pyd": None,
    }
    assert hz.hay_marca(zonas, ".cmd") and hz.hay_marca(zonas, ".pyd")


def test_hay_marca_falla_sin_marca_en_un_tipo():
    zonas = {"C:\\x\\Vigia.cmd": 3, "C:\\x\\a.pyd": None}
    assert hz.hay_marca(zonas, ".cmd")
    assert not hz.hay_marca(zonas, ".pyd")
    assert not hz.hay_marca({}, ".cmd")
    # Una zona local (0) no es la de Internet.
    assert not hz.hay_marca({"C:\\x\\a.pyd": 0}, ".pyd")


def test_la_marca_se_escribe_en_el_zip_y_no_en_los_extraidos():
    # El humo marca la copia del zip; el único sitio donde escribe el stream es el paso 1.
    fuente = HUMO.read_text(encoding="utf-8")
    assert fuente.count("Zone.Identifier\", \"w\"") == 1
    assert "Expand-Archive" not in fuente.replace("Nunca Expand-Archive", "").replace(
        "nunca Expand-Archive", ""
    ).replace("Expand-Archive`", "")


# --------------------------------------------------------------------------
# entorno limpio
# --------------------------------------------------------------------------

SISTEMA = {
    "SystemRoot": r"C:\Windows",
    "NUMBER_OF_PROCESSORS": "8",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PYTHONPATH": r"D:\no\debe\pasar",
    "VIRTUAL_ENV": r"D:\venv",
    "VIGIA_HOME": r"D:\datos",
    "PATH": r"D:\python313;D:\venv\Scripts",
    "USERPROFILE": r"C:\Users\persona",
}


def _env(**kw):
    return hz.entorno_limpio(
        Path(r"C:\Users\persona\Documents\banco\instalacion\n1\perfil"),
        Path(r"C:\Users\persona\Documents\banco\instalacion\n1\tmp"),
        SISTEMA,
        **kw,
    )


def test_entorno_limpio_apunta_el_perfil_a_la_carpeta_de_prueba():
    env = _env()
    perfil = r"C:\Users\persona\Documents\banco\instalacion\n1\perfil"
    assert env["USERPROFILE"] == perfil
    assert env["HOMEDRIVE"] == "C:"
    assert env["HOMEPATH"] == r"\Users\persona\Documents\banco\instalacion\n1\perfil"
    assert env["APPDATA"].startswith(perfil) and env["LOCALAPPDATA"].startswith(perfil)
    assert env["TEMP"] == env["TMP"] and env["TEMP"].endswith(r"n1\tmp")


def test_entorno_limpio_no_hereda_nada_prohibido():
    env = _env()
    assert hz.claves_prohibidas_en_entorno(env) == []
    for clave in ("PYTHONPATH", "VIRTUAL_ENV", "VIGIA_HOME"):
        assert clave not in env
    # Ni el PATH ni el perfil de la máquina real se cuelan.
    assert "python313" not in env["PATH"].lower() and "venv" not in env["PATH"].lower()
    assert "persona\\appdata" not in env["APPDATA"].lower().replace("n1\\perfil", "")


def test_entorno_limpio_path_solo_con_carpetas_de_windows():
    carpetas = _env()["PATH"].split(";")
    assert carpetas
    assert all(c.lower().startswith(r"c:\windows") for c in carpetas)


def test_entorno_limpio_lleva_lo_que_windows_necesita():
    env = _env()
    for clave in ("SystemRoot", "windir", "COMSPEC", "PATHEXT"):
        assert env[clave]
    assert env["COMSPEC"].lower().endswith("cmd.exe")
    assert ".CMD" in env["PATHEXT"]
    assert env["NUMBER_OF_PROCESSORS"] == "8"


def test_entorno_limpio_anula_el_navegador_salvo_que_se_pida():
    assert _env()["BROWSER"] == "cmd /c rem %s"
    assert "BROWSER" not in _env(abrir_navegador=True)


def test_entorno_limpio_con_el_entorno_real_de_la_maquina():
    env = hz.entorno_limpio(Path("C:/p/perfil"), Path("C:/p/tmp"))
    assert hz.claves_prohibidas_en_entorno(env) == []
    assert env["USERPROFILE"].replace("/", "\\").lower().endswith(r"p\perfil")


def test_claves_prohibidas_detecta_cualquier_capitalizacion():
    assert hz.claves_prohibidas_en_entorno({"pythonpath": "x", "Path": "y"}) == ["pythonpath"]


# --------------------------------------------------------------------------
# puerto
# --------------------------------------------------------------------------


def test_puerto_de_salida():
    assert hz.puerto_de_salida("Vigía en http://127.0.0.1:8766 listo") == 8766
    assert hz.puerto_de_salida("abre http://localhost:8765/") == 8765
    assert hz.puerto_de_salida("sin puerto") is None
    assert hz.puerto_de_salida("") is None


def test_puerto_y_token_de_lock():
    lock = json.dumps({"pid": 1, "port": 8767, "token": "abc", "started_at": "x"})
    assert hz.puerto_de_lock(lock) == 8767
    assert hz.token_de_lock(lock) == "abc"
    assert hz.puerto_de_lock("no es json") is None
    assert hz.puerto_de_lock('{"port": "8767"}') is None
    assert hz.token_de_lock('{"pid": 1}') is None


@pytest.mark.parametrize("puerto", sorted(hz.PUERTOS_PROHIBIDOS))
def test_puertos_prohibidos(puerto):
    assert not hz.puerto_permitido(puerto)


@pytest.mark.parametrize("puerto", [8765, 8766, 8789, 8791, 8849, 8855, 8975])
def test_puertos_permitidos(puerto):
    assert hz.puerto_permitido(puerto)


# --------------------------------------------------------------------------
# rutas, versión
# --------------------------------------------------------------------------


def test_dentro_de():
    base = r"C:\banco\n1\extraido\vigia-0.9.0-win64"
    assert hz.dentro_de(base + r"\runtime\python\python.exe", base)
    assert hz.dentro_de(base.upper() + r"\x", base)  # sin distinguir mayúsculas
    assert hz.dentro_de(base, base)
    assert not hz.dentro_de(r"C:\banco\n1\extraido\vigia-0.9.0-win64-otro\x", base)
    assert not hz.dentro_de(r"C:\Users\persona\Documents\vigia-datos", base)


def test_version_del_zip():
    assert hz.version_del_zip("vigia-0.9.0-win64.zip") == "0.9.0"
    assert hz.version_del_zip("vigia-1.2.3-win64-sin-shap.zip") == "1.2.3"
    assert hz.version_del_zip("otra-cosa.zip") is None


# --------------------------------------------------------------------------
# imports: lentitud frente a bloqueo 4551
# --------------------------------------------------------------------------

BLOQUEO = (
    "ImportError: DLL load failed while importing _multiarray_umath: "
    "Una directiva de Control de aplicaciones bloqueó este archivo. "
    r"(C:\x\runtime\python\Lib\site-packages\numpy\_core\_multiarray_umath.cp313-win_amd64.pyd)"
    "\nOSError: [WinError 4551]"
)


def test_clasificar_import_ok_lento_error_y_bloqueo():
    assert hz.clasificar_import(0, "{}", 1.2) == "ok"
    assert hz.clasificar_import(0, "{}", 25.0) == "lento"
    assert hz.clasificar_import(1, "ModuleNotFoundError: No module named 'x'", 0.3) == "error"
    assert hz.clasificar_import(1, BLOQUEO, 0.3) == "bloqueo_politica"


def test_una_carga_lenta_no_se_confunde_con_un_bloqueo():
    assert hz.clasificar_import(0, "", 120.0) == "lento"
    assert not hz.es_bloqueo_politica("tardó 120 s en cargar")


def test_es_bloqueo_politica_por_codigo_o_por_texto():
    assert hz.es_bloqueo_politica("[WinError 4551]")
    assert hz.es_bloqueo_politica("Una directiva de Control de aplicaciones bloqueó este archivo")
    assert not hz.es_bloqueo_politica("ImportError: DLL load failed: no se encontró el módulo")


def test_fichero_bloqueado_nombra_el_pyd():
    assert hz.fichero_bloqueado(BLOQUEO).endswith("_multiarray_umath.cp313-win_amd64.pyd")
    assert hz.fichero_bloqueado("sin rutas") is None


def test_los_modulos_nativos_son_los_del_spec():
    assert hz.MODULOS_NATIVOS == (
        "numpy", "scipy", "sklearn", "onnxruntime", "lime", "shap", "llvmlite.binding", "numba",
    )  # fmt: skip
    # `import llvmlite` a secas no carga el DLL de LLVM: tiene que ser `.binding` (o numba).
    assert "llvmlite" not in hz.MODULOS_NATIVOS


# --------------------------------------------------------------------------
# fecha de la carpeta de datos real
# --------------------------------------------------------------------------


def test_fecha_mas_reciente_sin_carpeta(tmp_path):
    r = hz.fecha_mas_reciente(tmp_path / "no-existe")
    assert r == {"existe": False, "mtime_ns": None, "entradas": 0}


def test_fecha_mas_reciente_sigue_el_fichero_mas_nuevo(tmp_path):
    (tmp_path / "a").mkdir()
    f1, f2 = tmp_path / "a" / "uno.db", tmp_path / "dos.log"
    f1.write_text("x")
    f2.write_text("y")
    os.utime(f1, ns=(1_000_000_000, 1_000_000_000))
    os.utime(f2, ns=(2_000_000_000, 2_000_000_000))
    antes = hz.fecha_mas_reciente(tmp_path)
    assert antes["existe"] and antes["entradas"] == 3
    assert antes["mtime_ns"] >= 2_000_000_000
    # Tocar un fichero cambia el resultado; dejarlo igual, no.
    assert hz.fecha_mas_reciente(tmp_path) == antes
    os.utime(f1, ns=(9_000_000_000_000_000_000, 9_000_000_000_000_000_000))
    assert hz.fecha_mas_reciente(tmp_path) != antes


def test_fecha_mas_reciente_no_abre_los_ficheros(tmp_path, monkeypatch):
    (tmp_path / "x.db").write_text("secreto")

    def prohibido(*a, **k):
        raise AssertionError("no se abren ficheros")

    monkeypatch.setattr("builtins.open", prohibido)
    monkeypatch.setattr(Path, "open", prohibido)
    monkeypatch.setattr(Path, "read_text", prohibido)
    monkeypatch.setattr(Path, "read_bytes", prohibido)
    assert hz.fecha_mas_reciente(tmp_path)["existe"]


# --------------------------------------------------------------------------
# zip, PowerShell, resumen
# --------------------------------------------------------------------------


def test_contar_zip_ignora_carpetas(tmp_path):
    z = tmp_path / "v.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("raiz/", "")
        zf.writestr("raiz/a.txt", "1234")
        zf.writestr("raiz/sub/b.txt", "123456")
    assert hz.contar_zip(z) == (2, 10)


def test_codificar_powershell_es_utf16_base64():
    cod = hz.codificar_powershell("Write-Output 'á'")
    assert base64.b64decode(cod).decode("utf-16-le") == "Write-Output 'á'"


def test_ps_literal_duplica_las_comillas():
    assert hz.ps_literal(r"C:\a b\o'neil") == r"'C:\a b\o''neil'"


def test_script_de_extraccion_usa_el_explorador_con_las_banderas_y_espera():
    s = hz.script_extraer(Path(r"C:\t\v.zip"), Path(r"C:\t\ext"), 123, 4567, 600)
    assert "Shell.Application" in s and "CopyHere" in s
    assert f"CopyHere($src.Items(), {4 + 16 + 1024})" in s
    assert hz.FLAGS_COPYHERE == 1044
    assert "$esperados = 123" in s and "$bytes = 4567" in s and "$max = 600" in s
    assert "while ($true)" in s and "Start-Sleep" in s
    assert "Expand-Archive" not in s


def test_script_de_zonas_lee_el_stream_con_get_item():
    s = hz.script_zonas([Path(r"C:\t\Vigia.cmd"), Path(r"C:\t\_ssl.pyd")])
    assert "Get-Item -LiteralPath $p -Stream Zone.Identifier" in s
    assert "'C:\\t\\Vigia.cmd'" in s and "'C:\\t\\_ssl.pyd'" in s
    assert "Set-Content" not in s and "Add-Content" not in s  # no escribe la marca


def test_resumen_y_codigo_de_salida():
    informe = {
        "zip": "vigia-0.9.0-win64.zip",
        "carpeta": "C:/banco/n1",
        "ok": False,
        "bloqueo_politica": None,
        "pasos": [
            {"id": "1", "estado": "ok", "segundos": 1.5, "resumen": "marcado"},
            {"id": "2", "estado": "FALLA", "segundos": 20.0, "resumen": "tiempo agotado"},
        ],
    }
    texto = hz.resumen_texto(informe)
    assert "FALLA" in texto and "tiempo agotado" in texto
    assert hz.codigo_de_salida(informe) == 1
    assert hz.codigo_de_salida({**informe, "ok": True}) == 0
    assert hz.codigo_de_salida({**informe, "bloqueo_politica": {"modulo": "numpy"}}) == 2


def test_el_parser_y_los_valores_por_defecto():
    args = hz.build_parser().parse_args(["--zip", "x.zip"])
    assert args.puerto_max_espera > 0
    assert args.abrir_navegador is False
    assert args.smoke_ir.endswith("smoke_ir.py")


def test_el_humo_sigue_los_once_pasos_en_orden():
    fuente = HUMO.read_text(encoding="utf-8")
    ids = [
        fuente.index(f'self.correr("{n}"')
        for n in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11")
    ]
    assert ids == sorted(ids)


def test_el_resumen_dice_si_la_carpeta_de_datos_real_cambio():
    base = {"zip": "z", "carpeta": "c", "ok": True, "bloqueo_politica": None, "pasos": []}
    sin = hz.resumen_texto({**base, "datos_reales": {"sin_cambios": True, "lock_presente": False}})
    assert "sin cambios de fecha" in sin
    con = hz.resumen_texto({**base, "datos_reales": {"sin_cambios": False, "lock_presente": True}})
    assert "CAMBIÓ DE FECHA" in con and "lock" in con


def test_los_datos_reales_se_comprueban_aunque_el_humo_se_detenga_antes():
    # La comparación vive en `ejecutar`, fuera de los pasos: no depende de llegar al 11.
    fuente = HUMO.read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("def ejecutar(") :]
    assert cuerpo.index("reales_antes") < cuerpo.index('self.correr("1"')
    assert cuerpo.index("reales_despues") > cuerpo.index("self.limpiar()")


# --------------------------------------------------------------------------
# casos de la revisión
# --------------------------------------------------------------------------


def test_un_numero_4551_suelto_no_es_un_bloqueo():
    assert not hz.es_bloqueo_politica("escuchando en el puerto 14551")
    assert not hz.es_bloqueo_politica("File x.py, line 4551, in cargar")
    assert not hz.es_bloqueo_politica("health en 4551 ms")
    assert hz.es_bloqueo_politica("OSError 4551")
    assert hz.es_bloqueo_politica("código 4551 de Windows")


def test_un_bloqueo_sin_ruta_nombra_el_modulo_y_la_ultima_linea():
    texto = "ImportError: DLL load failed while importing _ffi: bloqueado\n[WinError 4551]\n"
    d = hz.describir_fichero_bloqueado(texto, "import llvmlite.binding")
    assert "import llvmlite.binding" in d and "WinError 4551" in d and "None" not in d
    assert hz.describir_fichero_bloqueado(BLOQUEO, "x").endswith("_multiarray_umath.cp313-win_amd64.pyd")
    assert "sin salida" in hz.describir_fichero_bloqueado("", "x")


# -- ejecución de extremo a extremo con pasos simulados -----------------------------

PASOS = (
    "paso_1_marcar", "paso_2_extraer", "paso_3_marca", "paso_4_arrancar", "paso_5_datos",
    "paso_6_health", "paso_7_rutas", "paso_8_imports", "paso_9_smoke_y_demo",
    "paso_10_apagar", "paso_11_tiempos",
)  # fmt: skip


def _humo(tmp_path, monkeypatch, simulados: dict):
    """Un `Humo` en `tmp_path` cuyos pasos son los de `simulados` (el resto da ok)."""
    real = tmp_path / "real"
    real.mkdir()
    args = hz.build_parser().parse_args(
        [
            "--zip", str(tmp_path / "vigia-0.9.0-win64.zip"),
            "--base", str(tmp_path / "banco"),
            "--carpeta", str(tmp_path / "carpeta"),
            "--salida", str(tmp_path / "salida"),
            "--datos-reales", str(real),
        ]
    )  # fmt: skip
    humo = hz.Humo(args)
    for nombre in PASOS:
        monkeypatch.setattr(humo, nombre, simulados.get(nombre, lambda: {"resumen": "simulado"}))
    return humo


def _estados(informe):
    return {p["id"]: p["estado"] for p in informe["pasos"]}


def test_todo_en_verde_da_codigo_0_y_escribe_el_json(tmp_path, monkeypatch):
    informe = _humo(tmp_path, monkeypatch, {}).ejecutar()
    assert informe["ok"] and hz.codigo_de_salida(informe) == 0
    assert set(_estados(informe).values()) == {"ok"} and len(informe["pasos"]) == 11
    assert Path(informe["json"]).is_file()


def test_un_paso_fallido_da_codigo_1_y_no_detiene_los_demas(tmp_path, monkeypatch):
    def falla():
        raise hz.PasoFallido("health con otra versión")

    informe = _humo(tmp_path, monkeypatch, {"paso_6_health": falla}).ejecutar()
    estados = _estados(informe)
    assert estados["6"] == "FALLA" and estados["7"] == "ok" and estados["11"] == "ok"
    assert not informe["ok"] and hz.codigo_de_salida(informe) == 1


def test_un_paso_omitido_tambien_hace_fallar_el_humo(tmp_path, monkeypatch):
    def omite():
        raise hz.PasoOmitido("no hay carpeta extraída")

    informe = _humo(tmp_path, monkeypatch, {"paso_5_datos": omite}).ejecutar()
    assert _estados(informe)["5"] == "omitido"
    assert not informe["ok"] and hz.codigo_de_salida(informe) == 1


def test_detener_salta_los_pasos_siguientes(tmp_path, monkeypatch):
    def para():
        raise hz.PasoFallido("la marca no llegó", detener=True)

    informe = _humo(tmp_path, monkeypatch, {"paso_3_marca": para}).ejecutar()
    estados = _estados(informe)
    assert estados["3"] == "FALLA"
    assert all(estados[str(n)] == "omitido" for n in range(4, 12))
    assert hz.codigo_de_salida(informe) == 1


def test_el_4551_al_arrancar_el_servidor_da_codigo_2_con_fichero_y_error(tmp_path, monkeypatch):
    humo = None

    def arranca():
        humo._si_bloqueo(BLOQUEO, "arrancar Vigía (frio)")

    humo = _humo(tmp_path, monkeypatch, {"paso_4_arrancar": arranca})
    informe = humo.ejecutar()
    estados = _estados(informe)
    assert estados["4"] == "FALLA" and estados["5"] == "omitido" and estados["11"] == "omitido"
    assert informe["bloqueo_politica"]["fichero"].endswith("_multiarray_umath.cp313-win_amd64.pyd")
    assert "4551" in informe["bloqueo_politica"]["error"]
    assert hz.codigo_de_salida(informe) == 2
    assert "BLOQUEO DE POLÍTICA" in hz.resumen_texto(informe)


def test_un_fallo_cualquiera_cuyo_texto_es_un_4551_se_trata_como_bloqueo(tmp_path, monkeypatch):
    def cae():
        raise RuntimeError("[WinError 4551] Una directiva de Control de aplicaciones bloqueó este archivo")

    informe = _humo(tmp_path, monkeypatch, {"paso_9_smoke_y_demo": cae}).ejecutar()
    assert informe["bloqueo_politica"] is not None
    assert _estados(informe)["10"] == "omitido" and hz.codigo_de_salida(informe) == 2


def test_los_datos_reales_se_comparan_en_el_informe_aunque_el_humo_se_detenga(tmp_path, monkeypatch):
    humo = _humo(tmp_path, monkeypatch, {})
    real = humo.datos_reales

    def toca():
        (real / "nuevo.txt").write_text("x", encoding="utf-8")
        raise hz.PasoFallido("se para", detener=True)

    monkeypatch.setattr(humo, "paso_2_extraer", toca)
    informe = humo.ejecutar()
    assert informe["datos_reales"]["sin_cambios"] is False and not informe["ok"]
    assert informe["datos_reales"]["lock_al_inicio"] is False


def test_el_paso_5_avisa_si_la_carpeta_real_cambio_y_hay_lock(tmp_path, monkeypatch):
    humo = _humo(tmp_path, monkeypatch, {})
    humo.ctx["reales_antes"] = hz.fecha_mas_reciente(humo.datos_reales)
    humo._comprobar_reales("el paso 5")  # sin cambios: no lanza
    (humo.datos_reales / "vigia.lock").write_text("{}", encoding="utf-8")
    with pytest.raises(hz.PasoFallido, match="no es concluyente") as exc:
        humo._comprobar_reales("el paso 5")
    assert exc.value.detalle["concluyente"] is False


def test_limpiar_cierra_el_log_aunque_no_haya_proceso(tmp_path, monkeypatch):
    humo = _humo(tmp_path, monkeypatch, {})
    log = open(tmp_path / "log.txt", "wb")  # noqa: SIM115 - es lo que `limpiar` debe cerrar
    humo.ctx.update(log=log, proceso=None)
    humo.limpiar()
    assert log.closed and humo.ctx["log"] is None


def test_la_espera_por_defecto_aguanta_el_arranque_en_frio_medido():
    # 143 s de arranque en frío medidos en una máquina de desarrollo: el margen es de 2x o más.
    assert hz.build_parser().parse_args(["--zip", "x.zip"]).puerto_max_espera >= 300


# --------------------------------------------------------------------------
# El paso nuevo del 9 (multiclase y regresión por la API)
# --------------------------------------------------------------------------

INFORME_TIPOS = {
    "ok": True,
    "tipos": [
        {"tipo": "multiclase", "ok": True, "segundos": 9.2, "evaluaciones": 3},
        {"tipo": "regresion", "ok": True, "segundos": 1.8, "evaluaciones": 3},
    ],
}


def _proceso(codigo, salida="", error=""):
    return subprocess.CompletedProcess(args=[], returncode=codigo, stdout=salida, stderr=error)


def test_el_parser_acepta_solo_tipos_sin_zip_y_el_humo_completo_lo_exige(capsys):
    args = hz.build_parser().parse_args(["--solo-tipos", "http://127.0.0.1:8906"])
    assert args.zip is None and args.solo_tipos == "http://127.0.0.1:8906"
    assert args.humo_tipos.endswith("humo_tipos.py") and args.espera_tipos >= 300
    with pytest.raises(SystemExit) as salida:
        hz.main([])
    assert salida.value.code == 2
    assert "--zip" in capsys.readouterr().err


def test_solo_tipos_corre_el_paso_con_este_python_y_da_codigo_0_o_1(monkeypatch, capsys):
    llamadas = []

    def falso(cmd, **kw):
        llamadas.append(cmd)
        return _proceso(0, json.dumps(INFORME_TIPOS))

    monkeypatch.setattr(hz.subprocess, "run", falso)
    assert hz.main(["--solo-tipos", "http://127.0.0.1:8906"]) == 0
    assert llamadas[0][0] == hz.sys.executable and llamadas[0][-2:] == ["--url", "http://127.0.0.1:8906"]
    assert "EN VERDE" in capsys.readouterr().out
    malo = {"ok": False, "tipos": [{"tipo": "regresion", "ok": False, "error": "FalloHumo: x"}]}
    monkeypatch.setattr(hz.subprocess, "run", lambda cmd, **kw: _proceso(1, json.dumps(malo)))
    assert hz.main(["--solo-tipos", "http://127.0.0.1:8906"]) == 1
    assert "FALLA" in capsys.readouterr().out


def test_el_paso_9_corre_el_humo_de_tipos_con_el_python_extraido(tmp_path, monkeypatch):
    humo = _humo(tmp_path, monkeypatch, {})
    lanzados = []

    def extraido(argumentos, timeout):
        lanzados.append((argumentos, timeout))
        return _proceso(0, json.dumps(INFORME_TIPOS))

    monkeypatch.setattr(humo, "_ejecutar_extraido", extraido)
    detalle: dict = {}
    informe = humo.humo_tipos("http://127.0.0.1:8123", detalle)
    assert informe["ok"] and detalle["tipos"] == INFORME_TIPOS and detalle["tipos_s"] >= 0
    argumentos, timeout = lanzados[0]
    assert argumentos[0].endswith("humo_tipos.py") and argumentos[-2:] == ["--url", "http://127.0.0.1:8123"]
    assert timeout == float(humo.args.espera_tipos)


def test_el_paso_9_falla_si_un_tipo_falla_y_dice_cual(tmp_path, monkeypatch):
    humo = _humo(tmp_path, monkeypatch, {})
    malo = {"ok": False, "tipos": [{"tipo": "regresion", "ok": False, "error": "FalloHumo: alta"}]}
    monkeypatch.setattr(humo, "_ejecutar_extraido", lambda a, t: _proceso(1, json.dumps(malo)))
    with pytest.raises(hz.PasoFallido, match="regresion FALLA: FalloHumo: alta") as exc:
        humo.humo_tipos("http://127.0.0.1:8123", {})
    assert exc.value.detalle["tipos"] == malo


def test_el_paso_9_sin_salida_json_enseña_el_error_del_proceso(tmp_path, monkeypatch):
    humo = _humo(tmp_path, monkeypatch, {})
    monkeypatch.setattr(humo, "_ejecutar_extraido", lambda a, t: _proceso(1, "", "Traceback: boom"))
    with pytest.raises(hz.PasoFallido, match="boom"):
        humo.humo_tipos("http://127.0.0.1:8123", {})


def test_el_paso_9_trata_un_4551_del_humo_de_tipos_como_bloqueo(tmp_path, monkeypatch):
    humo = _humo(tmp_path, monkeypatch, {})
    texto = r"DLL load failed: error 4551 al cargar C:\x\_ssl.pyd"
    monkeypatch.setattr(humo, "_ejecutar_extraido", lambda a, t: _proceso(1, "", texto))
    with pytest.raises(hz.PasoFallido, match="BLOQUEO DE POLÍTICA") as exc:
        humo.humo_tipos("http://127.0.0.1:8123", {})
    assert exc.value.detener and humo.bloqueo["fichero"].endswith("_ssl.pyd")


def test_el_paso_9_falla_con_el_tiempo_agotado(tmp_path, monkeypatch):
    humo = _humo(tmp_path, monkeypatch, {})

    def agota(a, t):
        raise hz.subprocess.TimeoutExpired(cmd="x", timeout=t)

    monkeypatch.setattr(humo, "_ejecutar_extraido", agota)
    with pytest.raises(hz.PasoFallido, match="tiempo agotado"):
        humo.humo_tipos("http://127.0.0.1:8123", {})


# --------------------------------------------------------------------------
# La versión sale de src/vigia/__init__.py
# --------------------------------------------------------------------------


def _raiz_con_version(destino: Path, version: str) -> Path:
    init = destino / "src" / "vigia" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text(f'"""x"""\n__version__ = "{version}"\n', encoding="utf-8")
    return destino


def test_la_version_esperada_sale_de_init_y_no_de_un_literal(tmp_path, monkeypatch):
    import vigia

    assert hz.version_del_producto() == vigia.__version__
    assert hz.version_del_producto(_raiz_con_version(tmp_path / "otra", "7.8.9")) == "7.8.9"
    # Sin versión en el nombre del zip, el humo espera la del producto.
    humo = _humo(tmp_path, monkeypatch, {})
    assert humo.version_esperada == hz.version_del_zip(humo.zip_origen.name)
    args = hz.build_parser().parse_args(["--zip", str(tmp_path / "otro.zip")])
    assert hz.Humo(args).version_esperada == vigia.__version__


def test_sin_version_en_init_el_humo_lo_dice(tmp_path):
    init = tmp_path / "src" / "vigia" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text('"""sin versión"""\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="__version__"):
        hz.version_del_producto(tmp_path)


def test_cambiar_la_version_cambia_el_nombre_del_zip_el_del_humo_y_el_mensaje_del_commit(
    tmp_path, monkeypatch
):
    """Una sola edición, la de `__init__.py`, mueve las tres salidas."""
    from build import build as bs
    from build import exportar_publico as ep

    raiz = _raiz_con_version(tmp_path / "raiz", "4.5.6")
    for modulo in (bs, ep):
        monkeypatch.setattr(modulo, "REPO_ROOT", raiz)
    assert bs.app_version() == "4.5.6"
    assert bs.dist_zip_name(bs.out_dir_for(bs.app_version(), None)) == "vigia-4.5.6-win64.zip"
    assert hz.version_del_zip("vigia-4.5.6-win64.zip") == hz.version_del_producto(raiz) == "4.5.6"
    assert ep.mensaje_commit() == "Vigía 4.5.6"


# --------------------------------------------------------------------------
# El paso 9 llama al humo de tipos después de la demo
# --------------------------------------------------------------------------


def _paso_9_real(tmp_path, monkeypatch, humo_tipos):
    """Un `Humo` con el `paso_9_smoke_y_demo` verdadero y todo lo externo simulado."""
    humo = _humo(tmp_path, monkeypatch, {})
    monkeypatch.setattr(humo, "paso_9_smoke_y_demo", hz.Humo.paso_9_smoke_y_demo.__get__(humo))
    raiz = tmp_path / "extraido" / "vigia-0.9.0-win64"
    raiz.mkdir(parents=True)
    humo.raiz = raiz
    humo.ctx["base"] = "http://127.0.0.1:8123"
    script = tmp_path / "smoke_ir.py"
    script.write_text("# simulado\n", encoding="utf-8")
    humo.args.smoke_ir = str(script)
    monkeypatch.setattr(humo, "_ejecutar_extraido", lambda a, t: _proceso(0, json.dumps({"ok": True})))
    llamadas = []

    def api_falsa(base, ruta, metodo="GET", cuerpo=None, token=None):
        llamadas.append((ruta, metodo))
        if ruta == "/api/demo/runs":
            return {"id": "r1"}
        if ruta.endswith("/play"):
            return {"id": "j1"}
        return {"id": "j1", "status": "terminado"}

    monkeypatch.setattr(hz, "api", api_falsa)
    monkeypatch.setattr(humo, "humo_tipos", humo_tipos)
    return humo, llamadas


def test_el_paso_9_llama_al_humo_de_tipos_tras_la_demo_y_lo_pone_en_el_resumen(tmp_path, monkeypatch):
    recibidas = []

    def tipos(base, detalle):
        recibidas.append(base)
        detalle["tipos"] = INFORME_TIPOS
        return INFORME_TIPOS

    humo, llamadas = _paso_9_real(tmp_path, monkeypatch, tipos)
    resultado = humo.paso_9_smoke_y_demo()
    assert recibidas == ["http://127.0.0.1:8123"]
    assert llamadas[0][0] == "/api/demo/runs"  # la demo va antes
    assert "multiclase 9.2 s" in resultado["resumen"] and "regresion 1.8 s" in resultado["resumen"]
    assert resultado["detalle"]["tipos"] == INFORME_TIPOS


def test_el_paso_9_falla_si_el_humo_de_tipos_falla(tmp_path, monkeypatch):
    def cae(base, detalle):
        raise hz.PasoFallido("humo de tipos falló", detalle=detalle)

    humo, _ = _paso_9_real(tmp_path, monkeypatch, cae)
    with pytest.raises(hz.PasoFallido, match="humo de tipos"):
        humo.paso_9_smoke_y_demo()


def test_la_version_por_defecto_se_resuelve_al_llamar_y_sigue_a_repo_root(tmp_path, monkeypatch):
    """Cambiar `hz.REPO_ROOT` cambia la versión esperada del humo."""
    monkeypatch.setattr(hz, "REPO_ROOT", _raiz_con_version(tmp_path / "raiz", "4.5.6"))
    assert hz.version_del_producto() == "4.5.6"
    args = hz.build_parser().parse_args(["--zip", str(tmp_path / "otro.zip")])
    assert hz.Humo(args).version_esperada == "4.5.6"
