"""Colas de trabajos en proceso: `rapida` y `llm`, un hilo worker cada una.

El estado vive en la tabla `job`; el progreso se publica además en el bus para
los SSE. La cancelación es cooperativa: el trabajo consulta `ctx.cancelled`, que
relee `cancel_requested` en una sesión de base de datos corta, y puede abortar lanzando
`JobCancelled` o devolviendo el control.

Con `Settings.jobs_inline=True` (tests) `enqueue` ejecuta el trabajo en el hilo de ejecución de ejecución
que llama y devuelve el `Job` ya terminado.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from vigia.app.bus import EventBus
from vigia.app.db import session_scope
from vigia.app.errores import texto_error_trabajo
from vigia.app.events import ACTOR_SISTEMA, record_event
from vigia.app.models import DossierReview, Job, now_iso
from vigia.app.settings import Settings

__all__ = ["COLAS", "JobCancelled", "JobContext", "JobManager"]

_log = logging.getLogger("vigia.app.jobs")

COLAS = ("rapida", "llm")

ESTADOS_FINALES = ("terminado", "error", "cancelado")


class JobCancelled(Exception):
    """La lanza un trabajo que se detiene porque le han pedido cancelar."""


class JobContext:
    """Lo que ve el trabajo desde dentro: su id, cómo informar y si le han cancelado.

    `progress()` escribe sobre la MISMA sesión que usa `fn` (la que abre
    `JobManager._run`), no sobre una sesión nueva: SQLite solo admite un
    escritor a la vez, y si `fn` tiene una escritura sin `commit` (por
    ejemplo un `session.add(...); session.flush()` a mitad de un lote),
    abrir aquí una segunda conexión de escritura sobre el mismo motor
    bloquea (`database is locked`) hasta agotar `busy_timeout`. Usar la
    sesión del llamador evita el segundo escritor; el progreso queda
    visible para otros lectores en cuanto `fn` haga `commit` (o al cerrar
    el trabajo). `cancelled` sí abre una sesión aparte porque es una
    lectura pura: bajo WAL no compite con el escritor.
    """

    def __init__(
        self,
        *,
        job_id: int,
        engine: Engine,
        session: Session,
        bus: EventBus | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.job_id = job_id
        self.correlation_id = correlation_id
        self._engine = engine
        self._session = session
        self._bus = bus

    def progress(self, p: float, message: str = "") -> None:
        """Actualiza el progreso (0..1) en la sesión del trabajo y lo publica en el bus."""
        valor = min(1.0, max(0.0, float(p)))
        job = self._session.get(Job, self.job_id)
        if job is None:
            return
        job.progress = valor
        if message:
            job.message = message
        self._session.add(job)
        self._session.flush()
        estado = job.status
        self._publish(estado, valor, message)

    @property
    def cancelled(self) -> bool:
        """Relee `cancel_requested` en una sesión de base de datos corta (solo lectura): cancelación cooperativa."""
        with session_scope(self._engine) as session:
            job = session.get(Job, self.job_id)
            return bool(job is not None and job.cancel_requested)

    def raise_if_cancelled(self) -> None:
        """Atajo para abortar un trabajo largo entre bloques."""
        if self.cancelled:
            raise JobCancelled("el trabajo se ha cancelado a petición")

    def _publish(self, status: str, progress: float, message: str) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            {
                "type": "job",
                "job_id": self.job_id,
                "status": status,
                "progress": progress,
                "message": message,
            }
        )


class JobManager:
    """Dos colas en proceso con un hilo worker cada una y estado persistido."""

    def __init__(self, engine: Engine, settings: Settings, bus: EventBus) -> None:
        self.engine = engine
        self.settings = settings
        self.bus = bus
        self._queues: dict[str, queue.Queue[Any]] = {nombre: queue.Queue() for nombre in COLAS}
        self._threads: dict[str, threading.Thread] = {}
        self._parar = threading.Event()
        # Claves de deduplicación -> id del trabajo vigente (ver `enqueue`).
        self._claves: dict[str, int] = {}
        self._lock_dedup = threading.RLock()
        if not settings.jobs_inline:
            self._start_workers()

    # -- ciclo de vida ----------------------------------------------------

    def _start_workers(self) -> None:
        for nombre in COLAS:
            hilo = threading.Thread(
                target=self._worker,
                args=(nombre,),
                name=f"vigia-job-{nombre}",
                daemon=True,
            )
            hilo.start()
            self._threads[nombre] = hilo

    def shutdown(self, timeout: float = 10.0) -> None:
        """Deja de aceptar trabajos y espera a los workers hasta `timeout` segundos."""
        self._parar.set()
        for cola in self._queues.values():
            cola.put(None)
        for hilo in self._threads.values():
            hilo.join(timeout=timeout)
        self._threads.clear()

    # -- API pública ------------------------------------------------------

    def enqueue(
        self,
        kind: str,
        queue_name: str,
        fn: Callable[..., Any],
        *,
        params: dict[str, Any] | None = None,
        project_id: int | None = None,
        correlation_id: str | None = None,
        clave_dedup: str | None = None,
    ) -> Job:
        """Crea la fila `pendiente` y encola el trabajo (o lo ejecuta si `jobs_inline`).

        Con `clave_dedup`, si ya hay un trabajo pendiente o en curso con la misma
        clave, devuelve ese en vez de encolar otro: pedir lo mismo varias veces no
        apila trabajos iguales. La clave nombra el objeto (por ejemplo
        `"evaluacion:lote:7"`); sin ella no se deduplica.
        """
        if queue_name not in COLAS:
            raise ValueError(f"cola desconocida: {queue_name!r}; válidas: {', '.join(COLAS)}")
        if clave_dedup is None:
            return self._encolar(kind, queue_name, fn, params, project_id, correlation_id, None)
        with self._lock_dedup:
            vigente = self._claves.get(clave_dedup)
            if vigente is not None:
                try:
                    job = self.get(vigente)
                except KeyError:
                    job = None
                if job is not None and job.status not in ESTADOS_FINALES:
                    return job
            return self._encolar(kind, queue_name, fn, params, project_id, correlation_id, clave_dedup)

    def _encolar(
        self,
        kind: str,
        queue_name: str,
        fn: Callable[..., Any],
        params: dict[str, Any] | None,
        project_id: int | None,
        correlation_id: str | None,
        clave_dedup: str | None,
    ) -> Job:
        params = dict(params or {})
        with session_scope(self.engine) as session:
            job = Job(
                kind=kind,
                queue=queue_name,
                status="pendiente",
                progress=0.0,
                message="",
                params_json=_serializable(params),
                project_id=project_id,
                correlation_id=correlation_id,
            )
            session.add(job)
            session.flush()
            job_id = int(job.id or 0)
        if clave_dedup is not None:
            self._claves[clave_dedup] = job_id

        self.bus.publish(
            {
                "type": "job",
                "job_id": job_id,
                "status": "pendiente",
                "progress": 0.0,
                "message": "",
            }
        )

        if self.settings.jobs_inline:
            self._run(job_id, fn, params, correlation_id)
        else:
            self._queues[queue_name].put((job_id, fn, params, correlation_id))
        return self.get(job_id)

    def get(self, job_id: int) -> Job:
        """Lee el trabajo de la base de datos, desligado de la sesión."""
        with session_scope(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(f"no existe el trabajo {job_id}")
            session.expunge(job)
            return job

    def cancel(self, job_id: int) -> Job:
        """Marca `cancel_requested`; si aún estaba pendiente, lo deja `cancelado`."""
        with session_scope(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(f"no existe el trabajo {job_id}")
            if job.status in ESTADOS_FINALES:
                session.expunge(job)
                return job
            job.cancel_requested = True
            if job.status == "pendiente":
                job.status = "cancelado"
                job.finished_at = now_iso()
                job.message = "cancelado antes de empezar"
            session.add(job)
        job = self.get(job_id)
        if job.status in ESTADOS_FINALES:
            self._soltar_clave(job_id)
        self._publish_job(job)
        return job

    def reconciliar_huerfanos(self) -> list[int]:
        """Al arrancar, deja en un estado final los trabajos que quedaron `pendiente` o
        `en_curso`.

        Las colas viven en memoria: tras un cierre, esos trabajos no los ejecutará nadie.
        Pasan a `cancelado`, con su evento `job.cancelado` del sistema, y las revisiones de
        dossier vivas pasan a `cancelada`; así nada se queda «en curso» para siempre ni
        bloquea una revisión nueva. Devuelve los ids de los trabajos reconciliados.
        """
        motivo = "Vigía se cerró antes de que el trabajo terminara"
        ahora = now_iso()
        ids: list[int] = []
        with session_scope(self.engine) as session:
            vivos = session.exec(
                select(Job).where(Job.status.in_(("pendiente", "en_curso")))  # type: ignore[attr-defined]
            ).all()
            for job in vivos:
                previo = job.status
                job.status = "cancelado"
                job.cancel_requested = True
                job.finished_at = ahora
                job.message = f"cancelado: {motivo}"
                session.add(job)
                ids.append(int(job.id or 0))
                record_event(
                    session,
                    actor_kind=ACTOR_SISTEMA[0],
                    actor_id=ACTOR_SISTEMA[1],
                    action="job.cancelado",
                    object_type="job",
                    object_id=job.id,
                    project_id=job.project_id,
                    before={"status": previo},
                    after={"status": "cancelado"},
                    motivo=motivo,
                    correlation_id=job.correlation_id,
                    job_id=job.id,
                    bus=self.bus,
                )
            revisiones = session.exec(
                select(DossierReview).where(
                    DossierReview.status.in_(("pendiente", "en_curso"))  # type: ignore[attr-defined]
                )
            ).all()
            for revision in revisiones:
                revision.status = "cancelada"
                revision.error = f"cancelada: {motivo}"
                revision.finished_at = ahora
                session.add(revision)
        return ids

    def queue_counts(self, session: Session) -> dict[str, dict[str, int]]:
        """Pendientes y en curso por cola, leídos de la tabla `job` (para /health)."""
        counts = {nombre: {"pendientes": 0, "en_curso": 0} for nombre in COLAS}
        filas = session.exec(
            select(Job.queue, Job.status).where(Job.status.in_(("pendiente", "en_curso")))  # type: ignore[attr-defined]
        ).all()
        for cola, estado in filas:
            if cola not in counts:
                counts[cola] = {"pendientes": 0, "en_curso": 0}
            clave = "pendientes" if estado == "pendiente" else "en_curso"
            counts[cola][clave] += 1
        return counts

    # -- interno ----------------------------------------------------------

    def _worker(self, queue_name: str) -> None:
        cola = self._queues[queue_name]
        while not self._parar.is_set():
            item = cola.get()
            if item is None:
                break
            job_id, fn, params, correlation_id = item
            try:
                self._run(job_id, fn, params, correlation_id)
            except Exception:  # noqa: BLE001  # pragma: no cover - salvaguarda del hilo de ejecución de ejecución
                _log.exception("fallo no controlado en la cola %s", queue_name)

    def _run(
        self,
        job_id: int,
        fn: Callable[..., Any],
        params: dict[str, Any],
        correlation_id: str | None,
    ) -> None:
        """Ejecuta el trabajo con su propia sesión y actualiza estado y progreso."""
        with session_scope(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            if job.cancel_requested or job.status in ESTADOS_FINALES:
                return
            job.status = "en_curso"
            job.started_at = now_iso()
            session.add(job)
        self._publish_job(self.get(job_id))

        estado = "terminado"
        resultado: Any = None
        error: str | None = None
        try:
            with session_scope(self.engine) as session:
                ctx = JobContext(
                    job_id=job_id,
                    engine=self.engine,
                    session=session,
                    bus=self.bus,
                    correlation_id=correlation_id,
                )
                resultado = fn(ctx, session, **params)
        except JobCancelled as exc:
            estado = "cancelado"
            error = str(exc) or "cancelado"
            _log.info("trabajo %s cancelado: %s", job_id, error)
        except Exception as exc:  # noqa: BLE001
            estado = "error"
            _log.exception("trabajo %s terminado con error", job_id)
            error = self._texto_error(job_id, exc)

        with session_scope(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = estado
            job.error = error if estado == "error" else None
            job.finished_at = now_iso()
            if estado == "terminado":
                job.progress = 1.0
                job.result_json = _serializable(resultado) if resultado is not None else None
            elif estado == "cancelado":
                job.message = error or "cancelado"
            session.add(job)
        self._soltar_clave(job_id)
        self._publish_job(self.get(job_id))

    def _soltar_clave(self, job_id: int) -> None:
        """Quita las claves de deduplicación de un trabajo que ya terminó."""
        with self._lock_dedup:
            for clave in [c for c, j in self._claves.items() if j == job_id]:
                del self._claves[clave]

    def _texto_error(self, job_id: int, exc: BaseException) -> str:
        """`job.error` limpio: ver `errores.texto_error_trabajo`."""
        try:
            tipo = self.get(job_id).kind
        except Exception:  # noqa: BLE001 - sin tipo, el texto genérico sirve igual
            tipo = ""
        return texto_error_trabajo(exc, tipo)

    def _publish_job(self, job: Job) -> None:
        """Publica el trabajo completo: `result` y `error`, no solo el progreso.

        Sin esto, quien sigue el trabajo por SSE mientras corre (`useJob`) nunca ve
        el resultado en el mensaje que lo cierra: tenía que releer `GET /jobs/{id}`.
        `job.result_json` ya viene serializable (`_serializable` lo deja así al
        guardarlo en `_run`), así que pasa tal cual por `json.dumps`.
        """
        self.bus.publish(
            {
                "type": "job",
                "job_id": job.id,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "result": job.result_json,
                "error": job.error,
            }
        )


def _serializable(valor: Any) -> Any:
    """Deja pasar lo que SQLite puede guardar como JSON; el resto va como texto."""
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    if isinstance(valor, dict):
        return {str(k): _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_serializable(v) for v in valor]
    return str(valor)
