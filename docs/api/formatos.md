# Formatos de subida (`POST /projects/{id}/datasets/upload`)

Formatos de fichero que acepta la subida de datos, cómo se detectan el
dialecto y la codificación, y qué errores devuelve la API cuando un fichero o su
mapeo no valen.

## CSV: dialecto detectado, no asumido 

Antes de leer, Vigía detecta:

- **Codificación**: `utf-8-sig` primero (quita el BOM si lo hay; decodifica
  utf-8 normal si no); si el fichero no es utf-8 válido, cae a `cp1252`
  (Excel en Windows en español). Solo mira los primeros 64 KB.
- **Separador**: coma, punto y coma o tabulador, con `csv.Sniffer` sobre esos
  mismos 64 KB. Un CSV de una sola columna (ningún separador en la cabecera)
  es válido: cae a coma.
- **Decimal**: coma si el separador no es la coma y las celdas numéricas de
  las primeras filas la usan (`12,34`); si no, punto.

Si ni `utf-8-sig` ni `cp1252` decodifican el fichero (o el prefijo tiene un
byte `NUL`, señal de binario), la subida da:

> 422 «no se reconoce el formato del fichero: se esperaba CSV (coma, punto y
> coma o tabulador) o JSON»

El dialecto detectado viaja en `dialect` de la respuesta de la subida
(`{"encoding", "separator", "decimal"}`, `null` para JSON):

```json
{
  "dataset": {"...": "..."},
  "preview": ["...": "..."],
  "dialect": {"encoding": "utf-8-sig", "separator": ";", "decimal": ","}
}
```

**Dónde se guarda el dialecto**: solo viaja en la respuesta de la subida y en
el diario (en el `after` del evento `dataset.subido`), no en
`GET /datasets/{id}`.

## XLSX y XLS: 422 sin leer

Vigía no lee Excel. Un fichero `.xlsx` o `.xls`, reconocido por su extensión
**o por su firma binaria** (ZIP `PK\x03\x04` para `.xlsx`, OLE
`D0 CF 11 E0 A1 B1 1A E1` para `.xls` — también si viene renombrado con otra
extensión), da:

> 422 «Vigía lee CSV y JSON: abre el fichero en Excel y guárdalo como CSV
> (delimitado por comas o por punto y coma)»

Nunca un 500: la detección es por firma, antes de intentar decodificar nada.
La vía es guardar el fichero como CSV desde Excel.

Vigía lee CSV y JSON; un fichero Parquet da 422.

## Nulos: solo la celda vacía cuenta, salvo en predicción, probabilidad y etiqueta

Por defecto, pandas trata `None`, `NA`, `NULL`, `nan` y una veintena más de
cadenas como nulo, aunque sean el valor real de una columna de datos (por
ejemplo, un resultado `"NA"` de "no aplica"). Vigía lee con
`keep_default_na=False` y `na_values=[""]`: solo la celda vacía es nula, el
resto de esas cadenas se conserva como texto.

**Excepción**: las columnas mapeadas como predicción, probabilidad o
etiqueta conservan los nulos por defecto de pandas, porque ahí `"NA"` sí
suele ser un vacío legítimo que el motor necesita tratar como tal. En la
subida (antes de fijar el mapeo) todavía no se sabe cuáles son esas
columnas, así que se leen todas de forma literal; el ajuste llega al fijar
el mapeo y al ingerir.

## Columna del mapeo que ya no está en el fichero

Si se reingiere un fichero al que le falta una columna que el mapeo
necesita (una de las ocho directas o cualquiera de `feature_cols`), el
trabajo de ingesta queda en `error` con:

> «el fichero ya no tiene la columna 'X' que el mapeo necesita: revisa el
> mapeo o vuelve a subir el fichero»

Nunca el `KeyError` crudo de pandas. La misma comprobación (`core.loaders
.comprobar_columnas_mapeo`) la usan `load_tabular` (CLI, reingesta) y
`to_canonical` (ingesta real), para no duplicar la validación.

