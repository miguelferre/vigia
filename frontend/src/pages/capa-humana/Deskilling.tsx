/**
 * Bloque «Deskilling» (`#deskilling`): ventanas, tendencia,
 * señal y resumen del apoyo humano-modelo sobre el diario de uso.
 */

import { useState, type ReactNode } from "react";
import { CartesianGrid, Legend, Line, LineChart, Tooltip as RTooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChartContainer } from "@/components/ui/chart";
import { DataTable, EmptyState, ErrorDeConsulta, InfoTooltip, StateBadge } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { useGlosario } from "@/api/queries-contenido";
import { useDeskilling, useOverrides, useOverridesClinicians } from "@/api/queries-humana";
import type { DeskillingWindow, OverridesByGroupResponse } from "@/api/types";
import { formatoCorto, formatoFecha } from "@/lib/metrics";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { descripcionSinRango } from "./cruzadas-textos";
import { traducirRazon } from "./razones";
import { MOTIVO_SIN_RANGO } from "./registro-uso-decision";

const OPCIONES_N = [2, 4, 6, 8, 12];

// Valor interno del elemento «sin filtro» de los selectores (un `SelectItem`
// no admite la cadena vacía).
const TODOS = "__todos__";

/** Frase que dice sobre qué datos se calcula la tarjeta. */
function textoFiltro(subgroup: string | undefined, clinician: string | undefined): string {
  if (subgroup && clinician) return `el subgrupo «${subgroup}» y el profesional «${clinician}»`;
  if (subgroup) return `el subgrupo «${subgroup}»`;
  if (clinician) return `el profesional «${clinician}»`;
  return "todo el registro, sin filtrar por subgrupo ni profesional";
}

// Pendiente OLS por ventana de `trends`: el resumen del paquete
// (`summary_md`) viene en inglés y no se pinta (regla de idioma de §8.1);
// estas cuatro cifras son las mismas que resume su bloque de tendencias.
const FORMATO_PENDIENTE = new Intl.NumberFormat("es-ES", {
  maximumFractionDigits: 3,
  minimumFractionDigits: 3,
  signDisplay: "always",
});

function pendiente(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "sin dato" : FORMATO_PENDIENTE.format(valor);
}

/** Una ventana con menos de `min_n` decisiones sale atenuada, porque no cuenta para la pendiente. */
function Celda({ excluida, children }: { excluida: boolean; children: ReactNode }) {
  return excluida ? <span className="text-muted-foreground opacity-60">{children}</span> : <>{children}</>;
}

const textoReglaVentanas = (minN: number) =>
  `Las ventanas con menos de ${minN} decisiones no cuentan para la pendiente.`;

