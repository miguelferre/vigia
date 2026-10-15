/**
 * Composición por grupo de `/datos/:batch`: tabla y barra apilada (Recharts).
 * «Predicción frente a etiqueta» confundía; la
 * tabla trae recuentos (`pred_favorable_n`) y el gráfico es una barra apilada
 * por grupo (favorables en `--chart-1`, resto en `--line-2`) con el recuento
 * de favorables como etiqueta. La tasa de etiqueta sale del gráfico y se
 * queda solo en la tabla.
 * Los grupos se etiquetan por rango de edad y papel
 * («18-35 · supervisado»), no por código en crudo; el tooltip usa un cuadro
 * opaco (mismo patrón que `ChartTooltipContent`), no el `contentStyle` de
 * recharts, que se pintaba semitransparente sobre las barras.
 */

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts";

import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { BatchComposition, ColumnMappingOut } from "@/api/types";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { DataTable } from "@/components/vigia";
import { formatoPorcentaje } from "@/components/vigia/calculo-datos";
import type { LegacyColumnDef } from "@/components/vigia";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { formatoCorto, formatoNumero } from "@/lib/metrics";

import { EtiquetaFavorable, TextoFavorables, TooltipComposicion } from "./composicion-grafico";
import { CONFIG_COMPOSICION, type FilaComposicion, type ModoComposicion } from "./composicion-modos";
import { etiquetaGrupo, etiquetaGrupoConPapel, papelDeGrupo } from "./grupo";

interface Props {
  batchId: number;
  mapping: ColumnMappingOut | null | undefined;
  /** Proyecto del lote: el tipo de tarea sale de él, no del proyecto de la sesión. */
  projectId: number | null;
}