## Límite de un millón de filas por subida

Por encima de 1 000 000 de filas, la subida da:

> 422 «el fichero tiene N filas; el máximo por lote es 1 000 000: pártelo en
> varios lotes»

El recuento es por trozos de 1 MiB contando saltos de línea, antes de crear
el dataset o escribir nada en disco: nunca se construye un `DataFrame` del
fichero completo solo para rechazarlo. Para JSON
se cuenta sobre el JSON ya parseado (`len(values)`), porque no hay una forma
más barata sin parsearlo. El tope es de un millón de filas.

## `DatosNoValidos` (la lanza `core/quality.py`)

Si la evaluación de un lote encuentra probabilidades nulas o fuera de 0 a 1,
`core/quality.py` lanza `DatosNoValidos` con un mensaje limpio, en español,
sin traza. La API la captura por tipo en los dos caminos:

- **Ingesta con `evaluate=true`**: la ingesta no se rompe;
  `evaluated: false`, `evaluate_revertida: true` y `evaluate_motivo` con el
  mensaje. `evaluate_revertida` quiere decir que el lote y sus filas quedan
  guardados, pero que la evaluación falló y se deshizo entera: no queda
  ninguna medida ni alerta a medias. Pide la evaluación del lote más tarde
  con `POST /batches/{id}/evaluate`, cuando los datos estén arreglados.
- **`POST /batches/{id}/evaluate`**: el trabajo queda en `error` con ese
  mismo mensaje (nunca la traza de scikit-learn).

## `favorable_label`: se hereda o se pierde en 422, nunca se aplana en silencio

`favorable_label` en `PUT /datasets/{id}/mapping` es opcional (`int | str |
list[int | str] | None`, la lista solo con un valor). Si se omite, se
hereda en este orden y el valor resuelto queda guardado en el mapeo del
dataset (no queda `null`):

1. `project.mapping_template_json.favorable_label` (la plantilla del modelo),
   si la tiene.
2. Si no, el `favorable_label` del mapeo de la línea base congelada de la
   versión (la de la versión activa si la tiene, si no la congelada más
   reciente del proyecto).
3. Si ninguna de las dos lo tiene, **422** «no hay una clase favorable que
   heredar: indica favorable_label en el mapeo, en la plantilla del modelo, o
   mapea antes la línea base».

Solo hace falta resolverlo cuando el mapeo tiene `prediction_col` o
`label_col` (un dataset sin ninguna de las dos, como algunos `usage_log`, no
lo necesita).

### Comparación normalizada

La predicción y la etiqueta (y la etiqueta al emparejar feedback,
`app/services/ingest._ingest_emparejar`) se comparan contra la clase
favorable así (`core.loaders.resolver_favorable`):

- **Número contra número**: igualdad directa (`1 == 1`, `0 == 1` es falso).
- **Texto**: `strip().casefold()` en los dos lados. Dos alias fijos, cada uno
  una sola clase: `sí`, `si`, `true`, `verdadero`, `1` valen como una;
  `no`, `false`, `falso`, `0` como la otra. Un texto que no es ninguno de los
  dos alias pero coincide letra a letra con `favorable_label` (por ejemplo
  `favorable_label="positivo"` y el valor es `"Positivo"`) también cuenta
  como favorable.
- **Sin alias reconocido y sin coincidencia exacta**: la fila pasa a nulo
  (`None`/`NaN`), **nunca** a la clase no favorable en silencio. En la
  etiqueta esto es un dato perdido normal (la columna ya admite nulo); el
  recuento de cuántas filas cayeron así viaja como aviso en el resultado del
  trabajo (`avisos`, ver más abajo). En la **predicción** no hay nulo posible
  (la ingesta la necesita en todas las filas): una predicción sin alias
  reconocido detiene la ingesta con `DatosNoValidos` («...no coinciden con la
  clase favorable ni sus alias...»), no la deja pasar como si fuera 0.

