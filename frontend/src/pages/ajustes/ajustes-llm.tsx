/**
 * Bloque «Backend LLM» de `/ajustes`: apagado por
 * defecto; activar `anthropic` desde otro backend exige la confirmación
 * antes de guardar. Solo `ajustes_avanzados` (gestor); los demás roles
 * ven una línea informativa (montada por `index.tsx`, no aquí).
 */

import { useState } from "react";

import { AlertTriangleIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { InfoTooltip, MotivoDialog } from "@/components/vigia";
import type { ActorBody, SettingsLlm } from "@/api/types";
import { CONFIRMACION_NO_LOCAL, ETIQUETA_BACKEND_LLM, GLOSARIO_FALLBACK } from "./ajustes-datos";

export interface AjustesLlmProps {
  llm: SettingsLlm;
  glosarioBackendLlm?: { etiqueta: string; definicion: string };
  onGuardar: (
    llm: SettingsLlm & { confirmacion_no_local?: string; confirmar_remoto?: boolean },
    cuerpo: ActorBody,
  ) => Promise<unknown>;
}

/** Host de una URL base, o `null` si está vacía o no es una URL. */
function hostDe(url: string): string | null {
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

/** `true` si la URL apunta a este equipo (o está vacía: Ollama usa el local). */
function esLocal(url: string): boolean {
  if (!url.trim()) return true;
  const host = hostDe(url.trim());
  return host === "127.0.0.1" || host === "localhost" || host === "[::1]";
}

export function AjustesLlm({ llm, glosarioBackendLlm, onGuardar }: AjustesLlmProps) {
  const [borrador, setBorrador] = useState<SettingsLlm>(llm);
  const [abierto, setAbierto] = useState(false);
  const [confirmado, setConfirmado] = useState(false);
  const [confirmadoRemoto, setConfirmadoRemoto] = useState(false);

  const activaNoLocal = borrador.backend === "anthropic" && llm.backend !== "anthropic";
  const ollamaRemoto = borrador.backend === "ollama" && !esLocal(borrador.base_url);
  const puedeAbrir = (activaNoLocal ? confirmado : true) && (ollamaRemoto ? confirmadoRemoto : true);
  const destinoOllama = hostDe(borrador.base_url.trim()) || "una dirección no válida";
  const glosario = glosarioBackendLlm ?? GLOSARIO_FALLBACK.backend_llm;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-1.5">
        <Label>Backend</Label>
        <InfoTooltip titulo={glosario.etiqueta} queMide={glosario.definicion} />
      </div>
      <Select
        value={borrador.backend}
        onValueChange={(v) => {
          setBorrador((b) => ({ ...b, backend: v }));
          setConfirmado(false);
        }}
      >
        <SelectTrigger className="w-64" size="sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(ETIQUETA_BACKEND_LLM).map(([valor, etiqueta]) => (
            <SelectItem key={valor} value={valor}>
              {etiqueta}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {borrador.backend !== "none" ? (
        <Alert>
          <AlertTriangleIcon />
          <AlertDescription>
            Con el backend encendido, la redacción del dossier sale de Vigía hacia{" "}
            {borrador.backend === "ollama"
              ? ollamaRemoto
                ? `Ollama, en ${destinoOllama}, fuera de este equipo`
                : "Ollama, en este equipo"
              : "Anthropic, fuera del equipo"}
            .
          </AlertDescription>
        </Alert>
      ) : null}

      {borrador.backend !== "none" ? (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="llm-model">Modelo</Label>
            <Input
              id="llm-model"
              value={borrador.model}
              onChange={(e) => setBorrador((b) => ({ ...b, model: e.target.value }))}
            />
          </div>
          {borrador.backend === "ollama" ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="llm-base-url">URL base</Label>
              <Input
                id="llm-base-url"
                value={borrador.base_url}
                onChange={(e) => {
                  setBorrador((b) => ({ ...b, base_url: e.target.value }));
                  setConfirmadoRemoto(false);
                }}
                placeholder="http://localhost:11434"
              />
            </div>
          ) : null}
          {borrador.backend === "anthropic" ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="llm-api-key">Clave de API</Label>
              <Input
                id="llm-api-key"
                type="password"
                value={borrador.api_key}
                onChange={(e) => setBorrador((b) => ({ ...b, api_key: e.target.value }))}
                placeholder="Se guarda sin cifrar en la carpeta de datos; no se vuelve a enseñar"
              />
            </div>
          ) : null}
        </>
      ) : null}

      {activaNoLocal ? (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4"
            checked={confirmado}
            onChange={(e) => setConfirmado(e.target.checked)}
          />
          <span>Confirmo que {CONFIRMACION_NO_LOCAL}.</span>
        </label>
      ) : null}

      {ollamaRemoto ? (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4"
            checked={confirmadoRemoto}
            onChange={(e) => setConfirmadoRemoto(e.target.checked)}
          />
          <span>
            Confirmo que el servidor de {destinoOllama} es de mi organización y que {CONFIRMACION_NO_LOCAL}.
          </span>
        </label>
      ) : null}

      <div>
        <Button variant="outline" disabled={!puedeAbrir} onClick={() => setAbierto(true)}>
          Guardar backend
        </Button>
      </div>

      <MotivoDialog
        open={abierto}
        onOpenChange={setAbierto}
        titulo="Cambiar el backend LLM"
        etiquetaConfirmar="Guardar"
        deshabilitado={!puedeAbrir}
        onConfirm={async (cuerpo) => {
          await onGuardar(
            {
              ...borrador,
              ...(activaNoLocal ? { confirmacion_no_local: CONFIRMACION_NO_LOCAL } : {}),
              ...(ollamaRemoto ? { confirmar_remoto: true } : {}),
            },
            cuerpo,
          );
        }}
      />
    </div>
  );
}
