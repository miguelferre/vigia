"""Empaquetado de Vigia con Python embebido.

Subcomandos: fetch, assemble, measure, zip, all. Solo stdlib + uv en PATH.
No usa pip ni get-pip.py: la instalacion en el runtime embebido se hace con
"uv pip install --target". Ver build/README.md para el flujo completo.

Ejecutar con el Python 3.13 del sistema (el que no está en un venv ni lo
descargó uv):
    python.exe build\\build.py --help
Si ese intérprete no es el que resuelve `sys.base_prefix`, se indica con la
variable de entorno VIGIA_PYTHON_SISTEMA (ruta a su python.exe).
"""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
EMBED_DIR = BUILD_DIR / "embed"
WHEELS_DIR = BUILD_DIR / "wheels"
OUT_DIR = BUILD_DIR / "out"
DIST_DIR = REPO_ROOT / "dist"
FRONTEND_DIR = REPO_ROOT / "frontend"
STATIC_DIR = REPO_ROOT / "src" / "vigia" / "static"

DEFAULT_VERSION = "3.13.12"
EXPECTED_SIZE = 10_941_233  # bytes, python-3.13.12-embed-amd64.zip

# Huella sha256 de cada zip embebido aceptado. Una versión que no está aquí no se acepta.
# La de 3.13.12 coincide con la que publica https://www.python.org/downloads/release/python-31312/
# (consultada el 2026-10-07) y con el zip que ya descargó build.py (tamaño EXPECTED_SIZE).
PYTHON_EMBED_SHA256: dict[str, str] = {
    "3.13.12": "76f238f606250c87c6beac75dccd35ee99070a13490555936abb6cb64ecce3d0",
}
VERSION_PYTHON_RE = re.compile(r"3\.13\.\d{1,3}")

UV_ESPERADO = "0.12.10"  # versión de uv con la que se verificó el build

POLICY_BLOCK_MARKER = "4551"

ENV_PYTHON_SISTEMA = "VIGIA_PYTHON_SISTEMA"
PYTHON_REQUERIDO = (3, 13)
TEMA_PUBLICO = "miguel"


class PolicyBlockError(RuntimeError):
    """El Control de aplicaciones bloqueo un binario (winerror 4551)."""


class SystemPythonError(RuntimeError):
    """No hay un Python 3.13 del sistema utilizable para uv."""


class EstaticoError(RuntimeError):
    """El estático del frontend falta, es de otro tema o está desactualizado."""


# --------------------------------------------------------------------------
# Python del sistema (sin ruta personal)
# --------------------------------------------------------------------------


def candidate_system_python(env: Mapping[str, str], base_prefix: str | Path) -> Path:
    """Elige el python.exe del sistema: la variable de entorno manda; si no, sys.base_prefix.

    `sys.base_prefix` apunta al intérprete base aunque el script se lance desde un venv.
    """
    override = (env.get(ENV_PYTHON_SISTEMA) or "").strip()
    if override:
        return Path(override)
    return Path(base_prefix) / "python.exe"


def parse_python_version(output: str) -> tuple[int, int] | None:
    """Lee 'M.m' (o 'M.m.p') de la salida de `python -c`; None si no tiene esa forma."""
    found = re.search(r"^\s*(\d+)\.(\d+)(?:\.\d+)?\s*$", output)
    return (int(found.group(1)), int(found.group(2))) if found else None


def is_uv_managed(path: Path) -> bool:
    """True si la ruta cuelga de la carpeta de intérpretes que descarga uv."""
    partes = [p.lower() for p in Path(path).parts]
    return any(a == "uv" and b == "python" for a, b in pairwise(partes))


def validate_system_python(path: Path, version: tuple[int, int] | None) -> None:
    """Falla con un mensaje claro si el intérprete no es el 3.13 del sistema."""
    pista = f"Fija la variable {ENV_PYTHON_SISTEMA} a la ruta del python.exe del Python 3.13 del sistema."
    if is_uv_managed(path):
        raise SystemPythonError(
            f"{path} es un intérprete que descargó uv; el Control de aplicaciones lo bloquea. {pista}"
        )
    if version is None:
        raise SystemPythonError(f"No se pudo leer la versión de {path}. {pista}")
    if version != PYTHON_REQUERIDO:
        esperado = ".".join(map(str, PYTHON_REQUERIDO))
        leido = ".".join(map(str, version))
        raise SystemPythonError(f"{path} es Python {leido}; se necesita {esperado}. {pista}")


_SYSTEM_PYTHON_CACHE: Path | None = None


