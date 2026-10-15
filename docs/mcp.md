# Servidor MCP de Vigía

`vigia.mcp.server` expone Vigía como servidor MCP por `stdio` (`FastMCP`).
Habla solo con la API HTTP local (`127.0.0.1`) de una instancia de
`vigia serve` ya en marcha: nunca abre `vigia.db` directamente.

## Requisito: `vigia serve` en marcha

El MCP no arranca ni apaga la API por su cuenta: antes de
usarlo, arranca `vigia serve --data-dir <carpeta>` (o el lanzador de
Windows) sobre la carpeta de datos que le vas a pasar al MCP. `vigia serve`
deja un `vigia.lock` en esa carpeta con el puerto en marcha; el MCP lo lee.

## Registro en Claude Code

Con `--url` apuntas al puerto en el que ya corre Vigía (se ve en la barra de
direcciones del navegador y en `vigia.lock`). `--url` solo admite `http://` a
`127.0.0.1` o `localhost`; otra dirección da un error al arrancar. Dentro de
eso, fija la dirección sin comprobarla: si Vigía no está en marcha, la primera
tool falla con un error legible en vez de salir el servidor al arrancar. Sin
`--url`, el MCP localiza el puerto por el lock y comprueba que el servidor es
el dueño del lock antes de mandar nada; si no lo es, da `VigiaError` 502. Las
tools de subida rechazan rutas de red y ficheros de más de 200 MB. Con el paquete de Windows, el
Python embebido va en `runtime\python\python.exe`. Ejemplo para un `.mcp.json`:

```json
{"mcpServers": {"vigia": {"command": "runtime\\python\\python.exe",
  "args": ["-m", "vigia", "mcp", "--url", "http://127.0.0.1:<puerto>", "--actor", "claude-code"]}}}
```

Con la carpeta de datos en vez de la URL (Vigía localiza el puerto por el fichero
`vigia.lock`):

```
claude mcp add vigia -- <ruta al Python embebido>\python.exe -m vigia mcp --data-dir <carpeta>
```

Desde un clon del código fuente, con `uv`:

```
claude mcp add vigia -- uv run vigia-mcp --data-dir <carpeta>
```

## Registro en Claude Desktop

