/**
 * Interruptor accesible mínimo (promovido a `components/ui` desde
 * `pages/monitores/Switch.tsx`, para que otros
 * componentes lo reutilicen sin depender de `pages/monitores`).
 */

import { cn } from "@/lib/utils";

export interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
  disabled?: boolean;
  /** Etiqueta accesible cuando no hay un `<Label htmlFor>` visible al lado. */
  label?: string;
}

export function Switch({ checked, onCheckedChange, id, disabled, label }: SwitchProps) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-input transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
      )}
      style={{ background: checked ? "var(--primary)" : "var(--muted)" }}
    >
      <span
        aria-hidden="true"
        className={cn(
          "inline-block size-4 translate-x-0.5 rounded-full bg-background shadow transition-transform",
          checked && "translate-x-4",
        )}
      />
    </button>
  );
}
