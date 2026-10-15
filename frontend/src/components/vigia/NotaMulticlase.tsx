/**
 * Una línea que nombra la diferencia multiclase de una métrica en la ayuda
 * general. Con la ayuda general (sin proyecto, o con uno binario)
 * la ayuda enseña el texto binario; si la entrada trae el bloque `multiclase`,
 * esta línea dice qué cambia. En un proyecto multiclase la ayuda ya sale
 * resuelta por tipo (`ayudaPorTipo`) y no se dibuja nada.
 */

import type { AyudaMetrica } from "@/api/queries-contenido";

/** `true` si hay que nombrar la diferencia: ayuda general (sin tipo conocido) y bloque multiclase con texto. */
function hayDiferenciaMulticlase(ayuda: AyudaMetrica | undefined, ayudaGeneral: boolean): boolean {
  const bloque = ayuda?.multiclase;
  return ayudaGeneral && !!bloque && !!(bloque.que_mide ?? bloque.como_se_lee);
}

/** `true` si hay que nombrar la diferencia de regresión: ayuda general y bloque `regresion` con texto. */
function hayDiferenciaRegresion(ayuda: AyudaMetrica | undefined, ayudaGeneral: boolean): boolean {
  const bloque = ayuda?.regresion;
  return ayudaGeneral && !!bloque && !!(bloque.que_mide ?? bloque.como_se_lee);
}

export function NotaMulticlase({ ayuda, ayudaGeneral }: { ayuda: AyudaMetrica | undefined; ayudaGeneral: boolean }) {
  const bloque = ayuda?.multiclase;
  const regresion = ayuda?.regresion;
  const notaMulticlase = !!bloque && hayDiferenciaMulticlase(ayuda, ayudaGeneral);
  const notaRegresion = !!regresion && hayDiferenciaRegresion(ayuda, ayudaGeneral);
  if (!notaMulticlase && !notaRegresion) return null;
  return (
    <>
      {notaMulticlase ? (
        <p className="text-xs italic" data-testid="nota-multiclase">
          En un modelo multiclase: {bloque?.que_mide ?? bloque?.como_se_lee}
        </p>
      ) : null}
      {notaRegresion ? (
        <p className="text-xs italic" data-testid="nota-regresion">
          En una regresión: {regresion?.que_mide ?? regresion?.como_se_lee}
        </p>
      ) : null}
    </>
  );
}
