/** Estado vacío reutilizable: icono, título, explicación y una acción. */

import type { LucideIcon } from "lucide-react";
import { InboxIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  titulo: string;
  descripcion?: ReactNode;
  icono?: LucideIcon;
  accion?: ReactNode;
  className?: string;
}

export function EmptyState({
  titulo,
  descripcion,
  icono: Icono = InboxIcon,
  accion,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-12 text-center",
        className,
      )}
    >
      <Icono className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="font-semibold">{titulo}</p>
      {descripcion ? (
        <div className="max-w-prose text-sm text-muted-foreground">{descripcion}</div>
      ) : null}
      {accion}
    </div>
  );
}
