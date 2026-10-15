/**
 * Campos de edición de `configuracion.tsx`: umbrales y config simple
 * (< 9 KB por fichero). `ConfigSimpleEditor` etiqueta cada clave técnica en
 * español y añade su ayuda (diccionario en
 * `configuracion-etiquetas.ts`); una clave sin entrada cae a la clave en
 * crudo, como antes.
 */

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { MetricLabel } from "@/components/vigia";

import { AyudaColumnaUmbral } from "@/pages/modelos/alta-umbrales-cabecera";
import { AYUDA_UMBRALES_MONITOR } from "@/pages/modelos/alta-umbrales-textos";
import { esMedidaEnUnidad, metricLabelPorTipo } from "@/lib/metrics";
import { ETIQUETA_CONFIG, OPCIONES_CONFIG } from "./configuracion-etiquetas";
import type { ConfigSimple, ThresholdEntry } from "./tipos";
import type { ThresholdOrigen } from "@/api/queries-alta";
import { OrigenUmbralEditor } from "./configuracion-umbral-origen";
import { NotaUmbralRelativo } from "./umbral-relativo";
import { textoUnidadMedida } from "./regresion-datos";
import { umbralCambiado, umbralSinEfectoEnMulticlase } from "./umbrales-efectivos";

export interface UmbralesEditorProps {
  umbrales: ThresholdEntry[];
  onCambiar: (idx: number, valor: number) => void;
  /** Proyecto del monitor: la nota de un umbral relativo lee su última medida. */
  projectId?: number;
  /** Calidad multiclase, donde el umbral de fábrica no se evalúa; las etiquetas llevan «macro». */
  multiclaseCalidad?: boolean;
  tipo?: string | null;
  /** Unidad de la salida del proyecto de regresión; los umbrales de error se editan en ella. */
  unidad?: string | null;
  /** Los umbrales al abrir la hoja; una fila con otro valor pide su origen y su nota. */
  iniciales?: ThresholdEntry[];
  dominio?: string;
  /** Regresión con rango: las medidas de pertenencia lo dicen en su etiqueta. */
  conRango?: boolean;
  onOrigen?: (idx: number, origen: ThresholdOrigen) => void;
  onNota?: (idx: number, nota: string) => void;
}

