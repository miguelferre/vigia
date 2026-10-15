"""Respuesta de `GET /content/guia-datos`: la guía de datos,
generada por `build/gen_content_guia_datos.py`. Esquemas cerrados."""

from __future__ import annotations

from vigia.app.schemas.respuestas_base import Respuesta

__all__ = [
    "GuiaDatos",
    "GuiaDatosClaseFavorable",
    "GuiaDatosColumna",
    "GuiaDatosEjemploFavorable",
    "GuiaDatosFecha",
    "GuiaDatosFormatos",
    "GuiaDatosInconclusa",
    "GuiaDatosSeccion",
]


class GuiaDatosColumna(Respuesta):
    nombre: str
    que_es: str
    valores: str
    ejemplo: str


class GuiaDatosSeccion(Respuesta):
    """Un fichero que pide Vigía. `plantilla` es el `{tipo}` de
    `GET /content/plantillas/{tipo}.csv`; `None` en el modelo, que no es CSV."""

    id: str
    titulo: str
    para_que: str
    tipo_en_vigia: str | None
    plantilla: str | None
    nombre_plantilla: str | None
    obligatorias: list[GuiaDatosColumna]
    opcionales: list[GuiaDatosColumna]
    notas: list[str]


class GuiaDatosFecha(Respuesta):
    formato: str
    ejemplo: str
    nota: str


class GuiaDatosFormatos(Respuesta):
    titulo: str
    ficheros: str
    separador: str
    codificacion: str
    decimal: str
    fechas: list[GuiaDatosFecha]
    fecha_ilegible: str
    excel: str


class GuiaDatosEjemploFavorable(Respuesta):
    caso: str
    favorable: str
    motivo: str


class GuiaDatosClaseFavorable(Respuesta):
    titulo: str
    pregunta: str
    frase: str
    pasos: list[str]
    ejemplos: list[GuiaDatosEjemploFavorable]


class GuiaDatosInconclusa(Respuesta):
    titulo: str
    texto: str
    pasos: list[str]


class GuiaDatos(Respuesta):
    titulo: str
    resumen: str
    aviso_sintetico: str
    secciones: list[GuiaDatosSeccion]
    formatos: GuiaDatosFormatos
    clase_favorable: GuiaDatosClaseFavorable
    codificacion_inconclusa: GuiaDatosInconclusa