def system_python() -> Path:
    """python.exe 3.13 del sistema, comprobado una vez por proceso."""
    global _SYSTEM_PYTHON_CACHE
    if _SYSTEM_PYTHON_CACHE is not None:
        return _SYSTEM_PYTHON_CACHE
    path = candidate_system_python(os.environ, sys.base_prefix)
    if not path.is_file():
        raise SystemPythonError(
            f"No existe {path}. Fija la variable {ENV_PYTHON_SISTEMA} a la ruta del "
            "python.exe del Python 3.13 del sistema."
        )
    try:
        proc = subprocess.run(
            [str(path), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        salida = proc.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemPythonError(f"No se pudo ejecutar {path}: {exc}") from exc
    validate_system_python(path, parse_python_version(salida))
    _SYSTEM_PYTHON_CACHE = path
    return path


def validar_version_python(version: str) -> str:
    """Devuelve la versión si tiene la forma 3.13.N; ValueError si no (va a una URL y a una ruta)."""
    if not isinstance(version, str) or not VERSION_PYTHON_RE.fullmatch(version):
        raise ValueError(f"versión de Python no válida: {version!r}; se espera 3.13.N")
    return version


def _version_argumento(texto: str) -> str:
    try:
        return validar_version_python(texto)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def embed_zip_name(version: str) -> str:
    return f"python-{validar_version_python(version)}-embed-amd64.zip"


def embed_url(version: str) -> str:
    return f"https://www.python.org/ftp/python/{version}/{embed_zip_name(version)}"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verificar_embed(zip_path: Path, version: str) -> str | None:
    """None si el zip embebido tiene la huella fijada para esa versión; si no, el motivo."""
    esperada = PYTHON_EMBED_SHA256.get(version)
    if not esperada:
        return (
            f"no hay huella sha256 fijada para Python {version}: añádela a "
            "PYTHON_EMBED_SHA256 tras comprobarla en python.org"
        )
    digest = sha256_of(zip_path)
    if digest != esperada:
        return f"el sha256 de {zip_path.name} es {digest}, no el fijado {esperada}"
    return None


def aviso_version_uv(salida: str) -> str | None:
    """None si `uv --version` dice la versión esperada; si no, el aviso."""
    leida = re.match(r"\s*uv\s+(\S+)", salida)
    if leida and leida.group(1) == UV_ESPERADO:
        return None
    return (
        f"uv no es la versión verificada: se esperaba {UV_ESPERADO} y dice "
        f"{(salida.strip() or 'nada')!r}"
    )


def comprobar_uv() -> str | None:
    """Lanza `uv --version`, avisa por stderr si no es la esperada y devuelve el aviso."""
    try:
        proc = subprocess.run(
            ["uv", "--version"], capture_output=True, text=True, check=False, timeout=30
        )
        aviso = aviso_version_uv(proc.stdout or "")
    except (OSError, subprocess.SubprocessError) as exc:
        aviso = f"no se pudo ejecutar uv --version: {exc}"
    if aviso:
        print(f"aviso: {aviso}", file=sys.stderr)
    return aviso


def is_policy_block(output: str) -> bool:
    """True si la salida de un subproceso indica bloqueo del Control de aplicaciones."""
    lowered = output.lower()
    return POLICY_BLOCK_MARKER in output or "directiva de control de aplicaciones" in lowered


def run_uv(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Lanza uv con UV_PYTHON fijado al 3.13 del sistema y sin descargas de uv."""
    env = os.environ.copy()
    env["UV_PYTHON"] = str(system_python())
    env["UV_PYTHON_DOWNLOADS"] = "never"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        ["uv", *args],
        cwd=str(cwd or REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        if is_policy_block(combined):
            raise PolicyBlockError(f"uv {' '.join(args)} bloqueado por politica:\n{combined}")
        raise RuntimeError(f"uv {' '.join(args)} fallo (codigo {proc.returncode}):\n{combined}")
    return proc


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------


def cmd_fetch(args: argparse.Namespace) -> int:
    version = args.version
    try:
        validar_version_python(version)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    dest = EMBED_DIR / embed_zip_name(version)
    url = embed_url(version)

    if dest.exists():
        print(f"ya existe: {dest} ({dest.stat().st_size} bytes), no se descarga de nuevo")
    else:
        print(f"descargando {url} -> {dest}")
        try:
            urllib.request.urlretrieve(url, dest)
        except urllib.error.URLError as exc:
            print(f"error de red descargando el zip embebido: {exc}", file=sys.stderr)
            return 1

    size = dest.stat().st_size
    if version == DEFAULT_VERSION and size != EXPECTED_SIZE:
        print(
            f"aviso: tamano {size} no coincide con el esperado {EXPECTED_SIZE} "
            "para 3.13.12 (release distinta o descarga corrupta)",
            file=sys.stderr,
        )

    if not zipfile.is_zipfile(dest):
        print(f"error: {dest} no es un zip valido", file=sys.stderr)
        return 1

    digest = sha256_of(dest)
    print(f"sha256: {digest}")
    print(f"tamano: {size} bytes")
    problema = verificar_embed(dest, version)
    if problema:
        print(f"error: {problema}", file=sys.stderr)
        return 1
    return 0


# --------------------------------------------------------------------------
# assemble: funciones puras (testeadas en seco, sin red)
# --------------------------------------------------------------------------


def patch_pth_content(original: str) -> str:
    r"""Devuelve el contenido editado de python313._pth para el runtime embebido.

    Anade r'Lib\site-packages' como ruta de busqueda y descomenta 'import site' (el
    embebido lo trae comentado por defecto). Ninguna ruta externa al runtime: el
    codigo vive solo en site-packages.
    """
    lines = original.splitlines()
    out: list[str] = []
    has_site_packages = any(l.strip() == r"Lib\site-packages" for l in lines)
    for line in lines:
        if line.strip() == r"..\app":
            continue
        if line.strip() == "#import site":
            out.append("import site")
        else:
            out.append(line)
    if not has_site_packages:
        out.append(r"Lib\site-packages")
    if not any(l.strip() == "import site" for l in out):
        out.append("import site")
    return "\n".join(out) + "\n"


def extras_del_paquete(with_shap: bool, con_parquet: bool) -> list[str]:
    """Extras de pyproject.toml que entran en el paquete.

    SHAP entra por defecto. Parquet no entra salvo con --con-parquet: el
    extra pesa 82 MB y está bloqueado en esta máquina.
    """
    extras: list[str] = []
    if with_shap:
        extras.append("shap")
    if con_parquet:
        extras.append("parquet")
    return extras


def uv_export_command(
    out_requirements: Path, with_shap: bool, con_parquet: bool = False
) -> list[str]:
    """Compone los argumentos de 'uv export' para el requirements.txt del paquete."""
    args = [
        "export",
        "--format",
        "requirements-txt",
        "--no-dev",
        "--no-emit-project",
        "--no-editable",
        "--locked",  # el lock manda: si no coincide con pyproject.toml, falla en vez de recalcular
    ]
    for extra in extras_del_paquete(with_shap, con_parquet):
        args += ["--extra", extra]
    args += ["-o", str(out_requirements)]
    return args


def uv_build_wheel_command(project_dir: Path, out_dir: Path) -> list[str]:
    return ["build", "--wheel", "--out-dir", str(out_dir), str(project_dir)]


def filter_local_requirements(text: str) -> tuple[str, list[str]]:
    """Quita del requirements.txt exportado las dependencias de ruta local.

    'uv export --no-editable' emite las dependencias de ruta local como ruta
    relativa cruda. Esas lineas se descartan: el wheel local se instala aparte,
    con --no-deps.
    Devuelve (texto filtrado, lineas descartadas).
    """
    kept: list[str] = []
    dropped: list[str] = []
    for line in text.splitlines():
        req = line.split("#", 1)[0].split(";", 1)[0].strip()
        local_prefixes = ("-e", ".", "/", "\\", "file:")
        is_local = req.startswith(local_prefixes) or bool(re.match(r"^[A-Za-z]:[\\/]", req))
        (dropped if is_local else kept).append(line)
    return "\n".join(kept) + "\n", dropped


def variantes_de_ruta(*rutas: Path | str) -> list[str]:
    """Formas en que una ruta de la máquina puede quedar escrita en un fichero, en minúsculas."""
    formas: set[str] = set()
    for ruta in rutas:
        texto = str(ruta).rstrip("\\/")
        if not texto:
            continue
        posix = texto.replace("\\", "/")
        formas.update({texto, posix, texto.replace("\\", "\\\\")})
    return sorted(f.lower() for f in formas)


def quitar_rutas_de_requirements(text: str, rutas: Iterable[Path | str]) -> str:
    """Quita del requirements.txt las líneas de comentario con la orden de uv o una ruta de la máquina."""
    formas = variantes_de_ruta(*rutas)
    kept: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            bajo = line.lower()
            if "uv export" in bajo or any(f in bajo for f in formas):
                continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def limpiar_paquete(out_dir: Path, rutas: Iterable[Path | str]) -> list[str]:
    """Quita del paquete lo que lleva la ruta de la máquina de compilación.

    - `Lib/site-packages/bin`: lanzadores .exe con la ruta del intérprete; el zip arranca con
      `Vigia.cmd` y `python -m vigia`.
    - `direct_url.json` de cada dist-info (guarda la ruta del wheel local) y su línea de RECORD.
    - `__pycache__`: los .pyc guardan la ruta de origen.
    - Comentarios de `requirements.txt` con la orden de uv y sus rutas.
    Devuelve lo quitado, relativo al paquete.
    """
    out_dir = Path(out_dir)
    quitado: list[str] = []
    site_packages = out_dir / "runtime" / "python" / "Lib" / "site-packages"
    bin_dir = site_packages / "bin"
    if bin_dir.is_dir():
        shutil.rmtree(bin_dir)
        quitado.append(bin_dir.relative_to(out_dir).as_posix() + "/")
    if site_packages.is_dir():
        for dist in site_packages.glob("*.dist-info"):
            url = dist / "direct_url.json"
            if url.is_file():
                url.unlink()
                quitado.append(url.relative_to(out_dir).as_posix())
            record = dist / "RECORD"
            if record.is_file():
                lineas = record.read_text(encoding="utf-8").splitlines()
                limpias = [
                    ln
                    for ln in lineas
                    if not re.match(r"^(\.\./)+bin/", ln) and not ln.startswith(
                        (f"{dist.name}/direct_url.json,", "direct_url.json,")
                    )
                ]
                if limpias != lineas:
                    record.write_text("\n".join(limpias) + "\n", encoding="utf-8")
    for cache in sorted(out_dir.rglob("__pycache__")):
        if cache.is_dir():
            shutil.rmtree(cache)
            quitado.append(cache.relative_to(out_dir).as_posix() + "/")
    requirements = out_dir / "requirements.txt"
    if requirements.is_file():
        original = requirements.read_text(encoding="utf-8")
        limpio = quitar_rutas_de_requirements(original, rutas)
        if limpio != original:
            requirements.write_text(limpio, encoding="utf-8")
            quitado.append("requirements.txt (comentarios con rutas)")
    return quitado


def buscar_rutas_en_paquete(out_dir: Path, rutas: Iterable[Path | str]) -> list[str]:
    """Ficheros del paquete (texto o binario) que contienen alguna ruta de la máquina; sin distinguir mayúsculas."""
    agujas = [f.encode("utf-8") for f in variantes_de_ruta(*rutas)]
    if not agujas:
        return []
    solape = max(len(a) for a in agujas)
    halladas: list[str] = []
    out_dir = Path(out_dir)
    for fichero in sorted(p for p in out_dir.rglob("*") if p.is_file()):
        cola = b""
        try:
            with open(fichero, "rb") as f:
                while True:
                    trozo = f.read(8 * 1024 * 1024)
                    if not trozo:
                        break
                    bloque = (cola + trozo).lower()
                    if any(a in bloque for a in agujas):
                        halladas.append(fichero.relative_to(out_dir).as_posix())
                        break
                    cola = bloque[-solape:]
        except OSError:
            continue
    return halladas


# Lista blanca del paquete: lo que `assemble` deja en `out_dir`.
PAQUETE_RAIZ = frozenset(
    {
        "runtime",
        "docs",
        "Vigia.cmd",
        "Vigia-consola.cmd",
        "LEEME.txt",
        "README.md",
        "SEGURIDAD.md",
        "build",
        "LICENSE",
        "NOTICE",
        "TERCEROS.txt",
        "requirements.txt",
    }
)
PAQUETE_DOCS_EXT = frozenset({".md", ".png", ".svg", ".jpg", ".html", ".css", ".txt", ".json"})
# Documentos sueltos que enlaza el README: viajan en la misma ruta que en el repositorio.
DOCS_SUELTOS = ("docs/mcp.md", "docs/api/formatos.md", "docs/api/openapi.json", "build/README.md")
# Datos locales que no deben viajar en ninguna parte del paquete.
PAQUETE_PROHIBIDO_SUFIJOS = (".db", ".env", ".privado.csv", ".log")
# Además, en el código propio (no en los datos de prueba de terceros).
PAQUETE_PROHIBIDO_PROPIO = PAQUETE_PROHIBIDO_SUFIJOS + (".pkl", ".joblib")
PAQUETE_PROPIO = ("vigia",)


def comprobar_contenido_paquete(out_dir: Path, rutas: Iterable[Path | str] = ()) -> list[str]:
    """Problemas del contenido de `out_dir` frente a la lista blanca; vacío si es el esperado.

    - Solo las entradas de `PAQUETE_RAIZ` en la raíz; en `docs/` solo `manual/` con
      extensiones de documentación.
    - Ningún `*.db`, `*.env`, `*.privado.csv` ni `*.log` en todo el paquete; `*.pkl` y
      `*.joblib` tampoco en el código propio (los datos de prueba de terceros los llevan).
    - La ruta de la máquina o del usuario de compilación (`rutas`) no aparece en lo propio:
      ficheros de la raíz, `docs/` y el código de Vigía en site-packages.
    """
    out_dir = Path(out_dir)
    problemas: list[str] = []
    site = out_dir / "runtime" / "python" / "Lib" / "site-packages"
    propios: list[Path] = []
    for fichero in sorted(p for p in out_dir.rglob("*") if p.is_file()):
        rel = fichero.relative_to(out_dir).as_posix()
        partes = rel.split("/")
        nombre = partes[-1].lower()
        if partes[0] not in PAQUETE_RAIZ:
            problemas.append(f"{rel}: fuera de la lista blanca del paquete")
            continue
        if partes[0] in ("docs", "build") and not (
            rel in DOCS_SUELTOS
            or (
                len(partes) >= 3
                and partes[1] == "manual"
                and fichero.suffix.lower() in PAQUETE_DOCS_EXT
            )
        ):
            problemas.append(f"{rel}: fuera de la lista blanca de docs/")
            continue
        es_propio = len(partes) == 1 or partes[0] in ("docs", "build")
        if fichero.is_relative_to(site) and fichero.relative_to(site).parts[0] in PAQUETE_PROPIO:
            es_propio = True
            prohibidos = PAQUETE_PROHIBIDO_PROPIO
        else:
            prohibidos = PAQUETE_PROHIBIDO_SUFIJOS
        if nombre == ".env" or nombre.endswith(prohibidos):
            problemas.append(
                f"{rel}: dato local que no debe viajar en el paquete "
                "(lista en PAQUETE_PROHIBIDO_SUFIJOS de build/build.py)"
            )
            continue
        if es_propio:
            propios.append(fichero)
    agujas = [f.encode("utf-8") for f in variantes_de_ruta(*rutas)]
    for fichero in propios:
        try:
            datos = fichero.read_bytes().lower()
        except OSError:
            continue
        if any(a in datos for a in agujas):
            rel = fichero.relative_to(out_dir).as_posix()
            problemas.append(f"{rel}: lleva la ruta de la máquina o del usuario de compilación")
    return problemas


def rutas_de_la_maquina(out_dir: Path) -> list[Path]:
    """Rutas de la máquina de compilación que no deben viajar en el paquete."""
    return [REPO_ROOT, Path(out_dir).resolve()]


def uv_pip_install_command(
    target_python: Path,
    site_packages: Path,
    requirements: Path | None = None,
    wheel_paths: list[str] | None = None,
    no_deps: bool = False,
) -> list[str]:
    """Compone 'uv pip install' con los .whl ya expandidos (Windows no expande globs)."""
    args = ["pip", "install", "--python", str(target_python), "--target", str(site_packages)]
    if no_deps:
        args.append("--no-deps")
    if requirements is not None:
        args += ["-r", str(requirements)]
    args += list(wheel_paths or [])
    return args


def app_version() -> str:
    """Versión de Vigía leída de src/vigia/__init__.py (no la de Python)."""
    init = (REPO_ROOT / "src" / "vigia" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    return found.group(1) if found else "0.0.0"


def variant_suffix(with_shap: bool, con_parquet: bool) -> str:
    """Sufijo del nombre: vacío para el paquete de siempre (con SHAP, sin Parquet)."""
    return ("" if with_shap else "-sin-shap") + ("-con-parquet" if con_parquet else "")


def out_dir_for(
    version: str,
    out_override: str | None,
    with_shap: bool = True,
    con_parquet: bool = False,
    tema: str = TEMA_PUBLICO,
) -> Path:
    """Directorio del paquete: build/out/vigia-<versión>[-<tema>]-win64 (un solo zip).

    El tema solo entra en el nombre si no es el público.
    """
    if out_override:
        return Path(out_override)
    sufijo_tema = "" if tema == TEMA_PUBLICO else f"-{tema}"
    return OUT_DIR / f"vigia-{version}{sufijo_tema}-win64{variant_suffix(with_shap, con_parquet)}"


_TEMA_VALIDO = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def tema_argumento(valor: str) -> str:
    """Nombre de una estética para `--tema`: el público o un tema único del repo de trabajo."""
    if not _TEMA_VALIDO.match(valor) or valor == "todos":
        raise argparse.ArgumentTypeError(f"tema no válido: {valor!r}")
    return valor


def read_cmd_template(name: str) -> str:
    path = BUILD_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --------------------------------------------------------------------------
# wheel de Vigía: una carpeta nueva y un solo wheel (C5)
# --------------------------------------------------------------------------


def wheels_dir_for(out_dir: Path) -> Path:
    """Carpeta de wheels propia de este paquete: build/wheels/<nombre del paquete>."""
    return WHEELS_DIR / Path(out_dir).name


def select_vigia_wheel(candidates: Iterable[Path | str], version: str) -> Path:
    """Devuelve el único wheel de Vigía de esa versión; falla si hay otro o ninguno.

    Evita instalar un wheel viejo que haya quedado en la carpeta de wheels.
    """
    wheels = sorted(Path(c) for c in candidates)
    if len(wheels) != 1:
        nombres = ", ".join(w.name for w in wheels) or "ninguno"
        raise RuntimeError(f"se esperaba un solo wheel de vigia {version}; hay: {nombres}")
    wheel = wheels[0]
    if not wheel.name.startswith(f"vigia-{version}-") or wheel.suffix != ".whl":
        raise RuntimeError(f"el wheel {wheel.name} no es de vigia {version}")
    return wheel


PRIVADOS_FILE = BUILD_DIR / "publico" / "privados.txt"


def rutas_privadas_en_wheel(wheel_names: Iterable[str], privados_text: str) -> list[str]:
    """Rutas de privados.txt (bajo src/) que el wheel lleva dentro; lista vacía si ninguna.

    La estética privada no viaja en el wheel ni en el zip. Las rutas de
    `privados.txt` son del repo (`src/vigia/...`); en el wheel cuelgan de `vigia/...`.
    """
    nombres = {n.replace("\\", "/") for n in wheel_names}
    halladas: list[str] = []
    for linea in privados_text.splitlines():
        ruta = linea.strip().replace("\\", "/")
        if not ruta or ruta.startswith("#") or not ruta.startswith("src/"):
            continue
        en_wheel = ruta[len("src/") :]
        if en_wheel in nombres:
            halladas.append(ruta)
    return halladas


ENV_EXIGIR_PRIVADOS = "VIGIA_EXIGIR_PRIVADOS"


def privados_exigidos(env: Mapping[str, str] | None = None) -> bool:
    """True si la variable `VIGIA_EXIGIR_PRIVADOS` pide la lista (1, true, si, yes)."""
    valor = (os.environ if env is None else env).get(ENV_EXIGIR_PRIVADOS, "")
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes"}


def comprobar_wheel_sin_privados(wheel: Path, exigir: bool | None = None) -> list[str]:
    """Aplica `rutas_privadas_en_wheel` al wheel.

    En el árbol público no hay lista y no hay nada que comprobar. Con `exigir` (o la
    variable `VIGIA_EXIGIR_PRIVADOS`) la lista es obligatoria: un renombrado de
    `privados.txt` en el árbol de trabajo no apaga la comprobación.
    """
    if not PRIVADOS_FILE.is_file():
        if exigir or (exigir is None and privados_exigidos()):
            raise FileNotFoundError(
                f"falta {PRIVADOS_FILE}: se exigió la lista de privados y la comprobación "
                "del wheel no puede hacerse"
            )
        return []
    with zipfile.ZipFile(wheel) as zf:
        return rutas_privadas_en_wheel(zf.namelist(), PRIVADOS_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# estático del frontend
# --------------------------------------------------------------------------

_META_TEMA = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)


def tema_del_estatico(index_html: str) -> str | None:
    """Valor de <meta name="vigia-tema" content="..."> en cualquier orden de atributos."""
    for tag in _META_TEMA.findall(index_html):
        nombre = re.search(r'\bname\s*=\s*["\']([^"\']*)["\']', tag)
        if nombre and nombre.group(1) == "vigia-tema":
            contenido = re.search(r'\bcontent\s*=\s*["\']([^"\']*)["\']', tag)
            return contenido.group(1) if contenido else None
    return None


def verificar_estatico(
    index_html: str | None,
    index_mtime: float | None,
    ultimo_commit_frontend: int | None,
    tema_esperado: str = TEMA_PUBLICO,
) -> list[str]:
    """Problemas del estático: lista vacía si es válido.

    - `index_html` None: no existe `src/vigia/static/index.html`.
    - Sin marca del tema o con otro tema que `tema_esperado`.
    - Más viejo que el último commit que toca `frontend/` (se salta si no hay git).
    """
    if index_html is None:
        return ["falta src/vigia/static/index.html: compila el frontend (npm run build)"]
    problemas: list[str] = []
    tema = tema_del_estatico(index_html)
    if tema is None:
        problemas.append('index.html no lleva <meta name="vigia-tema">: se compiló sin la marca')
    elif tema != tema_esperado:
        problemas.append(f"index.html se compiló con VITE_TEMA={tema!r}, no {tema_esperado!r}")
    if (
        ultimo_commit_frontend is not None
        and index_mtime is not None
        and index_mtime < ultimo_commit_frontend
    ):
        problemas.append(
            "index.html es más viejo que el último commit de frontend/: vuelve a compilar"
        )
    return problemas


def ultimo_commit_frontend(repo_root: Path = REPO_ROOT) -> int | None:
    """Marca de tiempo (s) del último commit que toca frontend/; None si git no responde."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", "frontend"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    salida = (proc.stdout or "").strip()
    return int(salida) if proc.returncode == 0 and salida.isdigit() else None


def comprobar_estatico(static_dir: Path | None = None, tema: str = TEMA_PUBLICO) -> list[str]:
    """Aplica `verificar_estatico` al disco (por defecto, src/vigia/static)."""
    index = (static_dir or STATIC_DIR) / "index.html"
    if not index.is_file():
        return verificar_estatico(None, None, None, tema)
    commit = ultimo_commit_frontend()
    if commit is None:
        print("aviso: git no responde; no se comprueba la edad del estático", file=sys.stderr)
    return verificar_estatico(
        index.read_text(encoding="utf-8", errors="replace"), index.stat().st_mtime, commit, tema
    )


def npm_command() -> list[str]:
    """`npm run build` (npm.cmd en Windows, que subprocess no resuelve como `npm`)."""
    return ["npm.cmd" if os.name == "nt" else "npm", "run", "build"]


def npm_ci_command() -> list[str]:
    """`npm ci --ignore-scripts`: instala lo que fija el lock, sin ejecutar scripts de paquetes."""
    return ["npm.cmd" if os.name == "nt" else "npm", "ci", "--ignore-scripts"]


def compile_frontend(instalar: bool = True, tema: str = TEMA_PUBLICO) -> None:
    """Compila el frontend con VITE_TEMA=<tema>; deja el estático en src/vigia/static.

    Antes instala con `npm ci --ignore-scripts` (salvo `instalar=False`), para no compilar
    sobre un `node_modules` que no coincide con el lock.
    """
    env = os.environ.copy()
    env["VITE_TEMA"] = tema
    if instalar:
        print(f"{' '.join(npm_ci_command())}  (frontend/)")
        proc = subprocess.run(
            npm_ci_command(),
            cwd=str(FRONTEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise EstaticoError(
                f"npm ci falló (código {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
            )
    print(f"{' '.join(npm_command())}  (frontend/, VITE_TEMA={tema})")
    proc = subprocess.run(
        npm_command(),
        cwd=str(FRONTEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise EstaticoError(
            f"npm run build falló (código {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
        )


def preparar_estatico(sin_npm: bool, sin_npm_ci: bool = False, tema: str = TEMA_PUBLICO) -> None:
    """Compila (salvo --sin-npm) y exige un estático válido; falla con el motivo."""
    if not sin_npm:
        compile_frontend(instalar=not sin_npm_ci, tema=tema)
    problemas = comprobar_estatico(tema=tema)
    if problemas:
        raise EstaticoError("estático no válido:\n  - " + "\n  - ".join(problemas))


# --------------------------------------------------------------------------
# licencias de terceros y manifiesto
# --------------------------------------------------------------------------

NO_DECLARADA = "no declarada en los metadatos"
_LICENCIA_LARGA = 120


def licencia_de_metadatos(metadata_text: str) -> tuple[str, str, str, list[str]]:
    """Lee (nombre, versión, licencia, ficheros de licencia) de un METADATA de dist-info.

    Orden: License-Expression; License de una sola línea corta; clasificadores
    `License ::`; si solo hay un texto largo, su primera línea entre comillas. Si no hay
    nada, "no declarada en los metadatos". No se deduce nada que el paquete no diga.
    """
    msg = email.parser.Parser().parsestr(metadata_text)
    nombre = (msg.get("Name") or "").strip()
    version = (msg.get("Version") or "").strip()
    expresion = (msg.get("License-Expression") or "").strip()
    licencia = " ".join((msg.get("License") or "").split())
    clasificadores = [
        c.split("::")[-1].strip()
        for c in msg.get_all("Classifier") or []
        if c.strip().startswith("License ::")
    ]
    ficheros = [f.strip() for f in msg.get_all("License-File") or [] if f.strip()]
    if expresion:
        texto = expresion
    elif licencia and "\n" not in (msg.get("License") or "").strip() and (
        len(licencia) <= _LICENCIA_LARGA
    ):
        texto = licencia
    elif clasificadores:
        texto = " / ".join(clasificadores)
    elif licencia:
        texto = f"texto de licencia en los metadatos, empieza: «{licencia[:60]}»"
    else:
        texto = NO_DECLARADA
    return nombre, version, texto, ficheros


def leer_distribuciones(site_packages: Path) -> list[dict]:
    """Una entrada por *.dist-info de site-packages: nombre, versión, licencia y ficheros."""
    resultado: list[dict] = []
    if not site_packages.is_dir():
        return resultado
    for dist in sorted(site_packages.glob("*.dist-info"), key=lambda p: p.name.lower()):
        metadata = dist / "METADATA"
        if not dist.is_dir() or not metadata.is_file():
            continue
        nombre, version, licencia, ficheros = licencia_de_metadatos(
            metadata.read_text(encoding="utf-8", errors="replace")
        )
        if not ficheros:
            carpeta = dist / "licenses"
            if carpeta.is_dir():
                ficheros = sorted(p.relative_to(carpeta).as_posix() for p in carpeta.rglob("*") if p.is_file())
        resultado.append(
            {
                "nombre": nombre or dist.name.split("-")[0],
                "version": version,
                "licencia": licencia,
                "ficheros": ficheros,
            }
        )
    return resultado


def generar_terceros(
    distribuciones: Sequence[Mapping],
    python_version: str,
    python_license_text: str | None,
    vigia_version: str,
) -> str:
    """Texto de TERCEROS.txt: cada dependencia con versión y licencia, y la de Python."""
    sin_declarar = sum(1 for d in distribuciones if d["licencia"] == NO_DECLARADA)
    lineas = [
        f"Vigía {vigia_version}: componentes de terceros que lleva este paquete",
        "",
        "Las licencias se leen de los metadatos de cada distribución instalada en",
        r"runtime\python\Lib\site-packages (ficheros METADATA). Donde el paquete no",
        f"declara licencia, dice «{NO_DECLARADA}».",
        "Los textos completos están en la carpeta dist-info de cada paquete, junto a",
        "los ficheros que se nombran aquí.",
        "",
        f"Distribuciones: {len(distribuciones)}. Sin licencia declarada: {sin_declarar}.",
        "",
        "Distribución | Versión | Licencia | Ficheros de licencia",
        "-------------|---------|----------|---------------------",
    ]
    for d in sorted(distribuciones, key=lambda x: x["nombre"].lower()):
        ficheros = ", ".join(d["ficheros"]) if d["ficheros"] else "(ninguno nombrado)"
        lineas.append(f"{d['nombre']} | {d['version']} | {d['licencia']} | {ficheros}")
    lineas += ["", f"Python embebido {python_version} (python.org, Python Software Foundation)", ""]
    if python_license_text:
        lineas += [
            r"Licencia de Python, copiada de LICENSE.txt del zip embebido (runtime\python\LICENSE.txt):",
            "",
            python_license_text.strip(),
        ]
    else:
        lineas.append(
            "El zip embebido no trae LICENSE.txt: la licencia de Python está en "
            "https://docs.python.org/3/license.html"
        )
    return "\n".join(lineas) + "\n"


def sha256_file_text(digest: str, zip_name: str) -> str:
    """Línea de `.sha256` en el formato de sha256sum: '<huella> *<nombre>'."""
    return f"{digest} *{zip_name}\n"


def manifiesto_texto(
    zip_name: str,
    digest: str,
    entries: Sequence[tuple[str, int]],
    distribuciones: Sequence[Mapping],
    vigia_version: str,
    python_version: str,
) -> str:
    """Texto de <zip>.MANIFIESTO.txt: ficheros con tamaño y versión de cada paquete."""
    total = sum(size for _, size in entries)
    lineas = [
        f"Manifiesto de {zip_name}",
        f"Vigía {vigia_version}; Python embebido {python_version}",
        f"sha256 del zip: {digest}",
        f"Ficheros: {len(entries)}; tamaño descomprimido: {total} bytes",
        "",
        "Paquetes (distribución y versión)",
        "---------------------------------",
    ]
    lineas += [
        f"{d['nombre']} {d['version']}"
        for d in sorted(distribuciones, key=lambda x: x["nombre"].lower())
    ]
    lineas += ["", "Ficheros (ruta; bytes)", "----------------------"]
    lineas += [f"{name}; {size}" for name, size in sorted(entries)]
    return "\n".join(lineas) + "\n"


def entradas_del_zip(zip_path: Path) -> list[tuple[str, int]]:
    """(ruta, tamaño) de cada fichero del zip, sin las carpetas."""
    with zipfile.ZipFile(zip_path) as zf:
        return [(i.filename, i.file_size) for i in zf.infolist() if not i.is_dir()]


# --------------------------------------------------------------------------
# documentación y LEEME dentro del paquete
# --------------------------------------------------------------------------

DOCS_EN_PAQUETE = ("README.md", "SEGURIDAD.md", "LICENSE", "NOTICE")


def copiar_documentacion(repo_root: Path, out_dir: Path) -> list[str]:
    """Copia README.md, SEGURIDAD.md, LICENSE, NOTICE, docs/manual/ (con img/) y los
    documentos que enlaza el README (`DOCS_SUELTOS`) al paquete.

    Falla si falta cualquiera: un zip sin licencia o sin manual no se entrega.
    Devuelve las rutas copiadas, relativas al paquete.
    """
    copiados: list[str] = []
    for nombre in DOCS_EN_PAQUETE:
        origen = repo_root / nombre
        if not origen.is_file():
            raise FileNotFoundError(f"falta {origen}: el paquete lo necesita")
        shutil.copy2(origen, out_dir / nombre)
        copiados.append(nombre)
    manual = repo_root / "docs" / "manual"
    if not manual.is_dir():
        raise FileNotFoundError(f"falta {manual}: el paquete lo necesita")
    destino = out_dir / "docs" / "manual"
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(manual, destino)
    copiados.append("docs/manual/")
    for rel in DOCS_SUELTOS:
        origen = repo_root / rel
        if not origen.is_file():
            raise FileNotFoundError(f"falta {origen}: el README lo enlaza")
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, out_dir / rel)
        copiados.append(rel)
    return copiados


def leeme_text(vigia_version: str, python_version: str) -> str:
    """LEEME.txt: versión de Vigía y, aparte, la de Python embebido; arranque y apagado."""
    return (
        f"Vigía {vigia_version} - paquete para Windows\n"
        f"Python embebido: {python_version} (de python.org, firmado por la PSF)\n"
        "\n"
        "Cómo se arranca\n"
        "  Doble clic en Vigia.cmd. Abre el navegador solo, sin ventana de consola.\n"
        "  Vigia-consola.cmd hace lo mismo y deja una consola con el registro.\n"
        "  La primera vez tarda más: Windows escanea los ficheros nuevos.\n"
        "\n"
        "Cómo se apaga\n"
        "  La interfaz no tiene botón de apagado.\n"
        "  - Con Vigia-consola.cmd: cierra su ventana. Con Ctrl+C, si Windows pregunta si\n"
        "    quieres terminar el trabajo por lotes, responde S.\n"
        "  - Con Vigia.cmd no hay ventana. Abre una consola en esta carpeta y escribe:\n"
        "      runtime\\python\\python.exe -m vigia shutdown\n"
        "    Si usaste otra carpeta de datos, añade --data-dir <carpeta>.\n"
        "\n"
        "Tus datos\n"
        "  Carpeta por defecto: Documents\\vigia-datos, dentro de tu carpeta de usuario.\n"
        "  Para otra carpeta: Vigia.cmd <carpeta>, o la variable de entorno VIGIA_HOME.\n"
        "  Los datos de la demostración son sintéticos, nunca datos reales de personas.\n"
        "\n"
        "Revisión del dossier con modelo\n"
        "  Pide una clave de API (Ajustes). Sin clave, esa revisión no corre y el resto\n"
        "  de Vigía funciona entero.\n"
        "\n"
        "Qué leer\n"
        "  README.md, SEGURIDAD.md y docs\\manual\\ (instalación, uso, datos y qué hacer\n"
        "  si algo falla).\n"
        "  LICENSE (MIT), NOTICE y TERCEROS.txt (licencias de las dependencias y de Python).\n"
    )


# --------------------------------------------------------------------------
# assemble: orquestacion (con red/subprocesos)
# --------------------------------------------------------------------------


def cmd_assemble(args: argparse.Namespace) -> int:
    version = args.version
    with_shap = args.with_shap
    try:
        validar_version_python(version)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    zip_path = EMBED_DIR / embed_zip_name(version)
    if not zip_path.exists():
        print(f"error: no existe {zip_path}; ejecuta 'fetch' primero", file=sys.stderr)
        return 1
    problema_embed = verificar_embed(zip_path, version)
    if problema_embed:
        print(f"error: {problema_embed}", file=sys.stderr)
        return 1

    con_parquet = args.con_parquet
    vigia_version = app_version()
    tema = getattr(args, "tema", TEMA_PUBLICO)
    out_dir = out_dir_for(vigia_version, args.out, with_shap, con_parquet, tema)

    # Falla pronto: Python 3.13 del sistema y estático válido antes de lo caro.
    print(f"python del sistema: {system_python()}")
    comprobar_uv()
    preparar_estatico(args.sin_npm, getattr(args, "sin_npm_ci", False), tema)

    runtime_python_dir = out_dir / "runtime" / "python"
    if runtime_python_dir.exists():
        shutil.rmtree(runtime_python_dir)
    runtime_python_dir.mkdir(parents=True, exist_ok=True)

    print(f"descomprimiendo {zip_path.name} en {runtime_python_dir}")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(runtime_python_dir)

    pth_candidates = list(runtime_python_dir.glob("python3*._pth"))
    if not pth_candidates:
        print("error: no se encontro python3*._pth en el runtime descomprimido", file=sys.stderr)
        return 1
    pth_path = pth_candidates[0]
    pth_path.write_text(patch_pth_content(pth_path.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"editado {pth_path.name}")

    requirements_path = out_dir / "requirements.txt"
    export_args = uv_export_command(requirements_path, with_shap, con_parquet)
    print(f"uv {' '.join(export_args)}")
    try:
        run_uv(export_args)
    except PolicyBlockError as exc:
        print(f"BLOQUEO DE POLITICA (4551) en uv export: {exc}", file=sys.stderr)
        return 1
    filtered, dropped = filter_local_requirements(requirements_path.read_text(encoding="utf-8"))
    requirements_path.write_text(filtered, encoding="utf-8")
    for line in dropped:
        print(f"requirements: descartada dependencia de ruta local -> {line.strip()}")

    # Carpeta de wheels nueva y vacía: así solo se instala el wheel de esta versión.
    wheels_dir = wheels_dir_for(out_dir)
    if wheels_dir.exists():
        shutil.rmtree(wheels_dir)
    wheels_dir.mkdir(parents=True)
    build_args = uv_build_wheel_command(REPO_ROOT, wheels_dir)
    print(f"uv {' '.join(build_args)}  (vigia)")
    try:
        run_uv(build_args)
    except PolicyBlockError as exc:
        print(f"BLOQUEO DE POLITICA (4551) construyendo vigia: {exc}", file=sys.stderr)
        return 1

    site_packages = runtime_python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    runtime_python_exe = runtime_python_dir / "python.exe"
    try:
        vigia_wheel = select_vigia_wheel(wheels_dir.glob("*.whl"), vigia_version)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        privadas = comprobar_wheel_sin_privados(
            vigia_wheel, exigir=True if getattr(args, "exigir_privados", False) else None
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if privadas:
        print(
            "error: el wheel lleva ficheros privados: "
            + ", ".join(privadas)
            + "; añádelos a [tool.hatch.build.targets.wheel] exclude en pyproject.toml",
            file=sys.stderr,
        )
        return 1
    wheel_paths = [str(vigia_wheel)]
    steps = (
        (
            "requirements",
            uv_pip_install_command(runtime_python_exe, site_packages, requirements_path),
        ),
        (
            "wheels locales",
            uv_pip_install_command(
                runtime_python_exe, site_packages, wheel_paths=wheel_paths, no_deps=True
            ),
        ),
    )
    for label, install_args in steps:
        print(f"uv {' '.join(install_args)}  ({label})")
        try:
            run_uv(install_args)
        except PolicyBlockError as exc:
            print(f"BLOQUEO DE POLITICA (4551) instalando {label}: {exc}", file=sys.stderr)
            return 1

    installed_static = site_packages / "vigia" / "static"
    if installed_static.exists():
        print(f"static ya incluido por el wheel: {installed_static}")
    else:
        # `preparar_estatico` ya comprobó que existe y es válido.
        shutil.copytree(STATIC_DIR, installed_static)
        print(f"copiado static de {STATIC_DIR} a {installed_static}")
    tema_instalado = tema_del_estatico(
        (installed_static / "index.html").read_text(encoding="utf-8", errors="replace")
        if (installed_static / "index.html").is_file()
        else ""
    )
    if tema_instalado != tema:
        print(
            f"error: el estático instalado lleva el tema {tema_instalado!r}, no {tema!r}",
            file=sys.stderr,
        )
        return 1

    cmd_template = read_cmd_template("Vigia.cmd.template")
    console_template = read_cmd_template("Vigia-consola.cmd.template")
    if cmd_template:
        (out_dir / "Vigia.cmd").write_text(cmd_template, encoding="utf-8")
    if console_template:
        (out_dir / "Vigia-consola.cmd").write_text(console_template, encoding="utf-8")

    # LEEME.txt: versión de Vigía y, aparte, la de Python embebido.
    (out_dir / "LEEME.txt").write_text(leeme_text(vigia_version, version), encoding="utf-8")

    # README, LICENSE, NOTICE y docs/manual dentro del paquete.
    try:
        copiados = copiar_documentacion(REPO_ROOT, out_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"documentación copiada: {', '.join(copiados)}")

    # TERCEROS.txt: licencias leídas de los metadatos, más la de Python embebido.
    licencia_python = runtime_python_dir / "LICENSE.txt"
    terceros = generar_terceros(
        leer_distribuciones(site_packages),
        version,
        licencia_python.read_text(encoding="utf-8", errors="replace")
        if licencia_python.is_file()
        else None,
        vigia_version,
    )
    (out_dir / "TERCEROS.txt").write_text(terceros, encoding="utf-8")
    print("TERCEROS.txt escrito")

    # El zip no lleva la ruta de esta máquina.
    rutas = rutas_de_la_maquina(out_dir) + [out_dir]
    for quitado in limpiar_paquete(out_dir, rutas):
        print(f"quitado del paquete (lleva rutas de la máquina o no hace falta): {quitado}")
    con_ruta = buscar_rutas_en_paquete(out_dir, rutas)
    if con_ruta:
        print(
            "error: el paquete lleva la ruta de la máquina de compilación en: "
            + ", ".join(con_ruta[:20]),
            file=sys.stderr,
        )
        return 1

    print(f"paquete ensamblado en {out_dir}")
    return 0


# --------------------------------------------------------------------------
# measure
# --------------------------------------------------------------------------


def dir_size_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def top_site_packages(site_packages: Path, n: int = 10) -> list[dict]:
    entries = []
    if not site_packages.exists():
        return entries
    for child in site_packages.iterdir():
        if child.is_dir() and not child.name.endswith(".dist-info"):
            entries.append({"name": child.name, "mb": round(dir_size_bytes(child) / 1_048_576, 1)})
    entries.sort(key=lambda e: e["mb"], reverse=True)
    return entries[:n]


def wait_for_health(url: str, timeout_s: float, interval_s: float = 0.2) -> float | None:
    """Sondea url hasta 200 OK. Devuelve milisegundos transcurridos o None si expira."""
    start = time.monotonic()
    deadline = start + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return (time.monotonic() - start) * 1000.0
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(interval_s)
    return None


def cmd_measure(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    runtime_python_dir = out_dir / "runtime" / "python"
    site_packages = runtime_python_dir / "Lib" / "site-packages"
    python_exe = runtime_python_dir / "python.exe"

    if not python_exe.exists():
        print(f"error: no existe {python_exe}; ejecuta 'assemble' primero", file=sys.stderr)
        return 1

    total_mb = round(dir_size_bytes(out_dir) / 1_048_576, 1)
    top10 = top_site_packages(site_packages)

    port = args.port
    data_dir = (
        Path(args.data_dir)
        if args.data_dir
        else Path(os.environ.get("TEMP", ".")) / "vigia-measure"
    )
    data_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["VIGIA_HOME"] = str(data_dir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # sin __pycache__ en el paquete (llevan la ruta de origen)
    proc = subprocess.Popen(
        [str(python_exe), "-m", "vigia", "serve", "--no-browser", "--port", str(port)],
        cwd=str(out_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    startup_ms = wait_for_health(f"http://127.0.0.1:{port}/api/health", timeout_s=args.timeout)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    output_tail = ""
    if proc.stdout:
        try:
            output_tail = proc.stdout.read()
        except (OSError, ValueError):
            output_tail = "(salida del proceso no legible)"

    result = {
        "paquete": str(out_dir),
        "con_shap": args.with_shap_label,
        "tamano_total_mb": total_mb,
        "top10_site_packages_mb": top10,
        "arranque_ms": startup_ms,
        "arranque_ok": startup_ms is not None,
    }
    if startup_ms is None and is_policy_block(output_tail):
        result["bloqueo_politica"] = True

    print(json.dumps(result, ensure_ascii=False, indent=2))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "con-shap" if args.with_shap_label else "sin-shap"
    measure_path = OUT_DIR / f"measure-{suffix}.json"
    measure_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"guardado en {measure_path}")
    return 0 if startup_ms is not None else 1


# --------------------------------------------------------------------------
# zip
# --------------------------------------------------------------------------


def dist_zip_name(out_dir: Path) -> str:
    """El zip se llama como el directorio ensamblado: vigia-<versión>-win64.zip."""
    return f"{Path(out_dir).name}.zip"


def cmd_zip(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    if not out_dir.exists():
        print(f"error: no existe {out_dir}; ejecuta 'assemble' primero", file=sys.stderr)
        return 1
    rutas = rutas_de_la_maquina(out_dir) + [out_dir]
    con_ruta = buscar_rutas_en_paquete(out_dir, rutas)
    if con_ruta:
        print(
            "error: el paquete lleva la ruta de la máquina de compilación en: "
            + ", ".join(con_ruta[:20]),
            file=sys.stderr,
        )
        return 1
    inesperado = comprobar_contenido_paquete(out_dir, rutas + [Path.home()])
    if inesperado:
        print(
            "error: el paquete no coincide con la lista blanca:\n  - "
            + "\n  - ".join(inesperado[:20]),
            file=sys.stderr,
        )
        return 1
    dist_dir = Path(args.dist) if getattr(args, "dist", None) else DIST_DIR
    dist_dir.mkdir(parents=True, exist_ok=True)
    dest = dist_dir / dist_zip_name(out_dir)
    if dest.exists():
        dest.unlink()
    base_name = str(dest.with_suffix(""))
    shutil.make_archive(base_name, "zip", root_dir=str(out_dir.parent), base_dir=out_dir.name)
    print(f"creado {dest} ({dest.stat().st_size} bytes)")

    # Junto al zip: huella y manifiesto.
    digest = sha256_of(dest)
    sha_path = dest.with_name(dest.name + ".sha256")
    sha_path.write_text(sha256_file_text(digest, dest.name), encoding="utf-8")
    site_packages = out_dir / "runtime" / "python" / "Lib" / "site-packages"
    manifiesto = manifiesto_texto(
        dest.name,
        digest,
        entradas_del_zip(dest),
        leer_distribuciones(site_packages),
        app_version(),
        args.version,
    )
    manifest_path = dest.with_name(dest.name + ".MANIFIESTO.txt")
    manifest_path.write_text(manifiesto, encoding="utf-8")
    print(f"creado {sha_path.name} y {manifest_path.name}; sha256 {digest}")
    return 0


# --------------------------------------------------------------------------
# all / main
# --------------------------------------------------------------------------


def cmd_all(args: argparse.Namespace) -> int:
    for step in (cmd_fetch, cmd_assemble, cmd_measure, cmd_zip):
        code = step(args)
        if code != 0:
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Empaqueta Vigia con Python embebido (sin PyInstaller)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--version",
            default=DEFAULT_VERSION,
            type=_version_argumento,
            help="version 3.13.N de Python (con huella fijada en PYTHON_EMBED_SHA256)",
        )

    def add_shap_flags(p: argparse.ArgumentParser) -> None:
        # SHAP entra por defecto; --no-shap produce la variante reducida.
        group = p.add_mutually_exclusive_group()
        group.add_argument(
            "--no-shap", dest="with_shap", action="store_false", help="variante reducida sin shap"
        )
        group.add_argument(
            "--with-shap", dest="with_shap", action="store_true", help="incluir shap (por defecto)"
        )
        p.set_defaults(with_shap=True)
        # Parquet no entra salvo que se pida.
        p.add_argument(
            "--con-parquet",
            dest="con_parquet",
            action="store_true",
            help="añade el extra parquet (pyarrow, 82 MB; sin él por defecto)",
        )
        # El estático se compila con VITE_TEMA=miguel salvo --sin-npm.
        p.add_argument(
            "--sin-npm",
            dest="sin_npm",
            action="store_true",
            help="no ejecuta npm run build; mantiene las comprobaciones del estático",
        )
        p.add_argument(
            "--tema",
            dest="tema",
            type=tema_argumento,
            default=TEMA_PUBLICO,
            help=f"estética del estático (por defecto {TEMA_PUBLICO}); otra deja solo esa",
        )
        # `npm ci --ignore-scripts` antes del build, salvo --sin-npm-ci.
        p.add_argument(
            "--sin-npm-ci",
            dest="sin_npm_ci",
            action="store_true",
            help="no ejecuta npm ci --ignore-scripts antes de npm run build",
        )
        # Exige privados.txt en el árbol de trabajo.
        p.add_argument(
            "--exigir-privados",
            dest="exigir_privados",
            action="store_true",
            help=f"falla si falta build/publico/privados.txt (o con {ENV_EXIGIR_PRIVADOS}=1)",
        )

    p_fetch = sub.add_parser("fetch", help="descarga el zip embebido de python.org")
    add_common(p_fetch)
    p_fetch.set_defaults(func=cmd_fetch)

    p_assemble = sub.add_parser("assemble", help="ensambla el paquete en build/out/")
    add_common(p_assemble)
    add_shap_flags(p_assemble)
    p_assemble.add_argument(
        "--out",
        default=None,
        help="directorio de salida (por defecto build/out/vigia-<version>-win64)",
    )
    p_assemble.set_defaults(func=cmd_assemble)

    p_measure = sub.add_parser("measure", help="mide tamano y arranque del paquete")
    add_common(p_measure)
    p_measure.add_argument("--out", required=True, help="directorio del paquete ensamblado")
    p_measure.add_argument("--port", type=int, default=8799)
    p_measure.add_argument("--data-dir", default=None)
    p_measure.add_argument(
        "--timeout", type=float, default=30.0, help="segundos de espera al arranque"
    )
    p_measure.add_argument(
        "--with-shap-label",
        action="store_true",
        help="solo etiqueta el JSON de salida como con-shap",
    )
    p_measure.set_defaults(func=cmd_measure)

    p_zip = sub.add_parser("zip", help="crea dist/vigia-<ver>-win64.zip, su .sha256 y <zip>.MANIFIESTO.txt")
    add_common(p_zip)
    p_zip.add_argument("--out", required=True, help="directorio del paquete ensamblado")
    p_zip.add_argument("--dist", default=None, help="carpeta del zip (por defecto dist/)")
    p_zip.set_defaults(func=cmd_zip)

    p_all = sub.add_parser("all", help="fetch + assemble + measure + zip")
    add_common(p_all)
    add_shap_flags(p_all)
    p_all.add_argument("--out", default=None)
    p_all.add_argument("--dist", default=None, help="carpeta del zip (por defecto dist/)")
    p_all.add_argument("--port", type=int, default=8799)
    p_all.add_argument("--data-dir", default=None)
    p_all.add_argument("--timeout", type=float, default=30.0)
    p_all.add_argument("--with-shap-label", action="store_true")
    p_all.set_defaults(func=cmd_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "all" and args.out is None:
        args.out = str(
            out_dir_for(app_version(), None, args.with_shap, args.con_parquet, args.tema)
        )
    if args.command == "measure" and getattr(args, "with_shap_label", None) is None:
        args.with_shap_label = False
    try:
        return args.func(args)
    except PolicyBlockError as exc:
        print(f"BLOQUEO DE POLITICA (winerror 4551): {exc}", file=sys.stderr)
        return 2
    except (SystemPythonError, EstaticoError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
