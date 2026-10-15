/**
 * Casilla de selección de la tabla de alertas (`columnas.tsx`): en su
 * propio fichero porque `react-refresh/only-export-components` se
 * queja de un componente exportado junto a funciones sueltas
 * (`columnasAlertas`, `textoUmbral`) en el mismo módulo.
 */

import { cn } from "@/lib/utils";

export type EstadoCasilla = "vacia" | "parcial" | "llena";

export function CasillaSeleccion({
  estado,
  onToggle,
  rayada,
  etiqueta,
}: {
  estado: EstadoCasilla;
  onToggle: () => void;
  rayada: boolean;
  etiqueta: string;
}) {
  return (
    <span className="relative -mx-3 -my-2 flex items-center justify-center px-3 py-2">
      {rayada ? (
        <span
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-1"
          style={{
            background: "repeating-linear-gradient(45deg, var(--state-warn) 0 3px, transparent 3px 6px)",
          }}
        />
      ) : null}
      <button
        type="button"
        role="checkbox"
        aria-checked={estado === "parcial" ? "mixed" : estado === "llena"}
        aria-label={etiqueta}
        onClick={(e) => {
          e.stopPropagation();
          onToggle();
        }}
        className={cn(
          "flex size-4 items-center justify-center rounded",
          estado === "vacia" ? "shadow-[inset_0_0_0_1px_var(--border)]" : "bg-foreground text-background",
        )}
      >
        {estado === "llena" ? (
          // Trazo 1,5 como el resto de iconos (antes 2).
          <svg viewBox="0 0 16 16" className="size-2.5" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
            <path d="M 3.5 8.5 6.5 11.5 12.5 5" />
          </svg>
        ) : estado === "parcial" ? (
          <span className="h-0.5 w-2 rounded-full bg-current" />
        ) : null}
      </button>
    </span>
  );
}

export default CasillaSeleccion;
