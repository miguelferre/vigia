# Seguridad

Vigía es un programa local para un solo usuario en su equipo. Este documento
dice qué protege y qué no. Cada frase se comprobó en el código de la versión 1.0,
que pasó tres auditorías de seguridad estáticas.

## Qué hace Vigía

- **Escucha solo en 127.0.0.1.** `vigia serve` rechaza cualquier otra dirección
  (`localhost` y `127.0.0.1` son las únicas admitidas) y sale con error.
  Ninguna opción abre el servidor a la red.
- **Rechaza peticiones con `Host` u `Origin` ajenos.** Una página web de otro
  sitio, abierta en el mismo equipo, no puede cambiar datos de Vigía, y una
  dirección que no sea `127.0.0.1` o `localhost` recibe un 403. La comprobación
  de `Origin` no mira el puerto (ver «Qué no protege y qué hacer»). Abre Vigía solo con
  esas direcciones.
- **Exige el tipo de contenido y envía cabeceras de seguridad.** Un cuerpo JSON
  pide `Content-Type: application/json` (`strict_content_type`). Cada respuesta
  lleva `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: no-referrer` y
  `Content-Security-Policy: frame-ancestors 'self'` (solo eso: no es una política
  completa). Otra página no puede enmarcar Vigía. Las páginas `/docs` y `/redoc`,
  que cargan scripts de un CDN, no existen. El esquema de la API sigue abierto en
  `/openapi.json`.
- **No sale a Internet por su cuenta.** Ni envía telemetría ni busca
  actualizaciones. La única llamada externa posible es la revisión del dossier con
  modelo de lenguaje, y solo si la activas (más abajo).
- **Tus datos viven en tu carpeta.** Por defecto, `Documents\vigia-datos`; se
  cambia con la variable `VIGIA_HOME`. Los ficheros que subes y la base de datos
  `vigia.db` se guardan ahí.
- **El apagado remoto pide un token.** `POST /api/shutdown` responde 403 sin la
  cabecera `X-Vigia-Token` con el token del arranque. Ese token está en el
  fichero `vigia.lock` de la carpeta de datos, que `vigia shutdown` lee por ti.
  `vigia shutdown` comprueba antes de enviar el token que el servidor del puerto
  es el dueño del lock, y el MCP lo repite antes de cada llamada: no envían el
  token ni ficheros a otro programa.
- **La subida de un modelo pickle o joblib exige una confirmación explícita.**
  Abrir un pickle ejecuta código. La subida de un modelo `pickle` o `joblib` falla
  con error 422 si la petición no lleva `confirmacion_pickle`, y en ese caso el
  fichero no se abre. La interfaz se lo pide a la persona. Un cliente de la API o
  un agente del MCP fija ese campo él mismo: Vigía no puede saber si un humano lo
  aprobó. Un modelo ONNX no pide confirmación y no ejecuta código de Python al
  cargarse, pero es un fichero de terceros que lee una librería: súbelo solo si
  conoces su origen. Sube un pickle solo si lo has generado tú. Vigía rechaza un
  ONNX con pesos en ficheros aparte. La clasificación de varias clases y la
  regresión usan los mismos formatos (ONNX de `k` clases, regresores ONNX y
  pickle) y el mismo consejo de origen.
- **El MCP actúa con tus permisos.** Un asistente conectado por MCP hace lo que
  hace tu usuario: puede subir datos, cambiar umbrales y reiniciar proyectos. Lo
  que hace queda en el diario, en el carril «agente», con el nombre de la entrada
  del MCP. Las tools destructivas llevan un parámetro `confirm`, pero lo fija el
  propio agente: no es una aprobación humana. La aprobación de cada llamada es del
  host del MCP (Claude Desktop, Claude Code): mantén activa la aprobación de
  herramientas. Lo que el asistente lee pasa por el proveedor de ese asistente:
  usa solo datos que puedas compartir con él.
- **La revisión con modelo envía el dossier a un proveedor solo si la activas.**
  La revisión rápida (sin modelo de lenguaje) se calcula en tu equipo y no envía
  nada. Las revisiones con modelo de lenguaje están desactivadas por defecto. Se
  activan en Ajustes, con el backend «anthropic» y una clave de API de Anthropic,
  y Vigía exige que confirmes que el dossier no lleva datos de personas
  afectadas. Con el backend «ollama» el texto va a la URL que indiques, que se
  espera local. Sin clave, Vigía funciona entero: el resto no la necesita. La
  clave de API se guarda en `vigia.db` **sin cifrar** y la API nunca la
  devuelve (sale enmascarada). Protege la carpeta de datos como protegerías la
  clave.

