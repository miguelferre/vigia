/**
 * Estado de la demo guiada en `localStorage` `vigia-demo` (no es dato de gobernanza, no va al diario). Guarda la reproducción y
 * el proyecto que sostienen la demo, el paso en curso, los pasos ya hechos y
 * si el panel está activo o plegado, para que sobreviva a navegar y a
 * recargar. Heredero de `pages/onboarding/progreso.ts`.
 *
 * Toda lectura y escritura va en `try/catch`: puede fallar (modo privado,
 * almacenamiento bloqueado) y la demo debe seguir funcionando en memoria.
 */

const CLAVE = "vigia-demo";

export interface EstadoDemo {
  /** El panel está en pantalla (o plegado a su pastilla). `cerrar()` lo apaga sin borrar el resto. */
  activa: boolean;
  runId: number | null;
  projectId: number | null;
  paso: number;
  completado: boolean;
  /**
   * Genérico desde que «Tras las medidas» salió del guion (ya no hay un paso
   * opcional fijo, `AccionPaso.tsx`, `contexto.ts:62`): si el guion vuelve a
   * traer alguno, marca que se ha visitado alguna vez.
   */
  opcionalVisto: boolean;
  hechos: number[];
  /** Panel plegado a la pastilla «Demo · paso N». Comodidad por navegador. */
  plegado: boolean;
}

export const ESTADO_INICIAL: EstadoDemo = {
  activa: false,
  runId: null,
  projectId: null,
  paso: 0,
  completado: false,
  opcionalVisto: false,
  hechos: [],
  plegado: false,
};

function numeroONulo(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function leerEstadoDemo(): EstadoDemo {
  try {
    const raw = localStorage.getItem(CLAVE);
    if (!raw) return { ...ESTADO_INICIAL };
    const p = JSON.parse(raw) as Partial<EstadoDemo>;
    return {
      activa: p.activa === true,
      runId: numeroONulo(p.runId),
      projectId: numeroONulo(p.projectId),
      paso: numeroONulo(p.paso) ?? 0,
      completado: p.completado === true,
      opcionalVisto: p.opcionalVisto === true,
      hechos: Array.isArray(p.hechos) ? p.hechos.filter((n): n is number => typeof n === "number") : [],
      plegado: p.plegado === true,
    };
  } catch {
    return { ...ESTADO_INICIAL };
  }
}

export function guardarEstadoDemo(estado: EstadoDemo): void {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(estado));
  } catch {
    // sin almacenamiento: la demo sigue en memoria, solo no se recuerda
  }
}

export function borrarEstadoDemo(): void {
  try {
    localStorage.removeItem(CLAVE);
  } catch {
    // igual: sin almacenamiento no hay nada que borrar
  }
}
