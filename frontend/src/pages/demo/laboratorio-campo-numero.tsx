/**
 * Campo numérico del laboratorio (la
 * definición viene del contenido). Un `<input type="number">` nativo descarta en silencio cualquier
 * separador decimal que el locale del navegador no reconozca en ese
 * instante: verificado en vivo, escribir "1.5" deja el campo en "15" sin
 * avisar y sin rechazar, y el ensayo se lanza con un número que nadie ha
 * pedido. Aquí el campo es de texto: acepta coma y punto como separador
 * decimal, y lo que no se puede interpretar (o cae fuera del rango del
 * generador) se ve como error visible antes de poder ejecutar. Nunca se
 * corrompe en silencio. La interpretación vive en `laboratorio-campo.ts`
 * (solo funciones, para que el refresco rápido de Vite no proteste).
 */

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { DefinicionParametro } from "./laboratorio-parametros";

export interface CampoNumeroProps {
  definicion: DefinicionParametro;
  texto: string;
  error: string | null;
  onChange: (texto: string) => void;
}

export function CampoNumero({ definicion: p, texto, error, onChange }: CampoNumeroProps) {
  const id = `lab-${p.clave}`;
  const idError = `${id}-error`;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{p.etiqueta}</Label>
      <Input
        id={id}
        type="text"
        inputMode="decimal"
        className="w-36"
        value={texto}
        aria-invalid={error !== null}
        aria-describedby={error ? idError : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {error ? (
        <p id={idError} className="text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