export default function ComposicionLote({ batchId, mapping, projectId }: Props) {
  // En multiclase «favorable» es un conjunto de clases y la composición lo dice.
  const tarea = useTipoTarea(projectId);
  // Tres modos según el tipo de resultado bueno; decide `caps`, no el tipo suelto.
  const conjunto = tarea.caps?.favorables === "conjunto";
  const modo: ModoComposicion = tarea.sinRango ? "sin_rango" : tarea.caps?.rangoFavorable ? "rango" : "favorable";
  const { data, isLoading } = useQuery({
    queryKey: qk.composition(batchId),
    queryFn: () => api.get<BatchComposition>(`/batches/${batchId}/composition`),
  });

  // Orden fijo supervisado, referencia, otros (feedback), con independencia
  // del orden en el que llegue `data.groups` (el backend ordena por código
  // crudo, donde -1 de «otros» queda antes que 0 y 1).
  const ordenPapel: Record<string, number> = { supervisado: 0, referencia: 1 };
  const filas: FilaComposicion[] = (data?.groups ?? [])
    .map((g) => {
      const rango = g.group_label ?? etiquetaGrupo(g.group_code, mapping);
      // `pred_favorable_n` es nulo en una regresión sin rango favorable;
      // la pantalla enseña el motivo en vez de un 0 % (modo `sin_rango`).
      const favorable = g.pred_favorable_n ?? 0;
      return {
        codigo: g.group_code,
        grupo: etiquetaGrupoConPapel(g.group_code, rango),
        n: g.n,
        favorable,
        predRate: g.pred_favorable_rate,
        labelRate: g.label_favorable_rate,
        resto: Math.max(0, g.n - favorable),
      };
    })
    .sort((a, b) => {
      const pa = ordenPapel[papelDeGrupo(a.codigo) ?? ""] ?? 2;
      const pb = ordenPapel[papelDeGrupo(b.codigo) ?? ""] ?? 2;
      return pa - pb;
    });

  const supervisado = data?.groups?.find((g) => g.group_code === 0);
  const totalN = data?.total?.n ?? 0;
  const pctSupervisado = supervisado && totalN > 0 ? (supervisado.n / totalN) * 100 : null;

  const columnasFavorables: LegacyColumnDef<FilaComposicion, unknown>[] = [
    {
      id: "favorables_tabla",
      header: modo === "rango" ? "Predicción dentro del rango" : "Favorables",
      cell: ({ row }) => `${formatoNumero(row.original.favorable, 0)} (${formatoPorcentaje(row.original.predRate)})`,
    },
    {
      id: "label_tabla",
      header: conjunto ? "Etiqueta en clases favorables" : modo === "rango" ? "Valor real dentro del rango" : "Valor favorable",
      cell: ({ row }) => formatoPorcentaje(row.original.labelRate),
    },
  ];
  const columnas: LegacyColumnDef<FilaComposicion, unknown>[] = [
    { header: "Grupo", accessorKey: "grupo" },
    { header: "Registros", accessorKey: "n" },
    ...(modo === "sin_rango" ? [] : columnasFavorables),
  ];

  // Sin el tipo de tarea no se dibuja la tabla (no parpadea de binario a multiclase).
  if (tarea.cargando) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Cargando la composición…
      </p>
    );
  }

  return (
    <div id="composicion" className="flex scroll-mt-20 flex-col gap-4" data-loading={isLoading || undefined}>
      <TextoFavorables
        modo={modo}
        conjunto={conjunto}
        favorables={tarea.favorables}
        rangos={tarea.rangos}
        unidad={tarea.unidad}
        motivo={data?.motivo}
      />
      <DataTable data={filas} columns={columnas} cargando={isLoading} titulo="Composición por grupo" />
      {filas.length > 0 ? (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">Registros</p>
          <ChartContainer config={CONFIG_COMPOSICION} className="h-64">
            <BarChart data={filas} margin={{ top: 24, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="grupo" stroke="var(--muted-foreground)" fontSize={12} />
              <YAxis
                stroke="var(--muted-foreground)"
                fontSize={12}
                tickFormatter={(v) => formatoCorto(Number(v), 0)}
              />
              <ChartTooltip
                // D14: cursor translúcido para no tapar las barras vecinas (mismo patrón que HistogramaBaseLote).
                cursor={{ fill: "var(--muted)", fillOpacity: 0.5 }}
                content={<TooltipComposicion modo={modo} />}
              />
              {/* Apilada, resto abajo (gris) y favorables arriba (color), con su
                  recuento encima; supervisado y referencia lado a lado, «otros» detrás
                  (orden ya resuelto en `filas`). */}
              <Bar
                dataKey="resto"
                name={modo === "sin_rango" ? "Registros" : "Resto"}
                stackId="comp"
                fill={modo === "sin_rango" ? "var(--chart-1)" : "var(--color-resto)"}
                isAnimationActive={false}
              />
              {modo === "sin_rango" ? null : (
                <Bar dataKey="favorable" name="Favorables" stackId="comp" fill="var(--color-favorable)" isAnimationActive={false}>
                  <LabelList dataKey="favorable" content={EtiquetaFavorable} />
                </Bar>
              )}
            </BarChart>
          </ChartContainer>
          {modo === "sin_rango" ? null : (
            <div className="flex items-center gap-3.5 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ background: "var(--chart-1)" }} />
                {modo === "rango" ? "Dentro del rango" : "Favorables"}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ background: "var(--line-2)" }} />
                Resto
              </span>
            </div>
          )}
        </div>
      ) : null}
      {data?.total && modo === "sin_rango" ? (
        <p className="text-sm text-muted-foreground">
          Total: n={data.total.n}.
          {pctSupervisado !== null ? ` El grupo supervisado es el ${formatoNumero(pctSupervisado, 1)} % del total.` : ""}
        </p>
      ) : null}
      {data?.total && modo !== "sin_rango" ? (
        <p className="text-sm text-muted-foreground">
          Total: n={data.total.n}, predicción {modo === "rango" ? "dentro del rango" : "favorable"}{" "}
          {formatoNumero(data.total.pred_favorable_rate)}, {modo === "rango" ? "valor real dentro del rango" : "etiqueta favorable"}{" "}
          {formatoNumero(data.total.label_favorable_rate)}.
          {pctSupervisado !== null ? ` El grupo supervisado es el ${formatoNumero(pctSupervisado, 1)} % del total.` : ""}
        </p>
      ) : null}
    </div>
  );
}
