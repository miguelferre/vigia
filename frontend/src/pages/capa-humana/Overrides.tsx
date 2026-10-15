/**
 * Bloque «Overrides» (`#overrides`): por subgrupo, por
 * fase y distribución agregada entre profesionales (nunca una
 * fila por pseudónimo).
 */

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, EmptyState, InfoTooltip } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { useGlosario } from "@/api/queries-contenido";
import { useOverrides } from "@/api/queries-humana";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import type { OverridesByClinicianResponse, OverridesGroupRow } from "@/api/types";
import { formatoCorto, formatoMetrica } from "@/lib/metrics";
import { TablaCambios } from "./overrides-cambios";
import { MOTIVO_SIN_RANGO } from "./registro-uso-decision";

/** La tasa de la fila es `tasa`, que viene nula bajo la celda mínima (`min_n`): se dice en vez de enseñar un número. */
function TablaGrupo({
  filas,
  minN,
  unidad,
  conDiferencia,
}: {
  filas: OverridesGroupRow[];
  minN: number;
  unidad?: string | null;
  conDiferencia: boolean;
}) {
  const columnas: LegacyColumnDef<OverridesGroupRow, unknown>[] = [
    { id: "grupo", header: "Grupo", cell: ({ row }) => row.original.group },
    { id: "n", header: "Decisiones", cell: ({ row }) => row.original.n },
    {
      id: "tasa",
      header: "Tasa de override",
      cell: ({ row }) => {
        const tasa = row.original.tasa;
        if (tasa === null) {
          return (
            <span className="text-muted-foreground" data-testid="tasa-bajo-minimo">
              Menos de {minN} decisiones
            </span>
          );
        }
        return (
          <div className="flex items-center gap-2">
            <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-[var(--chart-1)]" style={{ width: `${Math.round(tasa * 100)}%` }} />
            </div>
            <span>{formatoCorto(tasa)}</span>
          </div>
        );
      },
    },
    // Bajo la celda mínima (`tasa` nula) tampoco se enseñan los cuartiles de ese grupo.
    { id: "p25", header: "p25", cell: ({ row }) => (row.original.tasa === null ? "n/d" : formatoCorto(row.original.p25)) },
    { id: "p75", header: "p75", cell: ({ row }) => (row.original.tasa === null ? "n/d" : formatoCorto(row.original.p75)) },
    // En regresión, cuánto se aparta la cifra de la persona de la del modelo; informativa, sin estado.
    // La unidad es opcional: sin ella la columna sale igual, sin la unidad en el título.
    ...(conDiferencia
      ? [
          {
            id: "diferencia_media",
            header: unidad ? `Diferencia media (${unidad})` : "Diferencia media",
            cell: ({ row }: { row: { original: OverridesGroupRow } }) =>
              formatoMetrica("diferencia_media", row.original.diferencia_media, unidad),
          },
        ]
      : []),
  ];
  return <DataTable data={filas} columns={columnas} titulo="Overrides por grupo" />;
}

function DistribucionClinicos({ datos }: { datos: OverridesByClinicianResponse }) {
  if (!datos.distribution) {
    return <EmptyState titulo="Sin distribución" descripcion={datos.motivo ?? "Menos de dos profesionales cualificados."} />;
  }
  const d = datos.distribution;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        {datos.n_qualified} de {datos.n_clinicians} profesionales cualificados (n ≥ 30). Cuartiles: p25 {formatoCorto(d.p25)}, mediana{" "}
        {formatoCorto(d.median)}, p75 {formatoCorto(d.p75)}.
      </p>
      <div className="flex h-24 items-end gap-1">
        {d.bin_counts.map((n, i) => {
          const max = Math.max(1, ...d.bin_counts);
          return (
            <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
              <div className="w-full rounded-t bg-[var(--chart-1)]" style={{ height: `${(n / max) * 100}%` }} title={`${n}`} />
              <span className="text-[10px] text-muted-foreground">{d.bin_edges[i]?.toFixed(1)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Overrides({ projectId }: { projectId: number }) {
  const glosario = useGlosario();
  const entrada = glosario.data?.override;
  // En multiclase un override es una discrepancia entre dos clases cualesquiera.
  const tarea = useTipoTarea(projectId);
  const conDiferencia = tarea.caps?.decisionHumana === "rango";
  const subgrupo = useOverrides(projectId, "subgroup", undefined);
  const fase = useOverrides(projectId, "phase", undefined);
  const clinico = useOverrides(projectId, "clinician", undefined);

  // Una regresión sin rango favorable no tiene overrides; se dice el motivo de la API.
  if (tarea.sinRango) {
    const motivo = subgrupo.data && "motivo" in subgrupo.data ? subgrupo.data.motivo : null;
    return (
      <Card id="overrides" className="scroll-mt-20">
        <CardHeader>
          <CardTitle>Overrides</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState titulo="Sin overrides" descripcion={`${(motivo ?? MOTIVO_SIN_RANGO).replace(/^./, (c) => c.toUpperCase())}. Qué hacer: crea un modelo nuevo con rango favorable.`} />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card id="overrides" className="scroll-mt-20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>Overrides</CardTitle>
          {entrada ? <InfoTooltip titulo={entrada.etiqueta} queMide={entrada.definicion} /> : null}
        </div>
      </CardHeader>
      <CardContent>
        {tarea.caps?.decisionHumana === "clases" ? (
          <p className="mb-3 text-xs text-muted-foreground" data-testid="override-multiclase">
            Un override es una decisión del profesional distinta de la clase que propuso el modelo, aunque las dos
            sean clases no favorables. Una celda con pocas decisiones no enseña tasa.
          </p>
        ) : null}
        {conDiferencia ? (
          <p className="mb-3 text-xs text-muted-foreground" data-testid="override-regresion">
            Un override es una decisión de la persona que cae al otro lado del corte del rango favorable que la cifra
            del modelo. Un cambio de cifra que no cruza el corte no cuenta como override. La diferencia media enseña
            cuánto se aparta la cifra de la persona de la del modelo; es informativa y no abre alertas.
          </p>
        ) : null}
        <Tabs defaultValue="subgroup">
          <div className="max-w-full overflow-x-auto">
            <TabsList>
              <TabsTrigger value="subgroup">Por subgrupo</TabsTrigger>
              <TabsTrigger value="phase">Por fase</TabsTrigger>
              <TabsTrigger value="clinician">Entre profesionales</TabsTrigger>
              <TabsTrigger value="cambios">Cambios de decisión</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="subgroup">
            {subgrupo.data && "groups" in subgrupo.data ? (
              <TablaGrupo
                filas={subgrupo.data.groups}
                minN={subgrupo.data.min_n}
                unidad={subgrupo.data.unidad}
                conDiferencia={conDiferencia}
              />
            ) : null}
          </TabsContent>
          <TabsContent value="phase">
            {fase.data && "groups" in fase.data ? (
              <TablaGrupo
                filas={fase.data.groups}
                minN={fase.data.min_n}
                unidad={fase.data.unidad}
                conDiferencia={conDiferencia}
              />
            ) : null}
          </TabsContent>
          <TabsContent value="clinician">
            {clinico.data && "distribution" in clinico.data ? <DistribucionClinicos datos={clinico.data} /> : null}
          </TabsContent>
          <TabsContent value="cambios">
            <TablaCambios projectId={projectId} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
