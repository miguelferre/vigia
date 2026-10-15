/**
 * Tabla de cambios entre decisiones: filas = salida del
 * modelo, columnas = decisión del profesional. Sirve a los tres tipos:
 * `refer`/`no-refer` en binario, las clases en multiclase y «dentro del
 * rango»/«fuera del rango» en regresión. Los recuentos salen siempre; la
 * tasa de una fila con menos de `min_n` decisiones se dice con palabras.
 */

import { EmptyState } from "@/components/vigia";
import { useOverridesCambios, type OverridesCambiosFila } from "@/api/queries-regresion";
import { textoRangos } from "@/lib/metrics";

const PORCENTAJE = new Intl.NumberFormat("es-ES", { style: "percent", maximumFractionDigits: 1 });
const ENTERO = new Intl.NumberFormat("es-ES");

/** Primera letra en mayúscula y sin punto final: el motivo de la API llega en minúscula. */
function mayuscula(texto: string): string {
  return texto.replace(/^./, (c) => c.toUpperCase()).replace(/\.$/, "");
}

function Celda({ n, tasa, diagonal }: { n: number; tasa: number | null; diagonal: boolean }) {
  return (
    <td className={`px-3 py-2 text-right tabular-nums ${diagonal ? "" : "bg-muted/40"}`}>
      <span className="font-medium">{ENTERO.format(n)}</span>
      {tasa !== null ? <span className="ml-1.5 text-xs text-muted-foreground">{PORCENTAJE.format(tasa)}</span> : null}
    </td>
  );
}

function Fila({ fila, categorias, minN }: { fila: OverridesCambiosFila; categorias: string[]; minN: number }) {
  const bajoMinimo = fila.tasa_cambio === null && fila.n > 0;
  return (
    <tr className="border-t border-border">
      <th scope="row" className="px-3 py-2 text-left font-normal [overflow-wrap:anywhere]">
        {fila.salida_modelo}
        <span className="ml-1.5 text-xs text-muted-foreground">{ENTERO.format(fila.n)} decisiones</span>
      </th>
      {fila.celdas.map((c, i) => (
        <Celda key={c.decision_profesional} n={c.n} tasa={c.tasa} diagonal={categorias[i] === fila.salida_modelo} />
      ))}
      <td className="px-3 py-2 text-right tabular-nums">
        {bajoMinimo ? (
          <span className="text-xs text-muted-foreground" data-testid="cambios-bajo-minimo">
            Menos de {minN} decisiones
          </span>
        ) : fila.tasa_cambio === null ? (
          "n/d"
        ) : (
          PORCENTAJE.format(fila.tasa_cambio)
        )}
      </td>
    </tr>
  );
}

export function TablaCambios({ projectId }: { projectId: number }) {
  const q = useOverridesCambios(projectId);
  const d = q.data;
  if (q.isError) {
    return <EmptyState titulo="No se pudo cargar la tabla de cambios" descripcion="Qué hacer: recarga la página; si sigue igual, revisa que el servidor esté en marcha." />;
  }
  if (!d) return null;
  if (d.motivo && d.filas.length === 0) {
    return <EmptyState titulo="Sin tabla de cambios" descripcion={`${mayuscula(d.motivo)}.`} />;
  }
  // Solo una regresión con rango trae `rangos_favorables`.
  const rango = textoRangos(d.rangos_favorables as [number | null, number | null][] | null | undefined, d.unidad);
  return (
    <div className="flex flex-col gap-3" data-testid="tabla-cambios">
      <p className="text-sm text-muted-foreground">
        Cada fila es lo que propuso el modelo y cada columna, lo que decidió la persona. La diagonal son las decisiones
        sin cambio; el resto son cambios.
        {rango
          ? ` Una cifra cuenta como dentro del rango si cae ${rango}.`
          : ""}
      </p>
      <div className="overflow-x-auto rounded-md border border-border" role="region" aria-label="Cambios entre decisiones" tabIndex={0}>
        <table className="w-full min-w-[28rem] text-sm">
          <thead className="bg-muted/50 text-xs">
            <tr>
              <th scope="col" className="px-3 py-2 text-left font-medium">El modelo propuso</th>
              {d.categorias.map((c) => (
                <th key={c} scope="col" className="px-3 py-2 text-right font-medium [overflow-wrap:anywhere]">
                  La persona decidió: {c}
                </th>
              ))}
              <th scope="col" className="px-3 py-2 text-right font-medium">Cambios</th>
            </tr>
          </thead>
          <tbody>
            {d.filas.map((f) => (
              <Fila key={f.salida_modelo} fila={f} categorias={d.categorias} minN={d.min_n} />
            ))}
          </tbody>
        </table>
      </div>
      {d.n_sin_decision > 0 ? (
        <p className="text-xs text-muted-foreground">
          {ENTERO.format(d.n_sin_decision)} filas del registro no entran: no traen la decisión de la persona o la salida
          del modelo.
        </p>
      ) : null}
      {d.motivo ? <p className="text-xs text-muted-foreground">{mayuscula(d.motivo)}.</p> : null}
    </div>
  );
}
