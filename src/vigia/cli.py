"""CLI de Vigía: `serve` (arranque real), `eval` y `demo run`/`demo list`
(orquestación headless del motor, ver `vigia.core.engine`), `export`
(`events`, `openapi` y `report`, sin servidor), y los
clientes: `mcp` (delega en
`vigia.mcp.server.main`) y `shutdown` (`POST /shutdown` con el token del lock).
"""

from __future__ import annotations

import argparse
import ctypes
import io
import json
import logging
import signal
import sqlite3
import sys
import threading
import webbrowser
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
import uvicorn

from vigia.app.preflight import (
    CABECERA_PRUEBA,
    CABECERA_RETO,
    DOMINIO_APAGADO,
    LockFile,
    calcular_prueba,
    find_free_port,
    generate_token,
    import_with_retry,
    nuevo_reto,
    port_is_free,
)
from vigia.app.settings import Settings, prepare_cache_env

HEALTH_TIMEOUT_S = 20.0
MOTOR_MODULES = ["numpy", "pandas", "scipy", "sklearn"]
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vigia", description="Vigía: vigilancia de modelos de IA en producción")
    from vigia import __version__

    parser.add_argument("--version", action="version", version=f"vigia {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Arranca el servidor local de Vigía")
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--data-dir", type=str, default=None)
    serve.add_argument("--host", type=str, default=None)

    ev = sub.add_parser("eval", help="Evalúa un fichero de payload/feedback en los tres monitores")
    ev.add_argument("--payload", type=str, required=True, help="JSON de payload (formato del harness) o CSV/JSON tabular")
    ev.add_argument("--feedback", type=str, required=True, help="JSON de feedback con predicción y etiqueta")
    ev.add_argument("--mapping", type=str, default=None, help="JSON con un ColumnMapping; por defecto el mapeo del harness")
    ev.add_argument("--baseline-payload", type=str, default=None, help="payload del baseline congelado (deriva)")
    ev.add_argument("--baseline-feedback", type=str, default=None, help="feedback del baseline congelado")
    ev.add_argument("--min-records", type=int, default=None, help="ventana de equidad (por defecto 200)")
    ev.add_argument("--min-feedback", type=int, default=None, help="mínimo de filas con etiqueta para calidad (por defecto 100)")
    ev.add_argument("--out", type=str, default=None, help="fichero JSON de salida (si no, stdout)")
    ev.add_argument("--quiet", action="store_true", help="solo el JSON, sin resumen en texto")

    demo = sub.add_parser("demo", help="Ejecuta un guion de demo en modo headless")
    demo_sub = demo.add_subparsers(dest="demo_command", required=True)
    demo_run = demo_sub.add_parser("run", help="Ejecuta un guion")
    demo_run.add_argument("scenario", type=str, help="clave del guion (ver `vigia demo list`)")
    demo_run.add_argument("--source", choices=["canned", "generate"], default="canned", help="JSON enlatados o regeneración con las semillas")
    demo_run.add_argument("--with-human", action="store_true", help="simula decisiones humanas y evalúa las cruzadas")
    demo_run.add_argument("--out", type=str, default=None, help="carpeta para el JSON por fase y el resumen")
    demo_run.add_argument("--json", action="store_true", help="resumen JSON en vez de tabla")
    demo_sub.add_parser("list", help="Lista los guiones disponibles")

    export = sub.add_parser("export", help="Exporta el diario de eventos o el esquema OpenAPI")
    export_sub = export.add_subparsers(dest="export_command", required=True)

    export_events = export_sub.add_parser("events", help="Exporta el diario de eventos (evidencias)")
    export_events.add_argument("--since", type=str, required=True, help="ISO 8601, límite inferior")
    export_events.add_argument("--until", type=str, default=None, help="ISO 8601, límite superior")
    export_events.add_argument("--format", choices=["json", "html"], default="json")
    export_events.add_argument("--out", type=str, required=True, help="fichero de salida")
    export_events.add_argument("--data-dir", type=str, default=None, help="carpeta de datos con vigia.db")

    export_openapi = export_sub.add_parser("openapi", help="Exporta el esquema OpenAPI de la API")
    export_openapi.add_argument("--out", type=str, required=True, help="fichero JSON de salida")

    # Informe HTML de una revisión de dossier, sin servidor.
    export_report = export_sub.add_parser("report", help="Exporta el informe HTML de una revisión de dossier")
    export_report.add_argument("--review", type=int, required=True, help="id de la revisión (DossierReview)")
    export_report.add_argument("--out", type=str, required=True, help="fichero HTML de salida")
    export_report.add_argument("--data-dir", type=str, default=None, help="carpeta de datos con vigia.db")

    # El servidor MCP por stdio; los tres flags se reenvían
    # a `vigia.mcp.server.main`, que tiene su propio parser con los mismos nombres.
    mcp_p = sub.add_parser("mcp", help="Arranca el servidor MCP (stdio) para un agente")
    mcp_p.add_argument("--data-dir", type=str, default=None, help="carpeta de datos cuyo lock localiza la API")
    mcp_p.add_argument("--url", type=str, default=None, help="URL de la API; gana al lock")
    mcp_p.add_argument("--actor", type=str, default="claude-code", help="nombre del agente en el diario")

    # Apagado ordenado con el token del lock.
    sh = sub.add_parser("shutdown", help="Apaga el Vigía en marcha sobre una carpeta de datos")
    sh.add_argument("--data-dir", type=str, default=None, help="carpeta de datos con vigia.lock")

    return parser


