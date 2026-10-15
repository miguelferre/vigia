/**
 * Tabla de la pestaña «Comparar». Una fila por monitor,
 * métrica y grupo con umbral. Los atributos `data-*` son el contrato de la
 * batería de pruebas (la batería compara la pantalla con el JSON de la API celda a celda): el
 * texto visible redondea, el atributo lleva el número crudo.
 */

import { AlertTriangleIcon, ArrowLeftRightIcon, CircleCheckIcon, CircleHelpIcon, EqualIcon } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { ComparacionFila, ComparacionLado } from "@/api/queries-versiones";
import { StateBadge, colorEstado } from "@/components/vigia";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ETIQUETA_MONITOR, esMedidaEnUnidad, formatoMetrica, formatoNumero, metricLabelPorTipo } from "@/lib/metrics";
import { metricLabelDeClase } from "@/lib/metric-labels";
import { claseDeGrupo, esGrupoClase } from "@/lib/tipo-tarea";
import { ETIQUETA_DIRECCION, PISTA_DIRECCION, type DireccionComparacion } from "./comparar-textos";

const ICONO_DIRECCION: Record<DireccionComparacion, LucideIcon> = {
  mejora: CircleCheckIcon,
  empeora: AlertTriangleIcon,
  igual: EqualIcon,
  cambia: ArrowLeftRightIcon,
  sin_datos: CircleHelpIcon,
};

// «Cambia» y «igual» no llevan color de mejora ni de empeora.
const ESTADO_DIRECCION = {
  mejora: "ok",
  empeora: "alerta",
  igual: "sin_datos",
  cambia: "sin_datos",
  sin_datos: "sin_datos",
} as const;

/** Número crudo de la API como cadena; vacío si no hay valor. */
const crudo = (v: number | null | undefined): string => (v === null || v === undefined ? "" : String(v));

export function ChipDireccion({ direccion }: { direccion: DireccionComparacion }) {
  const Icono = ICONO_DIRECCION[direccion];
  return (
    <span
      data-direccion={direccion}
      title={PISTA_DIRECCION[direccion]}
      className="inline-flex w-fit items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold"
      style={{ borderColor: colorEstado(ESTADO_DIRECCION[direccion]) }}
    >
      <Icono className="size-3" aria-hidden="true" style={{ color: colorEstado(ESTADO_DIRECCION[direccion]) }} />
      {ETIQUETA_DIRECCION[direccion]}
    </span>
  );
}

/** Valor de una métrica: con la unidad de la salida en una regresión; sin ella, 3 decimales como siempre. */
function valorEn(clave: string, v: number | null, unidad: string | null | undefined): string {
  return unidad === undefined ? formatoNumero(v) : formatoMetrica(clave, v, unidad);
}

/** La diferencia B menos A de una medida en la unidad lleva signo explícito. */
function diferenciaEn(clave: string, v: number | null, unidad: string | null | undefined): string {
  if (v === null) return "n/d";
  if (unidad === undefined) return formatoNumero(v);
  if (esMedidaEnUnidad(clave)) return formatoMetrica("mean_error_difference", v, unidad);
  // R² y la deriva de la predicción no van en la unidad, pero una diferencia lleva siempre su signo.
  return Number.isFinite(v)
    ? v.toLocaleString("es-ES", { minimumFractionDigits: 3, maximumFractionDigits: 3, signDisplay: "exceptZero" })
    : formatoMetrica(clave, v, unidad);
}

function CeldaLado({
  lado,
  nombre,
  porClase,
  clave,
  unidad,
}: {
  lado: ComparacionLado;
  nombre: "a" | "b";
  porClase: boolean;
  clave: string;
  unidad?: string | null;
}) {
  return (
    <TableCell data-lado={nombre} data-valor={crudo(lado.valor)} className="align-top">
      <div className="flex flex-col gap-1">
        <span className="font-semibold tabular-nums">{valorEn(clave, lado.valor, unidad)}</span>
        <span className="flex flex-wrap items-center gap-1">
          {/* Una medida por clase no tiene umbral; solo su «sin datos» se enseña como estado. */}
          {porClase && lado.estado !== "sin_datos" ? null : <StateBadge estado={lado.estado} size="sm" />}
          {lado.n !== null ? <span className="text-xs text-muted-foreground">n = {lado.n}</span> : null}
        </span>
        {lado.motivo && lado.valor === null ? (
          <span className="max-w-44 whitespace-normal text-xs text-muted-foreground">{lado.motivo}</span>
        ) : null}
      </div>
    </TableCell>
  );
}

function etiquetaGrupo(grupo: string | null): string {
  const clase = claseDeGrupo(grupo);
  if (clase !== null) return `Clase ${clase}`;
  return grupo === null ? "Global" : `Grupo ${grupo}`;
}

export function TablaComparacion({ filas, etiquetaA, etiquetaB, tipo, unidad }: {
  /** Unidad de la salida de una regresión (`null` si no la declaró); `undefined` en clasificación. */
  unidad?: string | null;
  /** Tipo de tarea del proyecto: las etiquetas de calidad llevan «macro» en multiclase. */
  tipo?: string | null;
  filas: readonly ComparacionFila[];
  etiquetaA: string;
  etiquetaB: string;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Métrica</TableHead>
          <TableHead>A · {etiquetaA}</TableHead>
          <TableHead>B · {etiquetaB}</TableHead>
          <TableHead>Diferencia (B menos A)</TableHead>
          <TableHead>Resultado</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {filas.map((f) => (
          <TableRow
            key={`${f.monitor_type}|${f.metric_key}|${f.group_code ?? ""}`}
            data-t10-fila=""
            data-monitor={f.monitor_type}
            data-metrica={f.metric_key}
            data-grupo={f.group_code ?? ""}
          >
            <TableCell className="min-w-40 max-w-56 whitespace-normal align-top">
              <div className="flex flex-col">
                <span className="font-medium">
                  {/* Una medida por clase es de esa clase, sin «(macro)». */}
                  {esGrupoClase(f.group_code) ? metricLabelDeClase(f.metric_key) : metricLabelPorTipo(f.metric_key, tipo)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {ETIQUETA_MONITOR[f.monitor_type]} · {etiquetaGrupo(f.group_code)}
                </span>
              </div>
            </TableCell>
            <CeldaLado lado={f.a} nombre="a" porClase={esGrupoClase(f.group_code)} clave={f.metric_key} unidad={unidad} />
            <CeldaLado lado={f.b} nombre="b" porClase={esGrupoClase(f.group_code)} clave={f.metric_key} unidad={unidad} />
            <TableCell data-diferencia={crudo(f.diferencia)} className="align-top tabular-nums">
              {diferenciaEn(f.metric_key, f.diferencia, unidad)}
            </TableCell>
            <TableCell className="align-top">
              <div className="flex flex-col gap-1">
                <ChipDireccion direccion={f.direccion} />
                <span className="max-w-56 whitespace-normal text-xs text-muted-foreground">{f.motivo}</span>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
