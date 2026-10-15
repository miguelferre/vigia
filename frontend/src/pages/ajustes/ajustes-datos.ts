/**
 * Vocabulario y mapeos compartidos por `/ajustes`:
 * catálogos, etiquetas y la traducción entre las palabras del backend
 * (`tema`, `modo_color`) y las del `ThemeProvider` (`ThemeName`, `ThemeMode`).
 */

import { esTemaDisponible } from "@/themes/temas";
import type { ThemeMode, ThemeName } from "@/themes/theme";

export const ETIQUETA_MODO: Record<ThemeMode, string> = {
  light: "Claro",
  dark: "Oscuro",
  system: "Según el sistema",
};

/** `tema` del backend coincide literalmente con `ThemeName`: valida, no traduce. */
export function esThemeName(valor: string): valor is ThemeName {
  return esTemaDisponible(valor);
}

export function modoColorAMode(valor: string): ThemeMode | null {
  if (valor === "claro") return "light";
  if (valor === "oscuro") return "dark";
  if (valor === "sistema") return "system";
  return null;
}

export function modeAModoColor(mode: ThemeMode): "claro" | "oscuro" | "sistema" {
  if (mode === "dark") return "oscuro";
  if (mode === "system") return "sistema";
  return "claro";
}

export const ETIQUETA_BACKEND_LLM: Record<string, string> = {
  none: "Apagado",
  ollama: "Ollama, local",
  anthropic: "Anthropic, no local",
};

/**
 * Texto de confirmación exigido por `services/settings.py` para
 * activar un backend no local. El backend solo exige que no esté vacío
 * (`_validar`, línea 152-156); este es el texto que se envía y que queda en
 * el evento `ajuste.llm_confirmado`. Habla de todo el dossier que se
 * envía (formularios y, si se pidió, el resumen de deskilling), no solo de los
 * formularios.
 */
export const CONFIRMACION_NO_LOCAL =
  "el dossier (los formularios y, si se pide, el resumen de deskilling) no lleva datos de personas afectadas";

export const GLOSARIO_FALLBACK: Record<string, { etiqueta: string; definicion: string }> = {
  token_mcp: {
    etiqueta: "Token MCP",
    definicion:
      "Credencial que el servidor MCP de Vigía exige en la cabecera X-Vigia-Token de cada petición de la sesión de un agente.",
  },
  backend_llm: {
    etiqueta: "Backend del LLM",
    definicion:
      "Motor de lenguaje que redacta el borrador del dossier de auditoría: apagado por defecto, Ollama en local o Anthropic fuera del equipo (exige confirmación).",
  },
};