export function Deskilling({ projectId }: { projectId: number }) {
  const [nWindows, setNWindows] = useState<number | undefined>(undefined);
  const [subgroup, setSubgroup] = useState<string | undefined>(undefined);
  const [clinician, setClinician] = useState<string | undefined>(undefined);
  const tarea = useTipoTarea(projectId);
  const deskilling = useDeskilling(projectId, { nWindows, subgroup, clinician });
  // Las listas de los selectores salen de los mismos endpoints que el bloque
  // de overrides (`?by=subgroup` y `/overrides/clinicians`).
  const porSubgrupo = useOverrides(projectId, "subgroup", null);
  const subgrupos = ((porSubgrupo.data as OverridesByGroupResponse | undefined)?.groups ?? []).map((g) => g.group);
  const profesionales = useOverridesClinicians(projectId, null).data?.clinicians ?? [];
  const glosario = useGlosario();
  const entrada = glosario.data?.deskilling;
  const datos = deskilling.data;

  // Las ventanas con menos de `min_n` decisiones no aportan punto a la pendiente.
  const ventanasValidas = (datos?.windows ?? []).filter((w) => !w.excluida_de_pendiente).length;
  const excluidas = datos?.ventanas_excluidas ?? 0;
  // Sin ninguna ventana no hay nada que explicar (el caso binario de siempre): la regla sale solo con ventanas.
  const sinPendiente = (datos?.windows.length ?? 0) > 0 && ventanasValidas < 2;

  const columnas: LegacyColumnDef<DeskillingWindow, unknown>[] = [
    {
      id: "periodo",
      header: "Periodo",
      cell: ({ row }) => (
        <Celda excluida={row.original.excluida_de_pendiente}>
          {`${formatoFecha(row.original.start)} – ${formatoFecha(row.original.end)}`}
        </Celda>
      ),
    },
    { id: "n", header: "n", cell: ({ row }) => <Celda excluida={row.original.excluida_de_pendiente}>{row.original.n}</Celda> },
    {
      id: "apoyo",
      header: "Apoyo (acuerdo)",
      cell: ({ row }) => <Celda excluida={row.original.excluida_de_pendiente}>{formatoCorto(row.original.agreement_rate)}</Celda>,
    },
    {
      id: "acierto_humano",
      header: "Acierto humano",
      cell: ({ row }) => <Celda excluida={row.original.excluida_de_pendiente}>{formatoCorto(row.original.human_accuracy)}</Celda>,
    },
    {
      id: "acierto_modelo",
      header: "Acierto del modelo",
      cell: ({ row }) => <Celda excluida={row.original.excluida_de_pendiente}>{formatoCorto(row.original.model_accuracy)}</Celda>,
    },
    {
      id: "rescate",
      header: "Tasa de rescate",
      cell: ({ row }) => <Celda excluida={row.original.excluida_de_pendiente}>{formatoCorto(row.original.rescue_rate)}</Celda>,
    },
    // Solo con alguna ventana excluida: sin ellas, la tabla es la de siempre.
    ...(excluidas > 0
      ? ([
          {
            id: "pendiente",
            header: "En la pendiente",
            cell: ({ row }) =>
              row.original.excluida_de_pendiente ? (
                <span className="text-xs text-muted-foreground" data-testid="ventana-excluida">
                  Excluida: menos de {datos?.min_n ?? "el mínimo de"} decisiones
                </span>
              ) : (
                <span className="text-xs">Cuenta</span>
              ),
          },
        ] satisfies LegacyColumnDef<DeskillingWindow, unknown>[])
      : []),
  ];

  const serie = (datos?.windows ?? []).map((w) => ({
    periodo: formatoFecha(w.start),
    // Una ventana excluida no se dibuja: su punto no cuenta para la pendiente.
    apoyo: w.excluida_de_pendiente ? null : w.agreement_rate,
    rescate: w.excluida_de_pendiente ? null : w.rescue_rate,
  }));

  return (
    <Card id="deskilling" className="scroll-mt-20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>Deskilling</CardTitle>
          {entrada ? <InfoTooltip titulo={entrada.etiqueta} queMide={entrada.definicion} /> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Ventanas</span>
          <Select
            value={nWindows ? String(nWindows) : ""}
            onValueChange={(v) => setNWindows(v ? Number(v) : undefined)}
          >
            <SelectTrigger className="w-32" aria-label="Ventanas">
              <SelectValue placeholder="Automático" />
            </SelectTrigger>
            <SelectContent>
              {OPCIONES_N.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
          <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Subgrupo</span>
          <Select value={subgroup ?? TODOS} onValueChange={(v) => setSubgroup(v === TODOS ? undefined : v)}>
            <SelectTrigger className="w-40" aria-label="Subgrupo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todos</SelectItem>
              {subgrupos.map((g) => (
                <SelectItem key={g} value={g}>
                  {g}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
          <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Profesional</span>
          <Select value={clinician ?? TODOS} onValueChange={(v) => setClinician(v === TODOS ? undefined : v)}>
            <SelectTrigger className="w-40" aria-label="Profesional">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todos</SelectItem>
              {profesionales.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        </div>
        <p className="pt-1 text-xs text-muted-foreground" data-testid="deskilling-filtro">
          Calculado sobre {textoFiltro(subgroup, clinician)}.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {deskilling.isLoading ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : deskilling.isError ? (
          <ErrorDeConsulta
            que="el deskilling con este filtro"
            error={deskilling.error}
            onReintentar={() => void deskilling.refetch()}
          />
        ) : datos?.sin_datos ? (
          <EmptyState
            titulo="Sin datos de deskilling"
            descripcion={
              tarea.sinRango
                ? descripcionSinRango(datos.motivo ?? MOTIVO_SIN_RANGO)
                : (datos.motivo ?? "Sin diario de uso para esta versión.")
            }
          />
        ) : datos ? (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <StateBadge
                estado={datos.signal?.fired ? "alerta" : "ok"}
                texto={datos.signal?.fired ? "Señal de deskilling" : "Sin señal"}
              />
              {datos.signal ? (
                <span className="text-sm text-muted-foreground">{traducirRazon(datos.signal.reason)}</span>
              ) : null}
            </div>
            {serie.length > 0 ? (
              <ChartContainer config={{ apoyo: { label: "Apoyo", color: "var(--chart-1)" }, rescate: { label: "Rescate", color: "var(--chart-3)" } }} className="h-64">
                <LineChart data={serie}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="periodo" fontSize={11} />
                  <YAxis fontSize={11} />
                  <RTooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="apoyo" name="Apoyo" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="rescate" name="Rescate" stroke="var(--chart-3)" strokeWidth={2} dot={false} />
                </LineChart>
              </ChartContainer>
            ) : null}
            <DataTable data={datos.windows} columns={columnas} titulo="Ventanas de deskilling" />
            {excluidas > 0 || sinPendiente ? (
              <div className="flex flex-col gap-1 rounded-md border border-border bg-muted/30 p-3 text-sm" data-testid="deskilling-excluidas">
                <p>
                  {textoReglaVentanas(datos.min_n)}
                  {excluidas > 0
                    ? ` ${excluidas === 1 ? "Hay 1 ventana excluida" : `Hay ${excluidas} ventanas excluidas`}, atenuadas en la tabla.`
                    : ""}
                </p>
                {sinPendiente ? (
                  <p className="font-medium" data-testid="deskilling-sin-pendiente">
                    No hay pendiente: hacen falta al menos 2 ventanas con {datos.min_n} decisiones o más y aquí hay{" "}
                    {ventanasValidas}. Prueba con menos ventanas, o quita el filtro de subgrupo o de profesional.
                  </p>
                ) : null}
              </div>
            ) : null}
            {datos.trends ? (
              <div className="flex flex-col gap-1 text-sm text-muted-foreground">
                {!sinPendiente ? (
                  <p>
                    Tendencia por ventana: apoyo {pendiente(datos.trends.agreement_slope)}, acierto del
                    profesional {pendiente(datos.trends.human_accuracy_slope)}, acierto del modelo{" "}
                    {pendiente(datos.trends.model_accuracy_slope)}, tasa de rescate{" "}
                    {pendiente(datos.trends.rescue_slope)}. Hay convergencia cuando el apoyo sube.
                  </p>
                ) : null}
                <p>
                  Telemetría agregada, sin datos personales. Complementa lo que cuenta quien usa el
                  modelo, no lo sustituye: la señal es algo que investigar, no una conclusión.
                </p>
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
