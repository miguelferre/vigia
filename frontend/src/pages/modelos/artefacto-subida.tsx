/**
 * Diálogo de subida del artefacto del modelo de una versión:
 * ONNX por defecto; pickle o joblib solo con la casilla
 * explícita de confirmación y su aviso. Límite de 200 MB avisado antes de
 * subir; el 409/422 del backend (ya en español, con el motivo) se enseña
 * tal cual. Sin `MotivoDialog`: la ruta no exige actor ni motivo
 * (`Body_upload_artifact_api_model_versions__version_id__artifact_post`).
 */

import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { mensajeDeError } from "@/api/client";
import { useSubirArtefacto } from "@/api/queries-artefacto";
import type { Batch, ModelVersion } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ErrorPasoSubida } from "./subida-error-paso";
import { SUBIR_MODELO_IR_A_DATOS, SUBIR_MODELO_SIN_LINEA_BASE } from "./versiones-textos";

const LIMITE_MB = 200;
const AVISO_PICKLE = "un fichero pickle ejecuta código al abrirse: súbelo solo si lo has generado tú";

interface Props {
  /** Versión a la que se sube el modelo, o `null` con el diálogo cerrado. */
  version: ModelVersion | null;
  onOpenChange: (open: boolean) => void;
  /** Lotes del proyecto: con ellos el diálogo sabe si la versión aún no tiene línea base. */
  lotes?: readonly Batch[];
}

/**
 * El modelo se valida contra el mapeo de un lote de la propia versión.
 * Sin ningún lote ni línea base fijada la subida falla seguro, así que se avisa antes.
 */
function faltaLineaBase(version: ModelVersion | null, lotes: readonly Batch[] | undefined): boolean {
  if (version === null || lotes === undefined) return false;
  if (version.baseline_batch_id !== null) return false;
  return !lotes.some((l) => l.model_version_id === version.id);
}

export function ArtefactoSubidaDialog({ version, onOpenChange, lotes }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<"onnx" | "pickle">("onnx");
  const [confirmado, setConfirmado] = useState(false);
  const subir = useSubirArtefacto();
  const navigate = useNavigate();
  // El error de la subida se queda en el diálogo: hasta cambiar de
  // fichero, cerrarlo (`reset`) o repetir la subida, no solo en un aviso efímero.
  const errorSubida = subir.isError ? mensajeDeError(subir.error) : null;
  const sinLineaBase = faltaLineaBase(version, lotes);

  const cerrar = () => {
    onOpenChange(false);
    setFile(null);
    setKind("onnx");
    setConfirmado(false);
    subir.reset();
  };

  const enviar = () => {
    if (version?.id === null || version?.id === undefined || !file) return;
    subir.mutate(
      {
        versionId: version.id,
        file,
        artifactKind: kind,
        confirmacionPickle: kind === "pickle" && confirmado,
      },
      {
        onSuccess: (resp) => {
          toast.success("Modelo subido y validado");
          for (const aviso of resp.avisos ?? []) toast.warning(aviso);
          cerrar();
        },
        // Sin aviso emergente: el texto entero se queda en el diálogo (`errorSubida`).
      },
    );
  };

  const irADatos = () => {
    cerrar();
    navigate({ hash: "#datos" });
  };

  const demasiadoGrande = file !== null && file.size > LIMITE_MB * 1024 * 1024;
  const puedeEnviar = file !== null && !demasiadoGrande && (kind === "onnx" || confirmado) && !subir.isPending;

  return (
    <Dialog open={version !== null} onOpenChange={(o) => !o && cerrar()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Subir el modelo de «{version?.label ?? ""}»</DialogTitle>
          <DialogDescription>
            ONNX es el formato recomendado. Límite de {LIMITE_MB} MB por fichero.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="artefacto-kind">Formato</Label>
            <Select
              value={kind}
              onValueChange={(v) => {
                setKind(v as "onnx" | "pickle");
                setConfirmado(false);
              }}
            >
              <SelectTrigger id="artefacto-kind" className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="onnx">ONNX (recomendado)</SelectItem>
                <SelectItem value="pickle">Pickle o joblib</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="artefacto-file">Fichero del modelo</Label>
            <Input
              id="artefacto-file"
              type="file"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                subir.reset();
              }}
            />
            {demasiadoGrande ? (
              <p className="text-xs" style={{ color: "var(--state-alert)" }} role="alert">
                El fichero supera los {LIMITE_MB} MB: el backend lo rechazará.
              </p>
            ) : null}
          </div>
          {kind === "pickle" ? (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={confirmado}
                onChange={(e) => setConfirmado(e.target.checked)}
              />
              <span>{AVISO_PICKLE.charAt(0).toUpperCase() + AVISO_PICKLE.slice(1)}.</span>
            </label>
          ) : null}
          {sinLineaBase ? (
            <Alert data-testid="aviso-subir-sin-linea-base">
              <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
                <span>{SUBIR_MODELO_SIN_LINEA_BASE}</span>
                <Button type="button" size="sm" variant="outline" onClick={irADatos}>
                  {SUBIR_MODELO_IR_A_DATOS}
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
          <ErrorPasoSubida error={errorSubida} onCerrar={() => subir.reset()} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={cerrar} disabled={subir.isPending}>
            Cancelar
          </Button>
          <Button onClick={enviar} disabled={!puedeEnviar}>
            {subir.isPending ? "Subiendo…" : "Subir"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ArtefactoSubidaDialog;
