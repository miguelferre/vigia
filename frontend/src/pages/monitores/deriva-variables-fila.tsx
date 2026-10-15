/**
 * Fila de la lista de variables de `deriva-variables.tsx` (partido para no
 * pasar de 9 KB): puntuación (KS o JS), barra, marca «Máximo» en la variable
 * que da el `feature_drift_score` y marca «Sin categorías comunes con
 * la base».
 */

import { Badge } from "@/components/ui/badge";
import { formatoNumero } from "@/lib/metrics";

import { TEXTO_SIN_COMUNES } from "./deriva-variables-datos";
import type { FilaVariable } from "./deriva-variables-datos";

/** Barra de puntuación (KS o JS, de 0 a 1) de la fila de lista. */
function BarraPuntuacion({ score }: { score: number | null }) {
  const pct = score !== null ? Math.min(100, Math.max(0, score * 100)) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      {score !== null ? <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "var(--chart-1)" }} /> : null}
    </div>
  );
}

const TEXTO_MAXIMO = "Esta variable da el valor de la deriva de características";

export function FilaLista({
  fila,
  activa,
  esMaximo,
  onSeleccionar,
}: {
  fila: FilaVariable;
  activa: boolean;
  esMaximo: boolean;
  onSeleccionar: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSeleccionar}
      aria-pressed={activa}
      className={`flex w-full flex-col gap-1 rounded-lg border p-2.5 text-left transition-colors ${
        activa
          ? "border-foreground/40 bg-muted"
          : esMaximo
            ? "border-foreground/25 hover:bg-muted/60"
            : "border-transparent hover:bg-muted/60"
      }`}
    >
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="truncate font-medium" title={fila.feature}>
          {fila.featureLabel}
        </span>
        <span className="shrink-0 tabular-nums" title="Puntuación de deriva de la variable (KS si es numérica, JS si es categórica)">
          {fila.score !== null ? formatoNumero(fila.score) : "n/d"}
        </span>
      </div>
      <BarraPuntuacion score={fila.score} />
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        {esMaximo ? (
          <Badge variant="outline" className="font-semibold text-foreground" title={TEXTO_MAXIMO}>
            Máximo
          </Badge>
        ) : null}
        {fila.kind === "numerica" ? (
          <>
            <span>
              KS {formatoNumero(fila.ksStat)} (p {formatoNumero(fila.ksP)})
            </span>
            <span>{fila.psi !== null ? `PSI ${formatoNumero(fila.psi, 2)}` : "PSI n/d"}</span>
          </>
        ) : fila.kind === "categorica" ? (
          <span>
            Chi² {formatoNumero(fila.chi2)} (p {formatoNumero(fila.p)})
          </span>
        ) : null}
        {fila.sinValoresComunes ? (
          <Badge variant="outline" className="font-normal text-foreground" title={TEXTO_SIN_COMUNES}>
            Sin categorías comunes con la base
          </Badge>
        ) : null}
      </div>
    </button>
  );
}