## `prediction_col` opcional en feedback, obligatorio en combined y payload

`prediction_col` es opcional en `ColumnMapping`: un dataset
`kind="feedback"` se mapea con solo `id_col` y `label_col`. `PUT
/datasets/{id}/mapping` sigue exigiéndolo con 422 para `kind` en
`("combined", "payload")`.

## Etiquetas que no se pisan: `etiquetas_omitidas`

Una etiqueta registrada no se sobrescribe. Cuando un fichero de etiquetas (o
un lote con etiqueta que empareja filas ya existentes) trae una etiqueta para
una fila que ya la tiene, Vigía no la aplica y la cuenta. Esto incluye la
etiqueta en cualquiera de sus formas: `label`, `label_class` y `label_value`.
El resultado del trabajo de ingesta trae `etiquetas_omitidas`, la suma de dos
casos, y un aviso por cada uno en `avisos`:

- filas de la línea base congelada que ya tenían etiqueta (la línea base no
  se corrige: para cambiarla, crea una versión nueva del modelo);
- filas de otros lotes que ya tenían etiqueta.

La línea base sin etiquetas sí las recibe. `etiquetas_omitidas` es 0 si no se
omitió ninguna. No bloquea la ingesta.

## Un dataset ingerido no se mapea ni se ingiere otra vez

Después de la ingesta, el fichero en bruto se borra. Por eso un dataset con
`status: "ingerido"` da **409** si se vuelve a mapear
(`PUT /datasets/{id}/mapping`) o a ingerir, con el mensaje «este fichero de
datos ya está ingerido: no se puede volver a mapear ni a ingerir; sube el
fichero otra vez si necesitas otro mapeo». Reingerirlo duplicaría el lote o
repetiría las etiquetas del primer fichero sobre las que llegaron después.

## Nombres de columna reservados

Vigía reserva para sus propios datos estos nombres: `seq`, `batch_seq`,
`model_version`, `external_id`, `timestamp`, `prediction`, `prob_favorable`,
`label`, `protected_value`, `group_code`, `clinician_pseudonym`, `subgroup`,
`prediction_class`, `label_class`, `prediction_value`, `label_value` y
`prob__<n>` con `n` entero. El mapeo da **422** si una variable (`feature_cols`),
o una columna del fichero que queda sin mapear y pasaría a ser variable,
tiene uno de esos nombres: sustituiría en silencio el valor del lote. Una
columna con un nombre reservado que el mapeo usa como identificador,
predicción, probabilidad, etiqueta, grupo o fecha no da error. Un fichero de
etiquetas no construye el lote, así que sus columnas sobrantes no cuentan.

## Ids duplicados y ambiguos

El emparejamiento de feedback busca por `external_id` en toda la versión y
**ordena por lote descendente**: si el mismo id aparece en más de un lote,
gana el registro del lote más reciente (documentado, no un efecto de orden
de inserción de SQLite). Cuando hay más de un candidato, la
fila cuenta como **ambigua** además de emparejada; el resultado del trabajo
trae `n_ambiguos` y, si hay alguna, un aviso.

Al ingerir un lote nuevo (`combined`/`payload`), Vigía cuenta `n_id_duplicados`:
los ids que se repiten dentro del propio fichero más los que ya existían en
`Record` de la misma versión antes de esta ingesta. No bloquea la ingesta,
solo avisa (`avisos` en el resultado del trabajo).

## `id_col` obligatorio salvo que el modelo no reciba feedback

`id_col` es obligatorio en `PUT /datasets/{id}/mapping` para `kind` en
`("combined", "payload")` (además de para `feedback`, como ya era), salvo que
`Project.acepta_feedback` sea `false`: en ese caso se puede omitir sin aviso,
porque el proyecto declara de antemano que nunca va a recibir feedback.