## Qué no hace

- **No tiene usuarios ni permisos.** Cualquier proceso de tu equipo que alcance
  `127.0.0.1` en el puerto de Vigía puede leer y cambiar todo. Los «roles» de la
  interfaz ordenan la pantalla; no son un control de acceso.
- **El token del MCP separa al agente del humano en el diario; no es un
  secreto fuerte.** La API lo entrega a quien lo pide en el mismo equipo.
- **No cifra la carpeta de datos.** Protégela con el cifrado del disco de tu
  sistema operativo y con los permisos de tu usuario.
- **No desidentifica nada.** Vigía recibe datos ya desidentificados.

## Buenas prácticas

1. Usa un equipo y un usuario de confianza. No lo expongas con un túnel ni un
   proxy inverso.
2. Sube solo datos desidentificados.
3. No actives la revisión con modelo sin que tu organización lo haya aprobado.
4. Carga solo modelos ONNX o pickles que hayas generado tú.
5. Mantén el equipo al día; Vigía no vigila sus propias dependencias.

## Qué no protege y qué hacer

Cada punto dice qué no protege Vigía y qué hacer.

- **La web es la entrada principal.** Vigía rechaza las peticiones con `Host` u
  `Origin` ajenos. Eso no sustituye a un control de acceso: cualquier proceso
  local sigue alcanzando la API. Abre Vigía solo desde `127.0.0.1` o
  `localhost`, y no lo publiques con un túnel ni un proxy inverso.
- **Un agente del MCP fija sus propias confirmaciones.** El parámetro `confirm`
  de las tools lo envía el agente. La aprobación por llamada es del host del MCP
  (Claude Desktop, Claude Code): deja activa la aprobación de herramientas.
- **Con el MCP, un agente puede cargar un modelo pickle** si fija la
  confirmación. Conecta el MCP solo a asistentes de confianza y sube modelos
  que hayas generado tú.
- **El nombre del diario es autodeclarado.** Vigía no tiene cuentas: el actor
  que consta en cada evento lo declara quien llama, y el carril «agente» solo
  prueba que la llamada traía el token del MCP. El diario no es una firma ni
  prueba quién actuó.
- **La copia previa a una migración (`backups\*.bak`) guarda la base entera**,
  con la clave de API de la revisión con modelo incluida y sin cifrar, y no se
  borra al borrar un proyecto. Vigía la hace antes de aplicar cualquier migración
  pendiente sobre una base que ya tenía versión (las migraciones 12 a 15 de esta
  versión incluidas); una base nueva no genera copia. Protege la carpeta de datos
  y borra esas copias a mano cuando ya no las necesites.
- **Las tools del MCP leen ficheros por ruta** con los permisos de tu usuario.
  Vigía rechaza rutas de red y ficheros de más de 200 MB, pero no limita la
  carpeta. Un asistente de confianza es parte de tu modelo de amenazas.
- **El texto de los dossiers y de los ficheros que sube un agente es dato no
  confiable** para el modelo de lenguaje que lo revise. Lee los hallazgos con
  criterio y no los trates como órdenes.
- **Permisos de carpetas.** Vigía no cambia los permisos de la carpeta de
  instalación ni los de una carpeta de datos fuera de tu perfil: otra cuenta de
  Windows del equipo puede escribir en ellas si sus permisos lo dejan. Instala
  Vigía y guarda los datos en una carpeta de tu perfil, o quita a las demás
  cuentas el permiso de escritura.
- **Dependencias de tiempo de build.** El zip se compila con `uv export --locked`
  (el fichero de versiones fijadas, `lock`, manda) y con `npm ci --ignore-scripts`
  (lo que fija `package-lock.json`, sin ejecutar scripts de paquetes), y el
  Python embebido tiene una huella fijada. Quedan fuera del `lock` el propio
  `uv`, que solo avisa si no es la versión verificada, y Node con npm. Compílalo
  solo en un equipo de confianza y compara las versiones con las de `TERCEROS.txt`.
- **La huella `.sha256` del zip no está firmada.** Viaja junto al zip y se
  publica además en el texto de la release, que es otro canal del mismo sitio.
  Comparar las dos detecta un zip cambiado sin tocar ese texto, pero no protege si
  cambia todo el sitio. Si puedes, comprueba la huella por un canal ajeno.