def _wait_for_health(
    base_url: str,
    timeout_s: float,
    servidor_vivo: Callable[[], bool] | None = None,
    servidor_listo: Callable[[], bool] | None = None,
) -> bool:
    """Sondea /api/health hasta que responda 200 o se agote el tiempo.

    Con `servidor_vivo` y `servidor_listo` (el servidor propio de `serve`), un servidor
    que murió corta el sondeo y un 200 solo vale si el servidor propio ya escucha:
    así un proceso ajeno en el mismo puerto no se toma por Vigía.
    """
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if servidor_vivo is not None and not servidor_vivo():
            return False
        try:
            # trust_env=False: el servidor está en loopback y no pasa por el proxy del entorno.
            resp = httpx.get(f"{base_url}/api/health", timeout=1.0, trust_env=False)
            if resp.status_code == 200 and (servidor_listo is None or servidor_listo()):
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    return False


def _install_windows_ctrl_handler(callback) -> None:
    """En Windows, captura también el cierre de consola (X, cierre de ventana) vía ctypes."""
    if sys.platform != "win32":
        return
    HANDLER_TYPE = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

    def _handler(ctrl_type: int) -> int:
        callback()
        return 1

    # Se conserva la referencia para que el GC no la recoja.
    _install_windows_ctrl_handler._handler_ref = HANDLER_TYPE(_handler)  # type: ignore[attr-defined]
    try:
        ctypes.windll.kernel32.SetConsoleCtrlHandler(
            _install_windows_ctrl_handler._handler_ref,
            True,  # type: ignore[attr-defined]
        )
    except (AttributeError, OSError):
        pass


REGISTRO_NOMBRE = "vigia.log"
REGISTRO_MAX_BYTES = 5 * 1024 * 1024
REGISTRO_COPIAS = 3
_MARCA_REGISTRO = "_vigia_registro"


def cerrar_registro() -> None:
    """Quita y cierra los manejadores que puso `configurar_registro`."""
    paquete = logging.getLogger("vigia")
    for manejador in list(paquete.handlers):
        if getattr(manejador, _MARCA_REGISTRO, False):
            paquete.removeHandler(manejador)
            manejador.close()


