# Qué datos necesita Vigía

Este capítulo es el mismo texto que la sección «Datos» de la Ayuda de Vigía.

Vigía necesita hasta cinco ficheros y, de forma opcional, el modelo. Descarga una plantilla, cambia las filas por las tuyas y súbela. Un modelo multiclase, con más de dos clases, y un modelo de regresión, que predice un número, usan su propia plantilla de línea base.

> Las plantillas llevan datos sintéticos de ejemplo. No contienen datos de personas reales. Sustituye las filas por las tuyas ya desidentificadas.

## Formatos admitidos

- **Ficheros.** CSV con cabecera (también .tsv y .txt) o JSON en lista de objetos, un objeto por fila.
- **Separador.** Coma, punto y coma o tabulador. Vigía lo detecta solo.
- **Decimal.** Punto o coma. Vigía lo detecta solo.
- **Codificación.** UTF-8, con o sin BOM, o Windows-1252. Vigía lo detecta solo.
- **Excel.** Guárdalo como CSV (Archivo, Guardar como, CSV UTF-8). Vigía no abre ficheros .xlsx.
- **Fechas ilegibles.** Si la fecha de un lote no se lee, Vigía avisa con el número de filas y un ejemplo, y guarda la columna tal como viene. No rechaza el fichero.

Fechas admitidas:

| Formato | Ejemplo | Nota |
|---|---|---|
| aaaa-mm-dd | `2026-03-02` | Es el formato recomendado, en todos los ficheros. |
| dd/mm/aaaa y dd-mm-aaaa | `02/03/2026` | Se leen también en el registro de uso. El día va primero. |

## Cómo decidir la clase favorable

La clase favorable es el valor que cuenta como resultado bueno para la persona. La equidad mide quién lo recibe.

**¿Qué resultado quiere recibir la persona afectada?**

1. Piensa en la persona afectada, no en la clase positiva del modelo.
2. Busca ese valor en tu columna de etiqueta o de predicción, tal como está escrito.
3. Elígelo como valor favorable en el alta del modelo.
4. En un modelo multiclase puedes elegir varias clases favorables: son el conjunto favorable, de una a todas menos una. La equidad mide quién recibe una clase de ese conjunto. Si no eliges ninguna, la equidad solo compara la exactitud y la F1 macro de cada grupo.
5. Un modelo de regresión no tiene clase favorable: si quieres medir la equidad por el resultado, declara un rango favorable en la unidad de la salida, de uno a tres intervalos. Sin rango, la equidad solo compara el error de cada grupo.
6. En el registro de uso, refer (o 1) es la decisión favorable. Si en tu fichero la favorable es la contraria, elige no-refer (o 0) al subirlo: Vigía invierte las tres columnas al guardar.

Ejemplos:

| Caso | Valor favorable | Motivo |
|---|---|---|
| El modelo decide si se aprueba la solicitud de una persona. | Aprobar (por ejemplo 1) | Aprobar beneficia a la persona. |
| El modelo marca un riesgo alto: 1 es riesgo y 0 es sin riesgo. | Sin riesgo (por ejemplo 0) | Que la marquen como riesgo no beneficia a la persona. |
| Un modelo multiclase decide si un mensaje es permitido, dudoso o prohibido. | Permitido (una sola clase favorable) | Es lo que la persona quiere recibir. Si «dudoso» también le conviene, el conjunto favorable es permitido y dudoso. |

## Si la comprobación de codificación sale «inconclusa»

Al subir el registro de uso, Vigía compara las decisiones favorables del modelo en el registro con las de sus lotes, para avisar si la codificación está al revés. Sale «inconclusa» cuando no puede decidir: hay menos de 200 decisiones del modelo, no hay lotes todavía, o el modelo da casi todas las decisiones del mismo signo. No es un error: la subida se hace igual.

1. Decide por el significado de la decisión en tu equipo: qué valor es el favorable para la persona.
2. Elige ese valor al subir el registro: refer o no-refer.
3. Anota tu elección en el motivo, para que quede en el diario.

## Línea base

El lote con el que se compara todo lo demás: lo que hizo el modelo antes de ponerlo en uso, con el resultado real.

**Cómo se sube en Vigía:** Combinado, fase «Línea base».