- **La API y Ajustes enseñan la ruta de tus carpetas.** `GET /api/health`
  devuelve la ruta de la carpeta de datos y la de la base de datos, y Ajustes
  muestra la de la carpeta de datos. Esas rutas suelen llevar tu nombre de usuario
  de Windows. No compartas capturas de Ajustes ni la respuesta de `/api/health`
  sin revisarlas. Algunos enlaces de la demo, como `?demo=anotar&texto=`, abren un
  formulario con texto tomado de la dirección. Nada se guarda sin que escribas un
  motivo en el cuadro de confirmación, pero ese texto no lo escribiste tú: no
  abras enlaces a Vigía que no conozcas.
- **La revisión con modelo no es una prueba.** Está apagada por defecto y exige
  una confirmación y una clave (ver «Qué hace»). El criterio de anclaje de un
  hallazgo solo pide directriz, lugar y evidencia no vacíos: Vigía no comprueba
  que la evidencia aparezca en el dossier. El informe escribe «Sin hallazgos»
  siempre que la lista llega vacía, así que no distingue un dossier limpio de una
  respuesta vacía del modelo. Lee los hallazgos con criterio y no deduzcas que un
  dossier está limpio de que no salgan.
- **Vigía no poda nada por su cuenta.** El diario de eventos no se borra nunca,
  ni al reiniciar ni al borrar un proyecto. Los trabajos, las evaluaciones y los
  resultados reales (outcomes) crecen hasta que reinicias o borras el proyecto,
  que retira los de ese proyecto (de los trabajos, solo los terminados). Las copias
  `backups\*.bak` tampoco se podan. `vigia.log` sí rota (5 MB y 3 copias). La base
  se abre con `secure_delete`: las filas borradas se sobrescriben en `vigia.db`,
  pero las copias `.bak` conservan lo que tenían. Borra a mano lo que no
  necesites.
- **Los ficheros que subes se quedan en `uploads\`.** Al ingerir un fichero de
  datos, Vigía sustituye el original por una copia `.privado.csv` con los
  identificadores tal como venían (solo con las columnas mapeadas si desactivas
  guardar las variables de entrada). El CSV del registro de uso queda entero.
  Reiniciar o borrar el proyecto los retira. Si un fichero no se puede retirar,
  por ejemplo porque otro programa lo tiene abierto, queda en disco: Vigía lo
  anota en `vigia.log` y en el diario (`sistema.limpieza_incompleta`) y no lo
  barre al arrancar. Bórralo a mano.
- **Un pickle se carga dentro del proceso de Vigía.** `joblib.load` corre en el
  propio servidor, sin subproceso y sin plazo, con los permisos del proceso, que
  guarda la clave de API en la base. Solo la predicción de prueba tiene un plazo
  de 60 s, que libera la petición pero no detiene el cálculo. Sube un pickle solo
  si lo has generado tú.
- **Tres rutas no acotan su coste y pueden dejar Vigía ocupado.**
  `POST /api/demo/runs` con `project_id` ejecuta la demo dentro de la petición y
  no en la cola. Pedir una explicación carga el lote entero y encola un trabajo
  por petición, sin deduplicar, en la misma cola rápida que las evaluaciones. Un
  modelo ONNX no tiene plazo al validarlo ni al explicar: el de 60 s cubre solo al
  pickle y a la comprobación del orden de las clases. Un ONNX mal formado o muchas
  peticiones pueden retener un hilo o esa cola, y una evaluación puede tardar o
  fallar. Qué hacer: reinicia Vigía (`vigia shutdown` y `vigia serve`; los
  trabajos vivos pasan a «cancelado»), sube solo ONNX de origen conocido y no
  repitas una petición de explicación mientras sigue la anterior.
- **Variables categóricas enormes y borrados en marcha.** Vigía no acota el coste
  del motor con variables categóricas de miles de valores distintos, ni bloquea
  el borrado de un lote o de un dataset mientras un trabajo los usa. Qué hacer: no
  uses variables categóricas con miles de valores y no borres un lote ni un
  dataset con un trabajo en marcha.
- **La comprobación de `Origin` no mira el puerto.** Compara solo el nombre del
  host. Una página servida desde `localhost` o `127.0.0.1` en otro puerto del
  mismo equipo, abierta en tu navegador, pasa la frontera en las peticiones que
  escriben. Qué hacer: mientras Vigía esté en marcha, no abras en ese navegador
  páginas de otros servidores locales que no conozcas, y cierra los que no uses.

## Cómo avisar de un fallo

Escribe por el aviso privado de seguridad de GitHub del repositorio de Vigía
(pestaña «Security», «Report a vulnerability»). No publiques el detalle de un fallo de seguridad en
una incidencia abierta.
