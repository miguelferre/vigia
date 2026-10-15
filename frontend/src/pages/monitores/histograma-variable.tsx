/**
 * Histograma base frente a lote de una única variable de deriva:
 * sustituye las dos barras superpuestas por la forma B
 * del componente compartido `HistogramaBaseLote`. Numérica con `bin_edges` o
 * categórica con `categories`; perfil corto (n base, n lote, rango, PSI/KS o
 * Chi²) y los tramos que más cambian.
 *
 * `sinTitulo` (mismo patrón que `HistogramaConfianza`): omite el
 * bloque de título cuando la pestaña que lo monta (`deriva-variables.tsx`,
 * «Línea base frente a lote») ya pinta título y subtítulo.
 */

import { HistogramaBaseLote, construirFilasHistograma, etiquetasDeBordes, fraseTramosQueMasCambian, distribucionesIdenticas } from "@/components/vigia";
import { formatoNumero } from "@/lib/metrics";

import { CabeceraEstadistico, AYUDA_ESTADISTICO, TEXTO_DOS_CIFRAS_DERIVA } from "./deriva-estadisticos";
import { TEXTO_SIN_COMUNES, esNumerica, rangoDeVariable } from "./deriva-variables-datos";
import type { FilaVariable } from "./deriva-variables-datos";

export interface HistogramaVariableProps {
  variable: FilaVariable;
  /** Omite el bloque de título: la pestaña que lo monta ya pinta título y subtítulo. */
  sinTitulo?: boolean;
}

export function HistogramaVariable({ variable, sinTitulo }: HistogramaVariableProps) {
  const numerica = esNumerica(variable);
  const tramos = numerica ? etiquetasDeBordes(variable.binEdges) : variable.categories;
  const nBase = variable.countsBase.reduce((a, b) => a + b, 0);
  const nActual = variable.countsActual.reduce((a, b) => a + b, 0);
  const filas = construirFilasHistograma(tramos, variable.countsBase, variable.countsActual);
  const rango = rangoDeVariable(variable);

  const frase = filas.length === 0
    ? null
    : distribucionesIdenticas(filas)
      ? `Las dos distribuciones son idénticas: la línea base y el lote reparten los ${filas.length} tramos por igual.`
      : fraseTramosQueMasCambian(filas, 3);

  return (
    <div className="flex flex-col gap-3">
      {sinTitulo ? null : (
        <div>
          <h4 className="text-sm font-semibold">{variable.featureLabel}: línea base frente a lote</h4>
          <p className="text-xs text-muted-foreground" title={variable.feature}>
            {numerica ? "Numérica" : "Categórica"} · {rango}
          </p>
          {variable.sinValoresComunes ? (
            <p className="mt-1 text-xs text-muted-foreground">{TEXTO_SIN_COMUNES}</p>
          ) : null}
        </div>
      )}

      <HistogramaBaseLote
        tramos={tramos}
        base={variable.countsBase}
        actual={variable.countsActual}
        prefijoTramo={variable.featureLabel}
        alto={230}
      />

      <div className="flex flex-wrap items-center gap-3.5 text-xs text-muted-foreground tabular-nums">
        <span>
          n base <b className="font-semibold text-foreground">{formatoNumero(nBase, 0)}</b>
        </span>
        <span>
          n lote <b className="font-semibold text-foreground">{formatoNumero(nActual, 0)}</b>
        </span>
        {variable.psi !== null ? (
          <span className="inline-flex items-center gap-1">
            <CabeceraEstadistico {...AYUDA_ESTADISTICO.psi} />
            <b className="font-semibold text-foreground">{formatoNumero(variable.psi, 2)}</b>
          </span>
        ) : null}
        {variable.ksStat !== null ? (
          <span className="inline-flex items-center gap-1">
            <CabeceraEstadistico {...AYUDA_ESTADISTICO.ks} />
            <b className="font-semibold text-foreground">{formatoNumero(variable.ksStat, 2)}</b> (p{" "}
            {formatoNumero(variable.ksP)})
          </span>
        ) : null}
        {variable.chi2 !== null ? (
          <span className="inline-flex items-center gap-1">
            <CabeceraEstadistico {...AYUDA_ESTADISTICO.chi2} />
            <b className="font-semibold text-foreground">{formatoNumero(variable.chi2, 1)}</b> (p{" "}
            {formatoNumero(variable.p)})
          </span>
        ) : null}
      </div>
      {numerica ? (
        <p className="text-xs text-muted-foreground" data-testid="dos-cifras-deriva">
          {TEXTO_DOS_CIFRAS_DERIVA}
        </p>
      ) : null}
      {frase ? <p className="text-xs text-muted-foreground">{frase}</p> : null}
    </div>
  );
}

export default HistogramaVariable;
