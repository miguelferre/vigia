/** Punto único de importación de los componentes propios de Vigía. */

export { StateBadge, colorEstado } from "./StateBadge";
export type { StateBadgeProps } from "./StateBadge";
export { DataTable } from "./DataTable";
export type { DataTableProps, LegacyColumnDef } from "./DataTable";
export { MotivoDialog } from "./MotivoDialog";
export type { MotivoDialogProps } from "./MotivoDialog";
export { EJEMPLO_MOTIVO, MOTIVO_MINIMO } from "./motivo-textos";
export { EmptyState } from "./EmptyState";
export type { EmptyStateProps } from "./EmptyState";
export { SinProyecto } from "./SinProyecto";
export type { SinProyectoProps } from "./SinProyecto";
export { ErrorBoundary } from "./ErrorBoundary";
export type { ErrorBoundaryProps } from "./ErrorBoundary";
export { ErrorDeConsulta } from "./ErrorDeConsulta";
export type { ErrorDeConsultaProps } from "./ErrorDeConsulta";
export { ErrorDeTrabajo, textoErrorDeTrabajo } from "./ErrorDeTrabajo";
export type { ErrorDeTrabajoProps } from "./ErrorDeTrabajo";
export { PageHeader } from "./PageHeader";
export type { PageHeaderProps, Miga, MarcaTiempoHeader } from "./PageHeader";
export { BotonVolver } from "./BotonVolver";
export type { BotonVolverProps } from "./BotonVolver";
export { ChipsSeveridad } from "./ChipsSeveridad";
export type { ChipsSeveridadProps } from "./ChipsSeveridad";
export { KpiCard } from "./KpiCard";
export type { KpiCardProps, PuntoSerie } from "./KpiCard";
export { JsonView } from "./JsonView";
export type { JsonViewProps } from "./JsonView";
export { MetricLabel } from "./MetricLabel";
export type { MetricLabelProps } from "./MetricLabel";
export { SelectorPeriodo } from "./SelectorPeriodo";
export type { SelectorPeriodoProps, ValorPeriodo } from "./SelectorPeriodo";
export { InfoTooltip } from "./InfoTooltip";
export type { InfoTooltipProps } from "./InfoTooltip";
// `CajaFormula`: forma única de "Cómo se ha calculado" en toda
// métrica con fórmula; se exporta desde el barril para que cualquier pantalla
// la adopte.
export { CajaFormula } from "./CajaFormula";
export type { CajaFormulaProps } from "./CajaFormula";
export { RankingBarras } from "./RankingBarras";
export type { RankingBarrasProps, TooltipRankingProps } from "./RankingBarras";
export { CabeceraVentana } from "./CabeceraVentana";
export type { CabeceraVentanaProps } from "./CabeceraVentana";
export { GlosarioSheet } from "./GlosarioSheet";
export type { GlosarioSheetProps } from "./GlosarioSheet";
export { ModoPresentacionProvider, useModoPresentacion, BotonModoPresentacion } from "./ModoPresentacion";
export type { ModoPresentacionContextValue, BotonModoPresentacionProps } from "./ModoPresentacion";
export { Escena } from "./Escena";
export { LogoVigia } from "./LogoVigia";
export type { LogoVigiaProps } from "./LogoVigia";
export type { EscenaProps } from "./Escena";
// Demo guiada: el proveedor y el panel se importan por su ruta
// desde `App.tsx` y `AppShell.tsx`; aquí solo el hook, el contrato con las
// pantallas y el botón de reinicio que `/demo` reutiliza.
export { useDemoGuiada } from "./DemoGuiada/contexto";
export type { DemoGuiadaContextValue } from "./DemoGuiada/contexto";
export { BotonReiniciarDemo } from "./DemoGuiada/BotonReiniciarDemo";
export { notificarDemo, leerAccionDemo, leerPrecargaSubir, leerPrecargaAnotar } from "./DemoGuiada/contrato";
export type { EventoDemo, AccionDemo } from "./DemoGuiada/contrato";
export { LucesMonitor } from "./LucesMonitor";
export { ChipDespliegue } from "./ChipDespliegue";
export type { LucesMonitorProps } from "./LucesMonitor";
export { HistogramaBaseLote } from "./HistogramaBaseLote";
export type { HistogramaBaseLoteProps } from "./HistogramaBaseLote";
export {
  construirFilasHistograma,
  indicesQueMasCambian,
  etiquetasDeBordes,
  fraseTramosQueMasCambian,
  distribucionesIdenticas,
} from "./histograma-base-lote-datos";
export type { FilaHistograma } from "./histograma-base-lote-datos";
// `CalculoMetrica` no se reexporta aquí a propósito: importa
// `pages/monitores/histograma-confianza.tsx` y `ranking-deriva.tsx`, que a su
// vez importan de este barril (`InfoTooltip`, `RankingBarras`) — meterlo en
// el barril crearía un ciclo. Se importa siempre desde
// "@/components/vigia/CalculoMetrica" directamente (así lo hacen
// `AlertaPanel.tsx` y `pages/monitores/calculo.tsx`).
