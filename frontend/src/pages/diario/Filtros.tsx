/** Fila de filtros del diario: carril, tipo de objeto, correlación, fecha y alcance. */

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { DESCRIPCION_CARRIL, ETIQUETA_CARRIL } from "@/lib/metrics";
import type { ActorKind } from "@/api/types";
import { CARRILES, TIPOS_OBJETO, etiquetaObjeto } from "./etiquetas";

const TODOS = "__todos__";

export interface FiltrosProps {
  actorKind: ActorKind | null;
  onActorKindChange: (v: ActorKind | null) => void;
  objectType: string | null;
  onObjectTypeChange: (v: string | null) => void;
  correlationId: string;
  onCorrelationIdChange: (v: string) => void;
  since: string;
  onSinceChange: (v: string) => void;
  soloProyecto: boolean;
  onSoloProyectoChange: (v: boolean) => void;
  proyectoNombre: string | null;
  enVivo: boolean;
  onEnVivoChange: (v: boolean) => void;
}

export function Filtros({
  actorKind,
  onActorKindChange,
  objectType,
  onObjectTypeChange,
  correlationId,
  onCorrelationIdChange,
  since,
  onSinceChange,
  soloProyecto,
  onSoloProyectoChange,
  proyectoNombre,
  enVivo,
  onEnVivoChange,
}: FiltrosProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="filtro-carril">Carril</Label>
        <Select
          value={actorKind ?? TODOS}
          onValueChange={(v) => onActorKindChange(v === TODOS ? null : (v as ActorKind))}
        >
          <SelectTrigger id="filtro-carril" className="w-40" size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todos los carriles</SelectItem>
            {CARRILES.map((c) => (
              <SelectItem key={c} value={c} title={DESCRIPCION_CARRIL[c]}>
                {ETIQUETA_CARRIL[c]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="filtro-objeto">Tipo de objeto</Label>
        <Select
          value={objectType ?? TODOS}
          onValueChange={(v) => onObjectTypeChange(v === TODOS ? null : v)}
        >
          <SelectTrigger id="filtro-objeto" className="w-44" size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todos los objetos</SelectItem>
            {TIPOS_OBJETO.map((t) => (
              <SelectItem key={t} value={t}>
                {etiquetaObjeto(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="filtro-correlacion">Correlación</Label>
        <Input
          id="filtro-correlacion"
          value={correlationId}
          onChange={(e) => onCorrelationIdChange(e.target.value)}
          placeholder="id de correlación"
          className="h-8 w-52"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="filtro-desde">Desde</Label>
        <Input
          id="filtro-desde"
          type="date"
          value={since}
          onChange={(e) => onSinceChange(e.target.value)}
          className="h-8 w-40"
        />
      </div>

      <Button
        type="button"
        variant={soloProyecto ? "default" : "outline"}
        size="sm"
        aria-pressed={soloProyecto}
        onClick={() => onSoloProyectoChange(!soloProyecto)}
        disabled={proyectoNombre === null}
      >
        {proyectoNombre ? `Solo ${proyectoNombre}` : "Solo este proyecto"}
      </Button>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="filtro-en-vivo">Seguir en vivo</Label>
        <div className="flex h-8 items-center">
          <Switch
            id="filtro-en-vivo"
            checked={enVivo}
            onCheckedChange={onEnVivoChange}
            label="Seguir en vivo"
          />
        </div>
      </div>
    </div>
  );
}
