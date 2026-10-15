/**
 * Nombres de las reglas cruzadas: la
 * pantalla las llama por lo que pasa, no por el código. El código `CX-n` es la
 * `metric_key` interna y sale solo como detalle (atributo `title` y ayuda
 * técnica). Único sitio de los nombres en el frontend: `Cruzadas.tsx` y
 * `lib/metric-labels.ts` leen de aquí. El backend los repite en
 * `METRIC_LABELS` de `app/services/alerting.py` y el contenido en
 * `metricas-ayuda.json`; un test compara los tres.
 *
 * `human_review_zero` es una señal más de la misma lista, no una «CX-7».
 */

export interface NombreCruzada {
  nombre: string;
  ayuda: string;
}

export const CLAVE_HUMAN_REVIEW_ZERO = "human_review_zero";

export const CRUZADAS: Record<string, NombreCruzada> = {
  "CX-1": {
    nombre: "Tasa de correcciones en el grupo con más error",
    ayuda: "Frecuencia con la que los profesionales corrigen al modelo en el grupo donde más se equivoca.",
  },
  "CX-2": {
    nombre: "Tasa de correcciones con la calidad en alerta",
    ayuda: "Correcciones de los profesionales mientras el monitor de calidad está en alerta.",
  },
  "CX-3": {
    nombre: "Tasa de rescate de errores del modelo",
    ayuda: "Proporción de errores del modelo que los profesionales corrigen, frente a su referencia.",
  },
  "CX-4": {
    nombre: "Pérdida de criterio profesional (deskilling)",
    ayuda: "Convergencia entre profesional y modelo con caída del rescate.",
  },
  "CX-5": {
    nombre: "Diferencia de tasa de correcciones entre profesionales",
    ayuda: "Diferencia en la frecuencia de corrección de un profesional a otro.",
  },
  "CX-6": {
    nombre: "Diferencia de tasa de correcciones por grupo sin alerta de equidad",
    ayuda: "Un grupo recibe correcciones con una frecuencia distinta y el monitor de equidad no avisa.",
  },
  human_review_zero: {
    nombre: "Tasa de correcciones del modelo",
    ayuda: "Proporción de decisiones en las que un profesional corrige al modelo.",
  },
};

/** `clave -> nombre`, para `METRIC_LABELS` (`lib/metric-labels.ts`). */
export const NOMBRES_CRUZADAS: Record<string, string> = Object.fromEntries(
  Object.entries(CRUZADAS).map(([clave, { nombre }]) => [clave, nombre]),
);

export function ayudaCruzada(regla: string): string | null {
  return CRUZADAS[regla]?.ayuda ?? null;
}

const UN_DECIMAL = { minimumFractionDigits: 1, maximumFractionDigits: 1 } as const;

/** Un decimal y coma; `-0,0` no existe. */
function decimal(valor: number): string {
  return (Math.round(valor * 10) / 10 || 0).toLocaleString("es-ES", UN_DECIMAL);
}

/** Un decimal con coma y el signo explícito: «+2,4», «−3,6» (menos de verdad), «0,0». */
function decimalConSigno(valor: number): string {
  const redondeado = Math.round(valor * 10) / 10 || 0;
  if (redondeado === 0) return decimal(0);
  return `${redondeado > 0 ? "+" : "−"}${decimal(Math.abs(redondeado))}`;
}

/**
 * La desviación respecto a lo normal: «Desviación −3,6 · supera el umbral» o
 * «Desviación +2,4 · dentro del umbral». `supera` lo decide la API
 * (`supera_umbral`, B3): el valor cruza el umbral en el sentido en que la regla
 * alerta, no solo que sea grande. Una API anterior no lo manda (`null`): sin
 * veredicto.
 */
export function textoDesviacion(z: number, supera?: boolean | null, sinAlerta = false, regla = ""): string {
  const base = `Desviación ${decimalConSigno(z)}`;
  if (supera === null || supera === undefined) return base;
  if (!supera) return `${base} · dentro del umbral`;
  if (!sinAlerta) return `${base} · supera el umbral`;
  // El valor cruza el umbral pero la regla está en «Correcto». CX-6 calla si el grupo ya tiene otra alerta
  // abierta (de equidad o CX-1); en el resto, otra condición de la regla no se cumple.
  return regla === "CX-6"
    ? `${base} · supera el umbral · sin alerta: el grupo ya tiene otra abierta`
    : `${base} · supera el umbral · sin alerta: no se cumple otra condición de la regla`;
}

/**
 * Lo que enseña la tarjeta de cada regla. CX-5 trae una probabilidad (la de
 * que la diferencia entre profesionales sea azar) y CX-4 un 1 o un 0 (señal
 * activa o no); el resto trae la desviación.
 */
export function textoValor(regla: string, valor: number, supera?: boolean | null, estado?: string): string {
  if (regla === "CX-5") {
    return valor < 0.0001
      ? "Probabilidad de que sea azar: menos de 0,0001"
      : `Probabilidad de que sea azar: ${valor.toLocaleString("es-ES", { maximumFractionDigits: 4 })}`;
  }
  if (regla === "CX-4") return valor >= 0.5 ? "Señal activa" : "Señal sin activar";
  return textoDesviacion(valor, supera, estado === "ok", regla);
}

/** El grupo `otros` de la capa humana es el resto de grupos; los demás se nombran tal cual. */
export function textoGrupo(grupo: string): string {
  return grupo === "otros" ? "Resto de grupos" : `Grupo: ${grupo}`;
}
