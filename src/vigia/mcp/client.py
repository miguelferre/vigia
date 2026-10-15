"""Cliente HTTP del servidor MCP: localiza la API en marcha,
añade las cabeceras `X-Vigia-*` y expone las llamadas que usan las tools.

El MCP nunca abre `vigia.db`: habla solo por loopback con `vigia serve`.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from vigia.app.preflight import (
    CABECERA_RETO,
    DOMINIO_IDENTIDAD,
    LockFile,
    _pid_is_alive,
    nuevo_reto,
    prueba_valida,
)
from vigia.mcp.errores import (  # noqa: F401  (reexportados)
    CLAVES_COLUMN_MAPPING,
    CLAVES_MAPPING_TEMPLATE,
    MENSAJE_SIN_ARRANQUE,
    VigiaError,
    _claves_validas,
    _que_hacer,
    _texto_detalle,
    fallos_de_conexion,
)

MAX_SUBIDA_BYTES = 200 * 1024 * 1024
HOSTS_URL_LOCALES = frozenset({"127.0.0.1", "localhost"})


def validar_url_local(url: str) -> str:
    """`--url` solo admite `http://` a 127.0.0.1 o localhost: el cliente manda el token y ficheros."""
    from urllib.parse import urlsplit

    try:
        partes = urlsplit(url)
        host = (partes.hostname or "").lower()
        _ = partes.port  # un puerto no numérico lanza ValueError
        esquema = partes.scheme
    except ValueError:
        host, esquema = "", ""
    if esquema != "http" or host not in HOSTS_URL_LOCALES:
        raise RuntimeError(
            f"--url {url!r} no vale: solo se admite http:// a 127.0.0.1 o localhost, "
            "por ejemplo http://127.0.0.1:8765"
        )
    return url


# Copia de `vigia.app.jobs.ESTADOS_FINALES` (importar el backend colgaba stdio-B).
ESTADOS_FINALES = ("terminado", "error", "cancelado")


@dataclass
class VigiaClient:
    """Habla con la API de Vigía (`/api`) por loopback con cabeceras de actor
    `agente`. `discover` localiza el puerto; `bootstrap` pide el token."""

    url: str | None = None
    data_dir: Path | None = None
    actor: str = "claude-code"
    http: httpx.AsyncClient | None = None
    _base_url: str | None = field(default=None, init=False, repr=False)
    _token: str | None = field(default=None, init=False, repr=False)
    _owns_http: bool = field(default=False, init=False, repr=False)
    # Con la API localizada por el lock, el cliente exige la prueba de identidad
    # antes de mandar el token, un JSON o un fichero. `_via_lock` lo activa.
    _via_lock: bool = field(default=False, init=False, repr=False)
    _token_lock: str | None = field(default=None, init=False, repr=False)
    # Cliente descartado por `_olvidar_conexion`; se cierra en la siguiente llamada.
    _obsoleto: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    @property
    def base_url(self) -> str:
        """URL base de la API a la que habla este cliente."""
        return self._base_url or self.discover()

    def cuerpo_actor(self, actor: str | None) -> dict[str, Any]:
        """Campos de actor de una mutación: `actor` es el de la entrada
        (`--actor`); otro texto del modelo va como `actor_detalle`."""
        cuerpo: dict[str, Any] = {"actor": self.actor}
        detalle = (actor or "").strip()
        if detalle and detalle != self.actor:
            cuerpo["actor_detalle"] = detalle[:200]
        return cuerpo

    def discover(self) -> str:
        """Fija `_base_url` (primero la URL dada, después el lock de la carpeta de datos) y lo devuelve."""
        if self.url:
            self._base_url = self.url.rstrip("/")
            self._via_lock = False
            return self._base_url
        data_dir = self.data_dir
        if data_dir is not None:
            lock = LockFile(data_dir)
            datos = lock.read()
            if datos and "pid" in datos and _pid_is_alive(int(datos["pid"])):
                self._base_url = f"http://127.0.0.1:{datos['port']}"
                self._via_lock = True
                self._token_lock = datos.get("token") or None
                return self._base_url
        raise RuntimeError(MENSAJE_SIN_ARRANQUE)

    async def _verificar_identidad(self, http: httpx.AsyncClient) -> None:
        """Comprueba que el par del puerto del lock es el servidor dueño de ese lock."""
        fallo = VigiaError(
            502,
            "El programa que contesta en ese puerto no es este Vigía; no se le envía nada",
            "cierra lo que use ese puerto o arranca `vigia serve` de nuevo",
        )
        token = self._token_lock
        if not token:
            raise fallo
        reto = nuevo_reto()
        resp = await http.get("/api/identidad", headers={CABECERA_RETO: reto})
        try:
            prueba = resp.json()["prueba"] if resp.status_code == 200 else None
        except (ValueError, KeyError, TypeError):
            prueba = None
        if not isinstance(prueba, str) or not prueba_valida(token, reto, DOMINIO_IDENTIDAD, prueba):
            raise fallo

    async def _ensure_http(self) -> httpx.AsyncClient:
        """Cliente HTTP listo para una petición. Con la API localizada por el lock, la
        prueba de identidad se repite ANTES DE CADA PETICIÓN: si otro programa
        pasó a contestar en ese puerto, no recibe ni el token, ni el JSON ni los ficheros."""
        if self._obsoleto is not None:
            obsoleto, self._obsoleto = self._obsoleto, None
            await obsoleto.aclose()
        if self.http is None:
            # Sin proxy ni variables del entorno: el servidor está en loopback.
            self.http = httpx.AsyncClient(base_url=self._base_url or self.discover(), trust_env=False)
            self._owns_http = True
        if self._via_lock:
            try:
                await self._verificar_identidad(self.http)
            except BaseException:
                self._olvidar_conexion()
                raise
        return self.http

    def _olvidar_conexion(self) -> None:
        """Descarta puerto, token y cliente HTTP: la siguiente petición vuelve a
        leer el lock, pide el token y prueba la identidad del servidor que haya entonces."""
        if not self._owns_http:  # un cliente inyectado (tests, ASGI) no es nuestro
            return
        self._obsoleto = self.http  # se cierra en la siguiente llamada, ya con `await`
        self.http = None
        self._owns_http = False
        self._token = None
        self._token_lock = None
        if self.url is None:
            self._base_url = None
            self._via_lock = False

    @contextmanager
    def _conexion(self) -> Iterator[None]:
        """`fallos_de_conexion` y, si la conexión falla o el par no prueba su identidad,
        olvido de lo cacheado para que el cliente se vuelva a localizar."""
        try:
            with fallos_de_conexion(self.url):
                yield
        except VigiaError as exc:
            if exc.status_code in (502, 503):
                self._olvidar_conexion()
            raise
        except httpx.TransportError:
            self._olvidar_conexion()
            raise

    async def _listo(self) -> httpx.AsyncClient:
        """Cliente HTTP con el token ya pedido, en el mismo bucle que las peticiones
        (un bootstrap en bucle propio daba «Event loop is closed» en la primera tool)."""
        if self._token is None:
            await self.bootstrap()  # prueba la identidad antes de pedir el token
            assert self.http is not None
            return self.http
        return await self._ensure_http()

    async def bootstrap(self) -> str:
        """Pide y cachea `mcp_token` con `/settings?reveal=true`."""
        with self._conexion():
            if self._base_url is None:
                self.discover()
        with self._conexion():
            http = await self._ensure_http()
            resp = await http.get("/api/settings", params={"reveal": "true"})
        await self._raise_for_status(resp)
        self._token = resp.json()["mcp_token"]
        return self._token

    def _headers(self, correlation_id: str | None) -> dict[str, str]:
        cabeceras = {
            "X-Vigia-Actor-Kind": "agente",
            "X-Vigia-Actor": self.actor,
            "X-Vigia-Correlation": correlation_id or str(uuid.uuid4()),
        }
        if self._token:
            cabeceras["X-Vigia-Token"] = self._token
        return cabeceras

    async def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            try:
                detalle = resp.json().get("detail", resp.text)
            except (ValueError, AttributeError):
                detalle = resp.text
            detalle = _texto_detalle(detalle)
            try:
                ruta = resp.request.url.path
            except RuntimeError:  # una `Response` sin petición (tests)
                ruta = ""
            raise VigiaError(resp.status_code, detalle, _que_hacer(resp.status_code, detalle, ruta))

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        timeout: float | None = None,
    ) -> Any:
        """GET con el tiempo de espera del cliente (5 s de httpx) o, con `timeout`, uno
        propio para esta llamada (una lectura que calcula en el servidor)."""
        with self._conexion():
            http = await self._listo()
            extra = {} if timeout is None else {"timeout": timeout}
            resp = await http.get(
                f"/api{path}", params=params, headers=self._headers(correlation_id), **extra
            )
        await self._raise_for_status(resp)
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    async def post(
        self, path: str, *, json: Any = None, params: dict[str, Any] | None = None, correlation_id: str | None = None
    ) -> Any:
        with self._conexion():
            http = await self._listo()
            resp = await http.post(f"/api{path}", json=json, params=params, headers=self._headers(correlation_id))
        await self._raise_for_status(resp)
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    async def patch(self, path: str, *, json: Any = None, correlation_id: str | None = None) -> Any:
        with self._conexion():
            http = await self._listo()
            resp = await http.patch(f"/api{path}", json=json, headers=self._headers(correlation_id))
        await self._raise_for_status(resp)
        return resp.json()

    async def put(self, path: str, *, json: Any = None, correlation_id: str | None = None) -> Any:
        with self._conexion():
            http = await self._listo()
            resp = await http.put(f"/api{path}", json=json, headers=self._headers(correlation_id))
        await self._raise_for_status(resp)
        return resp.json()

    async def delete(
        self, path: str, *, params: dict[str, Any] | None = None, correlation_id: str | None = None
    ) -> Any:
        with self._conexion():
            http = await self._listo()
            resp = await http.delete(f"/api{path}", params=params, headers=self._headers(correlation_id))
        await self._raise_for_status(resp)
        return None

    async def upload(
        self,
        path: str,
        *,
        file_path: str,
        fields: dict[str, str],
        correlation_id: str | None = None,
    ) -> Any:
        """Sube un fichero multipart. Solo lee el fichero que se le nombra (§8.3)."""
        import anyio

        nombre = os.path.basename(file_path)
        try:
            tamano = os.path.getsize(file_path)
        except OSError:
            tamano = 0  # el error de lectura de abajo lo cuenta mejor
        if tamano > MAX_SUBIDA_BYTES:
            raise VigiaError(
                413,
                f"El fichero pesa {tamano / 1024 / 1024:.0f} MB y el tope de subida es de 200 MB",
                "divide el fichero o súbelo desde la ventana de Vigía",
            )
        contenido = await anyio.Path(file_path).read_bytes()
        with self._conexion():
            http = await self._listo()
            resp = await http.post(
                f"/api{path}",
                data=fields,
                files={"file": (nombre, contenido)},
                headers=self._headers(correlation_id),
            )
        await self._raise_for_status(resp)
        return resp.json()

    async def wait_for_job(self, job_id: int, timeout_s: float = 60.0) -> dict[str, Any]:
        """Sondea `/jobs/{id}` cada 500 ms hasta un estado final o el timeout."""
        inicio = time.monotonic()
        while True:
            job = await self.get(f"/jobs/{job_id}")
            if job.get("status") in ESTADOS_FINALES:
                return job
            if time.monotonic() - inicio >= timeout_s:
                return {
                    "status": "en_curso",
                    "timeout": True,
                    "job_id": job_id,
                    "aviso": f"sigue en curso; consulta get_job({job_id})",
                }
            import anyio

            await anyio.sleep(0.5)

    async def seguir_job(self, job: dict[str, Any], wait: bool, timeout_s: float = 60.0) -> dict[str, Any]:
        """Tools que encolan un trabajo: sin `wait` lo devuelve; con `wait` espera."""
        if not wait:
            return job
        return await self.wait_for_job(job["id"], timeout_s=timeout_s)

    async def aclose(self) -> None:
        if self._obsoleto is not None:
            obsoleto, self._obsoleto = self._obsoleto, None
            await obsoleto.aclose()
        if self.http is not None and self._owns_http:
            await self.http.aclose()


_client: VigiaClient | None = None


def set_client(client: VigiaClient) -> None:
    global _client
    _client = client


def get_client() -> VigiaClient:
    if _client is None:
        raise RuntimeError("VigiaClient no inicializado: llama a set_client() primero")
    return _client
