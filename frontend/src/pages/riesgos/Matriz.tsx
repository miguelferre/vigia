/**
 * Matriz 5x5 de impacto x probabilidad: agregada en el cliente a partir de
 * `GET /projects/{id}/risks` (sin endpoint aparte).
 * Filas de Severo (arriba) a Insignificante (abajo), columnas de Raro
 * (izquierda) a Casi seguro (derecha); cada celda con el nivel por color Y
 * por texto (§13.3: distinguibles sin depender del color) y sus códigos
 * como chips clicables.
 */

import { Fragment, useMemo, useState } from "react";

import { useRisks } from "@/api/queries-riesgos";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { ErrorDeConsulta } from "@/components/vigia";
import { celda, construirMatriz } from "./matriz-datos";
import {
  ETIQUETA_NIVEL,
  fondoNivel,
  IMPACTO_LABELS,
  IMPACTOS_DESCENDENTE,
  nivelDeCelda,
  PROBABILIDAD_LABELS,
  PROBABILIDADES_ASCENDENTE,
  TOKEN_NIVEL,
} from "./niveles";

export interface MatrizProps {
  projectId: number;
  onSelectRiesgo: (id: number) => void;
}

export function Matriz({ projectId, onSelectRiesgo }: MatrizProps) {
  const [incluirCerrados, setIncluirCerrados] = useState(false);
  const riesgos = useRisks(projectId, { limit: 500 });

  const items = useMemo(() => {
    const todos = riesgos.data?.items ?? [];
    return incluirCerrados ? todos : todos.filter((r) => r.status !== "cerrado");
  }, [riesgos.data, incluirCerrados]);

  const matriz = useMemo(() => construirMatriz(items), [items]);

  if (riesgos.isLoading) return <Skeleton className="h-96 w-full" />;
  if (riesgos.isError) {
    return <ErrorDeConsulta que="los riesgos" error={riesgos.error} onReintentar={() => void riesgos.refetch()} />;
  }

  return (
    <div id="matriz" className="flex scroll-mt-20 flex-col gap-3">
      <div className="flex items-center gap-2">
        <Switch id="incluir-cerrados" checked={incluirCerrados} onCheckedChange={setIncluirCerrados} />
        <Label htmlFor="incluir-cerrados" className="text-sm">
          Incluir cerrados
        </Label>
      </div>

      <div className="overflow-x-auto">
        <div className="grid min-w-[640px] grid-cols-[7rem_repeat(5,1fr)] gap-1">
          <div />
          {PROBABILIDADES_ASCENDENTE.map((p) => (
            <div key={p} className="px-1 text-center text-xs font-semibold text-muted-foreground">
              {PROBABILIDAD_LABELS[p]}
            </div>
          ))}
          {IMPACTOS_DESCENDENTE.map((impacto) => (
            <Fragment key={impacto}>
              <div
                key={`etiqueta-${impacto}`}
                className="flex items-center justify-end px-1 text-right text-xs font-semibold text-muted-foreground"
              >
                {IMPACTO_LABELS[impacto]}
              </div>
              {PROBABILIDADES_ASCENDENTE.map((probabilidad) => {
                const c = celda(matriz, impacto, probabilidad);
                const referencia = nivelDeCelda(impacto, probabilidad);
                return (
                  <div
                    key={`${impacto}-${probabilidad}`}
                    className="flex min-h-20 flex-col gap-1 rounded-md border p-1.5"
                    style={{ background: fondoNivel(referencia), borderColor: TOKEN_NIVEL[referencia] }}
                  >
                    <div className="flex items-center justify-between text-xs font-semibold">
                      <span style={{ color: TOKEN_NIVEL[referencia] }}>{ETIQUETA_NIVEL[referencia]}</span>
                      {c.riesgos.length > 0 ? <span>{c.riesgos.length}</span> : null}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {c.riesgos.map((r) => (
                        <button
                          key={r.id}
                          type="button"
                          onClick={() => onSelectRiesgo(r.id)}
                          className="rounded border border-border bg-card px-1.5 py-0.5 font-mono text-xs hover:bg-muted"
                        >
                          {r.code}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-3 text-xs">
        {(["bajo", "medio", "alto", "critico"] as const).map((nivel) => (
          <span key={nivel} className="flex items-center gap-1.5">
            <span
              className="inline-block size-3 rounded-sm border"
              style={{ background: fondoNivel(nivel), borderColor: TOKEN_NIVEL[nivel] }}
            />
            {ETIQUETA_NIVEL[nivel]}
          </span>
        ))}
      </div>
    </div>
  );
}
