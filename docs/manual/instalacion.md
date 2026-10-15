# Instalación

Vigía se distribuye como un zip para Windows 11 de 64 bits. Lleva su propio
Python y todas sus dependencias: no hace falta instalar nada más ni tener
permisos de administrador.

## Qué necesitas

- Windows 11, 64 bits.
- Unos 600 MB libres para la carpeta extraída, más el espacio de tus datos.
- Un navegador. Vigía abre el que tengas por defecto.

## Qué trae el zip

| Fichero | Para qué sirve |
|---|---|
| `Vigia.cmd` | Arranca Vigía sin ventana de consola y abre el navegador |
| `Vigia-consola.cmd` | Arranca Vigía con una consola que enseña el registro; cierra la ventana para pararlo |
| `LEEME.txt` | Resumen del paquete: versión de Vigía y de Python |
| `README.md` y `docs\manual\` | Este manual y la guía de primeros pasos |
| `LICENSE`, `NOTICE`, `TERCEROS.txt` | Licencia de Vigía y las de los componentes de terceros |
| `runtime\` | Python embebido y las bibliotecas. No lo toques |

Junto al zip hay dos ficheros más: `vigia-1.0.0-win64.zip.sha256`, con la huella
del zip, y `vigia-1.0.0-win64.zip.MANIFIESTO.txt`, con la lista de ficheros, sus tamaños y las
versiones de los paquetes.

## Pasos

1. **Comprueba la huella.** En una consola de PowerShell, en la carpeta del zip:

   ```
   Get-FileHash vigia-1.0.0-win64.zip -Algorithm SHA256
   ```

   El resultado debe coincidir con el contenido de `vigia-1.0.0-win64.zip.sha256`.
   Si no coincide, descarga el zip otra vez.

2. **Extrae el zip entero** en una carpeta tuya, con una ruta corta y sin
   acentos, por ejemplo `C:\Vigia`. Usa «Extraer todo» del Explorador de archivos.
   No arranques Vigía desde dentro del zip.

3. **Arranca.** Doble clic en `Vigia.cmd`. En unos segundos se abre el navegador
   con Vigía. Si es la primera vez, mira el capítulo «Qué hacer si»: la primera
   carga puede tardar dos minutos o más.

4. **Para apagar.** La interfaz no tiene botón de apagado. Con `Vigia.cmd`: abre
   una consola en la carpeta de Vigía y escribe

   ```
   runtime\python\python.exe -m vigia shutdown
   ```

   Si usaste otra carpeta de datos, añade `--data-dir <carpeta>`. Con
   `Vigia-consola.cmd`, cierra la ventana de la consola. Con Ctrl+C, si Windows
   pregunta si quieres terminar el trabajo por lotes, responde S.

## Dónde quedan tus datos

Vigía guarda todo en una sola carpeta: `Documents\vigia-datos`, dentro de tu
carpeta de usuario. Ahí están la base de datos (`vigia.db`), los ficheros que
subes, los modelos y el registro (`vigia.log`). Para usar otra carpeta, pásala
como argumento (`Vigia.cmd D:\mis-datos`) o fija la variable de entorno
`VIGIA_HOME`. Haz copia de seguridad de esa carpeta, no de la de Vigía.

Antes de actualizar la base de datos a una versión nueva, Vigía deja una copia
en la carpeta `backups` (ficheros `.bak`). Esa copia guarda la base entera, con
la clave de API de la revisión con modelo sin cifrar, y Vigía no la borra al
borrar un proyecto. Bórrala a mano cuando ya no la necesites.

Borrar la carpeta de Vigía no borra tus datos. Para desinstalar, borra la
carpeta donde extrajiste el zip.

## Si Windows bloquea un fichero

Vigía no lleva firma digital. El Control de aplicaciones inteligente de Windows,
u otro antivirus con reputación de binarios, puede bloquear un fichero nuevo. El
capítulo «Qué hacer si» dice qué mirar.

## Actualizar

Extrae el zip nuevo en otra carpeta, apaga Vigía y arranca el nuevo. Usa la
misma carpeta de datos. Haz antes una copia de `vigia-datos`.

## Uso con un asistente de IA

Vigía puede operarse por MCP desde Claude Code o Claude Desktop. Con el paquete
de Windows, la orden que el asistente debe lanzar es:

```
<carpeta de Vigía>\runtime\python\python.exe -m vigia mcp --url http://127.0.0.1:<puerto> --actor <nombre>
```

El puerto aparece en la barra de direcciones del navegador y en
`vigia-datos\vigia.lock`. Hay más detalle y la lista de herramientas en
`docs/mcp.md`.
