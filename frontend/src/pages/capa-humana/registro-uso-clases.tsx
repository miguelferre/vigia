/**
 * Registro de uso de un modelo multiclase: la
 * decisión del profesional, la salida del modelo y la verdad van como nombres
 * de clase. No hay pregunta de «decisión favorable»: la inversión por
 * `valor_favorable` no se admite y el registro se guarda tal cual. Sustituye a
 * `registro-uso-favorable.tsx` en el bloque de subida.
 */

interface Props {
  clases: string[];
  favorables: string[];
}

export function ClasesRegistro({ clases, favorables }: Props) {
  return (
    <div className="flex flex-col gap-2" data-testid="registro-uso-clases">
      <p className="text-sm font-medium">Las decisiones van con el nombre de la clase</p>
      <p className="text-xs text-muted-foreground">
        En este modelo, las columnas human_decision, model_output y ground_truth llevan el nombre de una de sus
        clases. No valen refer ni no-refer. El registro se guarda tal como llega. Una clase que
        no esté en esta lista da error con la fila y las clases válidas.
      </p>
      <ul className="flex flex-wrap gap-1.5" aria-label="Clases del modelo">
        {clases.map((c) => {
          const favorable = favorables.includes(c);
          return (
            <li
              key={c}
              className={`rounded-md border px-2 py-0.5 text-xs [overflow-wrap:anywhere] ${
                favorable ? "border-primary/50 bg-primary/5" : "border-border bg-muted/40"
              }`}
            >
              <code>{c}</code>
              {favorable ? <span className="text-muted-foreground"> · favorable</span> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
