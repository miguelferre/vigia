/**
 * El paso «Así se ve un servicio sano» dice que la tabla
 * de alertas está vacía, pero con `/demo?paso=8&run=<id>` (un run ya
 * reproducido) la tabla enseña las alertas de ese run. El texto del guion
 * (contenido generado) se queda como está; aquí se sustituye lo que dice la
 * lista vacía cuando la tabla de `/alertas` tiene alertas, con el mismo
 * recuento que la tabla (sin las retiradas).
 */

import { useAlerts } from "@/api/queries";
import type { PasoDemo } from "@/api/queries-contenido";

const DICE_VACIA = /vac[ií]a/i;

/** ¿Es un paso de la tabla de alertas cuyo texto afirma que está vacía? */
export function afirmaListaVacia(paso: Pick<PasoDemo, "destino" | "frase" | "ve"> | null | undefined): boolean {
  if (!paso || paso.destino.ruta !== "/alertas") return false;
  return DICE_VACIA.test(paso.frase) || DICE_VACIA.test(paso.ve ?? "");
}

export function textoConAlertas(paso: Pick<PasoDemo, "frase" | "ve">, n: number): { frase: string; ve: string } {
  const alertas = n === 1 ? "1 alerta" : `${n} alertas`;
  // Sin la frase que dice «vacía»; el resto de la frase del guion se conserva.
  const frase = paso.frase
    .split(/(?<=\.)\s+/)
    .filter((f) => !DICE_VACIA.test(f))
    .join(" ");
  return {
    frase,
    ve: `La tabla enseña ${alertas} de la reproducción cargada. La lista vacía es lo que se ve con solo la línea base.`,
  };
}

/** `frase` y `ve` del paso, ajustados a lo que enseña la tabla de alertas del proyecto. */
export function useTextoPaso(projectId: number | null, paso: PasoDemo | null): { frase: string; ve: string | null } {
  const aplica = afirmaListaVacia(paso);
  const alertas = useAlerts(projectId, null, { enabled: aplica && projectId !== null });
  const n = (alertas.data?.items ?? []).filter((a) => a.status !== "retirada").length;
  if (!paso) return { frase: "", ve: null };
  if (aplica && n > 0) return textoConAlertas(paso, n);
  return { frase: paso.frase, ve: paso.ve ?? null };
}
