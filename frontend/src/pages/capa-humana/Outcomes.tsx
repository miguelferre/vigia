/**
 * Bloque «Outcomes» (`#outcomes`): tabla, serie por
 * `metric_key` y subida de CSV (`period, metric_key, value, source`). El
 * endpoint no exige `ActorBody` (el actor sale de las cabeceras `X-Vigia-*`
 * que ya manda el cliente, `routers/outcomes.py`), igual que `/cross/
 * evaluate`: con `MotivoDialog` de todas formas, por consistencia de
 * confirmación de escritura con el resto de subidas de la app (`datos/
 * index.tsx`, `demo/laboratorio-formulario.tsx`) y con el bloque «Cruzadas»
 * (corrección del corrector: el criterio original dejaba dos bloques con la
 * misma mecánica de backend confirmando de forma distinta).
 */

import { useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, Tooltip as RTooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChartContainer } from "@/components/ui/chart";
import { DataTable, EmptyState, InfoTooltip, MotivoDialog } from "@/components/vigia";
import type { LegacyColumnDef } from "@/components/vigia";
import { api, mensajeDeError } from "@/api/client";
import { useGlosario } from "@/api/queries-contenido";
import { useOutcomes } from "@/api/queries-humana";
import { useCan } from "@/session/session";
import { useQueryClient } from "@tanstack/react-query";
import { EnlaceFormato } from "@/pages/modelos/subida-enlace-formato";
import { TEXTO_OUTCOMES } from "./outcomes-textos";
import type { OutcomeRow } from "@/api/types";
import type { components } from "@/api/schema";

type OutcomeUploadResponse = components["schemas"]["OutcomeUploadResponse"];

export function Outcomes({ projectId }: { projectId: number }) {
  const glosario = useGlosario();
  const entrada = glosario.data?.outcome;
  const [metricElegida, setMetricElegida] = useState<string | undefined>(undefined);
  // Se piden siempre todas las métricas; el filtro por métrica es del
  // cliente, para que el selector conserve todas las opciones tras elegir.
  const outcomes = useOutcomes(projectId, undefined);
  const puedeConfig = useCan("config");
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ficheroPendiente, setFicheroPendiente] = useState<File | null>(null);
  const [abierto, setAbierto] = useState(false);
  const queryClient = useQueryClient();

  const metricas = Object.keys(outcomes.data?.series ?? {});
  const metricKey =
    metricElegida && metricas.includes(metricElegida) ? metricElegida : metricas[0];
  const serie = metricKey ? (outcomes.data?.series[metricKey] ?? []) : [];
  const filas = (outcomes.data?.rows ?? []).filter((r) => !metricKey || r.metric_key === metricKey);

  const columnas: LegacyColumnDef<OutcomeRow, unknown>[] = [
    { id: "periodo", header: "Periodo", cell: ({ row }) => row.original.period },
    { id: "metrica", header: "Métrica", cell: ({ row }) => row.original.metric_key },
    { id: "valor", header: "Valor", cell: ({ row }) => row.original.value ?? "—" },
    { id: "fuente", header: "Fuente", cell: ({ row }) => row.original.source },
  ];

  const subirFichero = async (file: File) => {
    setSubiendo(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.upload<OutcomeUploadResponse>(`/projects/${projectId}/outcomes`, form);
      await queryClient.invalidateQueries({ queryKey: ["humana", projectId, "outcomes"] });
    } catch (err) {
      setError(mensajeDeError(err));
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <Card id="outcomes" className="scroll-mt-20">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle>Outcomes</CardTitle>
            {entrada ? <InfoTooltip titulo={entrada.etiqueta} queMide={entrada.definicion} /> : null}
          </div>
          <div className="flex items-center gap-3">
            <EnlaceFormato />
            {puedeConfig ? (
              <>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      setFicheroPendiente(f);
                      setAbierto(true);
                    }
                  }}
                />
                <Button size="sm" variant="outline" disabled={subiendo} onClick={() => inputRef.current?.click()}>
                  {subiendo ? "Subiendo…" : "Subir CSV"}
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {outcomes.data && outcomes.data.rows.length === 0 ? (
          <EmptyState
            titulo="Sin outcomes"
            descripcion={TEXTO_OUTCOMES.vacio}
          />
        ) : (
          <>
            {metricas.length > 0 ? (
              <Select value={metricKey ?? ""} onValueChange={(v) => setMetricElegida(v || undefined)}>
                <SelectTrigger className="w-52">
                  <SelectValue placeholder="Elegir métrica" />
                </SelectTrigger>
                <SelectContent>
                  {metricas.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            {serie.length > 0 ? (
              <ChartContainer config={{ value: { label: metricKey ?? "", color: "var(--chart-1)" } }} className="h-56">
                <LineChart data={serie}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="period" fontSize={11} />
                  <YAxis fontSize={11} />
                  <RTooltip />
                  <Line type="monotone" dataKey="value" stroke="var(--chart-1)" strokeWidth={2} dot />
                </LineChart>
              </ChartContainer>
            ) : null}
            <DataTable data={filas} columns={columnas} titulo="Outcomes" />
          </>
        )}
      </CardContent>
      <MotivoDialog
        open={abierto}
        onOpenChange={(v) => {
          setAbierto(v);
          if (!v) {
            setFicheroPendiente(null);
            if (inputRef.current) inputRef.current.value = "";
          }
        }}
        titulo="Subir outcomes"
        descripcion={TEXTO_OUTCOMES.subida(ficheroPendiente?.name ?? "el CSV")}
        onConfirm={async () => {
          if (ficheroPendiente) await subirFichero(ficheroPendiente);
          setFicheroPendiente(null);
        }}
      />
    </Card>
  );
}
