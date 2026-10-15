/**
 * El dato del paso en el panel de la demo guiada: lo declarado en el guion
 * frente a lo real de la evaluación («el dato es contrato, no adorno»).
 * Heredero de
 * `pages/onboarding/PanelDato.tsx`, en versión compacta: el panel mide unos
 * 20 rem y la pantalla real ya enseña el histograma o el ranking al lado,
 * así que aquí no se incrustan gráficas.
 */

import type { PasoDemo } from "@/api/queries-contenido";
import { StateBadge } from "@/components/vigia/StateBadge";
import { formatoNumero, metricLabel } from "@/lib/metrics";

import { CLAVE_COMPOSICION, coincideConEsperado, GRUPO_SUPERVISADO, type DatoResuelto } from "./dato";

export interface PanelDatoProps {
  paso: PasoDemo;
  dato: DatoResuelto;
}

export function PanelDato({ paso, dato }: PanelDatoProps) {
  const { metric_key: metricKey, esperado, umbral, estado } = paso.dato;
  if (metricKey === null) return null;

  const coincide =
    estado !== null && dato.estadoReal !== null ? coincideConEsperado(metricKey, estado, dato.estadoReal) : null;
  const grupoSupervisado = dato.composicion?.groups.find((g) => g.group_code === GRUPO_SUPERVISADO);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-background p-3 text-left" data-dato={metricKey}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h3 className="text-xs text-muted-foreground">{metricLabel(metricKey)}</h3>
        {coincide !== null ? (
          <span
            className="text-xs font-semibold"
            style={{ color: coincide ? "var(--state-ok)" : "var(--state-alert)" }}
            data-coincide={coincide ? "si" : "no"}
          >
            {coincide ? "Coincide con lo esperado" : "No coincide con lo esperado"}
          </span>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Según el guion</span>
          {esperado !== null ? (
            <span className="text-lg font-semibold tabular-nums">{formatoNumero(esperado)}</span>
          ) : (
            <span className="text-xs text-muted-foreground">
              {umbral !== null ? `Umbral ${formatoNumero(umbral)}` : "Sin cifra en este paso"}
            </span>
          )}
          {estado ? <StateBadge estado={estado} size="sm" /> : null}
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Real</span>
          {dato.cargando ? (
            <span className="text-xs text-muted-foreground">Calculando…</span>
          ) : dato.valorReal !== null ? (
            <span className="text-lg font-semibold tabular-nums">{formatoNumero(dato.valorReal)}</span>
          ) : (
            <span className="text-xs text-muted-foreground">Sin medida en esta evaluación.</span>
          )}
          {dato.estadoReal ? <StateBadge estado={dato.estadoReal} size="sm" /> : null}
        </div>
      </div>
      {esperado !== null && umbral !== null ? (
        <p className="text-xs text-muted-foreground">Umbral {formatoNumero(umbral)}</p>
      ) : null}
      {metricKey === CLAVE_COMPOSICION && dato.composicion ? (
        <p className="text-xs text-muted-foreground">
          Grupo supervisado: {grupoSupervisado?.n ?? 0} de {dato.composicion.total.n} registros del lote.
        </p>
      ) : null}
    </div>
  );
}