def configurar_registro(data_dir: Path, *, consola: bool = False) -> Path:
    """Configura el registro del paquete en un solo sitio.

    `vigia.log` en la carpeta de datos es un archivo rotatorio de 5 MB con 3 copias, para
    que no crezca sin tope con los avisos del bus y los errores de los trabajos. Con
    `consola`, los avisos siguen saliendo también por la consola. Es idempotente.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    ruta = data_dir / REGISTRO_NOMBRE
    cerrar_registro()
    paquete = logging.getLogger("vigia")
    archivo = RotatingFileHandler(
        ruta, maxBytes=REGISTRO_MAX_BYTES, backupCount=REGISTRO_COPIAS, encoding="utf-8"
    )
    archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    manejadores: list[logging.Handler] = [archivo]
    if consola and sys.stderr is not None:
        pantalla = logging.StreamHandler(sys.stderr)
        pantalla.setLevel(logging.WARNING)
        manejadores.append(pantalla)
    for manejador in manejadores:
        setattr(manejador, _MARCA_REGISTRO, True)
        paquete.addHandler(manejador)
    # Lo que sale por `print` sin consola llega como INFO (stdout) o WARNING (stderr).
    logging.getLogger("vigia.salida").setLevel(logging.INFO)
    return ruta


class _SalidaALog:
    """Sustituto de `sys.stdout` y `sys.stderr` sin consola: cada línea va al registro rotatorio.

    Así `vigia.log` tiene un solo escritor y rota sin que otro manejador lo tenga abierto
    (en Windows no se puede renombrar un archivo abierto por otro).
    """

    encoding = "utf-8"

    def __init__(self, nivel: int) -> None:
        self._nivel = nivel
        self._pendiente = ""
        self._registro = logging.getLogger("vigia.salida")
        # uvicorn, los hilos de las colas y los `print` escriben a la vez.
        self._cerrojo = threading.Lock()

    def write(self, texto: str) -> int:
        with self._cerrojo:
            *lineas, self._pendiente = (self._pendiente + texto).split("\n")
        for linea in lineas:
            if linea.strip():
                self._registro.log(self._nivel, linea.rstrip("\r"))
        return len(texto)

    def flush(self) -> None:
        with self._cerrojo:
            resto, self._pendiente = self._pendiente, ""
        if resto.strip():
            self._registro.log(self._nivel, resto.rstrip("\r"))

    def close(self) -> None:
        self.flush()
        cerrar_registro()

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def fileno(self) -> int:
        raise io.UnsupportedOperation("fileno")


def redirect_streams_if_headless(data_dir: Path) -> Path | None:
    """Sin consola (pythonw.exe, el lanzador Vigia.cmd) sys.stdout y sys.stderr son None.

    Se redirigen a vigia.log en la carpeta de datos (archivo rotatorio, ver
    `configurar_registro`) para que uvicorn, logging y los print no revienten y para que
    el fallo, si lo hay, quede escrito. Devuelve la ruta del log si hubo redirección,
    None si ya había consola.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    log_path = configurar_registro(Path(data_dir))
    if sys.stdout is None:
        sys.stdout = _SalidaALog(logging.INFO)  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = _SalidaALog(logging.WARNING)  # type: ignore[assignment]
    return log_path


def puerto_guardado(data_dir: Path) -> int | None:
    """Puerto del ajuste `puerto` de la base de datos, o `None` si no hay
    base, no hay ajuste o no se puede leer: el arranque nunca falla por esto."""
    ruta = Path(data_dir) / "vigia.db"
    if not ruta.is_file():
        return None
    try:
        conexion = sqlite3.connect(f"{ruta.as_uri()}?mode=ro", uri=True, timeout=2)
        try:
            fila = conexion.execute("SELECT value_json FROM setting WHERE key = 'puerto'").fetchone()
        finally:
            conexion.close()
        valor = fila[0] if fila else None
        # La columna JSON guarda un número como número y un texto como JSON.
        if isinstance(valor, str | bytes):
            valor = json.loads(valor)
    except (sqlite3.Error, ValueError, OSError):
        return None
    if isinstance(valor, int) and not isinstance(valor, bool) and 1024 <= valor <= 65535:
        return valor
    return None


