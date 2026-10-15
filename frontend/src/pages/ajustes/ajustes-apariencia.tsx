/**
 * Bloque «Apariencia» de `/ajustes`: tema y modo de color,
 * guardados con motivo en `PATCH /settings` y aplicados al `ThemeProvider`.
 * Partido de `index.tsx` para no pasar de 9 KB. Los borradores siguen a
 * `theme`/`mode` cuando cambian de verdad (sincronización al cargar, evento
 * del bus u otra pestaña), derivado en el render, no en un efecto.
 */

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MotivoDialog } from "@/components/vigia";
import type { ActorBody } from "@/api/types";
import { useTheme } from "@/themes/theme";
import type { ThemeMode, ThemeName } from "@/themes/theme";
import { HAY_SELECTOR_TEMA, TEMAS_DISPONIBLES, etiquetaTema } from "@/themes/temas";
import { ETIQUETA_MODO, modeAModoColor } from "./ajustes-datos";

/** Con una sola estética en el build, la apariencia se describe solo por el modo. */
function describir(tema: ThemeName, modo: ThemeMode): string {
  const m = ETIQUETA_MODO[modo].toLowerCase();
  return HAY_SELECTOR_TEMA ? `${etiquetaTema(tema)}, ${m}` : m;
}

export interface AjustesAparienciaProps {
  guardar: (values: Record<string, unknown>, cuerpo: ActorBody) => Promise<void>;
  /** Tema y modo guardados en el backend cuando difieren de la sesión; `null` si coinciden. */
  avisoGuardado: { theme: ThemeName; mode: ThemeMode } | null;
  onUsarGuardado: () => void;
}

export function AjustesApariencia({ guardar, avisoGuardado, onUsarGuardado }: AjustesAparienciaProps) {
  const { theme, mode, setTheme, setMode } = useTheme();
  const [abierto, setAbierto] = useState(false);
  const [temaBorrador, setTemaBorrador] = useState(theme);
  const [modoBorrador, setModoBorrador] = useState(mode);
  const [aparienciaVista, setAparienciaVista] = useState({ theme, mode });
  if (theme !== aparienciaVista.theme || mode !== aparienciaVista.mode) {
    setAparienciaVista({ theme, mode });
    setTemaBorrador(theme);
    setModoBorrador(mode);
  }

  return (
    <Card id="apariencia" className="scroll-mt-20">
      <CardHeader>
        <CardTitle>Apariencia</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-end gap-4">
        {avisoGuardado ? (
          <div className="flex w-full flex-wrap items-center gap-3 rounded-lg bg-muted px-3 py-2 text-md">
            <span>
              La apariencia guardada es {describir(avisoGuardado.theme, avisoGuardado.mode)};
              esta sesión usa {describir(theme, mode)}.
            </span>
            <Button type="button" size="sm" variant="outline" onClick={onUsarGuardado}>
              Usar la guardada
            </Button>
          </div>
        ) : null}
        {HAY_SELECTOR_TEMA ? (
          <div className="flex flex-col gap-1.5">
            <Label>Tema</Label>
            <Select value={temaBorrador} onValueChange={(v) => setTemaBorrador(v as typeof theme)}>
              <SelectTrigger className="w-44" size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TEMAS_DISPONIBLES.map((t) => (
                  <SelectItem key={t.valor} value={t.valor}>
                    {t.etiquetaCorta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <Label>Modo de color</Label>
          <Select value={modoBorrador} onValueChange={(v) => setModoBorrador(v as typeof mode)}>
            <SelectTrigger className="w-44" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(["light", "dark", "system"] as const).map((m) => (
                <SelectItem key={m} value={m}>
                  {ETIQUETA_MODO[m]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" onClick={() => setAbierto(true)}>
          Guardar apariencia
        </Button>
      </CardContent>
      <MotivoDialog
        open={abierto}
        onOpenChange={setAbierto}
        titulo="Cambiar la apariencia"
        etiquetaConfirmar="Guardar"
        onConfirm={async (cuerpo) => {
          await guardar({ tema: temaBorrador, modo_color: modeAModoColor(modoBorrador) }, cuerpo);
          setTheme(temaBorrador);
          setMode(modoBorrador);
        }}
      />
    </Card>
  );
}
