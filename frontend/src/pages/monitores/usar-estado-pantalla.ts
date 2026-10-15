/**
 * Estado local de `/monitores/:tipo` que no depende de la respuesta del
 * servidor. Partido de `index.tsx` para no superar 9 KB en ese fichero:
 *
 * - `useConfigAbierta`: la hoja «Configurar», que también se abre con
 *   `#configurar` (paso «Dónde se configura el protocolo» de la
 *   demo); el hash se aplica una sola vez, ajustado en el render, para que
 *   cerrar la hoja no la reabra. Cerrar (Cancelar, aspa o guardar) limpia el
 *   hash de la URL: si se queda puesto, una segunda navegación
 *   al mismo enlace `#configurar` no reabre la hoja, porque nunca vuelve a
 *   ver el hash "cambiar" de `#configurar` a otra cosa.
 * - `useMetricaAmpliada`: la métrica ampliada de la rejilla, leída
 *   de `?metrica=<key>` solo al montar y que se limpia al
 *   cambiar de tipo de monitor para no arrastrar una métrica de otro.
 * - `usePeriodoMonitor`: el periodo, resuelto a
 *   since/until para pedir `/timeline`, con la comprobación de que «Desde»
 *   no sea posterior a «Hasta».
 */

import { useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";

import type { ValorPeriodo } from "@/components/vigia";
import { resolverPeriodo } from "@/lib/fechas";
import type { MonitorType } from "@/api/types";

export function useConfigAbierta() {
  const [configAbierta, setConfigAbiertaEstado] = useState(false);
  const { hash, pathname, search } = useLocation();
  const navigate = useNavigate();
  const [hashConfigAplicado, setHashConfigAplicado] = useState<string | null>(null);
  if (hash === "#configurar" && hashConfigAplicado !== hash) {
    setHashConfigAplicado(hash);
    setConfigAbiertaEstado(true);
  } else if (hash !== "#configurar" && hashConfigAplicado !== null) {
    setHashConfigAplicado(null);
  }
  const setConfigAbierta = (abierta: boolean) => {
    setConfigAbiertaEstado(abierta);
    if (!abierta && hash === "#configurar") {
      navigate({ pathname, search }, { replace: true });
    }
  };
  return [configAbierta, setConfigAbierta] as const;
}

export function useMetricaAmpliada(monitorType: MonitorType | undefined) {
  const [searchParams] = useSearchParams();
  const [metricaAmpliada, setMetricaAmpliada] = useState<string | null>(() => searchParams.get("metrica"));
  const [monitorTypeAnterior, setMonitorTypeAnterior] = useState(monitorType);
  if (monitorType !== monitorTypeAnterior) {
    setMonitorTypeAnterior(monitorType);
    setMetricaAmpliada(null);
  }
  return [metricaAmpliada, setMetricaAmpliada] as const;
}

export function usePeriodoMonitor() {
  const [periodoValor, setPeriodoValor] = useState<ValorPeriodo>({ periodo: "mes" });
  const periodo = useMemo(() => resolverPeriodo(periodoValor.periodo, periodoValor), [periodoValor]);
  // `resolverPeriodo` no comprueba el orden: con "Desde" > "Hasta" construiría
  // since > until y `/timeline` lo rechazaría con 422 (evaluations.py:261).
  const periodoInvalido =
    periodoValor.periodo === "personalizado" &&
    !!periodoValor.since &&
    !!periodoValor.until &&
    periodoValor.since > periodoValor.until;
  return { periodoValor, setPeriodoValor, periodo, periodoInvalido };
}
