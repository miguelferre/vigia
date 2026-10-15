# Qué hacer si

Los problemas más frecuentes, con la causa y qué hacer.

## Windows bloquea un fichero de Vigía

**Qué ves.** Un mensaje como «Una directiva de Control de aplicaciones bloqueó
este archivo» (error 4551) en `vigia.log` o en la consola, o una ventana de
Windows que impide abrir un `.cmd` o un `.pyd`.

**Causa.** El Control de aplicaciones inteligente de Windows decide por la firma
y la reputación de cada fichero, no por la carpeta. Los ficheros de Vigía son
nuevos para el sistema y pueden no tener reputación todavía. Vigía no está
firmado con un certificado de código.

**Qué hacer.**

1. Antes de extraer, abre las propiedades del zip. Si hay una casilla
   «Desbloquear», márcala y acepta. Después extrae el zip con el Explorador.
2. Si ya lo extrajiste, vuelve a extraerlo desde un zip desbloqueado en una
   carpeta nueva.
3. Espera y reintenta una vez: a veces el bloqueo es la primera carga (siguiente
   punto) y se resuelve solo.
4. Si el error vuelve a salir con el mismo fichero, es un bloqueo de política: no
   se arregla reintentando. Cambiar esa política es una decisión de seguridad de
   tu equipo, no de Vigía. Consúltala con quien lo administre.

Vigía separa los dos casos: el escaneo lento se reintenta solo; el bloqueo de
política se para y nombra el fichero.

## La primera carga es lenta

**Qué ves.** Haces doble clic en `Vigia.cmd` y el navegador tarda en abrirse,
a veces dos minutos o más.

**Causa.** Windows escanea los ficheros nuevos la primera vez que se usan. Con el
zip recién extraído, el primer arranque puede tardar dos o tres minutos, y la
explicabilidad (SHAP) puede añadir otro minuto la primera vez que se usa. Los
arranques siguientes tardan unos segundos.

**Qué hacer.** Espera. No cierres la ventana ni lances Vigía otra vez. Si quieres
ver qué hace, arranca con `Vigia-consola.cmd`.

## El navegador no se abre, o no sé el puerto

Vigía busca un puerto libre a partir del 8765. Con `Vigia.cmd` no hay consola
que lo diga. Para saber cuál es, abre `vigia.lock` en la carpeta de datos con un
editor de texto: lleva el puerto en el campo `port`. Escribe en el navegador
`http://127.0.0.1:<puerto>`.

## «Vigía ya está en marcha» o puerto ocupado

- Dos Vigías no pueden usar la misma carpeta de datos a la vez. Si el segundo
  arranque falla con «Vigía ya está en marcha», usa el primero (el puerto está en
  `vigia.lock`) o apágalo antes con
  `runtime\python\python.exe -m vigia shutdown`.
- Si arrancas con `--port <n>` y el puerto está ocupado, Vigía lo dice y no
  arranca: prueba otro número. Sin `--port`, Vigía elige uno libre solo.
- Si Vigía se cerró de golpe y quedó un `vigia.lock` viejo, no estorba: Vigía lo
  ignora si el proceso que lo escribió ya no existe.

## Vigía no lee mi fichero

**Qué ves.** Un error de la subida que nombra el fichero, la fila o la columna.

**Qué hacer.**

- Vigía lee **CSV** (también `.tsv` y `.txt`) y **JSON** en lista de objetos. No
  abre `.xlsx` ni `.xls`.
- Para guardar un Excel como CSV: en Excel, «Archivo», «Guardar como», y elige
  «CSV UTF-8 (delimitado por comas)». Guarda solo la hoja con los datos, con la
  cabecera en la primera fila.
- Vigía detecta solo el separador (coma, punto y coma o tabulador), el decimal
  (punto o coma) y la codificación (UTF-8 con o sin BOM, o Windows-1252).
- Las fechas van mejor como `aaaa-mm-dd`. Una fecha ilegible no rechaza el
  fichero: Vigía avisa con el número de filas y un ejemplo.
- Comprueba las columnas con la guía de datos del manual o, dentro de la app, con
  la sección «Datos» de Ayuda. Allí hay una plantilla con datos sintéticos para
  cada fichero.

## Dónde están mis datos

En `Documents\vigia-datos`, dentro de tu carpeta de usuario, salvo que hayas
pasado otra carpeta a `Vigia.cmd` o fijado la variable de entorno `VIGIA_HOME`.
Ajustes muestra la carpeta que está en uso. Ahí están `vigia.db` (base de datos),
los ficheros subidos, los modelos y `vigia.log`. Haz copia de esa carpeta.

## La revisión del dossier con modelo no funciona

Vigía tiene dos métodos de revisión del dossier de auditoría:

- **Rápida, sin modelo de lenguaje.** Funciona siempre, en tu equipo, sin clave.
- **Con modelo de lenguaje.** Está desactivada por defecto. Para usarla, activa un
  backend en Ajustes. Con el backend «anthropic» hace falta una clave de API de
  Anthropic (la que Anthropic llama `ANTHROPIC_API_KEY`), que escribes en el campo
  «Clave de API» de Ajustes, y confirmar que el dossier no lleva datos de
  personas afectadas. El texto del dossier se envía al proveedor. Con el backend
  «ollama» hace falta un servidor Ollama en la URL que indiques.

**Sin clave, Vigía funciona entero.** Solo esa revisión necesita el modelo. Si el
método con modelo sale desactivado en Auditoría, es que no hay backend activo en
Ajustes.

## Un modelo pickle me pide confirmación

Es a propósito. Abrir un fichero pickle o joblib ejecuta el código que lleva.
Súbelo solo si lo generaste tú y confirma la subida. Un modelo ONNX no pide
confirmación; súbelo solo si conoces su origen. Mira `SEGURIDAD.md`.

## Vigía dice que ya hay 50 proyectos de demo

Es el máximo (error 409): cada demo crea su propio proyecto y no se borran solos.
Abre uno de los proyectos de demo, entra en su Configuración y usa «Borrar
despliegue». Después crea la demo otra vez.

## Vigía dice que un fichero ya está ingerido

Un fichero de datos ya ingerido no se vuelve a mapear ni a ingerir (error 409):
Vigía borra el fichero en bruto al terminar la ingesta. Si necesitas otro mapeo,
sube el fichero otra vez. Mira la guía de datos.

## Otras cosas

- **Quiero empezar de cero.** Apaga Vigía y mueve la carpeta `vigia-datos` a otro
  sitio. Vigía creará una nueva al arrancar.
- **Algo no cuadra y no sé qué.** Mira `vigia.log` en la carpeta de datos, o
  arranca con `Vigia-consola.cmd` y lee la consola.
