// shadcn/ui · sonner. Adaptado: el modo claro/oscuro sale del hook de tema
// propio de Vigía (src/themes/theme.tsx) en vez de next-themes, y los colores
// del toast se toman de los tokens de tokens.css. Posición abajo a la
// izquierda y 4 s: abajo a la derecha tapaba «Siguiente» del
// panel de la demo guiada, que es fijo a la derecha.

import type { CSSProperties } from "react";
import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

import { useTheme } from "@/themes/theme";

const Toaster = ({ ...props }: ToasterProps) => {
  const { resolvedDark } = useTheme();

  return (
    <Sonner
      theme={resolvedDark ? "dark" : "light"}
      className="toaster group"
      position="bottom-left"
      duration={4000}
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--card)",
          "--normal-text": "var(--card-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "0.5rem",
        } as CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
