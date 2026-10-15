/**
 * Bloque «Cruzadas» (`#cruzadas`): CX-1 a CX-6 en una
 * rejilla de tarjetas con su nombre, modo de calibración y botón «Evaluar ahora». Destino
 * de la tarjeta de cruzadas del cuadro (`TarjetasMonitor.tsx`).
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, InfoTooltip, MotivoDialog, StateBadge } from "@/components/vigia";
import { useGlosario } from "@/api/queries-contenido";
import { useCrossLatest } from "@/api/queries-humana";
import { api, ApiError, mensajeDeError } from "@/api/client";
import { useCan } from "@/session/session";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { useJob } from "@/realtime/useJob";
import { formatoFecha, formatoNumero, metricLabel } from "@/lib/metrics";
import type { CrossRule, EstadoMotor, JobAccepted } from "@/api/types";
import {
  AVISO_PRIMERA_CRUZADA,
  AVISO_YA_CALIBRADA,
  DESCRIPCION_CALIBRACION_CRUZADAS,
  DESCRIPCION_EVALUAR_CRUZADAS,
  descripcionSinCruzadas,
  TITULO_CALIBRACION_CRUZADAS,
} from "./cruzadas-textos";
import { ayudaCruzada, CLAVE_HUMAN_REVIEW_ZERO, textoGrupo, textoValor } from "./cruzadas-nombres";

// Las reglas cruzadas se leen por su nombre (`cruzadas-nombres.ts`); el código
// CX-n queda en el `title`. `human_review_zero` es una tarjeta más:
// su valor es una tasa, no una desviación.
function TarjetaRegla({ regla }: { regla: CrossRule }) {
  const esCero = regla.rule === CLAVE_HUMAN_REVIEW_ZERO;
  const ayuda = ayudaCruzada(regla.rule);
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold" title={regla.rule}>
          {metricLabel(regla.rule)}
        </span>
        <StateBadge estado={regla.state as EstadoMotor} size="sm" />
      </div>
      {esCero || !ayuda ? null : <p className="text-xs text-muted-foreground">{ayuda}</p>}
      {regla.group ? <p className="text-xs text-muted-foreground">{textoGrupo(regla.group)}</p> : null}
      {esCero ? <DetalleCero regla={regla} /> : null}
      {!esCero && regla.value !== null ? <p className="text-xs">{textoValor(regla.rule, regla.value, regla.supera_umbral, regla.state)}</p> : null}
    </div>
  );
}

/**
 * Detalle de `human_review_zero`: la tasa de override de la
 * ventana de vigilancia por debajo del 1 % con `n` suficiente. Nunca abre
 * `Alert` (mismo patrón que CX-3). La API trae `motivo` (la frase de
 * la señal) y `n` (las decisiones de la ventana); el `value` es la tasa de
 * corrección, no un `z`.
 */
function DetalleCero({ regla }: { regla: CrossRule }) {
  return (
    <>
      {regla.motivo ? (
        <p className="text-xs" data-testid="human-review-zero-motivo">
          {regla.motivo}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">{ayudaCruzada(CLAVE_HUMAN_REVIEW_ZERO)}</p>
      )}
      {regla.n !== null && !regla.motivo ? <p className="text-xs">Decisiones en la ventana: {regla.n}</p> : null}
      {regla.value !== null ? <p className="text-xs">Tasa de corrección: {formatoNumero(regla.value * 100, 1)} %</p> : null}
    </>
  );
}

