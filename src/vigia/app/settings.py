"""Configuración de arranque de Vigía: carpeta de datos, host/puerto y cachés."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from vigia import __version__

DEFAULT_PORT_START = 8765
DEFAULT_HOST = "127.0.0.1"
# proyectos de demo vivos que admite `POST /demo/runs` sin `project_id`.
DEFAULT_MAX_PROYECTOS_DEMO = 50


def _default_data_dir() -> Path:
    """Resuelve el directorio de datos: VIGIA_HOME si está fijado, si no ~/Documents/vigia-datos."""
    env_home = os.environ.get("VIGIA_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / "Documents" / "vigia-datos"


@dataclass
class Settings:
    """Parámetros de arranque de la aplicación. No incluye configuración de negocio."""

    data_dir: Path = field(default_factory=_default_data_dir)
    host: str = DEFAULT_HOST
    port_start: int = DEFAULT_PORT_START
    open_browser: bool = True
    app_version: str = __version__
    jobs_inline: bool = False
    sse_heartbeat_s: float = 15.0
    max_proyectos_demo: int = DEFAULT_MAX_PROYECTOS_DEMO

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir).expanduser()

    @property
    def db_path(self) -> Path:
        """Ruta del fichero SQLite de la aplicación dentro de la carpeta de datos."""
        return self.data_dir / "vigia.db"


def prepare_cache_env(data_dir: Path) -> None:
    """Fija las variables de caché de numba/matplotlib/joblib bajo data_dir/cache.

    Debe llamarse ANTES de importar numpy/pandas/scipy/sklearn/numba, para que estas
    librerías no escriban caché en AppData del usuario.
    """
    data_dir = Path(data_dir).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = data_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    numba_dir = cache_dir / "numba"
    mpl_dir = cache_dir / "matplotlib"
    joblib_dir = cache_dir / "joblib"
    for d in (numba_dir, mpl_dir, joblib_dir):
        d.mkdir(parents=True, exist_ok=True)

    os.environ["NUMBA_CACHE_DIR"] = str(numba_dir)
    os.environ["MPLCONFIGDIR"] = str(mpl_dir)
    os.environ["JOBLIB_TEMP_FOLDER"] = str(joblib_dir)
