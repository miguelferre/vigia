import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { onVigiaEvent } from "@/realtime/events";
import {
  esTemaDisponible,
  HAY_SELECTOR_TEMA,
  TEMA_POR_DEFECTO,
  TEMAS_DISPONIBLES,
} from "@/themes/temas";

/** Nombre de una estética del build (`miguel` y las que registre `temas-extra.ts`). */
export type ThemeName = string;
export type ThemeMode = "light" | "dark" | "system";

interface ThemeState {
  theme: ThemeName;
  mode: ThemeMode;
}

interface ThemeContextValue extends ThemeState {
  setTheme: (theme: ThemeName) => void;
  setMode: (mode: ThemeMode) => void;
  toggleTheme: (originEvent?: MouseEvent | React.MouseEvent) => void;
  toggleMode: (originEvent?: MouseEvent | React.MouseEvent) => void;
  resolvedDark: boolean;
}

const STORAGE_KEY = "vigia-theme";
const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored(): ThemeState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ThemeState>;
      return {
        theme: esTemaDisponible(parsed.theme) ? parsed.theme : TEMA_POR_DEFECTO,
        mode: parsed.mode === "dark" || parsed.mode === "system" ? parsed.mode : "light",
      };
    }
  } catch {
    // localStorage no disponible (modo privado, etc.): usar valores por defecto
  }
  return { theme: TEMA_POR_DEFECTO, mode: "light" };
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

function applyToDocument(state: ThemeState) {
  const root = document.documentElement;
  root.setAttribute("data-theme", state.theme);
  const dark = state.mode === "dark" || (state.mode === "system" && systemPrefersDark());
  root.classList.toggle("dark", dark);
}

/** Aplica un cambio de estado con transicion circular (API View Transitions),
 * igual que el patron de beUI. Si la API no existe o el usuario prefiere
 * movimiento reducido, cae a un cambio instantaneo. */
function applyWithViewTransition(
  apply: () => void,
  originEvent?: MouseEvent | React.MouseEvent,
) {
  const docWithVT = document as Document & {
    startViewTransition?: (cb: () => void) => { ready: Promise<void> };
  };

  if (!docWithVT.startViewTransition || prefersReducedMotion()) {
    apply();
    return;
  }

  const x = originEvent?.clientX ?? window.innerWidth / 2;
  const y = originEvent?.clientY ?? window.innerHeight / 2;
  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y),
  );

  const transition = docWithVT.startViewTransition(apply);
  transition.ready
    .then(() => {
      document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${endRadius}px at ${x}px ${y}px)`,
          ],
        },
        {
          duration: 300,
          easing: "ease-out",
          pseudoElement: "::view-transition-new(root)",
        },
      );
    })
    .catch(() => {
      // navegador sin soporte pleno de pseudo-elementos: el cambio ya aplico
    });
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ThemeState>(() => readStored());

  useEffect(() => {
    applyToDocument(state);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // sin persistencia disponible: el tema sigue funcionando en memoria
    }
  }, [state]);

  useEffect(() => {
    if (state.mode !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyToDocument(state);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [state]);

  // Un `PATCH /settings` con `tema`/`modo_color`
  // (desde `/ajustes`, otra pestaña o la CLI) llega por el bus como
  // `ajuste.cambiado` con `after.tema`/`after.modo_color`; se aplica a este
  // tema sin recargar, mismo patrón que `session.tsx` con `after.rol`. El
  // backend usa las mismas palabras que `ThemeName` para
  // `tema`; `modo_color` se traduce (`claro|oscuro|sistema` → `light|dark|system`).
  useEffect(
    () =>
      onVigiaEvent((evento) => {
        if (evento.action !== "ajuste.cambiado") return;
        const tema = evento.after?.tema;
        const modoColor = evento.after?.modo_color;
        setState((s) => {
          let siguiente = s;
          if (esTemaDisponible(tema) && tema !== s.theme) {
            siguiente = { ...siguiente, theme: tema };
          }
          const modo = modoColor === "claro" ? "light" : modoColor === "oscuro" ? "dark" : modoColor === "sistema" ? "system" : null;
          if (modo && modo !== s.mode) {
            siguiente = { ...siguiente, mode: modo };
          }
          return siguiente;
        });
      }),
    [],
  );

  const setTheme = useCallback((theme: ThemeName) => {
    setState((s) => ({ ...s, theme }));
  }, []);

  const setMode = useCallback((mode: ThemeMode) => {
    setState((s) => ({ ...s, mode }));
  }, []);

  const toggleTheme = useCallback((originEvent?: MouseEvent | React.MouseEvent) => {
    applyWithViewTransition(() => {
      setState((s) => {
        if (!HAY_SELECTOR_TEMA) return s;
        const i = TEMAS_DISPONIBLES.findIndex((t) => t.valor === s.theme);
        return { ...s, theme: TEMAS_DISPONIBLES[(i + 1) % TEMAS_DISPONIBLES.length].valor };
      });
    }, originEvent);
  }, []);

  const toggleMode = useCallback((originEvent?: MouseEvent | React.MouseEvent) => {
    applyWithViewTransition(() => {
      setState((s) => ({ ...s, mode: s.mode === "dark" ? "light" : "dark" }));
    }, originEvent);
  }, []);

  const resolvedDark = state.mode === "dark" || (state.mode === "system" && systemPrefersDark());

  const value = useMemo<ThemeContextValue>(
    () => ({ ...state, setTheme, setMode, toggleTheme, toggleMode, resolvedDark }),
    [state, setTheme, setMode, toggleTheme, toggleMode, resolvedDark],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme debe usarse dentro de ThemeProvider");
  return ctx;
}
