/**
 * Controles sueltos del formulario de mapeo y del paso «Datos» del alta
 * (partidos de `mapeo-campos.tsx` para quedar por debajo de 9 KB): ayuda en
 * línea, campo de texto, rango numérico y el selector de
 * columnas del fichero subido.
 */

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AVISO_COLUMNA_AUSENTE } from "./alta-textos";
import { idDeEtiqueta } from "./mapeo-dataset-helpers";

const NINGUNA = "__ninguna__";

/** Ayuda en contexto bajo la etiqueta de un campo. */
export function Ayuda({ id, children }: { id: string; children: string }) {
  return (
    <p id={id} className="text-xs leading-snug text-muted-foreground">
      {children}
    </p>
  );
}

export function Campo({
  etiqueta,
  valor,
  onChange,
  tipo = "text",
  ayuda,
}: {
  etiqueta: string;
  valor: string;
  onChange: (v: string) => void;
  tipo?: string;
  ayuda?: string;
}) {
  const id = idDeEtiqueta(etiqueta);
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{etiqueta}</Label>
      <Input
        id={id}
        type={tipo}
        value={valor}
        aria-describedby={ayuda ? `${id}-ayuda` : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {ayuda ? <Ayuda id={`${id}-ayuda`}>{ayuda}</Ayuda> : null}
    </div>
  );
}

export function RangoCampo({
  etiqueta,
  min,
  max,
  onMin,
  onMax,
  idBase,
}: {
  etiqueta: string;
  min: string;
  max: string;
  onMin: (v: string) => void;
  onMax: (v: string) => void;
  /** Prefijo de los ids de los dos campos; por defecto, el derivado de la etiqueta. */
  idBase?: string;
}) {
  const id = idBase ?? idDeEtiqueta(etiqueta);
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`${id}-min`}>{etiqueta}</Label>
      <div className="flex gap-2">
        <Input id={`${id}-min`} type="number" value={min} placeholder="mín" onChange={(e) => onMin(e.target.value)} />
        <Input
          id={`${id}-max`}
          type="number"
          value={max}
          placeholder="máx"
          aria-label={`${etiqueta} máx`}
          onChange={(e) => onMax(e.target.value)}
        />
      </div>
    </div>
  );
}

interface SelectorColumnaProps {
  id: string;
  etiqueta: string;
  valor: string;
  onChange: (v: string) => void;
  /** Columnas del fichero subido. Sin ninguna (fichero sin cabecera leída), cae a una caja de texto. */
  columnas: string[];
  ayuda?: string;
  /** Texto de la opción que deja el campo sin columna; omitido, el campo vacío enseña `placeholder`. */
  ninguna?: string;
  placeholder?: string;
  /** Columna que la plantilla del modelo nombra para este campo; si el fichero no la trae, se avisa. */
  plantillaCol?: string | null;
}

/** Selector de columnas del fichero; lo que no está en él sale marcado «no está en el fichero». */
export function SelectorColumna({
  id,
  etiqueta,
  valor,
  onChange,
  columnas,
  ayuda,
  ninguna,
  placeholder = "Elige una columna",
  plantillaCol = null,
}: SelectorColumnaProps) {
  if (columnas.length === 0) return <Campo etiqueta={etiqueta} valor={valor} onChange={onChange} ayuda={ayuda} />;
  const ausente = valor !== "" && !columnas.includes(valor);
  const plantillaAusente = plantillaCol && !columnas.includes(plantillaCol) && plantillaCol !== valor ? plantillaCol : null;
  const ayudaId = `${id}-ayuda`;
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{etiqueta}</Label>
      <Select value={valor === "" && ninguna ? NINGUNA : valor} onValueChange={(v) => onChange(v === NINGUNA ? "" : v)}>
        <SelectTrigger id={id} className="w-full" aria-describedby={ayuda ? ayudaId : undefined}>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {ninguna ? <SelectItem value={NINGUNA}>{ninguna}</SelectItem> : null}
          {columnas.map((c) => (
            <SelectItem key={c} value={c}>
              {c}
            </SelectItem>
          ))}
          {ausente ? <SelectItem value={valor}>{valor} (no está en el fichero)</SelectItem> : null}
          {plantillaAusente ? (
            <SelectItem value={plantillaAusente} disabled>
              {plantillaAusente} (no está en el fichero)
            </SelectItem>
          ) : null}
        </SelectContent>
      </Select>
      {ayuda ? <Ayuda id={ayudaId}>{ayuda}</Ayuda> : null}
      {plantillaAusente ? (
        <p role="status" className="text-xs text-destructive">
          {AVISO_COLUMNA_AUSENTE(plantillaAusente)}
        </p>
      ) : null}
    </div>
  );
}
