"""Migraciones de esquema como funciones Python numeradas.

`MIGRATIONS` es la lista ordenada `(version, nombre, fn)`. `migrate` aplica las
pendientes en orden dentro de una transacción por migración y registra la
versión en `schema_version`. Si la base de datos ya tenía una versión
registrada, antes de aplicar nada copia el fichero a
`<data_dir>/backups/vigia.db.<version_origen>.<timestamp>.bak`.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlmodel import SQLModel

from vigia.app import models as _models  # noqa: F401  (registra las tablas en la metadata)
from vigia.app.models import now_iso

__all__ = ["MIGRATIONS", "current_version", "migrate", "target_version"]

_log = logging.getLogger("vigia.app.migrations")

_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS event_append_only_update
BEFORE UPDATE ON event
BEGIN
    SELECT RAISE(ABORT, 'event es append-only');
END
"""

_TRIGGER_DELETE = """
CREATE TRIGGER IF NOT EXISTS event_append_only_delete
BEFORE DELETE ON event
BEGIN
    SELECT RAISE(ABORT, 'event es append-only');
END
"""

_CREA_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL PRIMARY KEY,
    applied_at VARCHAR NOT NULL
)
"""

# Campos de `sim.scenarios.Phase` que se guardan en `demo_scenario.phases_json`:
# los serializables, sin generadores ni permutaciones.
_CAMPOS_FASE = (
    "key",
    "title",
    "kind",
    "model_version",
    "freeze_baseline",
    "orden_manipulado",
    "motivo_manipulacion",
    "expected",
    "explain_global",
    "narrative",
)


def _fase_a_dict(phase: object) -> dict:
    """Proyecta una `Phase` a los campos serializables de `phases_json`."""
    return {campo: getattr(phase, campo) for campo in _CAMPOS_FASE}


def _sembrar_guiones(conn: Connection) -> None:
    """Siembra `demo_scenario` desde `vigia.sim.scenarios.SCENARIOS`. Idempotente por `key`."""
    from vigia.sim.scenarios import SCENARIOS

    existentes = {
        fila[0] for fila in conn.execute(text("SELECT key FROM demo_scenario")).fetchall()
    }
    for key, scenario in SCENARIOS.items():
        if key in existentes:
            continue
        conn.execute(
            text(
                "INSERT INTO demo_scenario "
                "(key, title, domain, description, phases_json, default_params_json) "
                "VALUES (:key, :title, :domain, :description, :phases, :params)"
            ),
            {
                "key": key,
                "title": scenario.title,
                "domain": scenario.domain,
                "description": scenario.description,
                "phases": json.dumps(
                    [_fase_a_dict(p) for p in scenario.phases], ensure_ascii=False
                ),
                "params": json.dumps(scenario.default_params, ensure_ascii=False),
            },
        )


def _migracion_1(conn: Connection) -> None:
    """Esquema inicial: tablas de §2, triggers append-only de `event` y guiones de demo."""
    SQLModel.metadata.create_all(conn)
    conn.execute(text(_TRIGGER_UPDATE))
    conn.execute(text(_TRIGGER_DELETE))
    _sembrar_guiones(conn)


def _migracion_2(conn: Connection) -> None:
    """Añade `project.description`: base nueva ya la trae
    `create_all`; esta migración cubre la base existente en la versión 1."""
    columnas = {fila[1] for fila in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
    if "description" not in columnas:
        conn.execute(text("ALTER TABLE project ADD COLUMN description VARCHAR"))


def _migracion_3(conn: Connection) -> None:
    """Añade `project.deidentified`, `project.explain_auto` y `project.explain_method`:
    base nueva ya las trae `create_all`; esta migración cubre
    las bases existentes en versión 1 o 2."""
    columnas = {fila[1] for fila in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
    if "deidentified" not in columnas:
        conn.execute(text("ALTER TABLE project ADD COLUMN deidentified BOOLEAN NOT NULL DEFAULT 0"))
    if "explain_auto" not in columnas:
        conn.execute(text("ALTER TABLE project ADD COLUMN explain_auto BOOLEAN NOT NULL DEFAULT 1"))
    if "explain_method" not in columnas:
        conn.execute(
            text(
                "ALTER TABLE project ADD COLUMN explain_method VARCHAR NOT NULL DEFAULT 'permutation'"
            )
        )


def _migracion_4(conn: Connection) -> None:
    """Quita `project.deidentified`: Vigía deja de
    pseudonimizar, la columna sobra. SQLite del Python 3.13 admite
    `ALTER TABLE ... DROP COLUMN` de forma nativa (>= 3.35); `create_all` no
    la crea en una base nueva porque `models.Project` ya no la declara."""
    columnas = {fila[1] for fila in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
    if "deidentified" in columnas:
        conn.execute(text("ALTER TABLE project DROP COLUMN deidentified"))


def _migracion_5(conn: Connection) -> None:
    """Añade `project.deployment_stage`: base nueva ya la
    trae `create_all`; esta migración cubre las bases existentes. Los proyectos
    ya marcados `is_demo` pasan a `demo`, el resto se queda en `desarrollo`."""
    columnas = {fila[1] for fila in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
    if "deployment_stage" not in columnas:
        conn.execute(
            text(
                "ALTER TABLE project ADD COLUMN deployment_stage VARCHAR "
                "NOT NULL DEFAULT 'desarrollo'"
            )
        )
    conn.execute(text("UPDATE project SET deployment_stage='demo' WHERE is_demo=1"))


def _migracion_6(conn: Connection) -> None:
    """Añade `monitor.protocol_json`: los cinco hitos del
    protocolo de respuesta, editables por monitor. Base nueva ya la trae
    `create_all`; en las existentes se crea la columna y todo monitor sin
    protocolo recibe la plantilla de `content/protocolo-hitos.json`."""
    from vigia.app.content_loader import protocolo_hitos_plantilla

    columnas = {fila[1] for fila in conn.execute(text("PRAGMA table_info(monitor)")).fetchall()}
    if "protocol_json" not in columnas:
        conn.execute(text("ALTER TABLE monitor ADD COLUMN protocol_json JSON"))
    plantilla = json.dumps(protocolo_hitos_plantilla(), ensure_ascii=False)
    conn.execute(
        text("UPDATE monitor SET protocol_json=:plantilla WHERE protocol_json IS NULL"),
        {"plantilla": plantilla},
    )


def _migracion_7(conn: Connection) -> None:
    """Añade `outcome.baseline` y
    `outcome.target`, nulos, que la capa de valor rellenará después; base nueva
    ya los trae `create_all`. Retira `project.hmac_salt`,
    con el mismo `DROP COLUMN` nativo de `_migracion_4`."""
    columnas = {fila[1] for fila in conn.execute(text("PRAGMA table_info(outcome)")).fetchall()}
    for columna in ("baseline", "target"):
        if columna not in columnas:
            conn.execute(text(f"ALTER TABLE outcome ADD COLUMN {columna} FLOAT"))
    columnas = {fila[1] for fila in conn.execute(text("PRAGMA table_info(project)")).fetchall()}
    if "hmac_salt" in columnas:
        conn.execute(text("ALTER TABLE project DROP COLUMN hmac_salt"))


def _migracion_8(conn: Connection) -> None:
    """Crea `dossier` y `dossier_review`: mismo
    patrón que `_migracion_1` (`create_all` sobre la metadata), acotado a las
    dos tablas; idempotente en una base nueva porque `models.py` ya las
    declara y `create_all` no toca las que existen."""
    from vigia.app.models import Dossier, DossierReview

    SQLModel.metadata.create_all(conn, tables=[Dossier.__table__, DossierReview.__table__])


def _migracion_9(conn: Connection) -> None:
    """Crea `risk` y `risk_movement`, como
    la 8."""
    from vigia.app.models import Risk, RiskMovement

    SQLModel.metadata.create_all(conn, tables=[Risk.__table__, RiskMovement.__table__])


def _columnas(conn: Connection, tabla: str) -> set[str]:
    return {fila[1] for fila in conn.execute(text(f"PRAGMA table_info({tabla})")).fetchall()}


def _migracion_10(conn: Connection) -> None:
    """Añade al proyecto la plantilla de
    mapeo y `acepta_feedback`, al dataset el dialecto del CSV
    y a la versión el método del intervalo de equidad y los
    campos del artefacto ejecutable.
    Todo nulo o con el valor de antes: ningún proyecto existente cambia de
    comportamiento (los anteriores siguen en `ventanas` y aceptan feedback).
    Base nueva ya lo trae `create_all`."""
    # Una tabla que no existe (bases parciales de los tests) no se toca.
    columnas = _columnas(conn, "project")
    if columnas and "mapping_template_json" not in columnas:
        conn.execute(text("ALTER TABLE project ADD COLUMN mapping_template_json JSON"))
    if columnas and "acepta_feedback" not in columnas:
        conn.execute(
            text("ALTER TABLE project ADD COLUMN acepta_feedback BOOLEAN NOT NULL DEFAULT 1")
        )
    columnas = _columnas(conn, "dataset")
    if columnas and "dialect_json" not in columnas:
        conn.execute(text("ALTER TABLE dataset ADD COLUMN dialect_json JSON"))
    columnas = _columnas(conn, "model_version")
    if not columnas:
        return
    if "fairness_interval_method" not in columnas:
        conn.execute(
            text(
                "ALTER TABLE model_version ADD COLUMN fairness_interval_method VARCHAR "
                "NOT NULL DEFAULT 'ventanas'"
            )
        )
    for columna, tipo in (
        ("artifact_path", "VARCHAR"),
        ("artifact_kind", "VARCHAR"),
        ("artifact_sha256", "VARCHAR"),
        ("artifact_inputs_json", "JSON"),
        ("artifact_uploaded_at", "VARCHAR"),
    ):
        if columna not in columnas:
            conn.execute(text(f"ALTER TABLE model_version ADD COLUMN {columna} {tipo}"))


def _migracion_13(conn: Connection) -> None:
    """clases, probabilidades por clase y clases del diario de uso.
    `ADD COLUMN` nulo guardado por `_columnas` (patrón de la 10); las filas
    viejas quedan en nulo y `task_type` no se toca. Una tabla que no
    existe (bases parciales de los tests) no se toca. Base nueva ya lo trae
    `create_all`."""
    for tabla, columna, tipo in (
        ("record", "prediction_class", "VARCHAR"),
        ("record", "label_class", "VARCHAR"),
        ("record", "probabilities_json", "JSON"),
        ("project", "classes_json", "JSON"),
        ("usage_log", "human_class", "VARCHAR"),
        ("usage_log", "model_class", "VARCHAR"),
        ("usage_log", "truth_class", "VARCHAR"),
    ):
        columnas = _columnas(conn, tabla)
        if columnas and columna not in columnas:
            conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}"))


def _migracion_14(conn: Connection) -> None:
    """valores continuos de la regresión, unidad y rango favorable
    del proyecto y cifras del diario de uso. `ADD COLUMN` nulo guardado por
    `_columnas` (patrón de la 13); las filas viejas quedan en nulo y `task_type`
    no se toca. Una tabla que no existe no se toca."""
    for tabla, columna, tipo in (
        ("record", "prediction_value", "REAL"),
        ("record", "label_value", "REAL"),
        ("project", "target_unit", "VARCHAR"),
        ("project", "favorable_ranges_json", "JSON"),
        ("usage_log", "human_value", "REAL"),
        ("usage_log", "model_value", "REAL"),
        ("usage_log", "truth_value", "REAL"),
    ):
        columnas = _columnas(conn, tabla)
        if columnas and columna not in columnas:
            conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}"))


def _migracion_15(conn: Connection) -> None:
    """clave única `(project_id, period, metric_key, source)` en `outcome`,
    que habilita el upsert atómico. Si una base vieja tiene duplicados (subidas
    concurrentes anteriores a la clave), conserva la fila más reciente de cada
    clave antes de crear el índice. La copia previa de la base la hace `migrate`
    para todas las migraciones pendientes. Una tabla que no existe no se toca."""
    if not _columnas(conn, "outcome"):
        return
    conn.execute(
        text(
            "DELETE FROM outcome WHERE id NOT IN "
            "(SELECT MAX(id) FROM outcome GROUP BY project_id, period, metric_key, source)"
        )
    )
    conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_outcome_clave "
            "ON outcome (project_id, period, metric_key, source)"
        )
    )


_TABLAS_AUTOINCREMENT = ("dataset", "batch", "evaluation", "alert")


def _ddl_con_autoincrement(sql: str, tabla: str) -> str:
    """DDL de `tabla` (tal como está en `sqlite_master`) con el `id` como
    `INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT` y el resto igual (columnas,
    FK). Es la misma forma que SQLAlchemy emite con `sqlite_autoincrement`.
    Se parte del DDL vivo y no del modelo para no arrastrar columnas que
    todavía no ha añadido una migración posterior."""
    nuevo, n_id = re.subn(
        r"(\n\s*id INTEGER NOT NULL),", r"\1 PRIMARY KEY AUTOINCREMENT,", sql, count=1
    )
    if n_id:
        nuevo, n_pk = re.subn(r"\n\s*PRIMARY KEY \(id\),", "", nuevo, count=1)
        if n_pk == 0:
            nuevo, n_pk = re.subn(r",\s*PRIMARY KEY \(id\)", "", nuevo, count=1)
    else:
        # Tablas a mano de las bases parciales de los tests: `id INTEGER PRIMARY KEY`.
        nuevo, n_id = re.subn(
            r"\bid INTEGER PRIMARY KEY\b", "id INTEGER PRIMARY KEY AUTOINCREMENT", sql, count=1
        )
        n_pk = n_id
    nuevo, n_nombre = re.subn(
        rf'^CREATE TABLE\s+"?{tabla}"?\s*\(', f"CREATE TABLE {tabla}_nueva (", nuevo, count=1
    )
    if not (n_id and n_pk and n_nombre):
        raise RuntimeError(f"migración 11: no reconozco el DDL de la tabla {tabla}:\n{sql}")
    return nuevo


def _recrear_con_autoincrement(conn: Connection, tabla: str) -> bool:
    """Patrón de SQLite para cambiar una tabla: crea `<tabla>_nueva`, copia,
    borra la vieja, renombra y vuelve a crear los índices. Exige
    `foreign_keys=OFF` (el llamador lo garantiza): con las FK activas el
    `DROP TABLE` borraría en cascada los hijos. Devuelve si recreó."""
    fila = conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:t"), {"t": tabla}
    ).fetchone()
    if fila is None or "AUTOINCREMENT" in (fila[0] or "").upper():
        return False
    ddl = _ddl_con_autoincrement(fila[0], tabla)
    indices = [
        f[0]
        for f in conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=:t AND sql IS NOT NULL"),
            {"t": tabla},
        ).fetchall()
    ]
    columnas = ", ".join(f'"{c}"' for c in sorted(_columnas(conn, tabla)))
    conn.exec_driver_sql(f"DROP TABLE IF EXISTS {tabla}_nueva")
    conn.exec_driver_sql(ddl)
    conn.exec_driver_sql(f"INSERT INTO {tabla}_nueva ({columnas}) SELECT {columnas} FROM {tabla}")
    conn.exec_driver_sql(f"DROP TABLE {tabla}")
    conn.exec_driver_sql(f"ALTER TABLE {tabla}_nueva RENAME TO {tabla}")
    for sql_indice in indices:
        conn.exec_driver_sql(sql_indice)
    return True


def _sembrar_secuencia(conn: Connection, tabla: str) -> None:
    """`sqlite_sequence` con el máximo actual: el siguiente id nunca coincide
    con uno que ya existe ni, desde ahora, con uno borrado."""
    maximo = conn.execute(text(f"SELECT MAX(id) FROM {tabla}")).scalar()
    if maximo is None:
        return
    actual = conn.execute(
        text("SELECT seq FROM sqlite_sequence WHERE name=:t"), {"t": tabla}
    ).scalar()
    if actual is None:
        conn.execute(
            text("INSERT INTO sqlite_sequence (name, seq) VALUES (:t, :m)"),
            {"t": tabla, "m": maximo},
        )
    elif actual < maximo:
        conn.execute(
            text("UPDATE sqlite_sequence SET seq=:m WHERE name=:t"), {"t": tabla, "m": maximo}
        )


def _rellenar_origen_alertas(conn: Connection) -> None:
    """`origin_*` de las alertas anteriores, desde la primera entrada de
    `history_json` cuya evaluación siga viva. Sin ella se quedan nulos."""
    filas = conn.execute(
        text(
            "SELECT id, history_json FROM alert "
            "WHERE origin_evaluation_id IS NULL AND origin_batch_id IS NULL "
            "AND history_json IS NOT NULL"
        )
    ).fetchall()
    for alerta_id, crudo in filas:
        try:
            historial = json.loads(crudo) if isinstance(crudo, str) else crudo
        except ValueError:
            continue
        for entrada in historial or []:
            evaluacion_id = entrada.get("evaluation_id") if isinstance(entrada, dict) else None
            if evaluacion_id is None:
                continue
            viva = conn.execute(
                text("SELECT id, batch_id FROM evaluation WHERE id=:e"), {"e": evaluacion_id}
            ).fetchone()
            if viva is None:
                continue
            conn.execute(
                text("UPDATE alert SET origin_evaluation_id=:e, origin_batch_id=:b WHERE id=:a"),
                {"e": viva[0], "b": viva[1], "a": alerta_id},
            )
            break


def _migracion_11(conn: Connection) -> None:
    """`dataset`, `batch`,
    `evaluation` y `alert` pasan a `AUTOINCREMENT` para que un id borrado no se
    reutilice, y `alert` suma `origin_batch_id`, `origin_evaluation_id`
    y `retired_reason`. `record` no se recrea.

    Recrear tablas exige `foreign_keys=OFF` y ese PRAGMA no cambia dentro de
    una transacción, así que esta migración gestiona la suya: apaga las FK,
    abre y cierra su propia transacción y las vuelve a encender aunque falle.
    Es idempotente (lo ya recreado se salta), de modo que un fallo tras el
    `COMMIT` y antes de anotar la versión se repite sin daño.
    Base nueva: `create_all` ya la trae y solo se rellena `sqlite_sequence`."""
    presentes = [t for t in _TABLAS_AUTOINCREMENT if _columnas(conn, t)]
    if not presentes:
        return
    if "alert" in presentes:
        columnas = _columnas(conn, "alert")
        for columna, tipo in (
            ("origin_batch_id", "INTEGER"),
            ("origin_evaluation_id", "INTEGER"),
            ("retired_reason", "VARCHAR"),
        ):
            if columna not in columnas:
                conn.exec_driver_sql(f"ALTER TABLE alert ADD COLUMN {columna} {tipo}")
    raw = conn.connection.driver_connection
    if raw.in_transaction:
        raise RuntimeError("migración 11: hay una transacción abierta, no se pueden apagar las FK")
    conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        if conn.exec_driver_sql("PRAGMA foreign_keys").scalar():
            raise RuntimeError("migración 11: no se pudieron apagar las claves foráneas")
        conn.exec_driver_sql("BEGIN")
        try:
            for tabla in presentes:
                _recrear_con_autoincrement(conn, tabla)
                _sembrar_secuencia(conn, tabla)
            if "alert" in presentes and "evaluation" in presentes:
                _rellenar_origen_alertas(conn)
            huerfanas = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if huerfanas:
                _log.warning("migración 11: %s filas con clave foránea rota", len(huerfanas))
            conn.exec_driver_sql("COMMIT")
        except BaseException:
            if raw.in_transaction:
                conn.exec_driver_sql("ROLLBACK")
            raise
    finally:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def _migracion_12(conn: Connection) -> None:
    """Ciclo de vida: `project`
    pasa a `AUTOINCREMENT` para que un proyecto nuevo no herede el id de uno
    borrado y con él su diario (`event` no tiene FK). Misma técnica y mismas
    garantías que la 11: apaga las FK, recrea la tabla conservando datos e ids,
    las vuelve a encender aunque falle y es idempotente.
    La secuencia parte del mayor id que haya en `project` o en `event`: así
    tampoco se reutilizan los ids de proyectos ya borrados que dejaron eventos."""
    if not _columnas(conn, "project"):
        return
    raw = conn.connection.driver_connection
    if raw.in_transaction:
        raise RuntimeError("migración 12: hay una transacción abierta, no se pueden apagar las FK")
    conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        if conn.exec_driver_sql("PRAGMA foreign_keys").scalar():
            raise RuntimeError("migración 12: no se pudieron apagar las claves foráneas")
        conn.exec_driver_sql("BEGIN")
        try:
            _recrear_con_autoincrement(conn, "project")
            _sembrar_secuencia(conn, "project")
            if _columnas(conn, "event"):
                mayor_evento = conn.execute(text("SELECT MAX(project_id) FROM event")).scalar()
                if mayor_evento is not None:
                    actual = conn.execute(
                        text("SELECT seq FROM sqlite_sequence WHERE name='project'")
                    ).scalar()
                    if actual is None:
                        conn.execute(
                            text("INSERT INTO sqlite_sequence (name, seq) VALUES ('project', :m)"),
                            {"m": mayor_evento},
                        )
                    elif actual < mayor_evento:
                        conn.execute(
                            text("UPDATE sqlite_sequence SET seq=:m WHERE name='project'"),
                            {"m": mayor_evento},
                        )
            huerfanas = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if huerfanas:
                _log.warning("migración 12: %s filas con clave foránea rota", len(huerfanas))
            conn.exec_driver_sql("COMMIT")
        except BaseException:
            if raw.in_transaction:
                conn.exec_driver_sql("ROLLBACK")
            raise
    finally:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")


MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "esquema inicial", _migracion_1),
    (2, "descripción del proyecto", _migracion_2),
    (3, "desidentificación y explicación automática", _migracion_3),
    (4, "sin pseudonimización: quita project.deidentified", _migracion_4),
    (5, "estado de despliegue del proyecto", _migracion_5),
    (6, "protocolo de respuesta por monitor", _migracion_6),
    (7, "outcomes con línea base y objetivo; fuera project.hmac_salt", _migracion_7),
    (8, "dossier de auditoría y sus revisiones", _migracion_8),
    (9, "matriz de riesgos: risk y risk_movement", _migracion_9),
    (10, "Plantilla de mapeo, acepta_feedback, intervalo de equidad y artefacto", _migracion_10),
    (11, "Ids que no se reutilizan (AUTOINCREMENT) y origen y retirada de alertas", _migracion_11),
    (12, "ciclo de vida: ids de proyecto que no se reutilizan (AUTOINCREMENT)", _migracion_12),
    (13, "Clases, probabilidades por clase y clases del diario de uso", _migracion_13),
    (14, "Valores continuos, unidad y rango favorable de la regresión", _migracion_14),
    (15, "Clave única de los outcomes (upsert atómico)", _migracion_15),
]


def target_version() -> int:
    """Versión de esquema que espera este código."""
    return max((v for v, _n, _f in MIGRATIONS), default=0)


def _asegura_tabla_versiones(conn: Connection) -> None:
    conn.execute(text(_CREA_SCHEMA_VERSION))


def current_version(engine: Engine) -> int:
    """Versión de esquema registrada en la base de datos (0 si no hay ninguna)."""
    with engine.begin() as conn:
        _asegura_tabla_versiones(conn)
        fila = conn.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
    return int(fila) if fila is not None else 0


def _hay_version_registrada(engine: Engine) -> bool:
    with engine.begin() as conn:
        _asegura_tabla_versiones(conn)
        n = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar()
    return bool(n)


def _copia_previa(db_path: Path, version_origen: int) -> Path | None:
    """Copia la base de datos a `backups/` antes de aplicar migraciones. Devuelve la ruta."""
    if not db_path.is_file():
        return None
    backups = db_path.parent / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    destino = backups / f"{db_path.name}.{version_origen}.{marca}.bak"
    shutil.copy2(db_path, destino)
    _log.info("copia previa de la base de datos en %s", destino)
    return destino


def migrate(engine: Engine, db_path: Path | str | None = None) -> int:
    """Aplica las migraciones pendientes y devuelve la versión final. Es idempotente."""
    if db_path is None:
        db_path = engine.url.database or ""
    db_path = Path(db_path)

    version = current_version(engine)
    pendientes = [m for m in MIGRATIONS if m[0] > version]
    if not pendientes:
        return version

    if _hay_version_registrada(engine):
        _copia_previa(db_path, version)

    for numero, nombre, fn in pendientes:
        with engine.begin() as conn:
            fn(conn)
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :ts)"),
                {"v": numero, "ts": now_iso()},
            )
        _log.info("migración %s aplicada: %s", numero, nombre)
        version = numero
    return version