export function Cruzadas({ projectId }: { projectId: number }) {
  const glosario = useGlosario();
  const entrada = glosario.data?.calibracion_cruzadas;
  const latest = useCrossLatest(projectId);
  const puedeConfig = useCan("config");
  // Una regresión sin rango favorable no tiene capa humana: no se ofrece evaluar.
  const tarea = useTipoTarea(projectId);
  const puedeEvaluar = puedeConfig && !tarea.sinRango;
  const [abierto, setAbierto] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const job = useJob(jobId);
  const queryClient = useQueryClient();

  // El job de `/cross/evaluate` solo invalida ["jobs"] (`realtime/useJob.ts`);
  // sin esto la rejilla se queda con la evaluación anterior tras «Evaluar
  // ahora» aunque el job termine bien (hallazgo del corrector, codigo).
  useEffect(() => {
    if (job.terminado) {
      void queryClient.invalidateQueries({ queryKey: ["humana", projectId, "cross-latest"] });
    }
  }, [job.terminado, projectId, queryClient]);

  const evaluar = async () => {
    const resultado = await api.post<JobAccepted>(`/projects/${projectId}/cross/evaluate`);
    setJobId(resultado.id);
  };

  // Se avisa antes de pulsar mientras no haya una evaluación de vigilancia con reglas.
  const sinReglas = !latest.isLoading && !(latest.data?.mode === "vigilancia" && latest.data.rules.length > 0);

  return (
    <Card id="cruzadas" className="scroll-mt-20">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle>Cruzadas</CardTitle>
            {entrada ? <InfoTooltip titulo={entrada.etiqueta} queMide={entrada.definicion} /> : null}
          </div>
          {puedeEvaluar ? (
            <Button size="sm" variant="outline" onClick={() => setAbierto(true)} disabled={job.status !== null && !job.terminado}>
              Evaluar ahora
            </Button>
          ) : null}
        </div>
        {puedeEvaluar && sinReglas ? (
          <p className="text-xs text-muted-foreground" data-testid="aviso-primera-cruzada">
            {latest.data?.mode === "calibracion" ? AVISO_YA_CALIBRADA : AVISO_PRIMERA_CRUZADA}
          </p>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {latest.isLoading ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : (latest.error instanceof ApiError && latest.error.status === 404) ||
          latest.data?.estado === "sin_datos" ? (
          // Un proyecto sin diario de uso subido todavía
          // (`human_layer.cross_latest`) responde 200 con `estado: "sin_datos"`
          // (antes 404, que se conserva por si el backend es anterior);
          // mismo patrón que el 409 de `useThresholdsProposal`
          // (`queries-alta.ts`). Sin botón «Reintentar»: reintentar no
          // cambia nada hasta que se suba un diario de uso.
          <EmptyState
            titulo="Sin evaluación del monitor cruzado"
            descripcion={descripcionSinCruzadas(latest.data?.motivo)}
          />
        ) : latest.isError || !latest.data ? (
          <EmptyState
            titulo="No se pudo cargar el monitor cruzado"
            descripcion={mensajeDeError(latest.error)}
            accion={
              <Button size="sm" variant="outline" onClick={() => latest.refetch()}>
                Reintentar
              </Button>
            }
          />
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Modo: {latest.data.mode === "calibracion" ? "calibración" : "vigilancia"} · Última evaluación:{" "}
              {formatoFecha(latest.data.evaluated_at)}
              {latest.data.calibration_until ? ` · Referencia hasta ${formatoFecha(latest.data.calibration_until)}` : ""}
            </p>
            {latest.data.rules.length === 0 ? (
              // Una evaluación en modo calibración no trae reglas: la primera
              // corrida de cada versión del modelo fija la referencia
              // (la demo cambia de versión en el lote #9) y las reglas se
              // calculan en la siguiente. Sin este aviso el hueco entre la
              // cabecera y el botón parece un error, sobre todo llegando
              // desde la tarjeta del cuadro (hallazgo del recorrido).
              <EmptyState
                titulo={
                  latest.data.mode === "calibracion"
                    ? TITULO_CALIBRACION_CRUZADAS
                    : "Sin reglas calculadas en esta evaluación"
                }
                descripcion={
                  latest.data.mode === "calibracion"
                    ? DESCRIPCION_CALIBRACION_CRUZADAS
                    : "La evaluación más reciente no trae medidas de las reglas cruzadas. Evalúa ahora para tener datos."
                }
              />
            ) : (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {latest.data.rules.map((r, i) => (
                  <TarjetaRegla key={`${r.rule}-${r.group ?? i}`} regla={r} />
                ))}
              </div>
            )}
          </>
        )}
        {job.status && !job.terminado ? <p className="text-xs text-muted-foreground">Evaluando… {job.message}</p> : null}
      </CardContent>
      <MotivoDialog
        open={abierto}
        onOpenChange={setAbierto}
        titulo="Evaluar el monitor cruzado"
        descripcion={DESCRIPCION_EVALUAR_CRUZADAS}
        onConfirm={async () => {
          await evaluar();
        }}
      />
    </Card>
  );
}