export function UmbralesEditor({
  umbrales, onCambiar, projectId, multiclaseCalidad = false, tipo, unidad, iniciales, dominio, conRango, onOrigen, onNota,
}: UmbralesEditorProps) {
  if (umbrales.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <h3 className="flex items-center gap-1.5 text-sm text-muted-foreground">
        Umbrales
        <AyudaColumnaUmbral ayuda={AYUDA_UMBRALES_MONITOR} conOrigenes />
      </h3>
      <div className="flex flex-col gap-2">
        {umbrales.map((u, idx) => {
          // En calidad multiclase, un umbral de fábrica (o relativo) no se evalúa.
          const sinEfecto = multiclaseCalidad && umbralSinEfectoEnMulticlase(u);
          const relativoBloqueado = sinEfecto && u.relativo_a != null;
          // Un umbral de error de regresión está en la unidad de la salida (o su cuadrado).
          const unidadDelUmbral = unidad && esMedidaEnUnidad(u.metric_key) ? textoUnidadMedida(u.metric_key, unidad) : null;
          return (
            <div key={`${u.metric_key}-${u.kind}`} className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0 flex-1 text-sm">
                  <MetricLabel metrica={u.metric_key} tipo={tipo} conRango={conRango} />{" "}
                  <span className="text-muted-foreground">
                    ({u.kind === "lower_limit" ? "límite inferior" : "límite superior"})
                    {u.relativo_a ? ", relativo a la prevalencia" : ""}
                  </span>
                </span>
                <Input
                  type="number"
                  step="any"
                  value={u.value}
                  className="w-32"
                  disabled={relativoBloqueado}
                  aria-label={`${metricLabelPorTipo(u.metric_key, tipo)}${u.relativo_a ? ", fracción de la mejora de la línea base sobre la prevalencia" : ""}`}
                  onChange={(e) => {
                    // Campo vacío o no numérico: no se toca el valor (nunca se guarda un umbral a null).
                    if (!Number.isNaN(e.target.valueAsNumber)) onCambiar(idx, e.target.valueAsNumber);
                  }}
                />
              </div>
              {unidadDelUmbral ? (
                <p className="text-xs text-muted-foreground" data-testid="umbral-unidad">
                  En {unidadDelUmbral}
                  {u.origen === "linea_base" ? ". Sale de la línea base." : "."}
                </p>
              ) : null}
              {onOrigen && onNota && umbralCambiado(u, iniciales?.[idx]) ? (
                <OrigenUmbralEditor
                  umbral={u}
                  etiqueta={metricLabelPorTipo(u.metric_key, tipo)}
                  dominio={dominio}
                  onOrigen={(o) => onOrigen(idx, o)}
                  onNota={(n) => onNota(idx, n)}
                />
              ) : null}
              {u.relativo_a && !sinEfecto && projectId !== undefined ? (
                <NotaUmbralRelativo projectId={projectId} metricKey={u.metric_key} />
              ) : null}
              {relativoBloqueado ? (
                <p className="text-xs text-muted-foreground">
                  En multiclase este umbral relativo a la prevalencia no se evalúa: no hay una prevalencia única.
                </p>
              ) : sinEfecto ? (
                <p className="text-xs text-muted-foreground">
                  De fábrica: en multiclase no se evalúa. Si lo cambias, pasa a ser tuyo y se empieza a evaluar.
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export interface ConfigSimpleEditorProps {
  config: ConfigSimple;
  onCambiar: (clave: string, valor: string | number | boolean) => void;
  /** Claves que el backend rechaza siempre (se muestran deshabilitadas, con el motivo). */
  clavesBloqueadas?: Record<string, string>;
}

export function ConfigSimpleEditor({ config, onCambiar, clavesBloqueadas }: ConfigSimpleEditorProps) {
  const entradas = Object.entries(config);
  if (entradas.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm text-muted-foreground">Configuración</h3>
      {entradas.map(([k, v]) => {
        const motivoBloqueo = clavesBloqueadas?.[k];
        // Etiqueta y ayuda del diccionario; sin entrada, la clave en crudo.
        const info = ETIQUETA_CONFIG[k];
        const opciones = OPCIONES_CONFIG[k];
        return (
          <div key={k} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor={`config-${k}`}>{info?.etiqueta ?? k}</Label>
              {opciones && typeof v === "string" ? (
                <Select value={v} onValueChange={(nuevo) => onCambiar(k, nuevo)} disabled={motivoBloqueo !== undefined}>
                  <SelectTrigger id={`config-${k}`} className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(opciones).map(([valor, etiquetaValor]) => (
                      <SelectItem key={valor} value={valor}>
                        {etiquetaValor}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : typeof v === "boolean" ? (
                <Switch
                  id={`config-${k}`}
                  checked={v}
                  onCheckedChange={(c) => onCambiar(k, c)}
                  label={info?.etiqueta ?? k}
                  disabled={motivoBloqueo !== undefined}
                />
              ) : (
                <Input
                  id={`config-${k}`}
                  type={typeof v === "number" ? "number" : "text"}
                  step="any"
                  value={v}
                  className="w-40"
                  disabled={motivoBloqueo !== undefined}
                  onChange={(e) => {
                    if (typeof v === "number") {
                      // Campo vacío o no numérico: no se toca el valor (nunca se guarda una config a null).
                      if (!Number.isNaN(e.target.valueAsNumber)) onCambiar(k, e.target.valueAsNumber);
                    } else {
                      onCambiar(k, e.target.value);
                    }
                  }}
                />
              )}
            </div>
            {info ? <p className="text-xs text-muted-foreground">{info.ayuda}</p> : null}
            {motivoBloqueo ? <p className="text-xs text-muted-foreground">{motivoBloqueo}</p> : null}
          </div>
        );
      })}
    </div>
  );
}
