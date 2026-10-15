"""Tools de proyectos y plantilla de mapeo. Datasets en `tools_datasets`, monitores en `tools_monitores`."""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from vigia.mcp.client import get_client

# Etapas que `create_project` admite; `demo` solo la pone la demo.
ETAPAS_ADMITIDAS = ("desarrollo", "validacion", "produccion")
# Tipos de tarea que admite el alta.
TIPOS_DE_TAREA = ("binary", "multiclass", "regression")


def _favorable_distinto(de_plantilla: Any, del_parametro: Any) -> bool:
    """Dos favorables distintos, sin contar la forma: `1` y `[1]` son el mismo."""
    if de_plantilla is None:
        return False

    def conjunto(v: Any) -> list[Any]:
        return list(v) if isinstance(v, (list, tuple)) else [v]

    return conjunto(de_plantilla) != conjunto(del_parametro)


def registrar(mcp) -> None:
    @mcp.tool()
    async def list_projects(summary: bool = True, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        """Lista los proyectos de Vigía, opcionalmente con el resumen de la rejilla."""
        return await get_client().get(
            "/projects", params={"summary": summary, "offset": offset, "limit": limit}
        )

    @mcp.tool()
    async def create_project(
        name: str,
        domain: str = "libre",
        favorable_label: int | str | list[int | str] | None = None,
        store_features: bool = True,
        model_kind: str = "external_files",
        deployment_stage: str | None = None,
        mapping_template: dict[str, Any] | None = None,
        acepta_feedback: bool = True,
        fairness_interval_method: str | None = None,
        task_type: str = "binary",
        classes: list[int | str] | None = None,
        target_unit: str | None = None,
        favorable_ranges: list[list[float | None]] | None = None,
    ) -> dict[str, Any]:
        """Crea un proyecto nuevo con su versión v1 activa y sus cinco monitores
        por defecto. `mapping_template` fija de entrada el
        identificador, la clase favorable, las variables y el atributo
        protegido que van a heredar sus datasets; `acepta_feedback=false` si
        el proyecto no va a recibir feedback etiquetado. `fairness_interval_method`
        (`ventanas` o `lote`) es el de la v1; si no se pasa, la API pone
        `lote`.

        `deployment_stage` es OBLIGATORIO y no tiene valor por defecto:
        pregúntalo al usuario o léelo de la ficha del modelo. Valores: `desarrollo`
        (se prueba con datos de trabajo), `validacion` (se valida antes de ponerlo
        en uso) o `produccion` (los lotes que se suben son de uso real). `demo` no
        se admite aquí: solo lo pone la demo (`run_scenario`). Sin él, la tool
        falla antes de llamar a la API.

        TIPO DE TAREA. `task_type`: `binary` (por defecto, dos clases),
        `multiclass` (de 3 a 20 clases, un modelo que elige una entre varias, por
        ejemplo `spam`, `phishing` y `legitimo`) o `regression` (un modelo que
        predice un número, por ejemplo horas por semana o días hasta resolver un caso). El tipo
        NO se puede cambiar después del alta (un PATCH que lo cambia da 409): si te
        equivocas, crea otro proyecto.

        MULTICLASE. `classes` (opcional en el alta): la lista de clases, en el orden
        en que el modelo da sus probabilidades; también puede ir en
        `mapping_template.classes` (si van las dos, mandan las de `classes`). Sin ellas,
        las clases salen de la línea base al congelarla, y quedan fijas desde entonces.
        `favorable_label` es el CONJUNTO FAVORABLE: en multiclase una lista de 1 a k-1
        clases (por ejemplo `["legitimo"]`) o nada (sin conjunto favorable: Vigía solo
        mide calidad por grupo y la equidad queda en `sin_datos`); en binario, una
        clase (`1` por defecto). Una clase de texto en binario o una lista van a
        `mapping_template.favorable_label`; no pases el favorable en dos sitios. Al
        congelar la línea base de un multiclase, Vigía aplica sola los umbrales de
        exactitud, F1, AUC y deriva de la predicción (origen `linea_base`); para
        ajustarlos, `get_threshold_proposal` y `set_monitor`. Las medidas por clase
        (`group_code` `clase:<valor>`) no tienen umbral.

        REGRESIÓN. `task_type="regression"`: el modelo da un número (`prediction_col`
        y `label_col` son cifras, sin `probability_col`). `target_unit` es la unidad de la
        salida, por ejemplo `horas`; las medidas de error (MAE, RMSE, sesgo) y sus umbrales
        van en esa unidad. `favorable_ranges` es el RANGO FAVORABLE: de 1 a 3 intervalos
        `[min, max]` (`null` en un extremo lo deja abierto) que dicen qué cifras son una
        buena salida para la persona afectada. Los dos van como parámetros de esta tool o
        como claves de `mapping_template` (si van en los dos sitios, mandan los
        parámetros); en `set_mapping_template` y `upload_dataset` van como claves del
        mapeo. Con rango, Vigía mide la equidad por pertenencia al
        rango y activa la capa humana; sin rango, mide solo el error, y la capa humana
        (`upload_usage_log`) da el motivo «la capa humana de regresión necesita un rango
        favorable». El rango no cambia después de congelar la línea base. No pases
        `favorable_label` en regresión (la API da 422): lo favorable va en el rango. Al congelar la línea
        base, Vigía fija los umbrales de MAE, RMSE, R², sesgo y deriva de la predicción
        (origen `linea_base`); antes, el monitor de calidad no tiene umbrales y sus
        titulares dan `sin_datos` con «umbral pendiente de la línea base». Ejemplo:
        `task_type="regression"`, `target_unit="horas"`, `favorable_ranges=[[40, 81]]`,
        `mapping_template={"id_col": "id", "prediction_col": "pred", "label_col": "y"}`.

        Claves válidas de `mapping_template` (otra clave da 422; ninguna es
        obligatoria): `favorable_label`, `classes` y `probability_cols` (listas, para
        multiclase: una columna de probabilidad por clase, en el orden de `classes`),
        `prediction_col`, `probability_col`, `label_col`, `id_col`, `timestamp_col`, `feature_cols`
        (lista, sin la columna de fecha), `protected_attr_col`, `protected_kind`
        (`numeric_ranges` o `categorical`), `unpriv_groups` y `priv_groups`
        (listas; obligatorias con `protected_attr_col`), `target_unit` y
        `favorable_ranges` (solo en regresión: unidad de la salida y de 1 a 3
        intervalos `[min, max]`). Ejemplo:
        `{"id_col": "patient_id", "prediction_col": "pred", "label_col": "y",
        "feature_cols": ["edad", "crp"], "protected_attr_col": "edad",
        "protected_kind": "numeric_ranges", "unpriv_groups": [[65, 120]],
        "priv_groups": [[0, 64]]}`. Ejemplo multiclase: `task_type="multiclass"`,
        `classes=["spam","phishing","legitimo"]`, `favorable_label=["legitimo"]`,
        `mapping_template={"prediction_col": "pred", "label_col": "y", "id_col": "id",
        "probability_cols": ["p_spam", "p_phishing", "p_legitimo"]}`."""
        if task_type not in TIPOS_DE_TAREA:
            raise ValueError(
                f"task_type no reconocido: {task_type!r}; válidos: {', '.join(TIPOS_DE_TAREA)}"
            )
        if deployment_stage not in ETAPAS_ADMITIDAS:
            visto = "falta" if deployment_stage is None else f"«{deployment_stage}» no vale"
            raise ValueError(
                f"deployment_stage: {visto}; pregunta al usuario en qué etapa está el modelo "
                "(desarrollo, validacion o produccion) o léela de su ficha. `demo` solo la pone la demo"
            )
        plantilla = dict(mapping_template) if mapping_template is not None else None
        favorable_entero = 1
        if favorable_label is not None:
            if plantilla is not None and _favorable_distinto(plantilla.get("favorable_label"), favorable_label):
                raise ValueError(
                    "favorable_label va dos veces y distinto (parámetro y mapping_template): "
                    "pásalo en un solo sitio"
                )
            es_entero = isinstance(favorable_label, int) and not isinstance(favorable_label, bool)
            match task_type:
                case "binary" if es_entero:
                    favorable_entero = favorable_label  # type: ignore[assignment]
                case "binary" | "multiclass" | "regression":
                    # Un conjunto, una clase de texto o cualquier favorable en multiclase: la API
                    # solo lee el conjunto de la plantilla (`ProjectCreate.favorable_label` es un
                    # entero). En regresión la API lo rechaza con un 422 que nombra el campo.
                    plantilla = {**(plantilla or {}), "favorable_label": favorable_label}
                case _:
                    raise ValueError(f"tipo de tarea no reconocido: {task_type!r}")
        cuerpo: dict[str, Any] = {
            "name": name,
            "domain": domain,
            "favorable_label": favorable_entero,
            "task_type": task_type,
            "store_features": store_features,
            "model_kind": model_kind,
            "deployment_stage": deployment_stage,
            "acepta_feedback": acepta_feedback,
        }
        if classes is not None:
            cuerpo["classes"] = classes
        if target_unit is not None:
            cuerpo["target_unit"] = target_unit
        if favorable_ranges is not None:
            cuerpo["favorable_ranges"] = favorable_ranges
        if plantilla is not None:
            cuerpo["mapping_template"] = plantilla
        if fairness_interval_method is not None:
            cuerpo["fairness_interval_method"] = fairness_interval_method
        return await get_client().post("/projects", json=cuerpo)

    @mcp.tool()
    async def set_mapping_template(
        project_id: int,
        mapping_template: dict[str, Any],
        motivo: str,
        actor: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        """Sustituye la plantilla de mapeo de un proyecto (identificador, clase favorable,
        variables y atributo protegido que heredan sus datasets) sobre `PATCH /projects/{id}`.
        La plantilla nueva reemplaza a la anterior entera; los datasets ya ingeridos no se
        tocan (para rehacerlos, `reset_project` y subirlos de nuevo). Deja el evento
        `proyecto.plantilla_actualizada` con la plantilla antes y después.

        Claves válidas de `mapping_template` (otra clave da 422): `favorable_label`,
        `classes` y `probability_cols` (listas, para multiclase), `prediction_col`, `probability_col`, `label_col`,
        `id_col`, `timestamp_col`, `feature_cols`, `protected_attr_col`,
        `protected_kind` (`numeric_ranges` o `categorical`), `unpriv_groups`,
        `priv_groups`, `target_unit` y `favorable_ranges` (solo en regresión).
        Ejemplo: `{"id_col": "id", "prediction_col": "pred",
        "label_col": "y", "feature_cols": ["edad", "crp"]}`.

        Proyecto MULTICLASE: `favorable_label` es una lista de 1 a k-1 clases (o
        `null`: sin conjunto favorable), `classes` la lista de clases y
        `probability_cols` una columna de probabilidad por clase, en el orden de
        `classes`. Las `classes` de la plantilla tienen que ser las del proyecto
        (fijadas en el alta o al congelar la línea base): otras dan 422 con las dos
        listas. El tipo de tarea no se cambia aquí (409). Ejemplo: `{"id_col": "id",
        "prediction_col": "pred", "label_col": "y", "favorable_label": ["legitimo"],
        "classes": ["spam", "phishing", "legitimo"],
        "probability_cols": ["p_spam", "p_phishing", "p_legitimo"]}`.

        Proyecto de REGRESIÓN: `target_unit` (la unidad de la salida) y
        `favorable_ranges` (de 1 a 3 intervalos `[min, max]`, con `null` en un extremo
        abierto) van como claves de la plantilla, no como parámetros. `favorable_label` no
        vale en regresión. Ejemplo: `{"id_col": "id", "prediction_col": "pred",
        "label_col": "y", "target_unit": "horas", "favorable_ranges": [[40, 81]]}`.

        `actor` es opcional: el nombre del diario es el de la entrada del MCP
        (`--actor`); uno distinto se guarda como `actor_detalle`."""
        cuerpo: dict[str, Any] = {
            **get_client().cuerpo_actor(actor),
            "role": role,
            "motivo": motivo,
            "mapping_template": mapping_template,
        }
        return await get_client().patch(f"/projects/{project_id}", json=cuerpo)

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    async def reset_project(
        project_id: int,
        motivo: str,
        actor: str | None = None,
        role: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """DESTRUCTIVA: deja el proyecto virgen sobre `POST /projects/{id}/reset`. Borra los
        ficheros subidos, los datasets, los lotes con sus registros, las evaluaciones y
        mediciones, las alertas con sus acciones, las explicaciones, los registros de uso y las
        demos del proyecto, y suelta la línea base de cada versión. Conserva el proyecto con su
        plantilla de mapeo, las versiones con su modelo, los monitores con sus umbrales y el
        diario. No rehace el mapeo: para cambiarlo, `set_mapping_template`.

        Exige `confirm=true` (igual que `close` de `act_on_alert`); sin él, esta tool falla
        antes de llamar a la API. El modelo rellena `confirm`: la aprobación por llamada es
        del host del MCP, no de Vigía. `actor` es opcional: el nombre del diario es el de la
        entrada del MCP; uno distinto se guarda como `actor_detalle`."""
        if not confirm:
            raise ValueError(
                "reiniciar un proyecto borra sus lotes, evaluaciones y alertas: pasa confirm=true para hacerlo"
            )
        client = get_client()
        cuerpo: dict[str, Any] = {**client.cuerpo_actor(actor), "role": role, "motivo": motivo, "confirm": True}
        return await client.post(f"/projects/{project_id}/reset", json=cuerpo)
