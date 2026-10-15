/**
 * Pestaña «Registro»: tabla filtrable de riesgos.
 * Filtros en servidor: `status` (multi, coma-separado como
 * `list_alerts`), `impact` y `probability` (1-5). El botón «Nuevo riesgo»
 * vive aquí (`NuevoRiesgo.tsx`).
 */

import { useMemo, useState } from "react";
import { Link } from "react-router";

import { useRisks } from "@/api/queries-riesgos";
import type { Risk } from "@/api/types";
import { DataTable, EmptyState, ErrorDeConsulta } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { useCan } from "@/session/session";
import { formatoRelativo } from "@/lib/fechas";
import { NuevoRiesgo } from "./NuevoRiesgo";
import { ESTADOS_RIESGO, ETIQUETA_ESTADO_RIESGO, ETIQUETA_NIVEL, IMPACTO_LABELS, PROBABILIDAD_LABELS, TOKEN_NIVEL } from "./niveles";

export interface RegistroProps {
  projectId: number;
  onSelectRiesgo: (id: number) => void;
}

const TODOS = "todos";

export function Registro({ projectId, onSelectRiesgo }: RegistroProps) {
  const puedeConfig = useCan("config");
  const [estados, setEstados] = useState<ReadonlySet<string>>(new Set());
  const [impacto, setImpacto] = useState<string>(TODOS);
  const [probabilidad, setProbabilidad] = useState<string>(TODOS);

  const filtros = useMemo(
    () => ({
      status: estados.size > 0 ? Array.from(estados).join(",") : null,
      impact: impacto === TODOS ? null : Number(impacto),
      probability: probabilidad === TODOS ? null : Number(probabilidad),
    }),
    [estados, impacto, probabilidad],
  );
  const riesgos = useRisks(projectId, filtros);

  const alternarEstado = (estado: string) => {
    setEstados((previos) => {
      const siguiente = new Set(previos);
      if (!siguiente.delete(estado)) siguiente.add(estado);
      return siguiente;
    });
  };

  const columnas: LegacyColumnDef<Risk, unknown>[] = [
    { id: "code", header: "Código", cell: ({ row }) => <span className="font-mono">{row.original.code}</span> },
    { id: "title", header: "Título", cell: ({ row }) => row.original.title },
    {
      id: "nivel",
      header: "Nivel",
      cell: ({ row }) => (
        <span style={{ color: TOKEN_NIVEL[row.original.level] }} className="font-semibold">
          {ETIQUETA_NIVEL[row.original.level]}
        </span>
      ),
    },
    { id: "impacto", header: "Impacto", cell: ({ row }) => row.original.impact_label },
    { id: "probabilidad", header: "Probabilidad", cell: ({ row }) => row.original.probability_label },
    {
      id: "origen",
      header: "Origen",
      cell: ({ row }) =>
        row.original.origin_alert_id ? (
          <Link
            to={`/alertas?panel=${row.original.origin_alert_id}`}
            className="text-link hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {row.original.origin_alert_title ?? `Alerta #${row.original.origin_alert_id}`}
          </Link>
        ) : (
          "a mano"
        ),
    },
    { id: "estado", header: "Estado", cell: ({ row }) => ETIQUETA_ESTADO_RIESGO[row.original.status] },
    { id: "fecha", header: "Fecha", cell: ({ row }) => formatoRelativo(row.original.created_at) },
  ];

  return (
    <div id="registro" className="flex scroll-mt-20 flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex items-center gap-1" role="group" aria-label="Filtro por estado">
            {ESTADOS_RIESGO.map((estado) => (
              <button
                key={estado}
                type="button"
                onClick={() => alternarEstado(estado)}
                aria-pressed={estados.has(estado)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs font-semibold",
                  estados.has(estado) ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground",
                )}
              >
                {ETIQUETA_ESTADO_RIESGO[estado]}
              </button>
            ))}
          </div>
          <Select value={impacto} onValueChange={setImpacto}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Impacto" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todo impacto</SelectItem>
              {Object.entries(IMPACTO_LABELS).map(([valor, etiqueta]) => (
                <SelectItem key={valor} value={valor}>
                  {etiqueta}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={probabilidad} onValueChange={setProbabilidad}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Probabilidad" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Toda probabilidad</SelectItem>
              {Object.entries(PROBABILIDAD_LABELS).map(([valor, etiqueta]) => (
                <SelectItem key={valor} value={valor}>
                  {etiqueta}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {puedeConfig ? <NuevoRiesgo projectId={projectId} /> : null}
      </div>

      {riesgos.isError ? (
        <ErrorDeConsulta que="los riesgos" error={riesgos.error} onReintentar={() => void riesgos.refetch()} />
      ) : (
        <DataTable
          data={riesgos.data?.items ?? []}
          columns={columnas}
          cargando={riesgos.isLoading}
          titulo="Registro de riesgos"
          onRowClick={(fila) => onSelectRiesgo(fila.id)}
          vacio={
            <EmptyState
              titulo="No hay riesgos con estos filtros"
              descripcion="Registra uno desde una alerta o a mano con «Nuevo riesgo»."
            />
          }
        />
      )}
    </div>
  );
}
