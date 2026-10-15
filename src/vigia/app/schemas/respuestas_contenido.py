"""Respuestas de `GET /api/content/*`.

Tipan tal cual la forma de `src/vigia/content/metricas-ayuda.json`,
`glosario.json`, `presentacion.json`, `demo-digestivo.json` y
`guia-uso.json`: el router los sirve sin transformarlos
(`app/routers/content.py`), así que estos modelos son el contrato de esos
ficheros, no de un servicio.
"""

from __future__ import annotations

from typing import Literal

from vigia.app.schemas.respuestas_base import EstadoMotor, MonitorType, Respuesta

__all__ = [
    "ContenidoDemo",
    "ContenidoGlosarioTermino",
    "ContenidoGuiaUso",
    "ContenidoMetrica",
    "ContenidoMetricaMulticlase",
    "ContenidoPresentacion",
    "ContenidoProtocoloHitos",
    "DemoDato",
    "DemoDestino",
    "DemoFase",
    "DemoGuion",
    "DemoLaboratorio",
    "DemoPaso",
    "GuiaUsoEntrada",
    "LaboratorioParametro",
    "PresentacionDiapositiva",
    "PresentacionFuente",
    "ProtocoloPaso",
]

# Las mismas cinco claves que se derivan por alerta (`GET /alerts/{id}`,
# `protocol_steps`): esta plantilla y ese estado describen los mismos cinco
# hitos, solo que por caminos distintos (la plantilla es contenido genérico;
# el estado se deriva de una alerta real).
type ProtocoloHitoKey = Literal["deteccion", "triaje", "investigacion", "decision", "seguimiento"]


class ContenidoMetricaMulticlase(Respuesta):
    """Bloque opcional `multiclase` de una entrada de `metricas-ayuda.json`.
    Un campo nulo hereda el de la entrada; la excepción es
    `formula_vars`, donde `[]` quiere decir «esta fórmula no se instancia con
    números» (sustituye a las variables de la entrada) y nulo las hereda. La
    interfaz elige el bloque según el `task_type` del proyecto."""

    que_mide: str | None
    como_se_lee: str | None
    formula: str | None
    formula_vars: list[str] | None
    # Nulo hereda el de la entrada; `{}` quiere decir «sin umbral de fábrica en
    # multiclase»: la interfaz no debe pintar el de la entrada.
    umbral_por_defecto: dict[str, float] | None


class ContenidoMetrica(Respuesta):
    """Una entrada de `metricas-ayuda.json`: qué mide una métrica y su fórmula.

    `nota` lleva el motivo cuando la métrica es una excepción declarada (sin
    equivalente local) en vez de una fórmula reproducible.
    """

    monitor: MonitorType
    etiqueta: str
    que_mide: str
    formula: str | None
    formula_vars: list[str] | None
    como_se_lee: str
    umbral_por_defecto: dict[str, float] | None
    nota: str | None
    # Solo las entradas que cambian de sentido en multiclase lo llevan; las
    # demás no traen la clave y el router no la rellena (`exclude_unset`).
    multiclase: ContenidoMetricaMulticlase | None = None
    # Lo mismo para regresión, con la forma del bloque `multiclase`
    # (un campo nulo hereda; `formula_vars: []` y `umbral_por_defecto: {}` no se
    # instancian / no tienen umbral de fábrica). Va en las entradas compartidas que
    # cambian de sentido en una regresión; las claves propias de regresión no lo llevan.
    regresion: ContenidoMetricaMulticlase | None = None


class ContenidoGlosarioTermino(Respuesta):
    """Una entrada de `glosario.json`: un concepto no métrico."""

    etiqueta: str
    definicion: str


class PresentacionFuente(Respuesta):
    """Una cita de `fuente` en una diapositiva: el texto tal como lo escribe
    el guion y, si el fragmento trae un dominio reconocible, el enlace
    (`https://` añadido si el guion no lo lleva)."""

    texto: str
    url: str | None


class PresentacionDiapositiva(Respuesta):
    """Una de las 10 diapositivas de `presentacion.json` (id 1 a 10, sin
    huecos: la antigua 8 se retiró y las
    siguientes se renumeraron). `puntos` son de 2 a 4 viñetas cortas, sin
    punto final; `frase` es como mucho una línea de apoyo y puede ser
    `None` cuando la diapositiva se sostiene solo con las viñetas.
    `consultado` es la fecha de «Consultadas el AAAA-MM-DD» cuando el guion
    la trae; `estado` es el texto libre del chip («en desarrollo»), no uno
    de los cinco estados del motor."""

    id: int
    kicker: str
    titulo: str
    puntos: list[str]
    frase: str | None
    diagrama: str
    fuente: list[PresentacionFuente]
    consultado: str | None
    estado: str | None
    notas: str


class ContenidoPresentacion(Respuesta):
    """`presentacion.json` completo: las 10 diapositivas de la presentación
    (en viñetas)."""

    diapositivas: list[PresentacionDiapositiva]


