/**
 * Detalle de una explicación: barras horizontales con las importancias
 * (global) o las contribuciones con signo (local), más `result_json`
 * restante en `JsonView`.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router";

import type { Explanation, JsonObject } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { JsonView } from "@/components/vigia";
import { formatoFecha, formatoNumero } from "@/lib/metrics";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { AvisoTipos } from "@/pages/modelos/aviso-tipos";
import { ClaseExplicadaPanel } from "./clase-explicada";
import { useProject } from "@/api/queries";
import { ETIQUETA_KIND, etiquetaVersion } from "./etiquetas";
import {
  colorContribucion,
  crearTooltipRegresion,
  formatoContribucion,
  formatoImportancia,
  LecturaRegresion,
  valorPredicho,
} from "./explicacion-regresion";
import { RankingBarrasFijo } from "./ranking-barras-fijo";
import { TooltipBarra } from "./TooltipBarra";

interface Fila {
  feature: string;
  valor: number;
  rule: string | null;
}

const TOP = 20;

function extraerFilas(result: JsonObject | null): Fila[] {
  if (!result || typeof result !== "object" || Array.isArray(result)) return [];
  const features = (result as JsonObject).features;
  if (!Array.isArray(features)) return [];
  return features
    .filter((f): f is JsonObject => f !== null && typeof f === "object" && !Array.isArray(f))
    .map((f) => ({
      feature: typeof f.feature === "string" ? f.feature : String(f.feature ?? ""),
      valor: typeof f.importance === "number" ? f.importance : 0,
      rule: typeof f.rule === "string" ? f.rule : null,
    }))
    .sort((a, b) => Math.abs(b.valor) - Math.abs(a.valor));
}

export interface DetalleExplicacionProps {
  explicacion: Explanation;
  /** Etiqueta del lote con la misma numeración que el selector y la tabla (p.ej. "#8 e2_recovery"). */
  loteEtiqueta?: string;
}

export function DetalleExplicacion({ explicacion, loteEtiqueta }: DetalleExplicacionProps) {
  const [verTodas, setVerTodas] = useState(false);
  const esLocal = explicacion.kind === "local_lime";
  const navegar = useNavigate();
  // En multiclase se dice qué clase o conjunto explica y, en la local, las `k` probabilidades.
  const tarea = useTipoTarea(explicacion.project_id);
  // «versión» con la etiqueta de la pantalla de versiones, no con el id interno.
  const versiones = useProject(explicacion.project_id).data?.versions;
  const multiclase = tarea.caps?.selectorClaseExplicacion === true;
  // En regresión las importancias y las contribuciones van en la unidad de la salida.
  const regresion = tarea.caps?.metricas === "regresion";
  const unidad = tarea.unidad;
  const tooltip = useMemo(() => (regresion ? crearTooltipRegresion(unidad, esLocal) : TooltipBarra), [regresion, unidad, esLocal]);

  // La local lleva la cifra en la barra (en regresión, en la unidad de la salida).
  const etiquetaBarra = regresion
    ? (v: number) => (esLocal ? formatoContribucion(v, unidad) : formatoImportancia(v, unidad))
    : esLocal
      ? (v: number) => formatoNumero(v, 3)
      : undefined;
  const filas = useMemo(() => extraerFilas(explicacion.result), [explicacion.result]);
  const visibles = verTodas ? filas : filas.slice(0, TOP);
  const otras = filas.length > TOP;

  const resultObjeto =
    explicacion.result && typeof explicacion.result === "object" && !Array.isArray(explicacion.result)
      ? (explicacion.result as JsonObject)
      : null;
  // Los campos de primer nivel que no aplican a este tipo de
  // explicación (p.ej. `motivo`/`row_seq`/`prob_favorable` en `global_shap`)
  // llegan `null` del backend. `JsonView` los pintaría como texto literal
  // "null" fuera de <code>/<pre>; se filtran aquí (fuera de mi frontera
  // tocar `JsonView.tsx`, componente compartido con otras pantallas) y, si
  // no queda nada que enseñar, se omite el visor entero en vez de mostrar
  // un `null` suelto.
  const restoResultado = resultObjeto
    ? Object.fromEntries(
        Object.entries(resultObjeto).filter(
          ([clave, valor]) =>
            clave !== "features" &&
            valor !== null &&
            // Las probabilidades por clase y la clase explicada ya salen en su panel.
            !(multiclase && (clave === "probabilities" || clave === "clase_explicada")) &&
            // El valor predicho ya sale en su línea.
            !(regresion && clave === "prediction_value"),
        ),
      )
    : null;
  const hayResto = restoResultado !== null && Object.keys(restoResultado).length > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {ETIQUETA_KIND[explicacion.kind]} · versión {etiquetaVersion(versiones, explicacion.model_version_id)}
          {explicacion.batch_id !== null ? ` · lote ${loteEtiqueta ?? "no disponible"}` : ""}
          {explicacion.row_seq !== null ? ` · fila ${explicacion.row_seq}` : ""}
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Calculada el {formatoFecha(explicacion.created_at)}
          {explicacion.result &&
          typeof explicacion.result === "object" &&
          !Array.isArray(explicacion.result) &&
          typeof (explicacion.result as JsonObject).prob_favorable === "number"
            ? ` · probabilidad ${multiclase ? "del conjunto favorable" : "favorable"} ${formatoNumero((explicacion.result as JsonObject).prob_favorable as number)}${
                multiclase && typeof (explicacion.result as JsonObject).clase_explicada === "string" ? " (no es la de la clase explicada)" : ""
              }`
            : ""}
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <AvisoTipos aviso={explicacion.aviso_tipos} />
        {multiclase && explicacion.available ? (
          <ClaseExplicadaPanel
            resultado={resultObjeto}
            params={explicacion.params as JsonObject | null}
            local={esLocal}
            clases={tarea.clases}
            favorables={tarea.favorables}
          />
        ) : null}
        {regresion && explicacion.available ? (
          <LecturaRegresion kind={explicacion.kind} unidad={unidad} predicho={valorPredicho(resultObjeto)} />
        ) : null}
        {!explicacion.available ? (
          <p className="text-sm text-muted-foreground">
            No disponible{explicacion.motivo ? `: ${explicacion.motivo}` : "."}
          </p>
        ) : filas.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin importancias en el resultado.</p>
        ) : (
          <>
            <RankingBarrasFijo
              datos={visibles}
              etiqueta={etiquetaBarra}
              claveCategoria="feature"
              claveValor="valor"
              tooltip={tooltip}
              color={(fila) =>
                esLocal
                  ? regresion
                    ? colorContribucion(fila.valor)
                    : `var(${fila.valor < 0 ? "--state-alert" : "--state-ok"})`
                  : "var(--chart-1)"
              }
              onClickBarra={
                esLocal
                  ? undefined
                  : (fila) => navegar(`/monitores/deriva?variable=${encodeURIComponent(fila.feature)}`)
              }
            />
            {!esLocal ? (
              <p className="text-xs text-muted-foreground">Clic en una variable para ver su distribución en deriva</p>
            ) : null}
            {otras ? (
              <Button type="button" size="sm" variant="outline" onClick={() => setVerTodas((v) => !v)}>
                {verTodas ? `Ver solo las ${TOP} primeras` : `Ver todas (${filas.length})`}
              </Button>
            ) : null}
          </>
        )}
        {hayResto ? <JsonView valor={restoResultado} abiertoHasta={1} /> : null}
      </CardContent>
    </Card>
  );
}

export default DetalleExplicacion;