**Plantilla con datos sintéticos:** `plantilla-linea-base-sintetico.csv`.

Columnas obligatorias:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `id` | Identificador de la fila, ya desidentificado; Vigía lo guarda tal como llega. Une las etiquetas que llegan después con su fila. | Texto o número, distinto en cada fila y sin datos personales. | `L-001` |
| `prediction` | La decisión que dio el modelo. | En un modelo de dos clases, dos valores: por ejemplo 1 y 0, o aprobar y denegar. En un modelo multiclase, la clase que predice el modelo (ver «Línea base de un modelo multiclase»). En un modelo de regresión, un número (ver «Línea base de un modelo de regresión»). | `1` |
| `label` | El resultado real de la fila. | En un modelo de dos clases, dos valores, con la clase favorable entre ellos. En un modelo multiclase, la clase real. En un modelo de regresión, el valor real, un número. | `1` |

Columnas opcionales:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `probability` | En un modelo de dos clases, la probabilidad que dio el modelo a la clase positiva. Con ella, Vigía vigila la confianza del modelo. Un modelo multiclase lleva una columna por clase, no esta, y un modelo de regresión no lleva probabilidad. | Número entre 0 y 1. | `0.87` |
| `date` | Fecha de la fila. | aaaa-mm-dd. | `2026-03-02` |
| `age_years` | El atributo del grupo que quieres vigilar, por ejemplo la edad. Sin él, el monitor de equidad no tiene qué comparar. | Número (se agrupa por rangos) o texto (cada valor es un grupo). | `61` |
| `crp, esr, joint_count` | Las variables que usa el modelo. Con ellas, Vigía vigila la deriva de cada una. | Una columna por variable, numérica o de texto. No marques fechas ni identificadores. | `18.4` |

- Cada versión del modelo tiene su propia línea base.
- Se congela sola al ingerirla: si la cambias después, pierdes la comparación con lo ya vigilado.
- Un fichero ya ingerido no se vuelve a mapear ni a ingerir: Vigía responde con el error 409. Si necesitas otro mapeo, sube el fichero otra vez.
- Vigía reserva estos nombres de columna para sus propios datos: seq, batch_seq, model_version, external_id, timestamp, prediction, prob_favorable, label, protected_value, group_code, clinician_pseudonym, subgroup, prediction_class, label_class, prediction_value, label_value, y prob__ seguido de un número. Una columna con uno de ellos que no hace de identificador, predicción, probabilidad, etiqueta, grupo o fecha en el mapeo da el error 422, porque pasaría a ser una variable del modelo. Renómbrala en el fichero.

## Lotes de producción

Cada periodo de uso real del modelo. Cada lote se evalúa contra la línea base.

**Cómo se sube en Vigía:** Combinado si el fichero trae la etiqueta; Predicciones si las etiquetas llegan después. Fase «Producción».

**Plantilla con datos sintéticos:** `plantilla-lote-sintetico.csv`.

Columnas obligatorias:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `id` | Identificador de la fila, ya desidentificado; Vigía lo guarda tal como llega. Une las etiquetas que llegan después con su fila. | Texto o número, distinto en cada fila y sin datos personales. | `L-001` |
| `prediction` | La decisión que dio el modelo. | En un modelo de dos clases, dos valores: por ejemplo 1 y 0, o aprobar y denegar. En un modelo multiclase, la clase que predice el modelo (ver «Línea base de un modelo multiclase»). En un modelo de regresión, un número (ver «Línea base de un modelo de regresión»). | `1` |

Columnas opcionales:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `probability` | En un modelo de dos clases, la probabilidad que dio el modelo a la clase positiva. Con ella, Vigía vigila la confianza del modelo. Un modelo multiclase lleva una columna por clase, no esta, y un modelo de regresión no lleva probabilidad. | Número entre 0 y 1. | `0.87` |
| `date` | Fecha de la fila. | aaaa-mm-dd. | `2026-03-02` |
| `age_years` | El atributo del grupo que quieres vigilar, por ejemplo la edad. Sin él, el monitor de equidad no tiene qué comparar. | Número (se agrupa por rangos) o texto (cada valor es un grupo). | `61` |
| `crp, esr, joint_count` | Las variables que usa el modelo. Con ellas, Vigía vigila la deriva de cada una. | Una columna por variable, numérica o de texto. No marques fechas ni identificadores. | `18.4` |
| `label` | El resultado real de la fila. | En un modelo de dos clases, dos valores, con la clase favorable entre ellos. En un modelo multiclase, la clase real. En un modelo de regresión, el valor real, un número. | `1` |

