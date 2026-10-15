/**
 * Chip del estado de despliegue: lo usan la
 * tarjeta de `/modelos` y la pestaña de configuración. Demo va en
 * `--secondary`, producción en `--state-ok` y desarrollo en `--muted`; el
 * texto siempre acompaña al color.
 */

import type { DeploymentStage } from "@/api/types";

/** Chip del estado de despliegue: tarjeta de `/modelos` y pestaña de configuración. */
export function ChipDespliegue({ estado }: { estado: DeploymentStage }) {
  const estilos: Record<DeploymentStage, { background: string; color: string; texto: string }> = {
    demo: { background: "var(--secondary)", color: "var(--secondary-foreground)", texto: "Demo" },
    produccion: { background: "var(--state-ok)", color: "var(--state-on-fill)", texto: "Producción" },
    desarrollo: { background: "var(--muted)", color: "var(--muted-foreground)", texto: "Desarrollo" },
    validacion: { background: "var(--muted)", color: "var(--foreground)", texto: "Validación" },
  };
  const e = estilos[estado];
  return (
    <span
      className="inline-flex h-[22px] flex-none items-center rounded-full px-2 text-xs font-medium"
      style={{ background: e.background, color: e.color }}
    >
      {e.texto}
    </span>
  );
}
