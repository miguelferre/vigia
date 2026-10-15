# Guía de uso

Este capítulo es el mismo texto que la sección «Guía» de la Ayuda de Vigía.

| Nº | Tema |
|---|---|
| 1 | Qué necesitas antes de empezar |
| 2 | Crear un modelo |
| 3 | Subir la línea base |
| 4 | Subir lotes de producción |
| 5 | Configurar monitores, umbrales y alertas |
| 6 | Leer el cuadro de mando |
| 7 | Investigar una alerta |
| 8 | Leer los monitores |
| 9 | Explicabilidad |
| 10 | El diario |
| 11 | Quién hace qué |
| 12 | Dónde está la ayuda |
| 13 | Versiones y comparación |
| 14 | Umbrales y su origen |
| 15 | Plantilla de mapeo |
| 16 | Capa humana |
| 17 | Auditoría |
| 18 | Riesgos |
| 19 | Operar Vigía con un asistente de IA |

## 1. Qué necesitas antes de empezar

**Para qué:** Saber si tu modelo y tus datos encajan en Vigía.

**Pantalla:** `/modelos`

1. Un modelo sobre datos tabulares que ya produce predicciones en tu sistema: de clasificación, con dos clases (por ejemplo, aprobar o denegar) o multiclase (una entre varias clases, de 3 a 20), o de regresión (un número, como los días hasta resolver un caso o las horas de atención por semana). Vigía recibe sus salidas; solo ejecuta el modelo si subes uno ONNX o pickle a la versión, para la explicabilidad.
2. Ficheros CSV o JSON con, por fila, un identificador de fila ya desidentificado (Vigía lo guarda tal como llega), la predicción y su probabilidad (en un modelo multiclase, una probabilidad por clase; en un modelo de regresión, el número predicho y sin probabilidad), el atributo del grupo que quieres vigilar (por ejemplo, la edad) y, cuando existan, la etiqueta real. Si tus datos están en Excel, guárdalos como CSV. En la sección «Datos» de esta Ayuda tienes las columnas de cada fichero y las plantillas para descargar, también la de un modelo multiclase y la de uno de regresión.
3. Datos ya desidentificados: Vigía no sustituye ni oculta identificadores.
4. Una carpeta local de datos en tu equipo; nada sale de él.

## 2. Crear un modelo

**Para qué:** Registrar un despliegue para empezar a vigilarlo.

**Pantalla:** `/modelos`

1. En Modelos, pulsa «Crear modelo».
2. Paso 1: elige el tipo de tarea, que es la primera pregunta: binaria (dos resultados, como aprobar o denegar), multiclase (tres o más clases, como permitido, spam u odio) o regresión (un número, como los días hasta resolver un caso). No se puede cambiar después. Escribe el nombre, elige el dominio del proyecto («General» salvo que uses uno de los ejemplos de la demo), el tipo de modelo («ficheros externos» para un modelo real; «simulado» solo en la demo) y la etapa: desarrollo, validación o producción. La etapa no viene preelegida.
3. Paso «Datos»: elige el fichero de ejemplo de tu línea base. Aquí solo se leen sus columnas, en tu navegador: el fichero todavía no se sube. Comprueba en la vista previa el papel de cada columna. En un modelo binario, indica el valor favorable: el que cuenta como resultado bueno para la persona afectada (por ejemplo, «aprobar»). En un modelo multiclase, revisa las clases que salen del fichero y marca las favorables: al menos una y al menos una sin marcar; elige también la columna de probabilidad de cada clase. En un modelo de regresión no hay valor favorable ni probabilidad: junto a la columna de predicción escribes la unidad de la salida («días», «horas por semana») y, si quieres, el rango favorable, de uno a tres intervalos en esa unidad. La vista previa dice qué parte de las primeras filas del fichero cae dentro del rango. La unidad y el rango se pueden cambiar en la plantilla hasta congelar la línea base; después no cambian. La equidad mide quién recibe el resultado favorable; en regresión sin rango, solo compara el error de cada grupo.
4. Pulsa Continuar. Vigía crea el modelo con su versión 1 y los monitores por defecto, y guarda tus columnas como plantilla de mapeo.
5. Abre el modelo y entra en «Datos»: sube ahí la línea base. Después, en la pestaña «Umbrales», confirma los valores propuestos o ajústalos.

## 3. Subir la línea base

**Para qué:** Fijar el lote de referencia con el que se compara todo lo demás.

**Pantalla:** `/modelos/:id`