def puerto_de_arranque(puerto_pedido: int | None, settings: Settings) -> int:
    """`--port` manda; sin él, el puerto guardado en Ajustes; sin él, el de fábrica. Si el
    elegido sin `--port` está ocupado, se busca el siguiente libre."""
    if puerto_pedido:
        return puerto_pedido
    inicio = puerto_guardado(settings.data_dir) or settings.port_start
    return find_free_port(start=inicio, host=settings.host)


def cmd_serve(args: argparse.Namespace) -> int:
    host = args.host or Settings().host
    if host not in LOOPBACK_HOSTS:
        print(
            f"vigia serve: --host {host!r} no vale; solo se admite "
            f"{' o '.join(sorted(LOOPBACK_HOSTS))} (Vigía escucha solo en este equipo)",
            file=sys.stderr,
        )
        return 2
    if args.port and not port_is_free(args.port, host):
        print(
            f"el puerto {args.port} está ocupado: prueba con --port {args.port + 1}",
            file=sys.stderr,
        )
        return 1
    settings = Settings(
        data_dir=Path(args.data_dir) if args.data_dir else Settings().data_dir,
        host=host,
        open_browser=not args.no_browser,
    )
    con_consola = redirect_streams_if_headless(settings.data_dir) is None
    if con_consola:
        configurar_registro(settings.data_dir, consola=True)
    try:
        return _servir(args, settings)
    finally:
        # Sin consola, `sys.stdout` y `sys.stderr` escriben en el registro: se cierra con ellos.
        if con_consola:
            cerrar_registro()


