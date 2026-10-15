/**
 * Registro de los diez diagramas de la presentación: la diapositiva `id` de
 * `presentacion.json` (1 a 10, sin huecos) indexa directamente el
 * componente que la dibuja. `Diapositiva.tsx` lo consulta con
 * `DIAGRAMAS[id]`.
 */

import type { ComponentType } from "react";

import { D01 } from "./D01";
import { D02 } from "./D02";
import { D03 } from "./D03";
import { D04 } from "./D04";
import { D05 } from "./D05";
import { D06 } from "./D06";
import { D07 } from "./D07";
import { D08 } from "./D08";
import { D09 } from "./D09";
import { D10 } from "./D10";

export const DIAGRAMAS: Record<number, ComponentType<{ className?: string }>> = {
  1: D01,
  2: D02,
  3: D03,
  4: D04,
  5: D05,
  6: D06,
  7: D07,
  8: D08,
  9: D09,
  10: D10,
};
