/**
 * Textos del alta de un modelo: paso 1, paso «Datos»
 * y vista previa. Fuera del JSX para que el vocabulario sea el de la guía de
 * uso (`guia-uso.json`, entradas 2 y 15). La ayuda de cada columna sale de
 * `AYUDA_MAPEO` (`etiquetas.ts`), la misma que enseña el mapeo de dataset.
 */

import type { DeploymentStage } from "@/api/types";
import type { TipoTarea } from "@/lib/tipo-tarea";
import { AYUDA_MAPEO, AYUDA_MAPEO_MULTICLASE, FRASE_FAVORABLE } from "./etiquetas";

/** Las tres etapas que elige quien da de alta; `demo` solo la pone el reproductor de la demo. */
export const ETAPAS: { valor: Exclude<DeploymentStage, "demo">; etiqueta: string }[] = [
  { valor: "desarrollo", etiqueta: "Desarrollo" },
  { valor: "validacion", etiqueta: "Validación" },
  { valor: "produccion", etiqueta: "Producción" },
];

/** El tipo de tarea es la primera pregunta del alta. */
export const TIPOS_TAREA: { valor: TipoTarea; etiqueta: string; ayuda: string }[] = [
  {
    valor: "binary",
    etiqueta: "Binaria",
    ayuda: "Dos resultados posibles, por ejemplo aprobar o denegar.",
  },
  {
    valor: "multiclass",
    etiqueta: "Multiclase",
    ayuda:
      "Tres o más clases, por ejemplo permitido, spam u odio. Marcarás qué clases cuentan como resultado bueno.",
  },
  {
    valor: "regression",
    etiqueta: "Regresión",
    ayuda:
      "Un número, por ejemplo los días hasta resolver un caso o las horas de atención por semana. Podrás marcar qué valores cuentan como resultado bueno.",
  },
];

export const TEXTO_ALTA = {
  tipoTarea:
    "Qué da el modelo: dos resultados, varias clases o un número. No se puede cambiar después: habría que crear otro modelo.",
  descripcionPaso1:
    "Nombre, dominio, tipo de modelo y etapa. En el paso siguiente eliges el fichero de tu línea base.",
  firmante:
    "Se pide tu nombre porque todo lo que haces en el alta queda registrado en el diario de eventos.",
  etapa: "En qué punto de su vida está el modelo. Se puede cambiar después en Configuración.",
  etapaPlaceholder: "Elige la etapa",
  descripcionDatos:
    "Elige el fichero de tu línea base: aquí solo se leen sus columnas, en tu navegador. " +
    "El fichero no se sube aquí: la línea base se sube después en Datos > Subir dataset, " +
    "y el modelo (ONNX) en Versiones.",
  sinPlantilla:
    "«Crear sin plantilla» deja el mapeo para el primer dataset: la clase favorable se toma de ese " +
    "mapeo y cada dataset se mapea por separado.",
} as const;

/** Los textos del paso «Datos» que cambian en multiclase. */
export const AYUDA_ALTA_MULTICLASE = {
  etiqueta: AYUDA_MAPEO_MULTICLASE.etiqueta,
  prediccion: AYUDA_MAPEO_MULTICLASE.prediccion,
  favorable: AYUDA_MAPEO_MULTICLASE.favorable,
  probabilidad: AYUDA_MAPEO_MULTICLASE.probabilidad,
  clases:
    "Las clases salen de las columnas de probabilidad, o de la predicción y la etiqueta del fichero de ejemplo. " +
    "Los umbrales de calidad se proponen desde la línea base cuando la congeles.",
} as const;

/** Los textos del paso «Datos» que cambian en regresión. */
export const AYUDA_ALTA_REGRESION = {
  etiqueta:
    "El valor real de cada caso: un número en la misma unidad que la predicción. Si llega más tarde, súbelo en un fichero de etiquetas reales.",
  prediccion: "El número que dio el modelo en cada caso, en la unidad de la salida.",
  unidad:
    "En qué se mide la salida del modelo, por ejemplo «días», «horas por semana» o «€». De 1 a 30 caracteres. " +
    "Los errores se enseñan en esta unidad. No se puede cambiar cuando congeles la línea base.",
  rango:
    "Los valores de la salida que cuentan como resultado bueno para la persona. Cada intervalo va de un mínimo a un " +
    "máximo, y los dos extremos cuentan dentro. Deja un extremo vacío para un intervalo abierto. Puedes poner hasta 3 " +
    "intervalos que no se solapen. Sin rango solo se mide el error por grupo y no hay capa humana. No se puede cambiar " +
    "cuando congeles la línea base.",
} as const;

export const AYUDA_ALTA = {
  identificador: AYUDA_MAPEO.identificador,
  etiqueta:
    "El resultado real de cada caso: lo que pasó de verdad. Si llega más tarde, súbelo en un fichero de etiquetas reales.",
  favorable: `Elige ${FRASE_FAVORABLE}.`,
  prediccion: AYUDA_MAPEO.prediccion,
  probabilidad: AYUDA_MAPEO.probabilidad,
  fecha: AYUDA_MAPEO.fecha,
  variables: AYUDA_MAPEO.caracteristicas,
  protegido: AYUDA_MAPEO.columnaProtegida,
  tipoAtributo: AYUDA_MAPEO.tipoAtributo,
  grupos:
    "Grupo supervisado: el que quieres vigilar. Grupo de referencia: con el que se compara. " +
    "Cada rango va de un mínimo a un máximo.",
} as const;

/** Rótulos de la vista previa y de la lista de variables. */
export const TITULO_VISTA_PREVIA = (n: number) => `Vista previa: las ${n} primeras filas y el papel de cada columna`;
export const SIN_COLUMNAS_LIBRES = "Sin columnas libres: todas tienen ya otro papel.";

/** La plantilla del modelo usa una columna que el fichero subido no trae. */
export const AVISO_COLUMNA_AUSENTE = (col: string) =>
  `La plantilla del modelo usa «${col}», que no está en el fichero: elige otra columna o déjala sin elegir.`;

/** Aviso en línea al marcar como variable una columna que parece fecha o identificador. */
export const AVISO_FECHA_VARIABLE = "esta columna parece una fecha: como variable, la deriva la verá cambiar en cada lote";
export const AVISO_ID_VARIABLE =
  "esta columna parece un identificador: como variable no aporta y la deriva la verá cambiar en cada lote";

/** Nota bajo el atributo protegido, que no se propone como variable. */
export const NOTA_PROTEGIDA_VARIABLE = "atributo protegido: márcala si el modelo la usa como entrada";

/** Papel de cada columna en la cabecera de la vista previa (mismo vocabulario que la guía). */
export const PAPEL = {
  identificador: "identificador",
  etiqueta: "etiqueta",
  prediccion: "predicción",
  probabilidad: "probabilidad",
  fecha: "fecha",
  variable: "variable",
  protegido: "atributo protegido",
  sinUsar: "sin usar",
} as const;