En `claude_desktop_config.json` (`%APPDATA%\Claude\`). Cierra la aplicación y haz
copia del fichero antes de editarlo: Claude Desktop lo reescribe desde memoria al
cerrarse. Con `--url` y el actor de la app:

```json
{"mcpServers": {"vigia": {"command": "<ruta al Python embebido>\\python.exe",
  "args": ["-m", "vigia", "mcp", "--url", "http://127.0.0.1:<puerto>", "--actor", "claude-desktop"]}}}
```

Con la carpeta de datos, si `vigia-mcp` está en el `PATH`:

```json
{"mcpServers": {"vigia": {"command": "vigia-mcp", "args": ["--data-dir", "<carpeta>"]}}}
```

Arranca Vigía antes de abrir la app.

## Parámetros de `vigia-mcp`

| parámetro | por defecto | qué hace |
|---|---|---|
| `--data-dir` | carpeta de datos por defecto de `vigia serve` | dónde leer `vigia.lock` para localizar el puerto |
| `--url` | (ninguno) | URL explícita de la API; si se pasa, gana al lock |
| `--actor` | `claude-code` | nombre que queda en el diario como `actor_id` de cada evento del carril `agente`; es el único nombre que consta, pase lo que pase en el parámetro `actor` de las tools; es autodeclarado, no una firma (ver `SEGURIDAD.md`) |

## Autenticación

En la primera petición, el MCP pide `GET /settings?reveal=true` (el único
punto sin autenticar, igual que el lock protege `POST /shutdown`) y cachea el
`mcp_token`. Se hace ahí y no al arrancar para que la conexión nazca en el
mismo bucle de eventos que atiende las tools. Cada petición manda `X-Vigia-Token`, `X-Vigia-Actor-Kind:
agente`, `X-Vigia-Actor: <--actor>` y `X-Vigia-Correlation` (un UUID por
llamada de tool). Sin token válido, la API responde 401.

## Las 39 tools

| tool | qué hace |
|---|---|
| `list_projects` | Lista los proyectos, con resumen opcional |
| `create_project` | Crea un proyecto con su versión v1 y sus cinco monitores; `deployment_stage` es obligatorio (`desarrollo`, `validacion` o `produccion`; `demo` solo la pone la demo) y sin él la tool falla antes de llamar a la API; `task_type` (`binary` por defecto, `multiclass` o `regression`), `classes`, `target_unit` y `favorable_ranges` (regresión); `favorable_label` admite un conjunto (lista) en multiclase y no vale en regresión |
| `upload_dataset` | Sube, mapea e ingiere un dataset; sin `mapping` hereda la plantilla del proyecto (`mapping_origen`) y, si no la hay, falla con 422 antes de subir nada; con `wait=true` devuelve el resultado de la ingesta (filas, avisos, errores); `model_version_id` la ingiere en una versión no activa (la línea base de la v2) |
| `set_monitor` | Cambia configuración, umbrales, activación o protocolo de un monitor |
| `set_mapping_template` | Sustituye la plantilla de mapeo de un proyecto (`PATCH /projects/{id}`); no toca los datasets ya ingeridos |
| `reset_project` | Reinicia un proyecto (`POST /projects/{id}/reset`): borra lotes, evaluaciones, alertas, resultados reales (outcomes) y trabajos terminados, quita la telemetría de los dossiers y conserva versiones, monitores y plantilla. Destructiva: exige `confirm=true` |
| `run_evaluation` | Evalúa un lote ya ingerido |
| `get_measurements` | Serie temporal de una o varias medidas; `model_version_id` deja solo los puntos de una versión; `group_code` filtra, y `clase:<valor>` da las medidas de una clase (multiclase); en regresión `value` va en la unidad del proyecto y `group_code` es `unpriv` o `priv` en las medidas de error por grupo |
| `explain_global` | Explicabilidad global (permutación); `clase` opcional en multiclase |
| `explain_row` | Explicación local (LIME) de una fila; `clase` opcional en multiclase, y devuelve las `k` probabilidades; en regresión devuelve `prediction_value` y `clase` da 422 |
| `get_alerts` | Alertas de un proyecto, filtradas |
| `get_alert` | Detalle de una alerta: historial de acciones, pasos del protocolo y riesgos enlazados |
| `act_on_alert` | Actúa sobre una alerta por hito (`close` es destructiva y exige `confirm=true`; `decide` lleva `acciones=[{"key", "notes"}]` con claves del catálogo de acciones); `attachment_path` es una referencia en texto, no sube el fichero |
| `run_scenario` | Crea y, si se pide, reproduce una demo |
| `next_phase` | Reproduce la siguiente fase de una demo |
| `lab_generate` | Genera una fase a la carta (laboratorio), sin avanzar el guion |
| `create_dossier` | Crea el dossier de un proyecto: importa un `dossier.json` (`dossier_path`) o lo arma a mano con `profile`, `experience` e `inventory` |
| `run_dossier_review` | Lanza una revisión de auditoría sobre un dossier; si ya hay una del mismo enfoque pendiente, en curso o terminada, devuelve `status="ya_existe"` con ella y no crea otra salvo `forzar=true` |
| `upload_usage_log` | Sube el diario de uso (CSV); `valor_favorable` es obligatorio en binario (opcional en la firma: sin él la tool lo pide) y no se usa en multiclase; la respuesta trae `comprobacion_codificacion`; en multiclase las columnas llevan nombres de clase y la comprobación va `inconcluso` con `r` nulo; en regresión hace falta rango favorable (sin él, la tool da el motivo antes de subir) y las columnas llevan cifras, sin `valor_favorable` |
| `evaluate_cross` | Encola la evaluación de las alertas cruzadas (modelo frente a decisión humana); la primera de una versión es de calibración, sin reglas, y la respuesta lo avisa en `aviso` |
| `get_cross_latest` | Última evaluación de las alertas cruzadas, con sus reglas |
| `get_deskilling` | Deskilling por ventanas, con filtro de subgrupo o profesional; las ventanas con menos de `min_n` decisiones salen con `excluida_de_pendiente` |
| `get_overrides` | Overrides por subgrupo, fase o profesional (cuartiles); `by="profesionales"` lista los pseudónimos; `by="cambios"` da la tabla salida del modelo por decisión de la persona; una celda con `n < min_n` da `tasa` nula; en regresión, `diferencia_media` por subgrupo o fase |
| `upload_outcomes` | Sube el CSV de resultados (outcomes) |
| `get_outcomes` | Tabla y series de outcomes, opcionalmente de una métrica |
| `list_risks` | Riesgos del proyecto, filtrables por estado |
| `create_risk` | Da de alta un riesgo, a mano o desde una alerta |
| `update_risk` | Mueve un riesgo en la matriz, lo pasa a seguimiento o lo cierra (`cerrar` exige `confirm=true`) |
| `get_threshold_proposal` | Propuesta de umbrales sobre la línea base de la versión activa; solo lee; en multiclase, la de exactitud, F1, AUC y deriva de la predicción, y la equidad por conjunto favorable; en regresión, la de MAE, RMSE, R², sesgo y deriva y, con rango, la de equidad; espera hasta 60 s |
| `get_job` | Estado de un trabajo en segundo plano, para seguirlo tras una espera agotada |
| `get_events` | Eventos del diario, filtrados |
| `export_report` | Exporta el diario (los 200 eventos más recientes por defecto, `limit`; `project_id` lo acota a un proyecto; la respuesta es un objeto con `total` y `truncado`) o el informe de una revisión (`{"review_id", "html"}`) |
| `list_versions` | Versiones de un proyecto con su línea base (`baseline_batch_id`) y su artefacto; solo lee |
| `create_version` | Crea una versión nueva sin activarla (`POST /projects/{id}/versions`); deja evento en el carril agente |
| `activate_version` | Activa una versión (`POST /model-versions/{id}/activate`); `congelar_linea_base` (id de lote o de dataset) congela su línea base en el mismo paso |
| `freeze_baseline` | Congela la línea base de una versión sobre un lote ya ingerido (`POST /model-versions/{id}/baseline`) |
| `upload_model_artifact` | Sube el modelo ejecutable de una versión desde una ruta local (`POST /model-versions/{id}/artifact`); un `pickle` o `joblib` exige `confirm_pickle=true`; en multiclase da `(n, k)` y el error cita el orden de clases leído y el declarado; en regresión da una cifra por fila y el 422 dice «es un clasificador» o «es un regresor», o la mediana de la diferencia con la línea base |
| `compare_versions` | Compara dos versiones métrica a métrica, cada una contra su línea base (`GET /projects/{id}/versions/compare`); solo lee; no compara alertas |
| `get_settings` | Ajustes actuales de la aplicación e `instancia` (`url_base`, `puerto_en_uso`, `data_dir`, `version`): a qué instancia habla esta entrada del MCP. `puerto` de los ajustes es el preferido del próximo arranque; `instancia.puerto_en_uso` es donde escucha ahora |

Las acciones destructivas o terminales llevan `confirm`: `close` de `act_on_alert`, `reset_project` y `cerrar` de
`update_risk`. Las tres fallan antes de llamar a la API si falta `confirm=true`, y `reset_project` además va marcada
con `destructiveHint` para que el cliente MCP la trate como tal.
Para rehacer el mapeo de un proyecto con datos cargados: `reset_project`, `set_mapping_template` y subir
los datasets de nuevo con `upload_dataset`.

Toda tool que escribe deja un evento en el carril `agente` del diario, con el actor del MCP y el
`correlation_id` de la llamada.

**Actor y `actor_detalle`.** El parámetro `actor` de las tools que lo llevan (`act_on_alert`, `set_monitor`,
`set_mapping_template`, `reset_project`, `create_risk`, `update_risk`, `create_dossier`, `run_dossier_review`,
`lab_generate`) es opcional. El cuerpo que llega a la API lleva siempre el `--actor` de la entrada; si el modelo da un
`actor` distinto, viaja como `actor_detalle` (máximo 200 caracteres, solo contexto: «por encargo de …») y la API lo guarda
en el payload (`after`) de los eventos de esa petición. El nombre que sale en el diario no cambia. La interfaz humana
no manda `actor_detalle`.

**Claves del mapeo.** `create_project` y `set_mapping_template` aceptan en `mapping_template` solo estas
claves (otra da 422 y el error las lista): `favorable_label`, `classes`, `probability_cols`, `prediction_col`,
`probability_col`, `label_col`, `id_col`, `timestamp_col`, `feature_cols`, `protected_attr_col`, `protected_kind`,
`unpriv_groups`, `priv_groups`. (El conjunto favorable define la clase positiva.) El `mapping` de
`upload_dataset` (un `ColumnMapping`) acepta: `prediction_col`,
`probability_col`, `probability_format`, `probability_index`, `label_col`, `id_col`, `timestamp_col`,
`protected_attr_col`, `protected_kind`, `unpriv_groups`, `priv_groups`, `feature_cols`, `clinician_col`,
`subgroup_col`, `favorable_label`, `classes`, `probability_cols`. Un test compara las dos listas del MCP con los modelos de `core/schema.py`.

**Origen de un umbral.** `set_monitor` admite `origen` por umbral: `linea_base`, `fabricante`,
`criterio_clinico`, `politica_organizacion` (una norma interna de la organización) o `fabrica` (sin calibrar). Solo
`fabrica`, que también es lo que se sirve cuando falta `origen`, sale con el aviso de «umbral de fábrica».

**Etapa del proyecto.** `create_project` exige `deployment_stage`, sin valor por defecto:
pregúntalo al usuario o léelo de la ficha del modelo. Valores: `desarrollo`, `validacion` y `produccion`; `demo` la pone
solo la demo. Sin él, la tool falla antes de llamar a la API. La API conserva su valor por defecto.

## Modelos multiclase

Un modelo que elige una clase entre 3 y 20 se vigila con las mismas 39 tools: los parámetros nuevos son opcionales y
un cliente binario no cambia. Orden de llamadas, con un ejemplo de tres clases:

1. `create_project(name, deployment_stage, task_type="multiclass", classes=["spam","phishing","legitimo"],
   favorable_label=["legitimo"], mapping_template={...})`. `classes` va en el orden en que el modelo da sus
   probabilidades. `favorable_label` es el conjunto favorable (de 1 a k-1 clases) o nada: sin conjunto favorable la
   equidad queda en `sin_datos` y solo se mide la calidad por grupo. El tipo no se cambia después del alta (409).
   Para un modelo que predice un número, ver «Modelos de regresión».
2. `upload_dataset(role="baseline", mapping={..., "classes": [...], "probability_cols": ["p_spam","p_phishing","p_legitimo"]})`.
   `prediction_col` y `label_col` llevan el nombre de la clase. La ingesta de la línea base fija las clases del
   proyecto y aplica sola los umbrales de `accuracy` (suelo 1/k), `f1_measure` y `area_under_roc` (promedios macro) y
   `prediction_drift_score`, con origen `linea_base`. Los avisos (orden de las probabilidades, suma distinta de 1,
   clases sin filas) salen en `ingest_job`.
3. `get_threshold_proposal(project_id)`: la propuesta con la forma de la binaria (`monitors` con `propuestas`:
   `quality` y `drift`, y `fairness` con los umbrales de las medidas de pertenencia al conjunto favorable, si lo hay; en `quality` y `drift`, `valor_linea_base` va nulo; la tool espera hasta 60 s porque la deriva remuestrea; es el cálculo que se aplicó al congelar: con el mismo `tamano_lote` la calidad coincide y la deriva depende del lote). `set_monitor` ajusta esos umbrales.
   Un umbral sobre una medida por clase da 422.
4. `get_measurements(project_id, monitor_type, metric_key, group_code="clase:spam")`: las medidas por clase llevan
   `group_code` `clase:<valor>` y la misma `metric_key` de siempre; sin `group_code` salen todas, junto al promedio
   macro. No tienen umbral. Una clase ausente del lote da `sin_datos`, nunca 0.
5. `explain_global(version_id, clase="spam")` y `explain_row(version_id, batch_id, row_seq, clase="spam")`: sin `clase`,
   el conjunto favorable (global) o la clase predicha de la fila (local). Una clase que no es del proyecto da 422 con
   las válidas.
6. `upload_model_artifact(version_id, file_path)`: ONNX o pickle con `(n, k)`. Si el orden de clases que lee Vigía
   difiere del declarado, reordena; si no coinciden las clases o el argmax no casa con la línea base (99 % de 200
   filas), 422 con los dos órdenes.
7. `upload_usage_log(project_id, file_path)`: `human_decision`, `model_output` y `ground_truth` con nombres de
   clase. `refer` y `no-refer` como celda dan 422 (solo valen en binario). `valor_favorable` no se usa en multiclase:
   si se pasa, la tool da un error que pide quitarlo. `comprobacion_codificacion` va `inconcluso` con `r` y `p`
   nulos y el motivo «no aplica en multiclase» (no hay codificación que invertir). Una discrepancia entre dos
   clases cuenta como override.
8. `get_deskilling` devuelve `min_n` (el mínimo aplicado) y `ventanas_excluidas`; cada ventana lleva
   `excluida_de_pendiente`. `get_overrides` devuelve `min_n` y, por celda, `n` y `tasa` (nula si `n < min_n`).

El prompt `diagnostico_de_alerta` nombra la clase afectada cuando la alerta trae un `group_code` `clase:<valor>`.

## Modelos de regresión

Un modelo que predice un número (horas por semana, días hasta resolver un caso) se vigila con las mismas 39 tools. Los parámetros
nuevos son opcionales y un cliente binario o multiclase no cambia. Orden de llamadas:

1. `create_project(name, deployment_stage, task_type="regression", target_unit="horas", favorable_ranges=[[40, 81]],
   mapping_template={...})`. `target_unit` es la unidad de la salida; `favorable_ranges` son de 1 a 3 intervalos
   `[min, max]` (`null` abre un extremo) con las cifras que son una buena salida. Sin rango, Vigía mide el error y la
   capa humana no tiene datos. El rango no cambia después de congelar la línea base. `favorable_label` no se usa (422).
   En `set_mapping_template` y `upload_dataset` los dos van como claves del mapeo, no como parámetros.
   Si creas el proyecto sin unidad ni rango, fíjalos con `set_mapping_template` (`target_unit` y `favorable_ranges` en
   `mapping_template`) o en el `mapping` de la línea base, antes de congelarla. Una línea base congelada sin ellos queda
   sin unidad ni rango: cambiarlos después da 409.
2. `upload_dataset(role="baseline", mapping={"prediction_col": ..., "label_col": ..., "target_unit": ..., "favorable_ranges": ...})`.
   `prediction_col` y `label_col` llevan cifras. Al congelar la línea base, Vigía aplica sola los umbrales de MAE, RMSE,
   R², sesgo medio y deriva de la predicción, con origen `linea_base`. Antes, el monitor de calidad no tiene umbrales y
   sus titulares dan `sin_datos` («umbral pendiente de la línea base»).
3. `get_threshold_proposal(project_id)`: misma forma que la binaria. `quality` y `drift` con los valores en la unidad del
   proyecto; `fairness` con las medidas de pertenencia al rango solo si hay rango. Espera hasta 60 s.
4. `get_measurements(...)`: `value` va en la unidad del proyecto; en las medidas de error por grupo (`mean_absolute_error`,
   `mean_error`), `group_code` es `unpriv` o `priv`. La respuesta trae `unidad` (la `target_unit` del proyecto, o
   `null`); `get_threshold_proposal` también. En clasificación el campo no sale.
5. `upload_model_artifact(version_id, file_path)`: una cifra por fila. 422 con «es un clasificador» (más de una columna,
   `ZipMap` o etiquetas de clase) o, en un proyecto de clasificación, «es un regresor»; si las cifras no casan con la
   línea base en 200 filas, el 422 da la mediana de la diferencia.
6. `explain_global` y `explain_row`: sin `clase` (da 422). `explain_row` devuelve `prediction_value`.
7. `upload_usage_log(project_id, file_path)`: con rango, `human_decision`, `model_output` y `ground_truth` llevan
   cifras con punto decimal y sin unidad; sin `valor_favorable`. `refer`, `no-refer` o texto en una celda dan 422 con la
   fila y «en regresión el registro trae las cifras». Sin rango, la tool da el motivo «la capa humana de regresión
   necesita un rango favorable» antes de subir nada.
8. `get_overrides(project_id, by="cambios")`: la tabla salida del modelo por decisión de la persona, con «dentro del
   rango» y «fuera del rango»; la misma tabla da `refer`/`no-refer` en binario y las clases en multiclase. Una fila con
   `n < min_n` da las tasas nulas. Con `by="subgroup"` o `by="phase"`, cada fila trae `diferencia_media` (en la unidad
   del proyecto) y la respuesta trae `unidad`. Un cambio que no cruza el corte del rango no cuenta como override.

Etiquetas tardías: `upload_dataset(kind="feedback")` trae al primer nivel `lotes_con_verdad` (los lotes que recibieron
etiquetas), `lotes_reevaluados` y `lotes_a_reevaluar`. Si `lotes_a_reevaluar` no está vacío, la calidad aún no usa esa
verdad: llama a `run_evaluation` con cada uno de esos lotes. `evaluate_motivo` dice por qué no se reevaluó.

## Versión nueva y comparación

Orden de llamadas para sacar una versión nueva y compararla con la anterior:

1. `list_versions(project_id)`: ids de las versiones y cuál está activa.
2. `create_version(project_id, label, motivo)`: da de alta la v2 sin activarla.
3. `upload_model_artifact(version_id, file_path)`: solo si el modelo es ejecutable; un `pickle` o `joblib` pide `confirm_pickle=true`.
4. `upload_dataset(..., role="baseline", model_version_id=<v2>)`: la línea base de la v2, sin activarla. La ingesta de una línea base ya la congela: no hace falta `freeze_baseline` después (daría 409).
5. `activate_version(version_id=<v2>, motivo)` cuando la v2 va a recibir la producción. `freeze_baseline` y `congelar_linea_base` solo sirven si la versión aún no tiene línea base congelada: con un lote de producción ya ingerido en ella, o con `laboratorio=true`, que permite recongelar.
6. `upload_dataset(..., role="production", model_version_id=<v2>)` con los lotes de producción de cada versión.
7. `compare_versions(project_id, a=<v1>, b=<v2>, ventana="ultimo"|"todos")`: filas por métrica con `direccion` (`mejora`, `empeora`, `igual`, `sin_datos`) y el `motivo` de la regla. No compara alertas: son del proyecto.
8. `get_measurements(..., model_version_id=<v>)` da la serie de una sola versión.

## Errores y esperas

**Errores.** Cuando la API rechaza una llamada, el texto que ve el agente empieza por el código HTTP, sigue
con el `detail` de la API en español y una línea «Qué hacer» según el código:

| código | qué hacer |
|---|---|
| 404 | el id no existe: nombra el parámetro de la tool que lo lleva (`project_id`, `alert_id`, `risk_id`, `version_id`, `job_id`) y la tool de listado según la ruta (`projects` a `list_projects`, `alerts` a `get_alerts`, `risks` a `list_risks`, `model-versions` a `list_versions`, `jobs` a `get_job`); sin patrón, «comprueba el id con la tool de listado» |
| 409 | el estado actual no lo permite: dice lo que falta y la tool que lo da (por ejemplo, sin línea base, `upload_dataset` con `role="baseline"` o `freeze_baseline`); si el mensaje no encaja en ningún caso conocido, haz primero el paso que dice o consulta el estado con la tool de lectura |
| 422 | corrige el campo que nombra el mensaje y vuelve a llamar; la ficha de la tool lista los valores válidos |
| 5xx | error de Vigía; el diario tiene el detalle |

El 409 y el 422 no repiten el `detail`, que ya va en la primera línea. Un backend parado, un lock sin proceso vivo y los fallos de conexión de `httpx` salen como `VigiaError` (código 503) con el texto «Vigía no está en marcha en esa carpeta de datos; arranca `vigia serve` o pasa `--url`», o, si el MCP se arrancó con `--url`, «Vigía no contesta en <dirección>; arranca `vigia serve` en esa dirección o comprueba la URL de `--url`»; una espera que agota el tiempo de red sale con 504.

Las validaciones propias de una tool (`confirm` ausente, `valor_favorable` no reconocido, `accion` desconocida) fallan
antes de llamar a la API y no llevan código.

**Esperas.** Las tools que encolan un trabajo (`run_evaluation`, `explain_global`, `explain_row`,
`evaluate_cross`, `run_dossier_review`, `upload_dataset`, `next_phase`) aceptan `wait` (por defecto `true`) y `timeout_s` (por
defecto 60). Con `wait=false` devuelven el trabajo encolado. Si la espera se agota devuelven
`{"status": "en_curso", "timeout": true, "job_id": N, "aviso": "sigue en curso; consulta get_job(N)"}`; el trabajo no
se cancela y `get_job` da su estado final.

## Los 7 resources

Prompts y resources llevan un título con tilde (`title`) que los clientes enseñan en vez del nombre técnico:
«Análisis de alerta», «Presentación», «Guía de uso», etc.

`schema://tables`, `glossary://`, `metrics-help://{metric}`,
`state://project/{id}`, `presentacion://`, `demo://guion`, `guia://uso`.

## Los 3 prompts

`demo_guiada(paso?)`, `diagnostico_de_alerta(alert_id)`,
`informe_semanal(project_id, since, until)`. Este último reúne, como única fuente, el diario del periodo, la última
evaluación de las alertas cruzadas, el deskilling de la versión activa y los riesgos abiertos; lo que la API no pueda
dar (por ejemplo, un proyecto sin diario de uso) lo marca como «sin datos» en vez de fallar.

## Prueba manual

Con Vigía en marcha y el asistente registrado, pide al asistente que llame
`list_projects` y `run_scenario` con `scenario_key="timeline_completo"` (crea una demo sintética con alertas). Después
pídele `act_on_alert(accion="acknowledge")` sobre una de las alertas y comprueba
el evento en el Diario de Vigía, carril «agente». `vigia shutdown` apaga Vigía al
acabar.

## Prueba por stdio real

`tests/mcp/test_stdio_real.py` arranca `vigia serve` en un puerto libre y `vigia mcp --url` como subproceso, abre una
`ClientSession` por stdio, lista las 39 tools y llama a `list_projects`, `create_project`, `list_versions` y `get_events`. Los tests en
memoria (`tests/mcp/test_tools_*.py`) no ven el bucle de eventos ni el arranque del proceso; este sí.