Si un lote se ingirió sin `id_col` en su mapeo (por ejemplo, con
`acepta_feedback=false` en ese momento) y luego llega feedback
para esa versión, el resultado del trabajo de feedback lo dice explícito en
vez de un `n_unmatched` igual al total, indistinguible de «no había
coincidencias»:

> «los lotes de esta versión se subieron sin columna de identificador: el
> feedback no se puede emparejar»

## Sugerencia de mapeo desde la plantilla del modelo

`GET /datasets/{id}` devuelve `suggested_mapping` rellenado desde
`project.mapping_template_json` (favorable, `id_col`, `feature_cols`,
atributo protegido y sus grupos): lo que la plantilla ya fija manda, lo que
le falta lo sigue proponiendo `_suggest_mapping` a partir de las columnas del
fichero. Un mapeo que se guarda apartado de la
plantilla (`PUT /datasets/{id}/mapping`) deja el evento
`dataset.mapeo_distinto_plantilla` en el diario; no bloquea la subida.

## Registros de uso (`refer`)

`POST /projects/{id}/usage-logs/upload` (formulario con `file`, `model_version_id`
opcional y `valor_favorable` opcional).

**Columnas.** Obligatorias: `date`, `human_decision`, `model_output`,
`ground_truth`. Opcionales: `clinician_pseudonym`, `subgroup`, `record_seq`,
`model_version`. `date` admite ISO (`aaaa-mm-dd`), `dd/mm/aaaa` y `dd-mm-aaaa` y
se guarda en ISO; cualquier otra cosa da 422 con el número de fila.

**Subida repetida.** Un fichero con la misma huella sha256 que un
registro de uso ya ingerido en el mismo proyecto da 409, con el nombre y la fecha
de la primera subida, y no suma filas. Para volver a subirlo con otro
`valor_favorable`, reinicia el proyecto (`POST /projects/{id}/reset`).

**Lectura.** Misma detección que los datasets (`core.loaders.
sniff_csv_dialect`): separador coma, punto y coma o tabulador, y codificación
UTF-8 con o sin BOM o Windows-1252. Los errores son 422 en español: formato no
reconocido, fila con otro número de columnas, columnas obligatorias que faltan,
fecha no reconocida (con la fila).

**Valor favorable.** `valor_favorable` es `refer`, `no-refer`, `1` o `0`
y dice qué valor del fichero es la decisión favorable para la persona.
Por defecto `refer`: sin el campo, o con `refer` o `1`, la
subida no recodifica nada. Con `no-refer` o `0` se invierten `human_decision`,
`model_output` y `ground_truth` antes de guardar (los vacíos siguen vacíos). Otro
valor da 422. La declaración queda en `Dataset.mapping_json` del registro
(`{"valor_favorable": ...}`), en el evento `usage_log.ingerido` y en la respuesta.

**Comprobación de la codificación.** La respuesta añade
`comprobacion_codificacion = {estado, r, p, n, motivo}`:

| Dato | Qué es |
|---|---|
| `r` | Tasa de `model_output` favorable del registro ya recodificado. |
| `p` | Media de las tasas de predicción favorable de los lotes de producción de la misma versión (sin la línea base). |
| `n` | Filas del registro con `model_output`. |

| `estado` | Cuándo |
|---|---|
| `inconcluso` | Sin lotes de producción de la versión; o `n` menor de 200; o `|2p-1|` menor de 0,30 (el modelo no se aparta lo bastante del 50 %). `motivo` lo explica. |
| `posible_inversion` | Se puede decidir y `|r-(1-p)| < |r-p|` con `|r-p| > 0,15`. |
| `coherente` | Se puede decidir y no se da lo anterior. |

Es un aviso, nunca un rechazo: la subida se guarda siempre, y el estado
queda en el evento `usage_log.ingerido`. El 0,15 es el umbral por defecto.

## `human_review_zero` como alerta

