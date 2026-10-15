/**
 * Nivel que sale de la combinación de impacto y probabilidad.
 * Los diálogos de alta de riesgo lo enseñan al elegir la combinación: sin él,
 * «Moderado × Probable» se registraba y el diario decía «nivel alto» sin
 * explicar de dónde salía. La tabla es la copia de `risk_levels.py` de
 * `niveles.ts`.
 */

import { ETIQUETA_NIVEL, IMPACTO_LABELS, PROBABILIDAD_LABELS, TOKEN_NIVEL, fondoNivel, nivelDeCelda } from "./niveles";

/** Texto del nivel de una combinación: «Moderado × Probable da nivel Alto». */
export function textoNivelResultante(impacto: number, probabilidad: number): string {
  const nivel = nivelDeCelda(impacto, probabilidad);
  return `${IMPACTO_LABELS[impacto]} × ${PROBABILIDAD_LABELS[probabilidad]} da nivel ${ETIQUETA_NIVEL[nivel]}`;
}

export interface NivelResultanteProps {
  /** Valor del selector de impacto: «1» a «5», o vacío / «propuesta» si no hay elección. */
  impacto: string;
  probabilidad: string;
}

export function NivelResultante({ impacto, probabilidad }: NivelResultanteProps) {
  const i = Number(impacto);
  const p = Number(probabilidad);
  const elegido = Number.isInteger(i) && i >= 1 && i <= 5 && Number.isInteger(p) && p >= 1 && p <= 5;
  if (!elegido) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="nivel-resultante">
        El nivel sale de la combinación de impacto y probabilidad en la matriz de 5 × 5 (por ejemplo, Moderado × Probable
        da nivel Alto). Elige las dos para verlo aquí; con la propuesta del monitor, se calcula al registrar.
      </p>
    );
  }
  const nivel = nivelDeCelda(i, p);
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="nivel-resultante">
      <span>Nivel resultante:</span>
      <span
        className="rounded-full border px-2 py-0.5 text-xs font-semibold"
        style={{ background: fondoNivel(nivel), borderColor: TOKEN_NIVEL[nivel] }}
      >
        {ETIQUETA_NIVEL[nivel]}
      </span>
      <span className="text-xs text-muted-foreground">({textoNivelResultante(i, p)})</span>
    </p>
  );
}
