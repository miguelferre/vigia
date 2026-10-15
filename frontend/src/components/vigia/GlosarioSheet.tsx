/**
 * Glosario local en un sheet: "Más información" desde
 * una pantalla de monitor abre esto, no una ruta nueva ni un enlace externo
 * (el producto funciona sin red).
 *
 * "Ver toda la ayuda" sube junto al título (antes al final
 * del todo) y el cuerpo deja de listar el glosario entero: ahora son los
 * bloques "Qué es", "Cómo se lee", "Umbral" y "Fórmula" de
 * `GET /api/content/metricas` (`ContenidoMetrica`) para la métrica ampliada
 * de la rejilla (o la principal si ninguna está ampliada, decidido por
 * `pages/monitores/cabecera.tsx`), y debajo la entrada de glosario del
 * monitor (`monitor_<tipo>`, la misma que usa `frase-apertura.tsx`).
 *
 * Nota de tipo: `EntradaGlosario` en `api/queries-contenido.ts` declara el
 * campo `descripcion`, pero `src/vigia/content/glosario.json` usa
 * `definicion`. Se lee aquí con fallback a los dos nombres para no romper
 * cuando se corrija uno de los dos lados.
 */

import { AlertCircleIcon } from "lucide-react";
import { Link } from "react-router";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useContenidoMetricasPorTipo, useGlosario } from "@/api/queries-contenido";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { NotaMulticlase } from "./NotaMulticlase";
import { metricLabel, formatoCorto } from "@/lib/metrics";
import type { MonitorType } from "@/api/types";

export interface GlosarioSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  monitorType: MonitorType;
  /** Métrica ampliada o principal; `null` mientras no hay ninguna (rejilla vacía o sin cargar). */
  metricKey: string | null;
}

/** Texto de una entrada del glosario, tolerante al nombre de campo real. */
function textoEntrada(entrada: { descripcion?: string; definicion?: string }): string {
  return entrada.definicion ?? entrada.descripcion ?? "";
}

/** `umbral_por_defecto` es un `dict[str, float]` (p. ej. `{"limite_inferior": 0.8}`, ver `build/gen_content.py`): sin claves fijas de antemano. */
function ETIQUETA_UMBRAL(clave: string): string {
  if (clave === "limite_inferior") return "Límite inferior";
  if (clave === "limite_superior") return "Límite superior";
  return clave;
}

export function GlosarioSheet({ open, onOpenChange, monitorType, metricKey }: GlosarioSheetProps) {
  const glosarioQ = useGlosario();
  // la ayuda sale resuelta por tipo (`ayudaPorTipo`); sin proyecto, la binaria y la nota multiclase.
  const metricasQ = useContenidoMetricasPorTipo();
  const { tipo, cargando: tipoCargando } = useTipoTarea();
  const entradaMonitor = glosarioQ.data?.[`monitor_${monitorType}`];
  const ayudaMetrica = metricKey ? metricasQ.data?.[metricKey] : undefined;
  const cargando = glosarioQ.isLoading || metricasQ.isLoading || tipoCargando;
  const error = glosarioQ.isError || metricasQ.isError;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <div className="flex items-center justify-between gap-3">
            <SheetTitle>Glosario</SheetTitle>
            <Link
              to="/ayuda"
              onClick={() => onOpenChange(false)}
              className="text-sm font-semibold text-link hover:underline"
            >
              Ver toda la ayuda
            </Link>
          </div>
          <SheetDescription>
            Qué mide la métrica ampliada de este monitor y qué vigila el monitor en conjunto.
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-4 px-4 pb-4">
          {cargando ? (
            <>
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-16 w-full" />
            </>
          ) : error ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <AlertCircleIcon className="size-4" aria-hidden="true" />
              El glosario no está disponible ahora mismo.
            </p>
          ) : (
            <>
              {metricKey && ayudaMetrica ? (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">{ayudaMetrica.etiqueta}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3 pt-0 text-sm text-muted-foreground">
                    <div>
                      <p className="text-xs font-semibold text-foreground">Qué es</p>
                      <p>{ayudaMetrica.que_mide}</p>
                      <NotaMulticlase ayuda={ayudaMetrica} ayudaGeneral={tipo === undefined} />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-foreground">Cómo se lee</p>
                      <p>{ayudaMetrica.como_se_lee}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-foreground">Umbral</p>
                      <p>
                        {ayudaMetrica.umbral_por_defecto
                          ? Object.entries(ayudaMetrica.umbral_por_defecto)
                              .map(([clave, valor]) => `${ETIQUETA_UMBRAL(clave)}: ${formatoCorto(valor)}`)
                              .join(" · ")
                          : "Sin umbral por defecto para esta métrica."}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-foreground">Fórmula</p>
                      <p>{ayudaMetrica.formula ?? ayudaMetrica.nota ?? "Sin fórmula reproducible en Vigía."}</p>
                    </div>
                  </CardContent>
                </Card>
              ) : metricKey ? (
                <p className="text-sm text-muted-foreground">
                  Sin ayuda para {metricLabel(metricKey)}.
                </p>
              ) : null}
              {entradaMonitor ? (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">{entradaMonitor.etiqueta}</CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0 text-sm text-muted-foreground">
                    {textoEntrada(entradaMonitor)}
                  </CardContent>
                </Card>
              ) : null}
              {!metricKey && !entradaMonitor ? (
                <p className="text-sm text-muted-foreground">Sin entradas todavía.</p>
              ) : null}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
