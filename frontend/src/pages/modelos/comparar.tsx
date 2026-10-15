/**
 * Pestaña «Comparar» de `/modelos/:id`: dos versiones
 * del mismo modelo, cada una contra su propia línea base, métrica a métrica.
 * Solo aparece con dos versiones o más (`detalle.tsx`). La tabla vive en
 * `comparar-tabla.tsx` y los textos de ayuda en `comparar-textos.ts`.
 */

import { useState } from "react";
import { CircleHelpIcon } from "lucide-react";

import { mensajeDeError } from "@/api/client";
import { useProject } from "@/api/queries";
import { useComparacionVersiones, type VentanaComparacion } from "@/api/queries-versiones";
import { EmptyState } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { esGrupoClase } from "@/lib/tipo-tarea";
import { AlertasVivas } from "./comparar-alertas";
import { TablaComparacion } from "./comparar-tabla";
import {
  AVISO_DESLIZAR_TABLA,
  AYUDA_COMPARAR,
  AYUDA_COMPARAR_REGRESION,
  ETIQUETA_VENTANA,
  TITULO_AYUDA_COMPARAR,
} from "./comparar-textos";

interface SelectorProps {
  id: string;
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  opciones: { valor: string; texto: string }[];
}

function Selector({ id, etiqueta, valor, onCambio, opciones }: SelectorProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{etiqueta}</Label>
      <Select value={valor} onValueChange={onCambio}>
        <SelectTrigger id={id} className="min-w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {opciones.map((o) => (
            <SelectItem key={o.valor} value={o.valor}>
              {o.texto}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default function CompararTab({ projectId }: { projectId: number }) {
  const { data: proyecto } = useProject(projectId);
  // En regresión los errores llevan la unidad y la ayuda explica la regla de «igual».
  const { caps, unidad } = useTipoTarea(projectId);
  const unidadTabla = caps?.unidad ? unidad : undefined;
  // `""` = por defecto: la API resuelve la activa anterior (A) y la activa (B).
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [ventana, setVentana] = useState<VentanaComparacion>("ultimo");
  const [ayudaAbierta, setAyudaAbierta] = useState(false);

  const q = useComparacionVersiones(projectId, a ? Number(a) : null, b ? Number(b) : null, ventana);
  const datos = q.data;
  const versiones = (proyecto?.versions ?? []).filter((v) => v.id !== null);
  const opciones = versiones.map((v) => ({ valor: String(v.id), texto: v.label }));
  const valorA = a || (datos ? String(datos.version_a.id) : "");
  const valorB = b || (datos ? String(datos.version_b.id) : "");
  const filasPorClase = (datos?.filas ?? []).filter((f) => esGrupoClase(f.group_code));
  const filasSinClase = (datos?.filas ?? []).filter((f) => !esGrupoClase(f.group_code));

  return (
    <div className="flex flex-col gap-4 pt-4" data-t10-comparar="">
      <div className="flex flex-wrap items-end gap-3">
        <Selector id="cmp-a" etiqueta="Versión A (anterior)" valor={valorA} onCambio={setA} opciones={opciones} />
        <Selector id="cmp-b" etiqueta="Versión B (nueva)" valor={valorB} onCambio={setB} opciones={opciones} />
        <Selector
          id="cmp-ventana"
          etiqueta="Ventana"
          valor={ventana}
          onCambio={(v) => setVentana(v as VentanaComparacion)}
          opciones={(["ultimo", "todos"] as const).map((k) => ({ valor: k, texto: ETIQUETA_VENTANA[k] }))}
        />
        <Button
          size="sm"
          variant="outline"
          aria-expanded={ayudaAbierta}
          aria-controls="cmp-ayuda"
          onClick={() => setAyudaAbierta((x) => !x)}
        >
          <CircleHelpIcon className="size-4" aria-hidden="true" />
          {TITULO_AYUDA_COMPARAR}
        </Button>
      </div>

      {ayudaAbierta ? (
        <div id="cmp-ayuda" className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 p-4 text-sm">
          <h3 className="font-semibold">{TITULO_AYUDA_COMPARAR}</h3>
          {[...AYUDA_COMPARAR, ...(caps?.metricas === "regresion" ? [AYUDA_COMPARAR_REGRESION] : [])].map((p) => (
            <p key={p}>{p}</p>
          ))}
        </div>
      ) : null}

      {valorA && valorA === valorB ? (
        <EmptyState titulo="Elige dos versiones distintas" descripcion="A y B apuntan a la misma versión." />
      ) : q.isError ? (
        <EmptyState
          titulo="No se pudo comparar"
          descripcion={mensajeDeError(q.error)}
          accion={
            <Button size="sm" variant="outline" onClick={() => q.refetch()}>
              Reintentar
            </Button>
          }
        />
      ) : q.isLoading || !datos ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <p className="text-sm text-muted-foreground" data-t10-versiones="">
            Versión A «{datos.version_a.label}» ({datos.version_a.n_lotes_evaluados} lotes evaluados) frente a la B «
            {datos.version_b.label}» ({datos.version_b.n_lotes_evaluados} lotes evaluados). Ventana:{" "}
            {ETIQUETA_VENTANA[datos.ventana].toLowerCase()}.
          </p>
          <p className="text-xs text-muted-foreground sm:hidden">
            {AVISO_DESLIZAR_TABLA}
          </p>
          {datos.motivo ? (
            <p className="rounded-md border border-border bg-muted/40 p-3 text-sm" data-testid="comparar-motivo">
              {datos.motivo.replace(/\.$/, "")}.
            </p>
          ) : null}
          <TablaComparacion
            filas={filasSinClase}
            etiquetaA={datos.version_a.label}
            etiquetaB={datos.version_b.label}
            tipo={proyecto?.task_type}
            unidad={unidadTabla}
          />
          {filasPorClase.length > 0 ? (
            // Las medidas por clase no son grupos protegidos ni tienen umbral; van aparte y plegadas.
            <details data-t10-por-clase="">
              <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
                Medidas por clase ({filasPorClase.length} filas, sin umbral)
              </summary>
              <div className="mt-2">
                <TablaComparacion
                  filas={filasPorClase}
                  etiquetaA={datos.version_a.label}
                  etiquetaB={datos.version_b.label}
                  tipo={proyecto?.task_type}
                />
              </div>
            </details>
          ) : null}
          <AlertasVivas alertas={datos.alertas_vivas} nota={datos.nota_alertas} />
        </>
      )}
    </div>
  );
}
