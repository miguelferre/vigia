# build/ — empaquetado de Vigía con Python embebido

Sin PyInstaller (un EXE recién compilado sin firma es lo que
bloquea el Control de aplicaciones inteligente). Se distribuye el intérprete
embebido de python.org (firmado por PSF) más `site-packages` instalado con
`uv pip install --target` desde un `requirements.txt` exportado del lock, y
un `Vigia.cmd` que arranca el servidor. Nada de `get-pip.py`: `uv pip
install` no necesita pip.

## Subcomandos de `build/build.py`

Ejecutar siempre con el Python 3.13 del sistema (nunca con `uv run`, para no
disparar un `uv sync` concurrente si otro proceso está usando el venv):

```
python.exe build\build.py <subcomando>
```

`build.py` busca ese Python en la variable de entorno `VIGIA_PYTHON_SISTEMA` (ruta a
su `python.exe`) y, si no existe, en `sys.base_prefix` (el intérprete base, también
cuando se lanza desde un venv). Falla con un mensaje claro si no es el 3.13 o si es un
intérprete que descargó uv.

| Subcomando | Qué hace |
|---|---|
| `fetch [--version 3.13.12]` | Descarga `python-<ver>-embed-amd64.zip` de `https://www.python.org/ftp/python/<ver>/` a `build/embed/` si no existe ya. La versión tiene la forma `3.13.N` y su huella sha256 está fijada en `PYTHON_EMBED_SHA256` de `build.py` (3.13.12: `76f238f6…cce3d0`, la del zip ya descargado de python.org, 10.941.233 bytes). Comprueba que el zip es válido y que su sha256 es el fijado, tanto si lo descarga como si ya existe; falla si no coincide o si la versión no tiene huella fijada. `assemble` repite la comprobación. Para aceptar otra versión, comprueba su huella en python.org y añádela a la tabla. |
| `assemble [--no-shap] [--con-parquet] [--sin-npm] [--sin-npm-ci] [--exigir-privados] [--out DIR]` | Antes de nada instala el frontend con `npm ci --ignore-scripts` (`--sin-npm-ci` lo salta), lo compila con `VITE_TEMA=miguel` (`npm run build`) y falla si `src/vigia/static/index.html` falta, no lleva `<meta name="vigia-tema" content="miguel">` o es más viejo que el último commit de `frontend/` (`--sin-npm` salta la compilación y mantiene esas comprobaciones). Después descomprime el zip en `<out>/runtime/python`, edita `python313._pth` (añade `Lib\site-packages` y descomenta `import site`; ninguna ruta fuera del runtime), avisa si `uv --version` no es la 0.12.10 verificada, exporta `requirements.txt` con `uv export --locked` (extra `shap` sí; extra `parquet` solo con `--con-parquet`), construye el wheel de vigia (con `interaction_review` vendorizado dentro) en una carpeta nueva `build/wheels/<paquete>/` con `uv build --wheel` e instala solo ese wheel en `<out>/runtime/python/Lib/site-packages` con `uv pip install --target`, copia `src/vigia/static` si el wheel no lo trae ya, y escribe `<out>/Vigia.cmd`, `<out>/Vigia-consola.cmd`, `<out>/LEEME.txt` (versión de Vigía y, aparte, la de Python; cómo se apaga), `<out>/README.md`, `<out>/LICENSE`, `<out>/NOTICE`, `<out>/docs/manual/` y `<out>/TERCEROS.txt` (licencia de cada distribución leída de su dist-info, más la de Python embebido). Al final quita del paquete `Lib\site-packages\bin` (lanzadores con la ruta de la máquina; se arranca con `Vigia.cmd` y `python -m vigia`), los `direct_url.json`, los `__pycache__` y los comentarios con rutas de `requirements.txt`, y falla si algún fichero, de texto o binario, aún lleva la ruta del repo o del paquete. `zip` repite esa comprobación y compara el contenido del paquete con una lista blanca (rutas y extensiones esperadas): falla con un `*.db`, `*.env`, `*.privado.csv`, `*.log`, un `*.pkl` o `*.joblib` en el código de Vigía, o la ruta del usuario de compilación. Con `--exigir-privados` (o `VIGIA_EXIGIR_PRIVADOS=1`) falla si falta la lista de ficheros que no deben viajar, que solo existe en el árbol de trabajo. `measure` corre con `PYTHONDONTWRITEBYTECODE=1`. |
| `measure --out DIR [--port 8799] [--with-shap-label]` | Tamaño total del paquete y los 10 paquetes más grandes de `site-packages`; arranca `runtime/python/python.exe -m vigia serve --no-browser` y mide milisegundos hasta que `GET /api/health` responde 200, luego lo termina. Guarda el JSON en `build/out/measure-<con|sin>-shap.json`. |
| `zip --out DIR [--dist DIR]` | Empaqueta `<out>` en `dist/<nombre del directorio>.zip` (`vigia-<versión de Vigía>-win64.zip`) y escribe junto al zip `<nombre>.zip.sha256` y `<nombre>.zip.MANIFIESTO.txt` (ficheros con tamaño y versiones de paquetes). |
| `all` | Encadena los cuatro pasos anteriores. |