def _servir(args: argparse.Namespace, settings: Settings) -> int:
    """Cuerpo de `vigia serve` tras configurar el registro."""
    prepare_cache_env(settings.data_dir)

    try:
        import_with_retry(MOTOR_MODULES)
    except Exception as exc:  # noqa: BLE001 - se informa y se aborta el arranque
        print(f"Fallo al importar el motor: {exc}", file=sys.stderr)
        return 1

    from vigia.app.main import create_app

    lock = LockFile(settings.data_dir)
    port = puerto_de_arranque(args.port, settings)
    shutdown_token = generate_token()

    server = None
    server_thread = None
    try:
        lock.acquire(port, token=shutdown_token)
        app = create_app(settings)
        app.state.port = port
        app.state.shutdown_token = shutdown_token
        shutdown_event = threading.Event()
        app.state.shutdown_event = shutdown_event

        # use_colors=False: sin consola (pythonw) uvicorn llamaría a sys.stdout.isatty().
        config = uvicorn.Config(
            app, host=settings.host, port=port, log_level="warning", use_colors=False
        )
        server = uvicorn.Server(config)

        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()

        base_url = f"http://{settings.host}:{port}"
        healthy = _wait_for_health(
            base_url,
            HEALTH_TIMEOUT_S,
            servidor_vivo=server_thread.is_alive,
            servidor_listo=lambda: bool(server.started),
        )
        if not healthy:
            # Sin servidor propio no se abre el navegador y el arranque falla.
            print(
                f"Vigía no ha podido arrancar en {base_url}: el servidor propio no escucha "
                "(puerto ocupado o fallo de inicio; mira vigia.log)",
                file=sys.stderr,
            )
            return 1

        print(f"Vigía está en marcha en {base_url}", flush=True)
        if settings.open_browser:
            webbrowser.open(base_url)

        def _shutdown(*_args: object) -> None:
            shutdown_event.set()

        signal.signal(signal.SIGINT, _shutdown)
        _install_windows_ctrl_handler(_shutdown)

        while not shutdown_event.wait(1.0):
            if not server_thread.is_alive():
                print("El servidor de Vigía se ha detenido de forma inesperada", file=sys.stderr)
                return 1
    except Exception as exc:  # noqa: BLE001 - queda en vigia.log y no deja lock huérfano
        print(f"Fallo en el arranque de Vigía: {exc!r}", file=sys.stderr)
        return 1
    finally:
        if server is not None:
            server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=10)
        lock.release()

    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    """`vigia eval`: evalúa un batch (con baseline opcional) en los tres
    monitores y devuelve el resultado por stdout y/o `--out`. Sin traza en errores
    operativos: código 1 y mensaje corto en stderr.
    """
    import json as json_mod

    from vigia.core.engine import History, MonitorSettings, evaluate_batch
    from vigia.core.loaders import load_harness_pair, load_tabular, to_canonical
    from vigia.core.schema import HARNESS_FEEDBACK_MAPPING, ColumnMapping, State, worst

    try:
        if args.mapping:
            mapping = ColumnMapping.model_validate(
                json_mod.loads(Path(args.mapping).read_text(encoding="utf-8"))
            )

            def canonical(feedback_path: str, batch_seq: int) -> object:
                df = load_tabular(feedback_path, mapping)
                return to_canonical(df, mapping, batch_seq=batch_seq, model_version="v1")

        else:
            mapping = HARNESS_FEEDBACK_MAPPING

            def canonical(feedback_path: str, batch_seq: int) -> object:
                return load_harness_pair(
                    args.payload if batch_seq == 1 else args.baseline_payload,
                    feedback_path,
                    batch_seq=batch_seq,
                    model_version="v1",
                )

        history = History()
        if args.baseline_feedback:
            df_baseline = canonical(args.baseline_feedback, 0)
            baseline_seq = history.add_batch(
                df_baseline, mapping=mapping, model_version="v1", phase_label="baseline"
            )
            history.freeze_baseline(baseline_seq, "v1")

        df_main = canonical(args.feedback, 1)
        main_seq = history.add_batch(
            df_main, mapping=mapping, model_version="v1", phase_label="batch"
        )
    except Exception as exc:  # noqa: BLE001 - error operativo, sin traza
        print(f"vigia eval: {exc}", file=sys.stderr)
        return 1

    settings = MonitorSettings.defaults()
    if args.min_records is not None:
        settings.fairness = settings.fairness.model_copy(update={"min_records": args.min_records})
    if args.min_feedback is not None:
        settings.quality = settings.quality.model_copy(update={"min_feedback": args.min_feedback})

    resultados = evaluate_batch(history, main_seq, settings)

    if not args.quiet:
        for clave in ("fairness", "quality", "drift"):
            for m in resultados[clave].measurements:
                valor = f"{m.value:.4f}" if isinstance(m.value, (int, float)) else "n/d"
                intervalo = (
                    f" [{m.interval_low:.4f}, {m.interval_high:.4f}]"
                    if m.interval_low is not None
                    else ""
                )
                print(f"{clave}.{m.metric_key} = {valor}{intervalo} ({m.state.value})")

    from vigia import __version__
    from vigia.core import CORE_VERSION

    salida = {
        "fairness": resultados["fairness"].to_dict(),
        "quality": resultados["quality"].to_dict(),
        "drift": resultados["drift"].to_dict(),
        "core_version": CORE_VERSION,
        "app_version": __version__,
        "config_snapshot": settings.model_dump(mode="json"),
    }
    texto_json = json_mod.dumps(salida, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(texto_json, encoding="utf-8")
    else:
        print(texto_json)

    peor = worst(resultados[c].worst_state for c in ("fairness", "quality", "drift"))
    if peor == State.alerta:
        return 3
    if peor == State.inestable:
        return 4
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """`vigia demo run <guion>` y `vigia demo list`, en modo headless (sin
    servidor ni BD): orquesta `run_scenario` y vuelca texto o JSON.
    """
    import json as json_mod

    from vigia.sim.scenarios import list_scenarios

    if args.demo_command == "list":
        for s in list_scenarios():
            print(f"{s['key']}: {s['title']} ({s['n_phases']} fases) - {s['description']}")
        return 0

    from vigia.core.engine import run_scenario

    try:
        reports = run_scenario(args.scenario, source=args.source, with_human=args.with_human)
    except KeyError as exc:
        print(f"vigia demo run: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - error operativo, sin traza
        print(f"vigia demo run: {exc}", file=sys.stderr)
        return 1

    resumen = [
        {
            "phase_key": r.phase_key,
            "model_version": r.model_version,
            "n": r.n,
            "orden_manipulado": r.orden_manipulado,
            "states": {k: v.value for k, v in r.states.items()},
            "expected": r.expected,
            "matches_expected": r.matches_expected,
        }
        for r in reports
    ]

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for r, resumen_fase in zip(reports, resumen, strict=True):
            (out_dir / f"{args.scenario}-{r.phase_key}.json").write_text(
                json_mod.dumps(r.model_dump(mode="json"), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        (out_dir / f"{args.scenario}-resumen.json").write_text(
            json_mod.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if args.json:
        print(json_mod.dumps(resumen, indent=2, ensure_ascii=False))
    else:
        for fila in resumen:
            estados = ", ".join(f"{k}={v}" for k, v in fila["states"].items())
            coincide = all(fila["matches_expected"].values())
            print(
                f"{fila['phase_key']:<12} {fila['model_version']:<4} n={fila['n']:<5} "
                f"orden_manipulado={fila['orden_manipulado']!s:<6} {estados} "
                f"esperado={fila['expected']} coincide={coincide}"
            )

    todo_coincide = all(all(fila["matches_expected"].values()) for fila in resumen)
    return 0 if todo_coincide else 5


def cmd_export_events(args: argparse.Namespace) -> int:
    """`vigia export events`: vuelca el diario de una BD existente, sin arrancar el servidor.

    Usa `services/evidence.py` (§9.4): mismo `select_events`/`render_events_html`
    que `GET /events/export`, para que el HTML de la API y el de la CLI sean idénticos.
    """
    import json as json_mod

    from sqlmodel import Session

    from vigia.app.db import make_engine
    from vigia.app.events import event_to_dict
    from vigia.app.services.evidence import render_events_html, select_events
    from vigia.app.settings import Settings

    data_dir = Path(args.data_dir) if args.data_dir else Settings().data_dir
    db_path = data_dir / "vigia.db"
    if not db_path.is_file():
        print(
            f"vigia export events: no existe la base de datos en {db_path}; "
            "arranca antes `vigia serve` sobre esa carpeta de datos",
            file=sys.stderr,
        )
        return 1

    engine = make_engine(db_path)
    try:
        with Session(engine) as session:
            filas = select_events(session, since=args.since, until=args.until)
            if args.format == "html":
                contenido = render_events_html(filas)
            else:
                contenido = json_mod.dumps(
                    [event_to_dict(e) for e in filas], indent=2, ensure_ascii=False
                )
            n_eventos = len(filas)
    finally:
        engine.dispose()

    Path(args.out).write_text(contenido, encoding="utf-8")
    print(f"vigia export events: {n_eventos} eventos escritos en {args.out}")
    return 0


def cmd_export_openapi(args: argparse.Namespace) -> int:
    """`vigia export openapi`: esquema OpenAPI de la app, sin lifespan ni base de datos."""
    import json as json_mod
    import tempfile

    from vigia.app.main import create_app
    from vigia.app.settings import Settings

    with tempfile.TemporaryDirectory(prefix="vigia-openapi-") as tmp_dir:
        settings = Settings(data_dir=Path(tmp_dir))
        app = create_app(settings)
        esquema = app.openapi()

    Path(args.out).write_text(json_mod.dumps(esquema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"vigia export openapi: esquema escrito en {args.out}")
    return 0


def cmd_export_report(args: argparse.Namespace) -> int:
    """`vigia export report`: informe HTML de una revisión de dossier.

    Redibuja la revisión guardada (`services.dossiers.informe_html`): acceso directo a `vigia.db`, sin
    arrancar el servidor (mismo patrón que `cmd_export_events`). `--format` no
    aplica: el informe es siempre HTML.
    """
    from sqlmodel import Session

    from vigia.app.db import make_engine
    from vigia.app.models import DossierReview
    from vigia.app.settings import Settings

    data_dir = Path(args.data_dir) if args.data_dir else Settings().data_dir
    db_path = data_dir / "vigia.db"
    if not db_path.is_file():
        print(f"vigia export report: no existe la base de datos en {db_path}", file=sys.stderr)
        return 1

    engine = make_engine(db_path)
    try:
        with Session(engine) as session:
            review = session.get(DossierReview, args.review)
            if review is None or not review.report_html:
                print(
                    f"vigia export report: revisión {args.review} no encontrada o sin informe "
                    "(¿sigue en curso o terminó en error?)",
                    file=sys.stderr,
                )
                return 1
            from vigia.app.services.dossiers import informe_html

            # Redibujado al leer, como la API: español y tema actual.
            contenido = informe_html(session, review)
    finally:
        engine.dispose()

    Path(args.out).write_text(contenido, encoding="utf-8", newline="")
    print(f"vigia export report: informe de la revisión {args.review} escrito en {args.out}")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """`vigia mcp`: reenvía `--data-dir`, `--url` y `--actor` a `vigia.mcp.server.main`.

    Import diferido: el paquete `vigia.mcp` arrastra `mcp` y `httpx`, que no
    hacen falta para el resto de subcomandos.
    """
    try:
        from vigia.mcp.server import main as mcp_main
    except ImportError:
        print("vigia mcp: el servidor MCP no está instalado en este entorno", file=sys.stderr)
        return 2

    argv: list[str] = []
    if args.data_dir is not None:
        argv += ["--data-dir", args.data_dir]
    if args.url is not None:
        argv += ["--url", args.url]
    argv += ["--actor", args.actor]
    return mcp_main(argv)


def cmd_shutdown(args: argparse.Namespace) -> int:
    """`vigia shutdown`: `POST /shutdown` con el token del lock.

    `0` apagado solicitado; `1` no hay lock o está obsoleto (nadie que apagar);
    `2` conexión fallida o rechazo del servidor (token del lock desactualizado).
    Sin reintentos: un apagado es una orden, no un sondeo.
    """
    data_dir = Path(args.data_dir) if args.data_dir else Settings().data_dir
    lock = LockFile(data_dir)
    data = lock.read()
    if data is None or lock.is_stale():
        print(f"vigia shutdown: no hay Vigía en marcha en {data_dir}", file=sys.stderr)
        return 1
    token = data.get("token") or ""
    if not token:
        print("vigia shutdown: el lock no trae token; no se envía nada", file=sys.stderr)
        return 2
    # El token no sale de este proceso: se manda una prueba firmada con él sobre un reto
    # nuevo, que un servidor ajeno no puede reutilizar.
    reto = nuevo_reto()
    try:
        resp = httpx.post(
            f"http://127.0.0.1:{data['port']}/api/shutdown",
            headers={
                CABECERA_RETO: reto,
                CABECERA_PRUEBA: calcular_prueba(token, reto, DOMINIO_APAGADO),
            },
            timeout=5.0,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        print(f"vigia shutdown: no se pudo contactar al servidor: {exc}", file=sys.stderr)
        return 2
    if resp.status_code != 200:
        print(f"vigia shutdown: rechazado ({resp.status_code}): {resp.text}", file=sys.stderr)
        return 2
    print("vigia shutdown: apagado solicitado")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    if args.export_command == "events":
        return cmd_export_events(args)
    if args.export_command == "report":
        return cmd_export_report(args)
    return cmd_export_openapi(args)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        return cmd_serve(args)
    if args.command == "eval":
        return cmd_eval(args)
    if args.command == "demo":
        return cmd_demo(args)
    if args.command == "mcp":
        return cmd_mcp(args)
    if args.command == "shutdown":
        return cmd_shutdown(args)
    return cmd_export(args)
