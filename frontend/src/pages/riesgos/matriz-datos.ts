/**
 * Agregación de la matriz 5x5 en el cliente (sin endpoint
 * aparte): `GET /projects/{id}/risks` ya trae impacto, probabilidad y
 * nivel por fila; aquí se cuentan y se agrupan los códigos por celda.
 */

import type { Risk } from "@/api/types";

export interface CeldaMatriz {
  impacto: number;
  probabilidad: number;
  riesgos: Risk[];
}

/** Una celda por cada combinación 1..5 x 1..5, con los riesgos que caen en ella. */
export function construirMatriz(riesgos: Risk[]): Map<string, CeldaMatriz> {
  const celdas = new Map<string, CeldaMatriz>();
  for (let impacto = 1; impacto <= 5; impacto += 1) {
    for (let probabilidad = 1; probabilidad <= 5; probabilidad += 1) {
      celdas.set(`${impacto},${probabilidad}`, { impacto, probabilidad, riesgos: [] });
    }
  }
  for (const riesgo of riesgos) {
    const clave = `${riesgo.impact_level},${riesgo.probability_level}`;
    celdas.get(clave)?.riesgos.push(riesgo);
  }
  return celdas;
}

export function celda(matriz: Map<string, CeldaMatriz>, impacto: number, probabilidad: number): CeldaMatriz {
  return matriz.get(`${impacto},${probabilidad}`) ?? { impacto, probabilidad, riesgos: [] };
}
