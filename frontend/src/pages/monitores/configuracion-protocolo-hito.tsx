/**
 * Un bloque del editor de protocolo (admite
 * hitos extra). Aparte de `configuracion-protocolo.tsx` para no superar los
 * 9 KB de ese fichero.
 */

import { ArrowDownIcon, ArrowUpIcon, PlusIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { HitoProtocoloEdit } from "./tipos";

/** Los cinco hitos estándar: posición y clave fijas; el protocolo
 * debe contenerlos siempre, en este orden relativo. */
export const HITOS_ESTANDAR: readonly string[] = [
  "deteccion",
  "triaje",
  "investigacion",
  "decision",
  "seguimiento",
];

export function esHitoEstandar(key: string): boolean {
  return HITOS_ESTANDAR.includes(key);
}

/** Etiqueta fija solo para los cinco estándar; un hito extra usa su propio
 * `titulo` y el número de orden que le toca en la lista. */
const ETIQUETA_HITO_FIJA: Record<string, string> = {
  deteccion: "1 · Detección",
  triaje: "2 · Triaje",
  investigacion: "3 · Investigación",
  decision: "4 · Decisión",
  seguimiento: "5 · Seguimiento",
};

interface EntregablesEditorProps {
  entregables: string[];
  onCambiar: (entregables: string[]) => void;
  hitoKey: string;
}

function EntregablesEditor({ entregables, onCambiar, hitoKey }: EntregablesEditorProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>Entregables</Label>
      {entregables.map((valor, i) => (
        <div key={`${hitoKey}-${i}`} className="flex items-center gap-1.5">
          <Input
            value={valor}
            onChange={(e) => {
              const siguiente = [...entregables];
              siguiente[i] = e.target.value;
              onCambiar(siguiente);
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Quitar entregable"
            onClick={() => onCambiar(entregables.filter((_, j) => j !== i))}
          >
            <XIcon className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => onCambiar([...entregables, ""])}
      >
        <PlusIcon className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
        Añadir entregable
      </Button>
    </div>
  );
}

export interface BloqueHitoProps {
  hito: HitoProtocoloEdit;
  /** Posición 1-based en la lista actual (etiqueta de los hitos extra). */
  orden: number;
  onCambiar: (siguiente: HitoProtocoloEdit) => void;
  /** Solo para un hito extra: lo quita de la lista en edición. */
  onQuitar?: () => void;
  onSubir?: () => void;
  onBajar?: () => void;
  puedeSubir?: boolean;
  puedeBajar?: boolean;
}

export function BloqueHito({
  hito,
  orden,
  onCambiar,
  onQuitar,
  onSubir,
  onBajar,
  puedeSubir,
  puedeBajar,
}: BloqueHitoProps) {
  const estandar = esHitoEstandar(hito.key);
  // El número es la posición real (`orden`, prop), no el fijo del
  // diccionario: un hito extra puede moverse por delante de un estándar
  // («Subir»/«Bajar») y dos filas no deben mostrar el mismo número.
  const etiqueta = estandar
    ? `${orden} · ${ETIQUETA_HITO_FIJA[hito.key].split(" · ")[1]}`
    : `${orden} · ${hito.titulo || "Hito nuevo"}`;

  return (
    <div className="flex flex-col gap-2.5 rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-tertiary">{etiqueta}</p>
        {!estandar ? (
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Subir hito"
              disabled={!puedeSubir}
              onClick={onSubir}
            >
              <ArrowUpIcon className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Bajar hito"
              disabled={!puedeBajar}
              onClick={onBajar}
            >
              <ArrowDownIcon className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={onQuitar}>
              <XIcon className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
              Quitar
            </Button>
          </div>
        ) : null}
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`protocolo-titulo-${hito.key}`}>Título</Label>
        <Input
          id={`protocolo-titulo-${hito.key}`}
          value={hito.titulo}
          onChange={(e) => onCambiar({ ...hito, titulo: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`protocolo-descripcion-${hito.key}`}>Descripción</Label>
        <Textarea
          id={`protocolo-descripcion-${hito.key}`}
          rows={2}
          value={hito.descripcion}
          onChange={(e) => onCambiar({ ...hito, descripcion: e.target.value })}
        />
      </div>
      <EntregablesEditor
        entregables={hito.entregables}
        hitoKey={hito.key}
        onCambiar={(entregables) => onCambiar({ ...hito, entregables })}
      />
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor={`protocolo-responsable-${hito.key}`}>Responsable</Label>
          <Input
            id={`protocolo-responsable-${hito.key}`}
            value={hito.responsable}
            placeholder="Sin asignar"
            onChange={(e) => onCambiar({ ...hito, responsable: e.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`protocolo-plazo-${hito.key}`}>Plazo (días)</Label>
          <Input
            id={`protocolo-plazo-${hito.key}`}
            type="number"
            min="0"
            step="1"
            value={hito.plazoDiasTexto}
            placeholder="Sin plazo"
            onChange={(e) => onCambiar({ ...hito, plazoDiasTexto: e.target.value })}
          />
        </div>
      </div>
    </div>
  );
}
