/**
 * Paso «subir» del asistente (`subida-dataset.tsx`): fichero, tipo, fase y
 * nombre. Aparte para no superar 9 KB con la lógica de la precarga de la
 * demo (`subida-dataset-demo.ts`).
 */

import type { RefObject } from "react";

import type { DatasetKind } from "@/api/types";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SubidaAyudaPanel } from "./subida-ayuda";
import { ErrorPasoSubida } from "./subida-error-paso";
import { ETIQUETA_KIND, ETIQUETA_ROLE } from "./etiquetas";
import { ACEPTA_SUBIDA } from "./subida-textos";

interface Props {
  inputFileRef: RefObject<HTMLInputElement | null>;
  onFile: (file: File | null) => void;
  kind: DatasetKind;
  onKind: (kind: DatasetKind) => void;
  role: string;
  onRole: (role: string) => void;
  name: string;
  onName: (name: string) => void;
  file: File | null;
  subiendo: boolean;
  precargaDemo: boolean;
  /** Nombre del fichero que descargó la precarga, o `null` sin precarga o sin llegar aún. */
  nombreEsperadoDemo?: string | null;
  onSubir: () => void;
  /** Error de la última subida, fijo hasta que se cierre o se cambie de fichero. */
  error?: string | null;
  onCerrarError?: () => void;
}

export function SubidaPasoFichero({
  inputFileRef,
  onFile,
  kind,
  onKind,
  role,
  onRole,
  name,
  onName,
  file,
  subiendo,
  precargaDemo,
  nombreEsperadoDemo = null,
  onSubir,
  error = null,
  onCerrarError = () => undefined,
}: Props) {
  // La demo espera justo el fichero que precargó; si el usuario
  // lo sustituye por otro (mismo input, otro nombre), avisar en vez de
  // dejarlo pasar en silencio.
  const ficheroCambiado = precargaDemo && nombreEsperadoDemo !== null && file !== null && file.name !== nombreEsperadoDemo;
  return (
    <div className="flex flex-col gap-3">
      <SubidaAyudaPanel />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ds-file">Fichero</Label>
        <Input
          id="ds-file"
          type="file"
          accept={ACEPTA_SUBIDA}
          ref={inputFileRef}
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
        {precargaDemo && !ficheroCambiado ? (
          <p className="text-xs text-muted-foreground">
            Fichero de la demo cargado: confirma tipo y fase y pulsa Subir.
          </p>
        ) : null}
        {ficheroCambiado ? (
          <p className="text-xs" style={{ color: "var(--state-alert)" }} role="alert">
            Este no es el fichero de la demo ({nombreEsperadoDemo}); si no es intencionado, vuelve a
            elegirlo.
          </p>
        ) : null}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-kind">Tipo</Label>
          <Select value={kind} onValueChange={(v) => onKind(v as DatasetKind)}>
            <SelectTrigger id="ds-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(ETIQUETA_KIND) as DatasetKind[]).map((k) => (
                <SelectItem key={k} value={k}>
                  {ETIQUETA_KIND[k]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-role">Fase</Label>
          <Select value={role} onValueChange={onRole}>
            <SelectTrigger id="ds-role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="baseline">{ETIQUETA_ROLE.baseline}</SelectItem>
              <SelectItem value="production">{ETIQUETA_ROLE.production}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ds-name">Nombre (opcional)</Label>
        <Input id="ds-name" value={name} onChange={(e) => onName(e.target.value)} />
      </div>
      <ErrorPasoSubida error={error} onCerrar={onCerrarError} />
      <DialogFooter>
        <Button onClick={onSubir} disabled={!file || subiendo}>
          Subir
        </Button>
      </DialogFooter>
    </div>
  );
}
