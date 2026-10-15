/**
 * Cabecera de columna con ⓘ y los textos de los cuatro estadísticos de deriva
 * y la lectura de `result.details.features`
 * (nombre técnico + etiqueta clínica del dominio Digestivo).
 *
 * Vive aparte por tres motivos: `ranking-deriva.tsx` se pasaba de los 9 KB
 * al añadirle el tope de características y la traducción de
 * dominio; `CabeceraEstadistico` estaba duplicada a mano en
 * `ranking-deriva.tsx` y `clases-predichas.tsx`.
 *
 * `ks_stat`, `psi`, `chi2` y `js` no son `metric_key` del motor y no tienen
 * entrada en `content/metricas-ayuda.json`: son estadísticos internos por
 * característica, así que su ayuda vive aquí y no en el ⓘ de la tarjeta.
 */

import { InfoTooltip } from "@/components/vigia";
import type { JsonObject } from "@/api/types";
import { etiquetaCaracteristica } from "@/lib/dominio-caracteristicas";

export interface CabeceraEstadisticoProps {
  titulo: string;
  queMide: string;
  formula?: string;
}

export function CabeceraEstadistico({ titulo, queMide, formula }: CabeceraEstadisticoProps) {
  return (
    <span className="inline-flex items-center gap-1">
      {titulo}
      <InfoTooltip titulo={titulo} queMide={queMide} formula={formula ?? null} />
    </span>
  );
}

/**
 * Lo que distingue las dos cifras de deriva con nombre
 * parecido. Se enseña bajo los estadísticos de la variable; el mismo texto
 * está en la guía de uso.
 */
export const TEXTO_DOS_CIFRAS_DERIVA =
  "No confundas dos cifras. La «Deriva de características» de la alerta es la mayor puntuación de deriva (KS en numéricas, JS en categóricas) entre todas las variables. El PSI es otra medida del cambio de esta variable y no entra en la alerta.";

/** Textos de ayuda de los cuatro estadísticos, en lenguaje de lector clínico. */
export const AYUDA_ESTADISTICO: Record<string, CabeceraEstadisticoProps> = {
  ks: {
    titulo: "KS",
    queMide:
      "Estadístico de Kolmogórov-Smirnov: mayor distancia entre la distribución de la línea base y la actual de una característica numérica. Va de 0 a 1.",
    formula: "ks_stat, con su significación ks_p",
  },
  psi: {
    titulo: "PSI",
    queMide:
      "Índice de estabilidad de la población: cuánto ha cambiado la distribución de una característica numérica entre la línea base y la actual. Por encima de 0,25 se considera cambio grande. No es la cifra de la alerta de deriva: esa es la mayor puntuación KS o JS entre todas las variables.",
  },
  chi2: {
    titulo: "Chi²",
    queMide:
      "Prueba de chi cuadrado: si la distribución de categorías de una característica categórica ha cambiado entre la línea base y la actual.",
    formula: "chi2, con su significación p",
  },
  js: {
    titulo: "JS",
    queMide:
      "Distancia de Jensen-Shannon entre las dos distribuciones de una característica categórica. Va de 0 a 1.",
  },
};

/* ---------- lectura de result.details.features, sin suponer forma ---------- */

export interface FilaCaracteristica {
  feature: string;
  /** Etiqueta clínica del dominio Digestivo; `feature` si no traduce. */
  featureLabel: string;
  kind: "numerica" | "categorica" | string;
  score: number;
  ks_stat: number | null;
  ks_p: number | null;
  psi: number | null;
  chi2: number | null;
  p: number | null;
  js: number | null;
}

function numeroONulo(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

/** `dominio` es la clave `dominio` de `useGuionDemo`, o `undefined` sin cargar. */
export function extraerCaracteristicas(
  details: JsonObject | null,
  dominio: Record<string, string> | undefined,
): FilaCaracteristica[] {
  if (!details) return [];
  const features = details.features;
  if (!Array.isArray(features)) return [];
  return features
    .filter((f): f is JsonObject => f !== null && typeof f === "object" && !Array.isArray(f))
    .map((f) => {
      const feature = typeof f.feature === "string" ? f.feature : String(f.feature ?? "");
      return {
        feature,
        featureLabel: etiquetaCaracteristica(feature, dominio),
        kind: typeof f.kind === "string" ? f.kind : "",
        score: numeroONulo(f.score) ?? 0,
        ks_stat: numeroONulo(f.ks_stat),
        ks_p: numeroONulo(f.ks_p),
        psi: numeroONulo(f.psi),
        chi2: numeroONulo(f.chi2),
        p: numeroONulo(f.p),
        js: numeroONulo(f.js),
      };
    })
    .sort((a, b) => b.score - a.score);
}