`fetch` y `assemble` distinguen el **winerror 4551** (bloqueo determinista del
Control de aplicaciones por política, sin reintento posible) de cualquier
otro fallo: si aparece, el mensaje lo marca como "BLOQUEO DE POLITICA" y
apunta al fichero. El escaneo asíncrono de un `.pyd` recién instalado (que sí
se resuelve solo, con espera) es responsabilidad del arranque de `vigia
serve`, no de este script.

## Qué se descarga y dónde queda

- `build/embed/python-<ver>-embed-amd64.zip` — el zip de python.org, una vez.
- `build/wheels/<paquete>/vigia-<versión>-*.whl` — el wheel de vigia, que lleva dentro la
  copia de `interaction_review` (`src/vigia/human/_vendor/`). Carpeta nueva en cada
  `assemble`, para no instalar un wheel viejo.
- `build/out/vigia-<versión de Vigía>-win64/` — el paquete ensamblado, listo para probar.
  Un solo paquete: con SHAP y sin Parquet. Las variantes llevan sufijo
  (`-sin-shap`, `-con-parquet`).
- `build/out/measure-*.json` — mediciones de tamaño y arranque.
- `dist/vigia-<versión de Vigía>-win64.zip`, su `.sha256` y `<zip>.MANIFIESTO.txt` — el entregable final.

Ninguno de estos pasos toca el sistema fuera del repo. Solo `fetch` descarga
el zip embebido, y solo la primera vez; el resto de subcomandos no hacen red
aparte de `uv export`/`uv build`/`uv pip install`, que resuelven contra el
índice de PyPI igual que `uv sync`.

## Por qué no PyInstaller

Un ejecutable recién compilado y sin firma es exactamente lo que el Control
de aplicaciones inteligente (`VerifiedAndReputablePolicyState = 1`) bloquea
por reputación, con independencia de la carpeta. El intérprete de python.org
está firmado por la PSF y las ruedas populares de PyPI pasan el escaneo de
reputación tras la primera vez.

## Cómo probar con el Control de aplicaciones activo

1. `assemble` en un equipo con el Control de aplicaciones activo.
2. Doble clic en `<out>/Vigia.cmd`. Si algún import falla con "Una directiva
   de Control de aplicaciones bloqueó este archivo", es el winerror 4551:
   anotar el fichero exacto, no reintentar.
3. Si el primer arranque es lento pero *funciona* la segunda vez, es el
   escaneo asíncrono de Windows Defender sobre un `.pyd` nuevo, no un
   bloqueo: normal, no hace falta acción.
4. `measure --out <out>` documenta el tiempo de arranque medido. SHAP entra por
   defecto; `--no-shap` construye la variante reducida.
5. Una prueba de humo del zip entero: lo marca como bajado de la web
   (`Zone.Identifier`), lo extrae con el Explorador, arranca `Vigia-consola.cmd` con un
   entorno limpio y comprueba versión, rutas, imports nativos, demo y apagado.

## Dependencias de build/build.py

Solo librería estándar de Python 3.13 más `uv` en PATH (0.12.10 verificado).
Ni `pip` ni `get-pip.py`: `uv pip install --target` sustituye a ambos.
