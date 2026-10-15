"""Comprobaciones previas al arranque: puerto libre, importación resiliente y lock de proceso."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
import time
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Self

# winerror de "una directiva de Control de aplicaciones bloqueó este archivo".
APP_CONTROL_WINERROR = 4551
APP_CONTROL_TEXT = "Control de aplicaciones"


class AppControlBlockedError(RuntimeError):
    """Se lanza cuando el Control de aplicaciones bloquea un fichero, sin reintento posible."""


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    """True si se puede hacer bind en host:port (sin SO_REUSEADDR, ver find_free_port)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(start: int = 8765, host: str = "127.0.0.1", max_tries: int = 50) -> int:
    """Devuelve el primer puerto libre en host a partir de start, probando puertos sucesivos."""
    for port in range(start, start + max_tries):
        # Sin SO_REUSEADDR: en Windows ese flag permite bind() sobre un puerto ya
        # escuchando, lo que daría falsos positivos de "libre".
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(
        f"No se encontró puerto libre entre {start} y {start + max_tries - 1} en {host}"
    )


def _is_app_control_block(exc: BaseException) -> bool:
    """Distingue el bloqueo de política (sin reintento) del escaneo asíncrono (con reintento)."""
    winerror = getattr(exc, "winerror", None)
    if winerror == APP_CONTROL_WINERROR:
        return True
    return APP_CONTROL_TEXT in str(exc)


def import_with_retry(
    modules: list[str], attempts: int = 3, wait_s: float = 3.0
) -> dict[str, ModuleType]:
    """Importa cada módulo de `modules`, reintentando solo ante fallos de escaneo asíncrono.

    Un bloqueo del Control de aplicaciones (winerror 4551 o texto correspondiente) se
    identifica sin reintentar y se relanza como AppControlBlockedError con el módulo y
    la instrucción para el usuario. Cualquier otro ImportError/OSError se reintenta
    `attempts` veces esperando `wait_s` segundos (puede ser el antivirus escaneando el
    fichero de forma asíncrona tras haberlo escrito uv).
    """
    imported: dict[str, ModuleType] = {}
    for name in modules:
        last_exc: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                imported[name] = import_module(name)
                last_exc = None
                break
            except (ImportError, OSError) as exc:
                if _is_app_control_block(exc):
                    raise AppControlBlockedError(
                        f"El Control de aplicaciones bloqueó la importación de '{name}': {exc}. "
                        "Revisa la política de Windows o pide una excepción a quien administre el equipo "
                        "(ver docs/manual/problemas.md); no tiene sentido reintentar."
                    ) from exc
                last_exc = exc
                if attempt < attempts:
                    time.sleep(wait_s)
        if last_exc is not None:
            raise last_exc
    return imported


def generate_token() -> str:
    """Genera un token opaco para proteger el endpoint de apagado."""
    return secrets.token_urlsafe(32)


CABECERA_RETO = "X-Vigia-Reto"
CABECERA_PRUEBA = "X-Vigia-Prueba"
DOMINIO_IDENTIDAD = "identidad"
DOMINIO_APAGADO = "apagado"
VENTANA_RETO_S = 60


def nuevo_reto() -> str:
    """Reto de un solo uso para pedir una prueba al servidor: hora y azar."""
    return f"{int(time.time())}.{secrets.token_hex(8)}"


def calcular_prueba(token: str, reto: str, dominio: str) -> str:
    """HMAC del reto con el token del lock: solo lo calcula quien conoce el token."""
    mensaje = f"{dominio}:{reto}".encode()
    return hmac.new(token.encode("utf-8"), mensaje, hashlib.sha256).hexdigest()


def prueba_valida(token: str, reto: str, dominio: str, prueba: str) -> bool:
    """Compara la prueba en tiempo constante."""
    esperada = calcular_prueba(token, reto, dominio).encode("ascii")
    return hmac.compare_digest(esperada, prueba.encode("utf-8"))


def reto_reciente(reto: str, ahora: float | None = None) -> bool:
    """El reto lleva la hora de su creación y caduca a los 60 s."""
    try:
        marca = int(reto.split(".", 1)[0])
    except ValueError:
        return False
    return abs((ahora if ahora is not None else time.time()) - marca) <= VENTANA_RETO_S


# Código de `GetExitCodeProcess` para un proceso que sigue corriendo.
_WINDOWS_STILL_ACTIVE = 259
# `OpenProcess` con permiso de consulta mínimo: basta para saber si el proceso vive.
_WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# `OpenProcess` deniega el acceso cuando el proceso existe pero es de otro usuario.
_WINDOWS_ERROR_ACCESS_DENIED = 5


