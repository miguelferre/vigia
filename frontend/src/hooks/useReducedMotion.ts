/**
 * Punto único de `prefers-reduced-motion`. Hoy se lee inline con `matchMedia` en `themes/theme.tsx`
 * (fuera de esta frontera); `ModoPresentacion` y `Escena` lo necesitan igual
 * y no deben duplicar esa lectura, así que se reexporta el hook que ya trae
 * `motion/react` en vez de reimplementarlo.
 */

export { useReducedMotion } from "motion/react";
