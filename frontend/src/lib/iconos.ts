/**
 * Vocabulario visual común: un icono por
 * monitor y un glifo por estado, compartidos por la tarjeta de modelo, el
 * cuadro, los monitores, `StateBadge` y `/ayuda`. Ningún estado se enseña
 * solo por color: el glifo o la cifra van siempre al lado del relleno
 * (`colorEstado(estado, "relleno")`, `lib/metrics.ts`).
 */

import {
  BlendIcon,
  ChartLineIcon,
  CheckIcon,
  CircleDashedIcon,
  CircleMinusIcon,
  ClipboardCheckIcon,
  LightbulbIcon,
  OctagonAlertIcon,
  ScaleIcon,
  TriangleAlertIcon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ETIQUETA_ESTADO } from "@/lib/metrics";
import type { EstadoMotor, MonitorType } from "@/api/types";

/** Icono por tipo de monitor. Calidad usa del indicador a la libreta de checks y
 * deriva de los deslizadores a una gráfica de línea. */
export const ICONO_MONITOR: Record<MonitorType, LucideIcon> = {
  fairness: ScaleIcon,
  quality: ClipboardCheckIcon,
  drift: ChartLineIcon,
  cross: BlendIcon,
  explain: LightbulbIcon,
};

/** Glifo por estado del motor. */
export const GLIFO_ESTADO: Record<EstadoMotor, LucideIcon> = {
  ok: CheckIcon,
  aviso: TriangleAlertIcon,
  alerta: OctagonAlertIcon,
  inestable: CircleDashedIcon,
  sin_datos: CircleMinusIcon,
};

/** Palabra del estado para `aria-label` junto al glifo; reexporta `ETIQUETA_ESTADO`. */
export const ETIQUETA_GLIFO: Record<EstadoMotor, string> = ETIQUETA_ESTADO;
