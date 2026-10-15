/**
 * Severidad de alerta a estado del motor, para reutilizar `StateBadge`
 * (alta con `--state-alert`, media con `--state-warn`). El backend
 * solo emite `alta`/`media` (`SEVERIDADES_ALERTA`); se acepta
 * cualquier cadena (incluida "baja") por si en el futuro se amplía, con
 * etiqueta igual al valor recibido cuando no está en el mapa.
 */

import type { EstadoMotor } from "@/api/types";

const SEVERIDAD_A_ESTADO: Record<string, EstadoMotor> = {
  alta: "alerta",
  media: "aviso",
  baja: "inestable",
};

const ETIQUETA_SEVERIDAD: Record<string, string> = {
  alta: "Alta",
  media: "Media",
  baja: "Baja",
};

export function estadoDeSeveridad(severidad: string): EstadoMotor {
  return SEVERIDAD_A_ESTADO[severidad] ?? "sin_datos";
}

export function etiquetaSeveridad(severidad: string): string {
  return ETIQUETA_SEVERIDAD[severidad] ?? severidad;
}
