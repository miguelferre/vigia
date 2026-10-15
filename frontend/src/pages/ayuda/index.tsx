/**
 * `/ayuda`:
 * buscador sobre la guía de uso, el glosario y las métricas, agrupados.
 * Reutiliza `useGlosario`/`useContenidoMetricas`/`useGuiaUso`
 * (`api/queries-contenido.ts`, `staleTime: Infinity`). Con `?q=` en la URL
 * (por ejemplo desde un enlace externo) el buscador arranca con ese texto.
 *
 * Partido en `agrupar.ts` (agrupación y filtro, sin React), `GuiaUso.tsx` /
 * `GuiaEntrada.tsx` (acordeón de la guía) y `Conceptos.tsx` / `Metricas.tsx`
 * (presentación) para que ningún fichero pase de 9 KB.
 */

import { useMemo, useState } from "react";
import { SearchIcon } from "lucide-react";
import { useSearchParams } from "react-router";

import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/vigia";
import { useContenidoMetricasPorTipo, useGlosario } from "@/api/queries-contenido";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { useTitulo } from "@/hooks/useTitulo";

import { agruparGlosario, agruparMetricas } from "./agrupar";
import { Conceptos } from "./Conceptos";
import { Datos } from "./Datos";
import { GuiaUso } from "./GuiaUso";
import { Metricas } from "./Metricas";
import { Simbolos } from "./Simbolos";

export default function Ayuda() {
  useTitulo("Ayuda");
  const [parametros] = useSearchParams();
  const [busqueda, setBusqueda] = useState(() => parametros.get("q") ?? "");
  const glosarioQ = useGlosario();
  // La ayuda de métricas sale resuelta por tipo (`ayudaPorTipo`); en la ayuda general (sin proyecto o binario), la binaria y la nota multiclase.
  const metricasQ = useContenidoMetricasPorTipo();
  const { caps, cargando: tipoCargando } = useTipoTarea();

  const gruposConceptos = useMemo(
    () => agruparGlosario(glosarioQ.data, busqueda),
    [glosarioQ.data, busqueda],
  );
  const gruposMetricas = useMemo(
    () => agruparMetricas(metricasQ.data, busqueda),
    [metricasQ.data, busqueda],
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Ayuda"
        descripcion="Cómo usar Vigía y qué significa cada concepto y cada métrica, en un solo sitio."
      />

      <div className="relative max-w-sm">
        <SearchIcon
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          value={busqueda}
          onChange={(evento) => setBusqueda(evento.target.value)}
          placeholder="Buscar un concepto o una métrica…"
          className="pl-8"
          aria-label="Buscar en la ayuda"
        />
      </div>

      <GuiaUso busqueda={busqueda} />

      <Datos oculto={busqueda.trim().length > 0} />

      <Simbolos oculto={busqueda.trim().length > 0} />

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Conceptos</h2>
        <Conceptos grupos={gruposConceptos} cargando={glosarioQ.isLoading} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Métricas por monitor</h2>
        <Metricas
          grupos={gruposMetricas}
          cargando={metricasQ.isLoading || tipoCargando}
          // Ayuda general = sin proyecto o con el bloque base (binario); multiclase y regresión ya salen resueltas.
          ayudaGeneral={(caps === undefined || caps.bloqueAyuda === "base") && !tipoCargando}
        />
      </section>
    </div>
  );
}