def _pid_is_alive_windows(pid: int) -> bool:
    """Existencia de un PID en Windows por `OpenProcess` + `GetExitCodeProcess`.

    `os.kill(pid, 0)` no sirve aquí: CPython lo resuelve con `OpenProcess` en modo
    total y, para un proceso que no desciende del que pregunta, falla con
    `WinError 87` (parámetro incorrecto) aunque el proceso esté vivo. Eso daba
    `is_stale() == True` con el servidor en marcha, y con él `vigia shutdown`
    devolviendo 1 y el servidor MCP sin localizar la API por el lock.
    """
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # Existe pero no es nuestro: cuenta como vivo, igual que el `PermissionError` de POSIX.
        return ctypes.get_last_error() == _WINDOWS_ERROR_ACCESS_DENIED
    try:
        codigo = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo)):
            return True
        return codigo.value == _WINDOWS_STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


# Segundos entre la hora guardada en el lock y la hora de creación actual del proceso con
# ese PID que se aceptan como el mismo proceso; un PID reutilizado nace mucho después.
_TOLERANCIA_HORA_PROCESO_S = 2.0
# Segundos entre 1601-01-01 (época de FILETIME) y 1970-01-01.
_FILETIME_A_EPOCH_S = 11_644_473_600


def _process_start_time(pid: int) -> float | None:
    """Hora de creación del proceso `pid` en segundos desde 1970, o None si no se puede leer.

    Solo en Windows (`GetProcessTimes`); en otros sistemas devuelve None y el lock se
    comporta como siempre (PID vivo). Distingue un proceso de otro con el mismo PID.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(_WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creacion, salida, nucleo, usuario = (wintypes.FILETIME() for _ in range(4))
            ok = kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creacion),
                ctypes.byref(salida),
                ctypes.byref(nucleo),
                ctypes.byref(usuario),
            )
            if not ok:
                return None
            ticks = (creacion.dwHighDateTime << 32) | creacion.dwLowDateTime
            return ticks / 10_000_000 - _FILETIME_A_EPOCH_S
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError, ValueError):
        return None


def _pid_is_alive(pid: int) -> bool:
    """Comprueba si un PID sigue vivo, sin depender de psutil (puede no estar instalado)."""
    if sys.platform == "win32":
        return _pid_is_alive_windows(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # El proceso existe pero no tenemos permiso para señalarlo: lo consideramos vivo.
        return True
    except OSError:
        return False


@dataclass
class LockFile:
    """Gestiona vigia.lock (PID, puerto, hora de arranque) en data_dir. Usable como context manager."""

    data_dir: Path

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.path = self.data_dir / "vigia.lock"

    def _read(self) -> dict | None:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def is_stale(self) -> bool:
        """Un lock es obsoleto si no existe, está corrupto, o su PID ya no está vivo.

        También lo es si el PID vive pero el proceso actual con ese PID se creó a otra hora
        que la guardada en el lock: el sistema reutilizó el PID tras un cierre brusco. Un lock sin la hora (versión anterior) se juzga solo por el PID.
        """
        data = self._read()
        if not data or "pid" not in data:
            return True
        pid = int(data["pid"])
        if not _pid_is_alive(pid):
            return True
        guardada = data.get("process_started")
        if isinstance(guardada, (int, float)) and not isinstance(guardada, bool):
            actual = _process_start_time(pid)
            if actual is not None and abs(actual - float(guardada)) > _TOLERANCIA_HORA_PROCESO_S:
                return True
        return False

    def acquire(self, port: int, token: str | None = None) -> None:
        """Escribe el lock con PID, puerto, hora y (si se pasa) el token de apagado.

        El token queda en la carpeta de datos del usuario para que un proceso externo
        legitimo (lanzador, CLI, servidor MCP) pueda llamar a POST /api/shutdown.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "port": port,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        creado = _process_start_time(os.getpid())
        if creado is not None:
            payload["process_started"] = creado
        if token:
            payload["token"] = token
        texto = json.dumps(payload)
        # Creación atómica (`O_EXCL`): dos arranques a la vez no pisan el lock del otro.
        for _intento in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if not self.is_stale():
                    existing = self._read() or {}
                    raise RuntimeError(
                        f"Vigía ya está en marcha (PID {existing.get('pid')}, puerto {existing.get('port')})"
                    ) from None
                try:
                    self.path.unlink()  # lock caduco: se sustituye
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(texto)
            return
        raise RuntimeError("Vigía ya está en marcha: otro arranque ha creado el lock a la vez")

    def read(self) -> dict | None:
        """Devuelve el contenido del lock (pid, port, started_at, token) o None."""
        return self._read()

    def release(self) -> None:
        """Borra el lock si pertenece a este proceso (o si es obsoleto)."""
        data = self._read()
        if data is not None and int(data.get("pid", -1)) != os.getpid() and not self.is_stale():
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
