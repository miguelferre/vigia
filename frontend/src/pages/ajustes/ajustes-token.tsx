/**
 * Bloque «Token MCP» de `/ajustes`: enmascarado con
 * «Revelar» (`GET /settings?reveal=true`, sin cachear) y «Copiar». Solo
 * `ajustes_avanzados`.
 */

import { useState } from "react";
import { CopyIcon, EyeIcon, EyeOffIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { InfoTooltip } from "@/components/vigia";
import { useSettingsReveal } from "@/api/queries-ajustes";
import { GLOSARIO_FALLBACK } from "./ajustes-datos";

export interface AjustesTokenProps {
  tokenEnmascarado: string;
  glosarioTokenMcp?: { etiqueta: string; definicion: string };
}

export function AjustesToken({ tokenEnmascarado, glosarioTokenMcp }: AjustesTokenProps) {
  const [revelado, setRevelado] = useState(false);
  const reveal = useSettingsReveal(revelado);
  const glosario = glosarioTokenMcp ?? GLOSARIO_FALLBACK.token_mcp;
  const valorVisible = revelado ? (reveal.data?.mcp_token ?? "") : tokenEnmascarado;

  const copiar = async () => {
    try {
      const texto = revelado ? reveal.data?.mcp_token : undefined;
      if (!texto) {
        toast.error("Revela el token antes de copiarlo.");
        return;
      }
      await navigator.clipboard.writeText(texto);
      toast.success("Token copiado.");
    } catch {
      toast.error("No se ha podido copiar el token.");
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        <Label>Token MCP</Label>
        <InfoTooltip titulo={glosario.etiqueta} queMide={glosario.definicion} />
      </div>
      <p className="text-sm text-muted-foreground">
        Lo pide el servidor MCP de Vigía en la cabecera <code>X-Vigia-Token</code> de cada petición
        de una sesión de agente.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <code className="max-w-full rounded border border-border bg-muted px-2 py-1 text-sm [overflow-wrap:anywhere]">
          {revelado && reveal.isLoading ? "Cargando…" : valorVisible}
        </code>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setRevelado((r) => !r)}
        >
          {revelado ? (
            <>
              <EyeOffIcon /> Ocultar
            </>
          ) : (
            <>
              <EyeIcon /> Revelar
            </>
          )}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => void copiar()} disabled={!revelado}>
          <CopyIcon /> Copiar
        </Button>
      </div>
    </div>
  );
}
