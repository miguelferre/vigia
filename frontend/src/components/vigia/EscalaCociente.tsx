/**
 * Fórmula del impacto dispar con cifras sustituidas, sobre
 * `CajaFormula`. Partido de `CalculoFormula.tsx` (que pasaba de 9 KB
 * al añadir el violín de equidad): `CalculoFormula.tsx` sigue
 * reexportando `EscalaCociente` para no tocar sus llamadores.
 */

import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import type { Measurement } from "@/api/types";
import { metricLabel } from "@/lib/metrics";

import { textoComoSeLee, textoQueMide } from "./AyudaTexto";
import { CajaFormula } from "./CajaFormula";
import { formatoCorto, formatoPorcentaje } from "./calculo-datos";
import { colorEstado } from "./StateBadge";
import { ViolinPartido } from "./ViolinPartido";
import { parseFavorableProbability } from "./violin-partido-datos";

export interface EscalaCocienteProps {
  mDi: Measurement | undefined;
  mUnpriv: Measurement | undefined;
  mPriv: Measurement | undefined;
  /** `details` de la evaluación: de ahí sale `favorable_probability` del violín. */
  detalles?: Record<string, unknown> | null;
  nombreSupervisado?: string;
  nombreReferencia?: string;
}

export function EscalaCociente({ mDi, mUnpriv, mPriv, detalles, nombreSupervisado, nombreReferencia }: EscalaCocienteProps) {
  const valor = mDi?.value ?? null;
  const umbral = typeof mDi?.threshold_low === "number" ? mDi.threshold_low : null;
  const dominio = Math.max(150, Math.ceil(((valor ?? 0) + 20) / 10) * 10, umbral !== null ? Math.ceil((umbral + 20) / 10) * 10 : 0);
  const pctValor = valor !== null ? Math.min(100, Math.max(0, (valor / dominio) * 100)) : null;
  const pctUmbral = umbral !== null ? Math.min(100, Math.max(0, (umbral / dominio) * 100)) : null;
  const color = colorEstado(mDi?.state);
  const todaAyuda = useContenidoMetricasPorTipo().data;
  const { caps } = useTipoTarea();
  const ayuda = todaAyuda?.["fairness_value"];
  const formula = ayuda?.formula ?? "";
  const favorableProbabilidad = parseFavorableProbability(detalles ?? null);

  return (
    <CajaFormula
      formula={formula}
      instanciada={
        <>
          {formatoPorcentaje(mUnpriv?.value ?? null)} / {formatoPorcentaje(mPriv?.value ?? null)} × 100
        </>
      }
      resultado={formatoCorto(valor)}
      umbralTexto={umbral !== null ? `Umbral: mínimo ${formatoCorto(umbral)}` : null}
      estado={mDi?.state}
      motivo={mDi?.motivo}
      info={{
        titulo: ayuda?.etiqueta ?? metricLabel("fairness_value"),
        queMide: textoQueMide(ayuda),
        comoSeLee: textoComoSeLee(ayuda),
        formula: ayuda?.formula,
      }}
    >
      <div className="relative mt-1 h-2.5 w-full rounded-full bg-muted">
        {pctValor !== null ? (
          <div className="h-full rounded-full" style={{ width: `${pctValor}%`, background: color }} />
        ) : null}
        {pctUmbral !== null ? (
          <div
            className="absolute inset-y-0 w-0.5 bg-foreground/70"
            style={{ left: `${pctUmbral}%` }}
            title={`Umbral: mínimo ${formatoCorto(umbral)}`}
          />
        ) : null}
      </div>
      {favorableProbabilidad.datos ? (
        <ViolinPartido
          detalles={detalles ?? null}
          nombreSupervisado={nombreSupervisado ?? "grupo supervisado"}
          nombreReferencia={nombreReferencia ?? "grupo de referencia"}
          conjuntoFavorable={caps?.favorables === "conjunto"}
        />
      ) : favorableProbabilidad.motivo ? (
        <p className="text-xs text-muted-foreground">{favorableProbabilidad.motivo}</p>
      ) : null}
    </CajaFormula>
  );
}

export default EscalaCociente;
