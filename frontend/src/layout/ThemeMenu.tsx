/**
 * Selector de tema y modo.
 *
 * El `ThemeToggle` de beUI sigue conmutando claro/oscuro con su
 * transición circular; aquí se le añade el menú que elige la estética
 * (si el build tiene más de una) y el modo, incluido «según el sistema».
 */

import { CheckIcon, PaletteIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeToggle } from "@/components/beui/theme-toggle";
import { useTheme } from "@/themes/theme";
import type { ThemeMode } from "@/themes/theme";
import { HAY_SELECTOR_TEMA, TEMAS_DISPONIBLES } from "@/themes/temas";

const MODOS: { valor: ThemeMode; etiqueta: string }[] = [
  { valor: "light", etiqueta: "Claro" },
  { valor: "dark", etiqueta: "Oscuro" },
  { valor: "system", etiqueta: "Según el sistema" },
];

export function ThemeMenu() {
  const { theme, mode, setTheme, setMode } = useTheme();

  return (
    <div className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" aria-label="Tema y modo de color">
            <PaletteIcon className="size-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          {HAY_SELECTOR_TEMA ? (
            <>
              <DropdownMenuLabel>Estética</DropdownMenuLabel>
              {TEMAS_DISPONIBLES.map((t) => (
                <DropdownMenuItem key={t.valor} onSelect={() => setTheme(t.valor)}>
                  <span className="flex-1">{t.etiqueta}</span>
                  {theme === t.valor ? <CheckIcon className="size-4" aria-hidden="true" /> : null}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
            </>
          ) : null}
          <DropdownMenuLabel>Modo</DropdownMenuLabel>
          {MODOS.map((m) => (
            <DropdownMenuItem key={m.valor} onSelect={() => setMode(m.valor)}>
              <span className="flex-1">{m.etiqueta}</span>
              {mode === m.valor ? <CheckIcon className="size-4" aria-hidden="true" /> : null}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <ThemeToggle
        variant="circle"
        className="h-9 w-9 rounded-md border border-border hover:bg-muted"
        iconClassName="h-4 w-4"
      />
    </div>
  );
}