class DemoGuion(Respuesta):
    """El `guion` de `demo-digestivo.json`: sobre qué reproducción se apoya
    la demo guiada (`caso_digestivo`)."""

    scenario_key: str
    domain: str
    with_human: bool


class DemoFase(Respuesta):
    """Una entrada de `fases`: el nombre de fase que sustituye a la regex de
    `lib/fases.ts`."""

    etiqueta: str
    descripcion: str


class DemoDestino(Respuesta):
    """A qué pantalla real lleva un paso. `ruta` puede llevar marcadores
    `:id`/`:batch` que el frontend sustituye por el proyecto o lote de la
    reproducción en curso; los pasos sin pantalla (`tipo="diapositiva"`)
    llevan `ruta` y `ancla` a `None`."""

    ruta: str | None
    ancla: str | None


class DemoDato(Respuesta):
    """El contrato numérico de un paso (el
    frontend enseña el valor real de la evaluación y el paso declara el que
    debería salir. `verificacion` lleva la nota de un `esperado` marcado
    «(a verificar…)» en el guion, hasta que se cierre reproduciendo
    `caso_digestivo` en vivo."""

    metric_key: str | None
    esperado: float | None
    umbral: float | None
    estado: EstadoMotor | None
    verificacion: str | None


class DemoPaso(Respuesta):
    """Uno de los 26 pasos de `demo-digestivo.json` (id 0 a 25, sin huecos:
    lo comprueba `tests/api/test_content.py`;
    un paso por pantalla entre el cuadro y la carga de casos nuevos).
    `tipo="diapositiva"` para los pasos sin clic del usuario (0 y 23);
    `opcional` solo es `true` en el 24."""

    id: int
    tipo: Literal["paso", "diapositiva"]
    opcional: bool
    kicker: str
    titulo: str
    frase: str
    hace: str | None
    ve: str | None
    destino: DemoDestino
    dato: DemoDato
    fase_minima: int
    capacidad: str


class LaboratorioParametro(Respuesta):
    """Un control del laboratorio: etiqueta en español y el rango y
    paso del control, acotados a los valores por defecto reales del
    generador para que "sin tocar nada" reproduzca el lote de hoy."""

    clave: str
    etiqueta: str
    min: float
    max: float
    paso: float
    por_defecto: float


class DemoLaboratorio(Respuesta):
    """`laboratorio` de `demo-digestivo.json`: los controles que
    `laboratorio-formulario.tsx` pinta, cruzados en el frontend con
    `lab_params` de `GET /demo/scenarios` (§3.4) para mostrar solo los que
    el generador ya acepta."""

    parametros: list[LaboratorioParametro]


class ContenidoDemo(Respuesta):
    """`demo-digestivo.json` completo: el guion, las fases, los 26 pasos, el
    laboratorio y el diccionario de dominio (nombre técnico de
    característica, capítulo L, a etiqueta de dominio del capítulo D).
    Sin `cierre`: el contrafactual con/sin
    vigilancia pasa a la diapositiva 5 de la presentación."""

    guion: DemoGuion
    fases: dict[str, DemoFase]
    pasos: list[DemoPaso]
    laboratorio: DemoLaboratorio
    dominio: dict[str, str]


class GuiaUsoEntrada(Respuesta):
    """Una de las 12 entradas de `guia-uso.json` (id 1 a 12, sin huecos).
    `ver_tambien` son claves reales del glosario (el generador falla si
    alguna no existe); `captura` y `estado` son `None` cuando el guion los
    deja en blanco."""

    id: int
    titulo: str
    para_que: str
    pasos: list[str]
    ruta: str
    captura: str | None
    ver_tambien: list[str]
    estado: str | None


class ContenidoGuiaUso(Respuesta):
    """`guia-uso.json` completo: las 12 entradas de la sección «Guía de uso»
    de `/ayuda`."""

    entradas: list[GuiaUsoEntrada]


class ProtocoloPaso(Respuesta):
    """Una entrada de `protocolo-hitos.json`: la plantilla de contenido de un
    hito del protocolo de respuesta a una alerta. Genérica, sin datos
    de ninguna alerta concreta: el estado (`done`/`current`/`pending`) y la
    fecha objetivo por alerta se añaden en `GET /alerts/{id}`, no esta ruta.
    """

    key: ProtocoloHitoKey
    orden: int
    titulo: str
    descripcion: str
    entregables: list[str]


class ContenidoProtocoloHitos(Respuesta):
    """`GET /content/protocolo-hitos`: los cinco pasos envueltos en un
    objeto, no una lista ni un mapa por clave. `protocolo-hitos.json` en
    disco sí es una lista (el orden 1 a 5 es el de sus elementos, sin
    depender de que nadie ordene por `orden` al leerlo); el envoltorio es
    solo de la respuesta HTTP, para que quede un `$ref` en la raíz del
    esquema OpenAPI, como el resto de rutas con modelo
    (`tests/api/test_contrato.py::test_el_openapi_declara_esquema_de_respuesta_200_en_cada_ruta`,
    no reconoce un `array` de nivel
    superior como modelado)."""

    pasos: list[ProtocoloPaso]
