/** Paso «Ingerir» del asistente de subida: formulario del `IngestBody`. */

import { useState } from "react";

import type { IngestBody, ModelVersion } from "@/api/types";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { VistaPreviaIngesta } from "./ingesta-vista-previa";
import { Ayuda } from "./mapeo-controles";
import { ErrorPasoSubida } from "./subida-error-paso";
import { AYUDA_INGESTA } from "./subida-textos";

interface Props {
  versiones: ModelVersion[];
  preview: unknown;
  onIngerir: (cuerpo: IngestBody) => void | Promise<void>;
  /**
   * Con la subida precargada de la demo (`?demo=subir`), la casilla
   * «Evaluar al ingerir» no se muestra: el atado de la reproducción
   * congela la línea base y la evalúa al terminar; si se evaluara antes, la
   * deriva quedaría sin datos con los que compararse.
   */
  ocultarEvaluar?: boolean;
  /**
   * Con la misma precarga, el atado de la demo sustituye
   * `phase_label` por `b1` sin más (`demo_player.py`, al fijar la línea
   * base); lo que se escriba aquí se ignora en silencio. Se oculta para no
   * sugerir que el valor tecleado vaya a ningún sitio.
   */
  ocultarEtiqueta?: boolean;
  /**
   * La línea base no se evalúa al ingerirla (el servidor lo ignora
   * aunque se pida): se evalúa al confirmar el paso «Umbrales», con los
   * umbrales ya elegidos. No se ofrece la casilla y se explica por qué.
   */
  esLineaBase?: boolean;
  /** Error de la última ingesta, fijo hasta que se cierre. */
  error?: string | null;
  onCerrarError?: () => void;
}

export default function IngestaDatasetForm({
  versiones,
  preview,
  onIngerir,
  ocultarEvaluar = false,
  ocultarEtiqueta = false,
  esLineaBase = false,
  error = null,
  onCerrarError = () => undefined,
}: Props) {
  const [modelVersionId, setModelVersionId] = useState("");
  const [phaseLabel, setPhaseLabel] = useState("");
  const [ordenManipulado, setOrdenManipulado] = useState(false);
  const [motivoManipulacion, setMotivoManipulacion] = useState("");
  const sinEvaluar = ocultarEvaluar || esLineaBase;
  const [evaluate, setEvaluate] = useState(!sinEvaluar);

  const puedeIngerir = !ordenManipulado || motivoManipulacion.trim().length > 0;

  const ingerir = () => {
    if (!puedeIngerir) return;
    void onIngerir({
      model_version_id: modelVersionId ? Number(modelVersionId) : null,
      phase_label: phaseLabel.trim() || null,
      orden_manipulado: ordenManipulado,
      motivo_manipulacion: ordenManipulado ? motivoManipulacion.trim() : null,
      evaluate: sinEvaluar ? false : evaluate,
    });
  };

  return (
    <div className="flex min-w-0 max-w-full flex-col gap-3">
      <VistaPreviaIngesta preview={preview} />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ds-version">Versión de modelo</Label>
        <Select value={modelVersionId} onValueChange={setModelVersionId}>
          <SelectTrigger id="ds-version" aria-describedby="ds-version-ayuda">
            <SelectValue placeholder="Automática" />
          </SelectTrigger>
          <SelectContent>
            {versiones.map((v) => (
              <SelectItem key={v.id} value={String(v.id)}>
                {v.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Ayuda id="ds-version-ayuda">{AYUDA_INGESTA.version}</Ayuda>
      </div>
      {ocultarEtiqueta ? null : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-phase">Etiqueta del lote (opcional)</Label>
          <Input id="ds-phase" value={phaseLabel} aria-describedby="ds-phase-ayuda" onChange={(e) => setPhaseLabel(e.target.value)} />
          <Ayuda id="ds-phase-ayuda">{AYUDA_INGESTA.etiquetaLote}</Ayuda>
        </div>
      )}
      <div className="flex flex-col gap-1">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={ordenManipulado}
            aria-describedby="ds-orden-ayuda"
            onChange={(e) => setOrdenManipulado(e.target.checked)}
          />
          El orden de las filas está manipulado
        </label>
        <Ayuda id="ds-orden-ayuda">{AYUDA_INGESTA.ordenManipulado}</Ayuda>
      </div>
      {ordenManipulado ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-motivo-orden">Motivo de la manipulación</Label>
          <Input
            id="ds-motivo-orden"
            value={motivoManipulacion}
            onChange={(e) => setMotivoManipulacion(e.target.value)}
          />
        </div>
      ) : null}
      {ocultarEvaluar ? (
        <p className="text-xs text-muted-foreground">
          La demo fija y evalúa la línea base al terminar; este lote no se evalúa ahora.
        </p>
      ) : esLineaBase ? (
        <p className="text-xs text-muted-foreground" data-testid="linea-base-sin-evaluar">
          La línea base no se evalúa al ingerirla: se evaluará con los umbrales cuando confirmes el
          paso «Umbrales» del alta.
        </p>
      ) : (
        <div className="flex flex-col gap-1">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={evaluate}
              aria-describedby="ds-evaluar-ayuda"
              onChange={(e) => setEvaluate(e.target.checked)}
            />
            Evaluar al ingerir
          </label>
          <Ayuda id="ds-evaluar-ayuda">{AYUDA_INGESTA.evaluarAlIngerir}</Ayuda>
        </div>
      )}
      <ErrorPasoSubida error={error} onCerrar={onCerrarError} />
      <DialogFooter>
        <Button onClick={ingerir} disabled={!puedeIngerir}>
          Ingerir
        </Button>
      </DialogFooter>
    </div>
  );
}