- Las columnas son las mismas que en la línea base: Vigía sugiere el mapeo desde la plantilla del modelo.
- El identificador no debe repetirse entre la línea base y los lotes.

## Etiquetas que llegan tarde

El resultado real de filas que ya subiste sin etiqueta. Vigía las empareja por identificador.

**Cómo se sube en Vigía:** Etiquetas reales, fase «Producción».

**Plantilla con datos sintéticos:** `plantilla-etiquetas-sintetico.csv`.

Columnas obligatorias:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `id` | El mismo identificador que tenía la fila en su lote. | Debe existir en un lote ya subido. | `L-001` |
| `label` | El resultado real de la fila. | En un modelo de dos clases, dos valores, con la clase favorable entre ellos. En un modelo multiclase, la clase real. En un modelo de regresión, el valor real, un número. | `1` |

- Las filas sin pareja se cuentan en el resultado de la ingesta.
- Si un identificador sale en varios lotes, la etiqueta va al lote más reciente.
- Una etiqueta ya registrada no se sobrescribe, y la de una fila de la línea base congelada tampoco. La ingesta cuenta esas etiquetas en `etiquetas_omitidas` y avisa. Para cambiar la línea base, crea una versión nueva del modelo.
- Un fichero de etiquetas ya ingerido no se vuelve a ingerir (error 409): sube el fichero otra vez.

## Registro de uso

Una fila por decisión: qué decidió la persona profesional, qué recomendó el modelo y qué pasó. Alimenta el deskilling, los overrides y las alertas cruzadas.

**Cómo se sube en Vigía:** Registro de uso, en la pantalla de Capa humana.

**Plantilla con datos sintéticos:** `plantilla-registro-uso-sintetico.csv`.

Columnas obligatorias:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `date` | Fecha de la decisión. | aaaa-mm-dd, dd/mm/aaaa o dd-mm-aaaa. Cualquier otro formato da error con el número de fila. | `2026-03-02` |
| `human_decision` | Lo que decidió la persona profesional. | refer o no-refer (también 1 o 0). En blanco se guarda como sin dato. | `refer` |
| `model_output` | Lo que recomendó el modelo en esa decisión. | refer o no-refer (también 1 o 0). En blanco se guarda como sin dato. | `no-refer` |
| `ground_truth` | El desenlace real, cuando se conoce. | refer o no-refer (también 1 o 0). En blanco si todavía no se sabe. | `refer` |

Columnas opcionales:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `clinician_pseudonym` | Seudónimo de la persona profesional. Permite ver a cada profesional por separado. | Texto libre, ya seudonimizado: Vigía no oculta identificadores. | `prof-01` |
| `subgroup` | Unidad o grupo de personas afectadas, para separar el deskilling por subgrupo. | Texto libre. | `unidad-a` |
| `record_seq` | Número de la fila del lote al que corresponde la decisión. Se guarda como referencia; no se cruza con las filas del lote. | Número entero. Un valor que no sea número da error. | `17` |
| `model_version` | Versión del modelo. Se admite porque la exportación la escribe, pero la subida no la lee. | La versión se elige en el formulario de subida, no en el fichero. | `v1` |

- Las fechas admiten tres formatos; los otros dan error con el número de fila.
- Las fechas del registro deben caer en periodos con lotes: si no, las reglas cruzadas las usan igual, pero sin lote que las acompañe.
- Si subes dos veces el mismo registro de uso al mismo modelo, la segunda subida da el error 409 y no suma nada. Para volver a subirlo con otro valor favorable, reinicia el modelo.

## Outcomes

El resultado del sistema completo, persona más modelo, por periodo. Sirve para ver su evolución; nunca abre una alerta por sí mismo.

**Cómo se sube en Vigía:** Outcomes, en la pantalla de Capa humana.

**Plantilla con datos sintéticos:** `plantilla-outcomes-sintetico.csv`.

