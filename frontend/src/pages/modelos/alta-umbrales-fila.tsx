/**
 * Fila de la tabla del paso «Umbrales» (partido de `alta-umbrales.tsx` para
 * no superar 9 KB): un `PropuestaUmbral` con su edición (origen, valor y
 * nota).
 */

import type { PropuestaUmbral, ThresholdOrigen } from "@/api/queries-alta";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TableCell, TableRow } from "@/components/ui/table";
import { esMedidaEnUnidad, formatoMetrica, metricLabel } from "@/lib/metrics";
import { etiquetaCriterio } from "@/pages/monitores/tipos";
import { TEXTO_RELATIVO_PREVALENCIA, etiquetaOrigenUmbral } from "./alta-umbrales-textos";

export interface EdicionUmbral {
  origen: ThresholdOrigen;
  value: string;
  nota: string;
}

const ETIQUETA_KIND: Record<PropuestaUmbral["kind"], string> = {
  lower_limit: "mínimo",
  upper_limit: "máximo",
};

function numero(v: number | null): string {
  return v === null ? "—" : new Intl.NumberFormat("es-ES", { maximumFractionDigits: 4 }).format(v);
}

interface Props {
  propuesta: PropuestaUmbral;
  edicion: EdicionUmbral;
  /** `Project.domain`, para el nombre del origen `criterio_clinico`. */
  dominio?: string;
  onCambiar: (siguiente: EdicionUmbral) => void;
  /** Con la nota única del conjunto, la fila no pide la suya. */
  notaEnConjunto?: boolean;
  /** Unidad de la salida de una regresión (`null` si no la declaró); `undefined` en clasificación. */
  unidad?: string | null;
}

export function FilaUmbral({ propuesta: p, edicion, dominio, onCambiar, unidad, notaEnConjunto }: Props) {
  // Las medidas de error de una regresión llevan su unidad; el resto sale como siempre.
  const valor = (v: number | null) =>
    v !== null && unidad !== undefined && esMedidaEnUnidad(p.metric_key) ? formatoMetrica(p.metric_key, v, unidad) : numero(v);
  // La unidad junto al campo en las medidas de error de una regresión.
  const conUnidad = !!unidad && esMedidaEnUnidad(p.metric_key);
  const origenElegible = edicion.origen !== "fabrica";
  // Sin propuesta (`value` nulo) no se ofrece «Aceptar propuesta» y
  // se enseña el motivo que trae la respuesta.
  const sinPropuesta = p.value === null;
  return (
    <TableRow className="whitespace-normal [&>td]:whitespace-normal">
      <TableCell>
        {metricLabel(p.metric_key)} <span className="text-xs text-muted-foreground">({ETIQUETA_KIND[p.kind]})</span>
      </TableCell>
      <TableCell>{valor(p.valor_linea_base)}</TableCell>
      <TableCell>
        {sinPropuesta ? (
          <span className="block max-w-[15rem] text-xs whitespace-normal text-muted-foreground" data-testid="sin-propuesta">
            {`Sin propuesta${p.motivo ? `: ${p.motivo}` : ""}`}
          </span>
        ) : (
          valor(p.value)
        )}
      </TableCell>
      <TableCell>
        {valor(p.umbral_actual)}{" "}
        <Badge variant="outline">{etiquetaOrigenUmbral(p.origen_actual, dominio)}</Badge>
        {p.metric_key === "area_under_pr" && p.origen_actual === "fabrica" ? (
          <span className="block text-xs whitespace-normal text-muted-foreground" data-testid="umbral-relativo">
            {TEXTO_RELATIVO_PREVALENCIA}
          </span>
        ) : null}
      </TableCell>
      <TableCell className="min-w-[9rem]">
        <div className="flex flex-col gap-1.5">
        <Select
          value={edicion.origen}
          onValueChange={(v) => {
            const origen = v as ThresholdOrigen;
            onCambiar({
              origen,
              // Valor sin formatear (coma de miles ni de decimal): tiene que
              // seguir siendo un número válido para `<input type="number">`
              // y para `Number(...)` al guardar (`alta-umbrales.tsx`).
              value:
                origen === "linea_base"
                  ? String(p.value ?? "")
                  : origen === "fabrica"
                    ? String(p.umbral_actual ?? "")
                    : edicion.value,
              nota: origen === "linea_base" || origen === "fabrica" ? "" : edicion.nota,
            });
          }}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper" sideOffset={4}>
            {sinPropuesta ? (
              <SelectItem value="fabrica">Mantener el actual</SelectItem>
            ) : (
              <SelectItem value="linea_base">Aceptar propuesta</SelectItem>
            )}
            <SelectItem value="fabricante">Fabricante</SelectItem>
            <SelectItem value="criterio_clinico">{etiquetaCriterio(dominio, true)}</SelectItem>
            <SelectItem value="politica_organizacion">Política de la organización</SelectItem>
          </SelectContent>
        </Select>
        {origenElegible && edicion.origen !== "linea_base" && !notaEnConjunto ? (
          <Input
            placeholder="Nota (obligatoria)"
            value={edicion.nota}
            onChange={(e) => onCambiar({ ...edicion, nota: e.target.value })}
          />
        ) : null}
        </div>
      </TableCell>
      <TableCell className="min-w-[9rem]">
        <div className="flex items-center gap-1.5">
          <Input
            type="number"
            step="any"
            className="min-w-[7rem]"
            value={edicion.value}
            disabled={edicion.origen === "linea_base" || edicion.origen === "fabrica"}
            onChange={(e) => onCambiar({ ...edicion, value: e.target.value })}
          />
          {conUnidad ? <span className="text-xs text-muted-foreground" data-testid="umbral-unidad">{unidad}</span> : null}
        </div>
      </TableCell>
    </TableRow>
  );
}