1. Abre el modelo y entra en «Datos».
2. Elige el fichero, el tipo (combinado, predicciones o etiquetas reales) y la fase «Línea base».
3. Mapea las columnas de tu fichero a lo que Vigía necesita: predicción, probabilidad, etiqueta y atributo del grupo. Si dudas del formato, abre «Formato y plantillas».
4. Pulsa Subir. La línea base se fija una vez: si la mueves, pierdes la comparación con lo ya vigilado.

## 4. Subir lotes de producción

**Para qué:** Que cada nuevo periodo se evalúe contra la línea base.

**Pantalla:** `/modelos/:id`

1. Mismo camino que la línea base, con la fase «Producción».
2. Añade una etiqueta al lote si quieres reconocerlo en los gráficos (por ejemplo, «marzo»).
3. Si el orden de las filas se ha manipulado, decláralo con su motivo: queda en el diario.
4. Al terminar la ingesta, Vigía evalúa el lote, calcula la explicación global y abre alertas si un monitor cruza su umbral.

## 5. Configurar monitores, umbrales y alertas

**Para qué:** Decidir qué se vigila y a partir de qué valor salta una alerta.

**Pantalla:** `/modelos/:id`

1. Abre el modelo y entra en «Monitores».
2. En equidad, declara el grupo supervisado y el de referencia, y la muestra mínima de la ventana.
3. Ajusta el umbral de cada métrica; en calidad, elige la métrica principal.
4. Activa o desactiva la explicación automática y su método.
5. Cada cambio pide un motivo y queda en el diario con tu nombre.

## 6. Leer el cuadro de mando

**Para qué:** Saber en un vistazo si algo requiere acción.

**Pantalla:** `/cuadro`

1. Las cuatro tarjetas de monitor dicen el estado, la cifra principal y las alertas abiertas; el ⓘ explica cada una.
2. «Alertas por lote» enseña cuándo saltaron, por lote, día u hora; clic en un tramo filtra la tabla.
3. «Alertas que requieren acción» abre cada alerta en un panel sin salir del cuadro.

## 7. Investigar una alerta

**Para qué:** Pasar de la alerta a una decisión con rastro.

**Pantalla:** `/alertas`

1. En Alertas, abre la fila: el panel enseña qué significa, cómo se ha calculado (con la fórmula instanciada y la tabla por grupo) y el historial.
2. Sigue el protocolo por hitos: detección, triaje, investigación, decisión y seguimiento; el estado de cada hito se deriva de lo que ya has hecho.
3. Pon la alerta en observación o ciérrala, sola o en lote; toda acción pide motivo y queda en el diario.
4. Para la métrica ampliada, ve al monitor desde el propio panel.

## 8. Leer los monitores

**Para qué:** Entender por qué ha saltado una alerta.

**Pantalla:** `/monitores/equidad`

1. Cada monitor (equidad, calidad, deriva) enseña sus métricas en rejilla; amplía la que te interese y abre «Cómo se ha calculado».
2. En equidad, la tabla por grupo compara al grupo supervisado con el de referencia; un lote con pocas filas (menos de la muestra mínima, 200 por defecto) sale como «aviso» si el valor cruza el umbral con un intervalo amplio, porque un lote pequeño no basta para confirmar el cruce.
3. En deriva, el bloque «Distribuciones» compara la línea base con el lote (confianza, clases predichas y variables) y la pestaña «Lote a lote» enseña cómo evoluciona cada variable.
4. No confundas dos cifras de deriva con nombre parecido. La «Deriva de características» de la alerta es la mayor puntuación de deriva (KS en numéricas, JS en categóricas) entre todas las variables. El PSI es otra medida del cambio de una variable: la ves en su panel y no entra en la alerta.
5. Cómo se lee la equidad: cada lote evalúa varias medidas, y los umbrales de la línea base se calibran al percentil 99 de cada una. Por multiplicidad, en un lote normal una de ellas puede salir «inestable» sin que haya un problema real. Una «inestable» aislada, sin otras medidas ni lotes que la acompañen, es una invitación a mirar, no una alarma. En un lote con menos filas que la muestra mínima (200 por defecto), ese mismo caso sale como «aviso».

## 9. Explicabilidad

**Para qué:** Saber en qué se fija el modelo y si eso ha cambiado.

**Pantalla:** `/explicabilidad`

1. La explicación global se calcula sola tras cada lote con el método por defecto (permutación); SHAP se lanza a demanda cuando está instalado. Necesita un modelo que Vigía pueda ejecutar: el simulado de la demo, o un modelo ONNX o pickle que hayas subido a la versión. Un modelo de ficheros externos no se puede explicar.
2. La estabilidad del ranking compara la explicación de cada lote con la anterior; con una sola explicación no hay dato.
3. Para un caso concreto, lanza una explicación local y verás hacia dónde empujó cada variable.

