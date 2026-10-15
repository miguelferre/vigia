/**
 * Iconos de las pantallas de la sonda (símbolos, no texto) y el contorno de
 * la persona pictograma. Cuadrícula de 24 x 24; `ico` los coloca y escala.
 */

const ICONOS = {
  equidad: '<path d="M12 3v18M6 21h12M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/>',
  calidad: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12l3 3 5-6"/>',
  deriva: '<path d="M 3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
  persona: '<circle cx="12" cy="8" r="4"/><path d="M 4 21c0-4 4-6 8-6s8 2 8 6"/>',
  sigue: '<path d="M 4 12l5 5 11-11"/>',
  corrige: '<path d="M 6 6l12 12M18 6L6 18"/>',
} as const;

export type NombreIcono = keyof typeof ICONOS;

export const ico = (n: NombreIcono, x: number, y: number, s: number, extra = "") =>
  `<g class="ico ${extra}" transform="translate(${x} ${y}) scale(${s / 24})">${ICONOS[n]}</g>`;

/** Cuerpo de la persona, de una pieza: brazos separados y pies redondeados; origen en los pies. */
export const CUERPO =
  "M-5 -44C-10 -44 -13.5 -42 -14.5 -37L-17 -22C-17.6 -18.5 -12.6 -17.5 -12.2 -21L-11.2 -33C-11 -34.5 -9.6 -34.6 -9.6 -33" +
  "L-9.4 -20L-9.2 -3C-9.2 -.5 -7.8 0 -5.5 0L-2.2 0C-1.2 0 -1 -.8 -1 -2.5L-1 -18C-1 -19.8 1 -19.8 1 -18L1 -2.5C1 -.8 1.2 0 2.2 0" +
  "L5.5 0C7.8 0 9.2 -.5 9.2 -3L9.4 -20L9.6 -33C9.6 -34.6 11 -34.5 11.2 -33L12.2 -21C12.6 -17.5 17.6 -18.5 17 -22L14.5 -37C13.5 -42 10 -44 5 -44Z";
