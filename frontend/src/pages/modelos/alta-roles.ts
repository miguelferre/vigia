/**
 * Papel de cada columna del fichero de ejemplo en el paso «Datos»:
 * alimenta la cabecera de la vista previa y la lista de variables. Funciones
 * puras, sin estado: el formulario (`alta-datos.tsx`) las llama en cada render.
 */

import { pareceFecha, pareceIdentificador } from "./alta-sniff";
import { PAPEL } from "./alta-textos";

export interface AsignacionAlta {
  idCol: string;
  labelCol: string;
  predictionCol: string;
  probabilityCol: string;
  timestampCol: string;
  /** Columna protegida ya elegida; vacía si el atributo protegido está apagado. */
  protectedCol: string;
  /** De cada columna de probabilidad, la clase a la que corresponde. */
  probabilidadPorColumna?: Record<string, string>;
}

type Fila = Record<string, string>;

/** Columnas que ya tienen un papel distinto de «variable» (no entran solas en las variables). */
function papelesFijos(col: string, a: AsignacionAlta): string[] {
  const papeles: string[] = [];
  if (col === a.idCol) papeles.push(PAPEL.identificador);
  if (col === a.labelCol) papeles.push(PAPEL.etiqueta);
  if (col === a.predictionCol) papeles.push(PAPEL.prediccion);
  if (col === a.probabilityCol) papeles.push(PAPEL.probabilidad);
  const claseProb = a.probabilidadPorColumna?.[col];
  if (claseProb !== undefined) papeles.push(`${PAPEL.probabilidad} de «${claseProb}»`);
  if (col === a.timestampCol) papeles.push(PAPEL.fecha);
  if (a.protectedCol !== "" && col === a.protectedCol) papeles.push(PAPEL.protegido);
  return papeles;
}

/**
 * Variables que se marcan solas: ni las columnas con otro papel (el atributo
 * protegido ya elegido incluido: sale desmarcado con una nota) ni las
 * que parecen fecha o identificador (el aviso de `alta-variables.tsx` las
 * cubre si el usuario las marca a mano). Un código con pocos valores
 * distintos, aunque se llame `*_id`, sí se propone (`pareceIdentificador`).
 */
export function marcadaPorDefecto(col: string, a: AsignacionAlta, filas: Fila[]): boolean {
  return papelesFijos(col, a).length === 0 && !pareceFecha(col, filas) && !pareceIdentificador(col, filas);
}

/** Papel o papeles de la columna: los fijos, «variable» si está marcada y «sin usar» si no tiene ninguno. */
export function papelesDeColumna(col: string, a: AsignacionAlta, esVariable: boolean): string[] {
  const papeles = papelesFijos(col, a);
  if (esVariable) papeles.push(PAPEL.variable);
  return papeles.length > 0 ? papeles : [PAPEL.sinUsar];
}
