"""Respuesta de `GET /content/registro-uso`: la ayuda de la subida
del registro de uso, generada por `build/gen_content_registro_uso.py`."""

from __future__ import annotations

from vigia.app.schemas.respuestas_base import Respuesta

__all__ = [
    "RegistroUsoAyuda",
    "RegistroUsoCodificacion",
    "RegistroUsoColumna",
    "RegistroUsoEjemplo",
    "RegistroUsoFormatoFecha",
    "RegistroUsoOpcionFavorable",
]


class RegistroUsoColumna(Respuesta):
    nombre: str
    que_es: str
    valores: str
    ejemplo: str


class RegistroUsoFormatoFecha(Respuesta):
    formato: str
    ejemplo: str
    nota: str


class RegistroUsoOpcionFavorable(Respuesta):
    valor: str
    significa: str


class RegistroUsoCodificacion(Respuesta):
    frase: str
    pregunta: str
    por_defecto: str
    opciones: list[RegistroUsoOpcionFavorable]
    aplica_a: list[str]
    comprobacion: str


class RegistroUsoEjemplo(Respuesta):
    nombre_fichero: str
    n_filas: int
    nota: str
    columnas: list[str]
    filas: list[list[str]]
    csv: str


class RegistroUsoAyuda(Respuesta):
    titulo: str
    resumen: str
    formato_fichero: str
    columnas_obligatorias: list[RegistroUsoColumna]
    columnas_opcionales: list[RegistroUsoColumna]
    formatos_fecha: list[RegistroUsoFormatoFecha]
    codificacion: RegistroUsoCodificacion
    ejemplo: RegistroUsoEjemplo
    # El ejemplo de un modelo multiclase (nombres de clase, sin `refer`).
    ejemplo_multiclase: RegistroUsoEjemplo | None = None
    # El ejemplo de un modelo de regresión (cifras en la unidad del modelo).
    ejemplo_regresion: RegistroUsoEjemplo | None = None