En la evaluación cruzada, `human_review_zero` en `aviso` (tasa de override del
acumulado por debajo del 1 % con al menos 300 decisiones) abre una alerta del
monitor `cross` con `metric_key = human_review_zero`, severidad `media` y título
«Nadie ha corregido al modelo en N decisiones» si la tasa es 0, o «Revisión humana en
cero: solo el X % de N decisiones corrigió al modelo» si es mayor que 0 (el motivo dice «solo K de N decisiones se
apartaron del modelo»). Con `ok` o `sin_datos` no abre, y
si ya había una abierta la pasa a `en_observacion` como las demás cruzadas.

## Importar el dossier.json de interaction_review

`POST /api/projects/{project_id}/dossiers/import`. Cuerpo: los cuatro campos del `dossier.json` del paquete más actor y motivo.

```json
{
  "system_name": "SistemaX ...", "domain": "General",
  "summary": "Texto del resumen.",
  "sources": [{"id": "doc-producto", "kind": "document", "label": "Ficha", "content": "..."}],
  "include_telemetry": false,
  "actor": "ana", "role": "auditor", "motivo": "dossier del caso externo"
}
```

Las claves de primer nivel que no son esas (por ejemplo `_nota`) se ignoran: no forman parte de `schemas.Dossier` del paquete.

Respuesta: un `Dossier` de Vigía (`id`, `profile`, `experience`, `inventory`, `summary`, `sha256`...). Se revisa igual que cualquier dossier (`POST /api/dossiers/{id}/reviews`; `approach="b0"` no exige backend de LLM). Emite `dossier.creado` con el actor de la petición; `after` lleva `system_name`, `domain`, `telemetry_included`, `origen="dossier.json"` y `n_fuentes`, nunca el texto.

### Tabla de correspondencia kind a plantilla

Solo aparecen tres valores de `kind` (`document`, `technician`, `end_user`); `other` es el cuarto que admite el paquete.

| `kind` | Plantilla de Vigía | Campo | Pregunta de cada respuesta |
|---|---|---|---|
| `technician` | Perfil del sistema (system card) | `profile` | `{label} [{id}]` |
| `end_user` | Experiencia de uso | `experience` | `{label} [{id}]` |
| `document` | Inventario de documentos | `inventory` | `{label} [{id}]` |
| `other` | clave propia | `profile["Fuentes que no encajan en las plantillas (importado de dossier.json)"]` | `[other] {label} [{id}]: {contenido}` |
| contenido vacío, o `document` cuyo contenido es solo «no» | la misma clave propia | idem | idem, con «(sin contenido)» si está vacío |
| `summary` del fichero | clave propia | `profile["Resumen del sistema (importado de dossier.json)"]`, y además `summary` en la fila | el propio resumen |

Notas de lectura:

- Las respuestas llevan el texto original. El saneado de la capa de dossier (`human/dossier_markdown.py`) antepone `\` a una línea de continuación que empiece por un marcador del parser del paquete (`#`, `>`, `**`, `- **`, `- [`, `---`) y cambia ✍ por ✎: no se pierde texto, pero el revisor ve esos caracteres.
- El paquete lee el inventario como `[x] {pregunta}`: en la reconstrucción las fuentes `document` aparecen con ese prefijo.
- El orden entre tipos de fuente no se conserva (el paquete agrupa por plantilla); el orden dentro de cada tipo, sí.
- Dos fuentes con el mismo `label` e `id` se desambiguan con ` #2`, ` #3`.

### 422 en español

El 422 de este endpoint sale como `{"detail": "texto"}` en español y con el campo que falla, tanto si falla el esquema del cuerpo como `schemas.Dossier` del paquete:

```
El dossier.json no es válido. Campos que fallan: sources[0].kind: valor no admitido (admitidos: 'document', 'technician', 'end_user' or 'other')
El dossier.json no es válido. Campos que fallan: sources[0].content: falta este campo
El dossier.json no es válido. Campos que fallan: (documento): el dossier necesita al menos una fuente
```

Hasta cinco campos por mensaje, con «y N más» si hay más. Un proyecto inexistente da 404 y ningún rechazo guarda nada.
