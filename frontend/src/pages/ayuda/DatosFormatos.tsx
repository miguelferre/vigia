/**
 * Formatos admitidos, clase favorable y codificación «inconclusa» de la guía
 * de datos (`/ayuda#datos`). Cada bloque lleva su id para enlazarlo desde el
 * alta (`/ayuda#clase-favorable`).
 */

import type { GuiaDatos } from "@/api/queries-contenido";

export interface DatosFormatosProps {
  formatos: GuiaDatos["formatos"];
  claseFavorable: GuiaDatos["clase_favorable"];
  inconclusa: GuiaDatos["codificacion_inconclusa"];
  idClase: string;
  idInconclusa: string;
}

function Pasos({ pasos }: { pasos: string[] }) {
  return (
    <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm text-muted-foreground">
      {pasos.map((p) => (
        <li key={p}>{p}</li>
      ))}
    </ol>
  );
}

export function DatosFormatos({ formatos: f, claseFavorable: c, inconclusa: i, idClase, idInconclusa }: DatosFormatosProps) {
  return (
    <div className="flex flex-col gap-5">
      <div id="datos-formatos" className="flex scroll-mt-20 flex-col gap-2">
        <h3 className="text-sm font-semibold">{f.titulo}</h3>
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-muted-foreground">
          <li>{f.ficheros}</li>
          <li>{f.separador}</li>
          <li>{f.codificacion}</li>
          <li>{f.decimal}</li>
          {f.fechas.map((x) => (
            <li key={x.formato}>
              Fechas {x.formato}, por ejemplo <code className="font-mono text-xs">{x.ejemplo}</code>. {x.nota}
            </li>
          ))}
          <li>{f.fecha_ilegible}</li>
          <li>{f.excel}</li>
        </ul>
      </div>
      <div id={idClase} className="flex scroll-mt-20 flex-col gap-2">
        <h3 className="text-sm font-semibold">{c.titulo}</h3>
        <p className="text-sm text-tertiary">{c.pregunta}</p>
        <p className="text-sm text-muted-foreground">{c.frase}</p>
        <Pasos pasos={c.pasos} />
        <ul className="flex flex-col gap-1.5 text-sm">
          {c.ejemplos.map((e) => (
            <li key={e.caso} className="rounded-md border border-border px-3 py-2">
              <span className="block">{e.caso}</span>
              <span className="block text-xs text-muted-foreground">
                Favorable: {e.favorable}. {e.motivo}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div id={idInconclusa} className="flex scroll-mt-20 flex-col gap-2">
        <h3 className="text-sm font-semibold">{i.titulo}</h3>
        <p className="text-sm text-muted-foreground">{i.texto}</p>
        <Pasos pasos={i.pasos} />
      </div>
    </div>
  );
}
