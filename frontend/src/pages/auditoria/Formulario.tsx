/**
 * Un paso del stepper: preguntas de una plantilla agrupadas por sección, con
 * un `Textarea` por pregunta.
 */

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { DossierPlantillaFormulario } from "@/api/types";
import { agruparPorSeccion } from "./stepper-datos";

export interface FormularioProps {
  formulario: DossierPlantillaFormulario | undefined;
  respuestas: Record<string, string>;
  onChange: (preguntaId: string, texto: string) => void;
}

export function Formulario({ formulario, respuestas, onChange }: FormularioProps) {
  const grupos = agruparPorSeccion(formulario);

  if (!formulario) {
    return <p className="text-sm text-muted-foreground">Cargando la plantilla…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      {formulario.quien ? (
        <p className="text-sm text-muted-foreground">{formulario.quien}</p>
      ) : null}
      {Array.from(grupos.entries()).map(([seccion, preguntas]) => (
        <div key={seccion} className="flex flex-col gap-4">
          <h3 className="text-sm font-semibold text-tertiary">{seccion}</h3>
          {preguntas.map((pregunta) => (
            <div key={pregunta.id} className="flex flex-col gap-1.5">
              <Label htmlFor={`pregunta-${pregunta.id}`}>{pregunta.texto}</Label>
              <Textarea
                id={`pregunta-${pregunta.id}`}
                rows={3}
                value={respuestas[pregunta.id] ?? ""}
                onChange={(e) => onChange(pregunta.id, e.target.value)}
              />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