## 10. El diario

**Para qué:** Reconstruir qué pasó, quién lo hizo y por qué.

**Pantalla:** `/diario`

1. Cuatro carriles: humano, agente, modelo y sistema; filtra por carril y por periodo.
2. Los eventos de una misma acción comparten correlación (por ejemplo, una ingesta con su evaluación y sus alertas): pulsa la correlación de una fila para ver solo esa cadena.
3. Añade una anotación humana cuando algo ocurra fuera de Vigía (una reunión, una decisión de tu equipo).
4. Exporta el diario para una auditoría.

## 11. Quién hace qué

**Para qué:** Saber qué puede hacer cada rol.

**Pantalla:** `/cuadro`

1. El responsable del modelo configura, hace el triaje y sigue el protocolo.
2. El profesional consulta y aporta su criterio con los overrides; en su vista propia compara sus curvas con las del equipo.
3. Auditoría lee el diario y lo exporta.
4. El cliente tiene una vista reducida, sin laboratorio, mapeos, registros en bruto ni ajustes avanzados.
5. Un asistente de IA puede operar Vigía por MCP (guía 19); sus acciones van al carril «agente».
6. Los botones que no te corresponden aparecen desactivados.

## 12. Dónde está la ayuda

**Para qué:** Resolver una duda sin salir de la pantalla.

**Pantalla:** `/ayuda`

1. El ⓘ de cada tarjeta y métrica abre su explicación.
2. Esta página reúne los símbolos, los conceptos y las métricas por monitor; el buscador filtra todo.
3. La demo recorre un caso completo sobre datos sintéticos y termina en un laboratorio para probar parámetros.

## 13. Versiones y comparación

**Para qué:** Sacar una versión nueva del modelo y ver si mejora a la anterior.

**Pantalla:** `/modelos/:id`

1. En la ficha del modelo, abre Versiones y crea la versión nueva. Cada versión necesita su propia línea base.
2. Sigue los cuatro pasos de la versión nueva: sube su línea base, congélala, sube el modelo si lo tienes (es opcional) y actívala.
3. Los lotes nuevos van a la versión activa. Los monitores, los umbrales y las alertas son del modelo: no cambian con la versión.
4. Con dos versiones o más aparece la pestaña «Comparar». Elige las dos versiones y la ventana: el último lote o todos.
5. Lee la tabla métrica a métrica: el valor de cada lado, la diferencia y un chip con texto que dice mejora, empeora o igual. Un lado sin lotes evaluados sale sin datos.
6. Las alertas vivas salen aparte, porque son del modelo y no de una versión.

## 14. Umbrales y su origen

**Para qué:** Saber de dónde sale cada umbral y cambiarlo con motivo.

**Pantalla:** `/modelos/:id`

1. Abre el modelo y entra en la pestaña «Umbrales», o abre el monitor desde la ficha del modelo.
2. Cada fila enseña la línea base de la métrica, el valor propuesto y el umbral que rige. Pasa el cursor por el título de cada columna para ver qué significa.
3. El origen dice quién fijó el umbral: la línea base, el fabricante, el criterio del responsable, la política de la organización o la fábrica (sin calibrar).
4. Cada cambio pide un motivo y queda en el diario con tu nombre.
5. La línea base no se evalúa al subirla: se evalúa al confirmar los umbrales o con el botón Evaluar.

## 15. Plantilla de mapeo

**Para qué:** No repetir el reparto de columnas en cada fichero.

**Pantalla:** `/modelos/:id`

1. En el alta, elige un fichero de ejemplo de tu línea base (solo se leen sus columnas) y asigna cada columna a su papel. La vista previa enseña las cinco primeras filas con el papel de cada columna.
2. Vigía guarda ese reparto como plantilla de mapeo del modelo.
3. En cada subida, Vigía propone esas columnas. Si el fichero no trae una de ellas, el selector la marca «no está en el fichero».
4. Si cambias algo respecto a la plantilla, la subida sigue y el apartamiento queda en el diario.
5. No marques como variable una columna de fecha ni un identificador: la deriva la vería cambiar en cada lote.

## 16. Capa humana

**Para qué:** Ver cómo decide la persona profesional frente al modelo.

**Pantalla:** `/capa-humana`

