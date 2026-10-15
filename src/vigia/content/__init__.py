"""Contenido estático de ayuda: JSON versionados, no código.

`glosario.json` y `metricas-ayuda.json` los genera `build/gen_content.py` a
partir del glosario de métricas; se leen con
`importlib.resources` desde `app/routers/content.py`, no se importan como
módulos Python.
"""
