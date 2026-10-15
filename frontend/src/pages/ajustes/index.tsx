/** `/ajustes`: tema y rol para todos los roles; backend
 * LLM, token MCP, datos y versión solo fuera de `cliente` (§6.11). */

import { useEffect, useState } from "react";
import { useLocation } from "react-router";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { InfoTooltip, MotivoDialog, PageHeader } from "@/components/vigia";
import { useHealth } from "@/api/queries";
import { usePatchSettings, useSettings } from "@/api/queries-ajustes";
import { useGlosario } from "@/api/queries-contenido";
import type { ActorBody, Rol } from "@/api/types";
import { useTitulo } from "@/hooks/useTitulo";
import { useTheme } from "@/themes/theme";
import { ETIQUETA_ROL, ROLES, useCan, useSession } from "@/session/session";
import { AjustesApariencia } from "./ajustes-apariencia";
import { AjustesLlm } from "./ajustes-llm";
import { AjustesToken } from "./ajustes-token";
import { AjustesDatosVersion } from "./ajustes-datos-version";
import { esThemeName, modoColorAMode } from "./ajustes-datos";

export default function AjustesIndex() {
  useTitulo("Ajustes");
  const { role, setRole } = useSession();
  const puedeAjustesAvanzados = useCan("ajustes_avanzados");
  const esCliente = role === "cliente";
  const { theme, mode, setTheme, setMode } = useTheme();
  const settings = useSettings();
  const health = useHealth();
  const glosario = useGlosario();
  const patch = usePatchSettings();
  const { hash } = useLocation();

  const [dialogo, setDialogo] = useState<null | "rol">(null);
  const [rolBorrador, setRolBorrador] = useState<Rol>(role);

  // Anclas: #apariencia #rol #llm #mcp #datos #version.
  useEffect(() => {
    if (!hash) return;
    document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [hash]);

  // Al cargar, nada se
  // aplica en silencio. Si lo guardado en el backend (tema, modo, rol) difiere
  // de esta sesión, cada bloque enseña un aviso con un botón «Usar ...»; el
  // evento del bus `ajuste.cambiado` sí se aplica (quien guardó, quiso). Motivo:
  // el toggle de la cabecera solo escribe en `localStorage` y el backend arranca
  // en «según el sistema» y `clinico`: sincronizar al entrar deshacía el modo
  // oscuro elegido y dejaba al gestor sin `ajustes_avanzados` sin pedirlo.
  const temaGuardado = settings.data && esThemeName(settings.data.tema) ? settings.data.tema : null;
  const modoGuardado = settings.data ? modoColorAMode(settings.data.modo_color) : null;
  const avisoApariencia =
    (temaGuardado && temaGuardado !== theme) || (modoGuardado && modoGuardado !== mode)
      ? { theme: temaGuardado ?? theme, mode: modoGuardado ?? mode }
      : null;
  const rolGuardado = settings.data?.rol;
  const avisoRol =
    rolGuardado && ROLES.includes(rolGuardado as Rol) && rolGuardado !== role ? (rolGuardado as Rol) : null;

  const guardar = async (values: Record<string, unknown>, cuerpo: ActorBody) => {
    await patch.mutateAsync({ ...cuerpo, values });
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader titulo="Ajustes" />

      <AjustesApariencia
        guardar={guardar}
        avisoGuardado={avisoApariencia}
        onUsarGuardado={() => {
          if (avisoApariencia) {
            setTheme(avisoApariencia.theme);
            setMode(avisoApariencia.mode);
          }
        }}
      />

      <Card id="rol" className="scroll-mt-20">
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            Rol
            <InfoTooltip
              titulo={glosario.data?.rol?.etiqueta ?? "Rol"}
              queMide={
                glosario.data?.rol?.definicion ??
                "Decide qué capacidades tiene esta sesión: registros, cambios de configuración y ajustes avanzados."
              }
            />
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {avisoRol ? (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted px-3 py-2 text-sm">
              <span>
                El rol guardado es {ETIQUETA_ROL[avisoRol]}; esta sesión usa {ETIQUETA_ROL[role]}.
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setRole(avisoRol);
                  setRolBorrador(avisoRol);
                }}
              >
                Usar {ETIQUETA_ROL[avisoRol]}
              </Button>
            </div>
          ) : null}
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>Rol de la sesión</Label>
              <Select value={rolBorrador} onValueChange={(v) => setRolBorrador(v as Rol)}>
                <SelectTrigger className="w-52" size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {ETIQUETA_ROL[r]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button variant="outline" onClick={() => setDialogo("rol")}>
              Guardar rol
            </Button>
          </div>
        </CardContent>
      </Card>

      {!esCliente && settings.data ? (
        <>
          <Card id="llm" className="scroll-mt-20">
            <CardHeader>
              <CardTitle>Backend LLM</CardTitle>
            </CardHeader>
            <CardContent>
              {puedeAjustesAvanzados ? (
                <AjustesLlm
                  llm={settings.data.llm}
                  glosarioBackendLlm={glosario.data?.backend_llm}
                  onGuardar={(llm, cuerpo) => guardar({ llm }, cuerpo)}
                />
              ) : (
                <p className="text-sm text-muted-foreground">Solo el gestor puede cambiarlo.</p>
              )}
            </CardContent>
          </Card>

          {puedeAjustesAvanzados ? (
            <Card id="mcp" className="scroll-mt-20">
              <CardHeader>
                <CardTitle>Token MCP</CardTitle>
              </CardHeader>
              <CardContent>
                <AjustesToken
                  tokenEnmascarado={settings.data.mcp_token}
                  glosarioTokenMcp={glosario.data?.token_mcp}
                />
              </CardContent>
            </Card>
          ) : null}

          <AjustesDatosVersion settings={settings.data} health={health.data} />
        </>
      ) : null}

      <MotivoDialog
        open={dialogo === "rol"}
        onOpenChange={(o) => !o && setDialogo(null)}
        titulo="Cambiar el rol"
        etiquetaConfirmar="Guardar"
        onConfirm={async (cuerpo) => {
          await guardar({ rol: rolBorrador }, cuerpo);
          setRole(rolBorrador);
        }}
      />
    </div>
  );
}
