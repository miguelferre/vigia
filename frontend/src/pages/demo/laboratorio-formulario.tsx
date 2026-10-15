/**
 * Formulario del laboratorio: elige la fase base (etiquetas de
 * `fases` del contenido) y mueve sus parámetros de generación, con actor y
 * motivo obligatorios (`MotivoDialog`, como toda mutación con `ActorBody`).
 * Lanza `POST /demo/runs/{id}/lab`, sigue el job con `useJob` y, al terminar,
 * entrega el resultado al contenedor (`onResultado`); nunca toca
 * `current_phase` ni `status` del guion.
 */

import { useState } from "react";

import { mensajeDeError } from "@/api/client";
import type { ContenidoDemo } from "@/api/queries-contenido";
import { useLaboratorio } from "@/api/queries-demo";
import type { ActorBody, JobResumen } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MotivoDialog } from "@/components/vigia";

import { evaluarCampo, parseEnteroOpcional } from "./laboratorio-campo";
import { CampoNumero } from "./laboratorio-campo-numero";
import { useEnsayoLaboratorio, type PendienteLab } from "./laboratorio-job";
import { parametrosDeFase, type DefinicionParametro, type ResultadoLab } from "./laboratorio-parametros";
import type { FaseGuion } from "./tipos";

/** Fase que abre el laboratorio: la de casos nuevos, que es donde está el sesgo. */
const FASE_POR_DEFECTO = "e1_evento";

export interface FormularioLaboratorioProps {
  runId: number;
  fases: FaseGuion[];
  contenido: ContenidoDemo;
  onResultado: (r: ResultadoLab) => void;
}

/** Valor por defecto tal como se escribe aquí: coma decimal (el campo la acepta). */
function textoPorDefecto(p: DefinicionParametro): string {
  return String(p.porDefecto).replace(".", ",");
}

function textosPorDefecto(definiciones: DefinicionParametro[]): Record<string, string> {
  return Object.fromEntries(definiciones.map((p) => [p.clave, textoPorDefecto(p)]));
}

export function FormularioLaboratorio({ runId, fases, contenido, onResultado }: FormularioLaboratorioProps) {
  const parametrosContenido = contenido.laboratorio.parametros;
  const fasesConLab = fases.filter((f) => parametrosDeFase(parametrosContenido, f).length > 0);
  const etiquetaFase = (f: FaseGuion) => contenido.fases[f.key]?.etiqueta ?? f.title;

  const [faseKey, setFaseKey] = useState(
    fasesConLab.find((f) => f.key === FASE_POR_DEFECTO)?.key ?? fasesConLab[0]?.key ?? "",
  );
  const faseActual = fases.find((f) => f.key === faseKey) ?? null;
  const definiciones = parametrosDeFase(parametrosContenido, faseActual);
  const [textos, setTextos] = useState<Record<string, string>>(() => textosPorDefecto(definiciones));
  const [semilla, setSemilla] = useState("");
  const [motivoAbierto, setMotivoAbierto] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const [pendiente, setPendiente] = useState<PendienteLab | null>(null);

  const laboratorio = useLaboratorio();
  const job = useEnsayoLaboratorio(jobId, pendiente, onResultado);

  // Cambiar de fase reinicia sus parámetros a los valores por defecto de esa
  // fase (estado derivado en el render, patrón del repo).
  const [faseVista, setFaseVista] = useState(faseKey);
  if (faseKey !== faseVista) {
    setFaseVista(faseKey);
    setTextos(textosPorDefecto(definiciones));
  }

  // Cada campo se evalúa por separado: el texto se guarda tal cual lo escribe
  // quien opera y aquí se interpreta, con coma o punto como decimal. Lo que
  // no se entiende o cae fuera de rango bloquea el botón con un mensaje.
  const evaluaciones = definiciones.map((p) => ({ p, ...evaluarCampo(p, textos[p.clave] ?? "") }));
  const semillaEval = parseEnteroOpcional(semilla);
  const hayErrores = evaluaciones.some((e) => e.error !== null) || semillaEval.error !== null;
  const enCurso = laboratorio.isPending || (jobId !== null && !job.terminado);

  const confirmar = async (cuerpo: ActorBody) => {
    if (hayErrores || !faseActual) return;
    const params = Object.fromEntries(evaluaciones.map((e) => [e.p.clave, e.valor as number]));
    setPendiente({ faseKey, faseTitulo: etiquetaFase(faseActual), expected: faseActual.expected, params });
    const res: JobResumen = await laboratorio.mutateAsync({
      runId,
      body: { phase_key: faseKey, params, seed: semillaEval.valor, actor: cuerpo.actor, role: cuerpo.role, motivo: cuerpo.motivo },
    });
    setJobId(res.id);
  };

  if (fasesConLab.length === 0) {
    return <p className="text-sm text-muted-foreground">Ninguna fase de este guion tiene parámetros de laboratorio.</p>;
  }

  return (
    <>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="lab-fase">Fase base</Label>
          <Select value={faseKey} onValueChange={setFaseKey}>
            <SelectTrigger id="lab-fase" className="w-72">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {fasesConLab.map((f) => (
                <SelectItem key={f.key} value={f.key}>
                  {etiquetaFase(f)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {faseActual ? (
            <p className="text-xs text-muted-foreground">{contenido.fases[faseActual.key]?.descripcion}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-end gap-4">
          {evaluaciones.map(({ p, error }) => (
            <CampoNumero
              key={p.clave}
              definicion={p}
              texto={textos[p.clave] ?? textoPorDefecto(p)}
              error={error}
              onChange={(texto) => setTextos((prev) => ({ ...prev, [p.clave]: texto }))}
            />
          ))}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="lab-seed">Semilla (opcional)</Label>
            <Input
              id="lab-seed"
              type="text"
              inputMode="numeric"
              className="w-28"
              placeholder="aleatoria"
              value={semilla}
              aria-invalid={semillaEval.error !== null}
              onChange={(e) => setSemilla(e.target.value)}
            />
            {semillaEval.error ? (
              <p className="text-xs text-destructive" role="alert">
                {semillaEval.error}
              </p>
            ) : null}
          </div>
          <Button type="button" onClick={() => setMotivoAbierto(true)} disabled={enCurso || hayErrores}>
            Ejecutar en el laboratorio
          </Button>
        </div>

        {jobId !== null && !job.terminado ? (
          <div className="flex items-center gap-3">
            <Progress value={job.progress * 100} className="w-56" />
            <span className="text-sm text-muted-foreground">{job.message || "Generando y evaluando…"}</span>
          </div>
        ) : null}
        {laboratorio.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {mensajeDeError(laboratorio.error)}
          </p>
        ) : null}
      </div>

      <MotivoDialog
        open={motivoAbierto}
        onOpenChange={setMotivoAbierto}
        titulo="Ejecutar ensayo de laboratorio"
        descripcion="No avanza el caso: es un ensayo aparte, con su propio evento en el diario."
        etiquetaConfirmar="Ejecutar"
        onConfirm={confirmar}
      />
    </>
  );
}
