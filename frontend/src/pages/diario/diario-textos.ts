/**
 * Número de carriles del diario dicho con letras: la
 * cabecera y la leyenda salen del mismo `CARRILES.length`, así no se
 * contradicen. El texto largo de la cabecera es `diario.carriles` de
 * `textos-pantalla.json`; este es el respaldo mientras no llega.
 */

import { CARRILES } from "./etiquetas";

const EN_LETRAS: Record<number, string> = { 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis" };

/** «cuatro», para el número de carriles que hay en `CARRILES`. */
export const NUMERO_DE_CARRILES = EN_LETRAS[CARRILES.length] ?? String(CARRILES.length);

export const RESPALDO_CARRILES = `El diario tiene ${NUMERO_DE_CARRILES} carriles: Usuario, Agente de IA, Vigía y Sistema. Filtra por carril para ver solo lo que te interesa.`;

export const TITULO_LEYENDA = `Los ${NUMERO_DE_CARRILES} carriles del diario`;