1. En Capa humana, sube el registro de uso del modelo: un CSV con una fila por decisión. Elige qué valor es el favorable. En un modelo de regresión con rango favorable, el registro trae cifras (la de la persona profesional, la del modelo y el valor real) y Vigía decide si cada cifra cae dentro o fuera del rango; sin rango, la capa humana no está disponible. Si dudas del formato, abre «Formato y plantillas».
2. Deskilling enseña, ventana a ventana, la coincidencia entre profesional y modelo, el acierto de cada uno y la tasa de rescate. Es una invitación a investigar, no una conclusión.
3. Los overrides cuentan las decisiones distintas de la del modelo, por subgrupo, por fase o entre profesionales, nunca por nombre. La tabla de cambios enseña, para cada salida del modelo, qué decidió la persona profesional: refer y no-refer en un modelo binario, cada clase en uno multiclase y dentro o fuera del rango en uno de regresión. Una fila con menos de 30 decisiones enseña sus recuentos y deja la tasa en blanco.
4. Las reglas cruzadas comparan el modelo con el registro de uso y abren alertas de la capa humana.
5. Los outcomes son el resultado del sistema completo por periodo. Nunca abren una alerta.
6. Cómo se lee el deskilling: la señal mide una pendiente sobre todo el histórico de la versión. Las ventanas con menos de 30 decisiones no cuentan en la pendiente. Mira la serie de coincidencia por ventana, no solo la señal, y compara las ventanas antiguas con las recientes.
7. En regresión, un cambio de la persona profesional que no cruza el corte del rango favorable no cuenta como override, porque la decisión se deriva de si la cifra cae dentro o fuera. Un profesional que corrige 20 horas a 22 cuando el rango empieza en 12 sigue en el mismo lado y no suma. Por subgrupo y por fase, Vigía enseña además la diferencia media entre la cifra de la persona profesional y la del modelo, en la unidad de la salida. Es informativa: no tiene umbral ni abre alertas. Qué hacer: úsala para ver dónde corrige más la persona profesional aunque no cambie de lado.
8. En regresión, fija el rango favorable antes de subir el registro de uso: el registro toma la pertenencia al rango vigente en el momento de la subida.

## 17. Auditoría

**Para qué:** Preparar el dossier y revisarlo contra las directrices de auditoría.

**Pantalla:** `/auditoria`

1. En Auditoría, rellena el dossier: perfil del sistema, experiencia de uso e inventario de documentos. Puedes empezar desde una plantilla.
2. Si quieres, adjunta el resumen de deskilling.
3. Lanza la revisión. Por defecto no usa modelo de lenguaje; con un backend configurado en Ajustes puedes elegir el otro enfoque.
4. Lee los hallazgos, con su severidad, y el informe en HTML. La correspondencia con las normas de gestión de riesgos y el AI Act sale agrupada por marco.
5. La revisión se puede reproducir: el informe guarda la versión del paquete y las huellas del dossier y de las directrices.

## 18. Riesgos

**Para qué:** Seguir en el tiempo un problema que salió de una alerta.

**Pantalla:** `/riesgos`

1. Desde una alerta, registra el riesgo con su impacto y su probabilidad.
2. Vigía le da un código R-nnn y lo ubica en la matriz de impacto por probabilidad.
3. Actualiza el riesgo cuando cambie algo. Cada cambio pide un motivo y queda en el diario.
4. Es el formato que conoce auditoría (normas de gestión de riesgos y AI Act).

## 19. Operar Vigía con un asistente de IA

**Para qué:** Que un asistente como Claude lea y opere Vigía por ti, con rastro en el diario.

**Pantalla:** `/ajustes`

1. Arranca Vigía antes de abrir el asistente. El asistente habla con tu copia local de Vigía. Lo que lee pasa por el asistente: usa solo datos que puedas compartir con él.
2. En Claude Code, escribe en el fichero .mcp.json del proyecto: {"mcpServers": {"vigia": {"command": ".venv\\Scripts\\python.exe", "args": ["-m", "vigia", "mcp", "--url", "http://127.0.0.1:<puerto de Vigía>", "--actor", "claude-code"]}}}
3. En Claude Desktop, cierra la aplicación y añade esta entrada a claude_desktop_config.json, en la carpeta %APPDATA%\Claude\ (haz antes una copia del fichero): {"mcpServers": {"vigia": {"command": "vigia-mcp", "args": ["--data-dir", "<carpeta de datos>"]}}}
4. El asistente dispone de 39 herramientas: ver proyectos, alertas y medidas; subir datos; evaluar; configurar monitores; y trabajar con riesgos, dossier y versiones.
5. Todo lo que hace queda en el diario, en el carril «agente», con el nombre que pusiste en «--actor».
