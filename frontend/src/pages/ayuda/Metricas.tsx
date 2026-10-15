/**
 * Sección «Métricas por monitor» de `/ayuda`: qué mide, fórmula y (si el JSON
 * ya los trae) cómo se lee y el umbral por defecto.
 */

import { formatoNumero } from "@/lib/metrics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import { NotaMulticlase } from "@/components/vigia/NotaMulticlase";
import type { GrupoMetricas } from "./agrupar";

export interface MetricasProps {
  grupos: GrupoMetricas[];
  cargando: boolean;
  /** Ayuda general (sin proyecto o con uno binario): cada métrica nombra su diferencia multiclase. */
  ayudaGeneral?: boolean;
}

export function Metricas({ grupos, cargando, ayudaGeneral = false }: MetricasProps) {
  if (cargando) {
    return <p className="text-sm text-muted-foreground">Cargando métricas…</p>;
  }
  if (grupos.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin métricas para esta búsqueda.</p>;
  }
  return (
    <div className="flex flex-col gap-6">
      {grupos.map((grupo) => (
        <div key={grupo.monitor} className="flex flex-col gap-3">
          <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            {grupo.monitor === "cross" ? "Reglas cruzadas" : ETIQUETA_MONITOR[grupo.monitor]}
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {grupo.entradas.map(([clave, entrada]) => (
              <Card key={clave}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">
                    {grupo.monitor === "cross" ? `${clave}: ${entrada.etiqueta}` : entrada.etiqueta}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-1.5 pt-0 text-sm text-muted-foreground">
                  <p>{entrada.que_mide}</p>
                  {entrada.formula ? (
                    <p className="rounded bg-muted px-2 py-1 font-mono text-xs">{entrada.formula}</p>
                  ) : null}
                  {entrada.como_se_lee ? <p>Cómo se lee: {entrada.como_se_lee}</p> : null}
                  {entrada.umbral_por_defecto ? (
                    <p>Umbral por defecto: {textoUmbral(entrada.umbral_por_defecto)}</p>
                  ) : null}
                  {entrada.nota ? <p className="text-xs italic">{entrada.nota}</p> : null}
                  <NotaMulticlase ayuda={entrada} ayudaGeneral={ayudaGeneral} />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/** `{limite_inferior, limite_superior}` a texto; las claves técnicas no se
 * enseñan. `formula_vars` tampoco: es para instanciar fórmulas. */
function textoUmbral(umbral: Record<string, number>): string {
  const partes: string[] = [];
  if (umbral.limite_inferior != null) partes.push(`inferior ${formatoNumero(umbral.limite_inferior)}`);
  if (umbral.limite_superior != null) partes.push(`superior ${formatoNumero(umbral.limite_superior)}`);
  return partes.join(" · ");
}