Columnas obligatorias:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `period` | El periodo al que corresponde el dato. | Texto, por ejemplo un mes: aaaa-mm. | `2026-03` |
| `metric_key` | El nombre de la medida. | Texto libre, siempre igual para la misma medida. | `tasa_decision_correcta` |
| `value` | El valor de la medida. | Número. En blanco se guarda como sin dato. | `0.83` |
| `source` | De dónde sale el dato. | Texto libre. | `manual` |

- Cada combinación de periodo, medida y origen sale una sola vez en el fichero.
- Si subes otra vez la misma combinación, Vigía actualiza el valor.

## Línea base de un modelo multiclase

Un modelo multiclase predice una entre varias clases, de 3 a 20, y no una decisión de dos valores. Este fichero es la línea base de un modelo así: la clase predicha, la clase real y una probabilidad por clase.

**Cómo se sube en Vigía:** Combinado, fase «Línea base», en un modelo con el tipo de tarea multiclase.

**Plantilla con datos sintéticos:** `plantilla-multiclase-sintetico.csv`.

Columnas obligatorias:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `id` | Identificador de la fila, ya desidentificado; Vigía lo guarda tal como llega. Une las etiquetas que llegan después con su fila. | Texto o número, distinto en cada fila y sin datos personales. | `L-001` |
| `prediction` | La clase que predijo el modelo, escrita igual que en la lista de clases del modelo. | Una de las clases, de 3 a 20. | `grave` |
| `prob_<clase>` | Una columna por clase, con la probabilidad que el modelo dio a esa clase. Van en el mismo orden que la lista de clases. | Número entre 0 y 1. Las columnas de una fila suman 1. | `0.70` |
| `label` | La clase real de la fila, escrita igual que en la lista de clases. | Una de las clases. | `grave` |

Columnas opcionales:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `date` | Fecha de la fila. | aaaa-mm-dd. | `2026-03-02` |
| `age_years` | El atributo del grupo que quieres vigilar, por ejemplo la edad. Sin él, el monitor de equidad no tiene qué comparar. | Número (se agrupa por rangos) o texto (cada valor es un grupo). | `61` |
| `crp, esr, joint_count` | Las variables que usa el modelo. Con ellas, Vigía vigila la deriva de cada una. | Una columna por variable, numérica o de texto. No marques fechas ni identificadores. | `18.4` |

- Las clases se declaran al crear el modelo, con su orden. Si no las declaras, Vigía las propone desde la columna de predicción de la línea base y las fija al congelarla.
- Las columnas de probabilidad se llaman prob_ seguido del nombre de la clase, por ejemplo prob_grave, y van en el mismo orden que las clases. Si el orden no coincide con la predicción, la ingesta avisa.
- El conjunto de clases favorables tiene de 1 a todas menos una de las clases, o ninguna. La equidad y las tasas favorables miden la pertenencia a ese conjunto. Sin conjunto favorable, la equidad solo compara la exactitud y la F1 macro de cada grupo, sin umbral.
- Las etiquetas de texto se leen sin espacios al principio ni al final. Si una etiqueta solo se distingue por las mayúsculas de una clase declarada, Vigía la asigna a esa clase y lo avisa.
- Una predicción con una clase que no está en la lista da error y dice cuáles son las clases del modelo. Si es una versión nueva del modelo, créala.
- Una clase real que no está en la lista no bloquea el fichero: esas filas se ingieren, quedan fuera de la calidad y la ingesta lo cuenta en un aviso.
- La plantilla lleva una columna de probabilidad por clase. Si tus probabilidades vienen en una sola columna, como una lista con una probabilidad por clase en el orden de las clases, indícalo en el mapeo (formato de lista); la plantilla no cubre ese formato.
- Los lotes de producción llevan las mismas columnas; la clase real llega con ellos o después, como en un modelo de dos clases.

## Línea base de un modelo de regresión

Un modelo de regresión predice un número, por ejemplo los días hasta resolver un caso o las horas de atención por semana, y no una clase. Este fichero es la línea base de un modelo así: el número predicho y el valor real.

**Cómo se sube en Vigía:** Combinado, fase «Línea base», en un modelo con el tipo de tarea regresión.

**Plantilla con datos sintéticos:** `plantilla-regresion-sintetico.csv`.

