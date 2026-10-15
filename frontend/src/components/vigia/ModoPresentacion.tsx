/**
 * Modo presentación: contexto, hook y botón. Pantalla limpia y tipografía mayor son cosa de quien pinta el
 * contenido (`Escena`) y del layout, que engancha `AppShell`
 * leyendo `useModoPresentacion().activo`; este fichero solo posee el estado
 * y la salida por `Escape`, para que reproductor y onboarding lo activen
 * desde el mismo sitio sin duplicar lógica.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { Maximize2Icon, Minimize2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface ModoPresentacionContextValue {
  activo: boolean;
  activar: () => void;
  desactivar: () => void;
  alternar: () => void;
}

const ModoPresentacionContext = createContext<ModoPresentacionContextValue | null>(null);

export function ModoPresentacionProvider({ children }: { children: ReactNode }) {
  const [activo, setActivo] = useState(false);

  const activar = useCallback(() => setActivo(true), []);
  const desactivar = useCallback(() => setActivo(false), []);
  const alternar = useCallback(() => setActivo((a) => !a), []);

  useEffect(() => {
    if (!activo) return;
    function alEscape(e: KeyboardEvent) {
      if (e.key === "Escape") desactivar();
    }
    window.addEventListener("keydown", alEscape);
    return () => window.removeEventListener("keydown", alEscape);
  }, [activo, desactivar]);

  const value = useMemo<ModoPresentacionContextValue>(
    () => ({ activo, activar, desactivar, alternar }),
    [activo, activar, desactivar, alternar],
  );

  return (
    <ModoPresentacionContext.Provider value={value}>{children}</ModoPresentacionContext.Provider>
  );
}

/** Estado y controles del modo presentación. Exige `ModoPresentacionProvider` por encima. */
export function useModoPresentacion(): ModoPresentacionContextValue {
  const ctx = useContext(ModoPresentacionContext);
  if (!ctx) throw new Error("useModoPresentacion debe usarse dentro de ModoPresentacionProvider");
  return ctx;
}

export interface BotonModoPresentacionProps {
  className?: string;
}

/** Botón de alternar, para la cabecera del reproductor y del onboarding. */
export function BotonModoPresentacion({ className }: BotonModoPresentacionProps) {
  const { activo, alternar } = useModoPresentacion();
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={alternar}
      aria-pressed={activo}
      aria-label={activo ? "Salir del modo presentación" : "Entrar en modo presentación"}
      title={activo ? "Salir del modo presentación (Esc)" : "Modo presentación"}
      className={cn(className)}
    >
      {activo ? (
        <Minimize2Icon className="size-4" aria-hidden="true" />
      ) : (
        <Maximize2Icon className="size-4" aria-hidden="true" />
      )}
    </Button>
  );
}
