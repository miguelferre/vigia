/**
 * Error de una consulta con su botón «Reintentar». Una
 * sola forma para las pantallas que enseñaban el error sin salida: el texto
 * llega ya en español de `mensajeDeError` (red caída incluida) y el botón
 * vuelve a lanzar la consulta.
 */

import { RefreshCwIcon } from "lucide-react";

import { mensajeDeError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface ErrorDeConsultaProps {
  /** Lo que no se pudo cargar, para la frase: «los riesgos», «el cálculo». */
  que: string;
  error: unknown;
  onReintentar: () => void;
  className?: string;
}

export function ErrorDeConsulta({ que, error, onReintentar, className }: ErrorDeConsultaProps) {
  return (
    <div className={cn("flex flex-col items-start gap-2", className)}>
      <p role="alert" className="text-sm text-destructive">
        Error al cargar {que}: {mensajeDeError(error)}
      </p>
      <Button type="button" variant="outline" size="sm" onClick={onReintentar}>
        <RefreshCwIcon className="size-4" aria-hidden="true" />
        Reintentar
      </Button>
    </div>
  );
}