Columnas obligatorias:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `id` | Identificador de la fila, ya desidentificado; Vigía lo guarda tal como llega. Une las etiquetas que llegan después con su fila. | Texto o número, distinto en cada fila y sin datos personales. | `L-001` |
| `prediction` | El número que predijo el modelo, en la unidad de la salida. | Número, con punto o coma decimal y sin la unidad pegada: 12, no «12 h». Sin celdas vacías, textos como «nan» ni valores infinitos. | `5.9` |
| `label` | El valor real de la fila, en la misma unidad que la predicción. | Número. En blanco si todavía no se conoce: la fila queda sin valor real. | `5.0` |

Columnas opcionales:

| Columna | Qué es | Valores | Ejemplo |
|---|---|---|---|
| `date` | Fecha de la fila. | aaaa-mm-dd. | `2026-03-02` |
| `age_years` | El atributo del grupo que quieres vigilar, por ejemplo la edad. Sin él, el monitor de equidad no tiene qué comparar. | Número (se agrupa por rangos) o texto (cada valor es un grupo). | `61` |
| `crp, esr, joint_count` | Las variables que usa el modelo. Con ellas, Vigía vigila la deriva de cada una. | Una columna por variable, numérica o de texto. No marques fechas ni identificadores. | `18.4` |

- La unidad de la salida (por ejemplo «días» u «horas por semana») se escribe al crear el modelo, no en las celdas. Las medidas de error y los umbrales de calidad se leen en esa unidad. No cambia después.
- Un modelo de regresión no lleva probabilidad ni clases. Si el mapeo trae una columna de probabilidad o un valor favorable, Vigía lo rechaza y nombra el campo. Si la predicción es texto con pocas clases, parece un modelo de clasificación: crea un modelo binario o multiclase.
- El rango favorable es opcional. Son de uno a tres intervalos en la unidad de la salida, con los extremos incluidos y un extremo vacío para un intervalo abierto: «desde 12 horas por semana» o «hasta 3 días». Se fija al crear el modelo o al congelar la línea base, y después no cambia: si necesitas otro, crea un modelo nuevo.
- Con rango favorable, la equidad y las tasas favorables miden si el valor cae dentro del rango, y la capa humana cuenta cada decisión como dentro o fuera del rango. Sin rango, Vigía solo compara el error de cada grupo (la diferencia y la razón del error absoluto medio, y la diferencia del sesgo) y la capa humana no está disponible.
- Una predicción vacía, de texto o infinita da error, con el número de filas y la primera fila afectada. Un valor real vacío deja la fila sin etiqueta. Un valor real de texto en algunas filas se avisa y también las deja sin etiqueta.
- Una predicción con el mismo valor en todas las filas o con solo dos valores distintos da un aviso: comprueba que es la columna correcta. Un lote con otra unidad, por ejemplo minutos en vez de horas, no bloquea la subida: la deriva de la predicción lo detecta.
- Si creas el modelo por la API o el MCP sin unidad ni rango favorable, fíjalos con la plantilla de mapeo (target_unit y favorable_ranges en set_mapping_template) antes de congelar la línea base: después no cambian.
- Los lotes de producción llevan las mismas columnas. El valor real llega con ellos o después, en un fichero de etiquetas con el identificador y el número.
- El registro de uso de un modelo de regresión con rango trae cifras en las columnas de siempre: human_decision es la cifra de la persona profesional, model_output es la cifra del modelo y ground_truth es el valor real, que puede ir en blanco. Son números con punto decimal y sin unidad. refer, no-refer o un texto dan error con el número de fila. No se indica valor favorable y no se comprueba la codificación: Vigía deriva solo si cada cifra cae dentro o fuera del rango.

## El modelo (opcional)

Vigía vigila sin el modelo. Solo lo necesita para explicar una fila concreta o calcular la explicación global.

**Cómo se sube en Vigía:** Versión con modelo ejecutable.

- Formatos admitidos: ONNX, o un pickle o joblib de scikit-learn con predict_proba.
- Un regresor en ONNX se exporta con entradas float32: con columnas float64 el grafo sale en doble precisión y Vigía no puede cargarlo.
- Un pickle ejecuta código al abrirse: súbelo solo si lo has generado tú. Vigía pide confirmarlo.
- Sin modelo, el modelo es de ficheros externos y Vigía recibe sus salidas.
