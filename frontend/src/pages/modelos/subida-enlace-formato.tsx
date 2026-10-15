/**
 * Enlace «Formato y plantillas»: lleva a la sección «Datos»
 * de la Ayuda (`/ayuda#datos`), con las columnas de cada fichero y las seis
 * plantillas CSV. Dentro de un diálogo se abre en otra pestaña, para no
 * perder el fichero ni lo ya elegido.
 */

import { Link } from "react-router";

import { cn } from "@/lib/utils";

export const RUTA_GUIA_DATOS = "/ayuda#datos";

/** Anclas de la sección «Datos» de la Ayuda a las que se enlaza desde el alta y el registro de uso. */
export const ANCLA_CLASE_FAVORABLE = "clase-favorable";
export const ANCLA_CODIFICACION = "codificacion-inconclusa";

interface Props {
  /** Texto del enlace; por defecto, «Formato y plantillas». */
  texto?: string;
  /** Ancla dentro de la Ayuda; sin ella, el principio de la sección «Datos». */
  ancla?: string;
  /** Abre la guía en otra pestaña (diálogos con trabajo a medias). */
  nuevaPestana?: boolean;
  className?: string;
}

export function EnlaceFormato({ texto = "Formato y plantillas", ancla, nuevaPestana = false, className }: Props) {
  return (
    <Link
      to={ancla ? `/ayuda#${ancla}` : RUTA_GUIA_DATOS}
      className={cn("text-sm text-link hover:underline", className)}
      {...(nuevaPestana ? { target: "_blank", rel: "noopener noreferrer" } : {})}
    >
      {texto}
      {nuevaPestana ? <span className="sr-only"> (se abre en otra pestaña)</span> : null}
    </Link>
  );
}
