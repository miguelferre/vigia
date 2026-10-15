/**
 * Navegación de la barra lateral.
 *
 * `Demo` tiene ruta propia: presentación y demo
 * guiada del caso Digestivo. `Onboarding` desaparece de la barra: `/onboarding` redirige a `/ayuda#guia`, la guía de uso, que es
 * donde vive ahora ese recorrido. Capa humana, auditoría y riesgos están en
 * «Vigilancia» y ajustes en «Configuración».
 */

import {
  BookOpenTextIcon,
  BoxesIcon,
  CircleHelpIcon,
  ClipboardCheckIcon,
  LayoutDashboardIcon,
  PlayIcon,
  ServerCogIcon,
  ShieldAlertIcon,
  TriangleAlertIcon,
  UsersIcon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ICONO_MONITOR } from "@/lib/iconos";

export interface EntradaNav {
  etiqueta: string;
  icono: LucideIcon;
  /** Ruta destino. */
  a: string;
  /** `true` cuando la ruta solo coincide de forma exacta. */
  exacta?: boolean;
}

export interface GrupoNav {
  titulo: string;
  entradas: EntradaNav[];
}

export const NAVEGACION: GrupoNav[] = [
  {
    titulo: "Vigilancia",
    entradas: [
      // la portada es la rejilla de modelos; el cuadro de mando de un
      // modelo concreto pasa a /cuadro.
      { etiqueta: "Modelos", icono: BoxesIcon, a: "/", exacta: true },
      { etiqueta: "Cuadro de mando", icono: LayoutDashboardIcon, a: "/cuadro", exacta: true },
      { etiqueta: "Equidad", icono: ICONO_MONITOR.fairness, a: "/monitores/equidad" },
      { etiqueta: "Calidad", icono: ICONO_MONITOR.quality, a: "/monitores/calidad" },
      { etiqueta: "Deriva", icono: ICONO_MONITOR.drift, a: "/monitores/deriva" },
      { etiqueta: "Alertas", icono: TriangleAlertIcon, a: "/alertas" },
      { etiqueta: "Explicabilidad", icono: ICONO_MONITOR.explain, a: "/explicabilidad" },
      { etiqueta: "Capa humana", icono: UsersIcon, a: "/capa-humana" },
      { etiqueta: "Auditoría", icono: ClipboardCheckIcon, a: "/auditoria" },
      { etiqueta: "Riesgos", icono: ShieldAlertIcon, a: "/riesgos" },
    ],
  },
  {
    titulo: "Configuración",
    entradas: [
      { etiqueta: "Diario", icono: BookOpenTextIcon, a: "/diario" },
      { etiqueta: "Ajustes", icono: ServerCogIcon, a: "/ajustes" },
      { etiqueta: "Ayuda", icono: CircleHelpIcon, a: "/ayuda" },
    ],
  },
  {
    titulo: "Demostración",
    entradas: [{ etiqueta: "Demo", icono: PlayIcon, a: "/demo" }],
  },
];
