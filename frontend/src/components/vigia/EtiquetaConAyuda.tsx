/**
 * Etiqueta de una métrica servida desde `content/`, con su ⓘ.
 *
 * Vive aparte de `calculo-datos.ts` para que ese módulo no mezcle funciones y
 * componentes: el linter del repo avisa cuando un fichero exporta las dos
 * cosas, porque rompe el refresco rápido de Vite.
 *
 * `etiquetaVisible` fuerza el texto de la izquierda sin tocar el tooltip: lo
 * usa la tabla de tasas de error, donde la etiqueta de `content/` ("Tasa de
 * falsos negativos, grupo supervisado") repetiría el grupo que ya está en la
 * cabecera de columna. El ⓘ sigue enseñando la etiqueta completa.
 */

import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";

import { textoComoSeLee, textoQueMide } from "./AyudaTexto";
import { InfoTooltip } from "./InfoTooltip";

export function EtiquetaConAyuda({
  clave,
  etiquetaAlt,
  etiquetaVisible,
}: {
  clave: string;
  etiquetaAlt: string;
  etiquetaVisible?: string;
}) {
  const { data: ayuda } = useContenidoMetricasPorTipo();
  const info = ayuda?.[clave];
  const etiqueta = info?.etiqueta ?? etiquetaAlt;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span>{etiquetaVisible ?? etiqueta}</span>
      <InfoTooltip
        titulo={etiqueta}
        queMide={textoQueMide(info, "Sin ayuda para esta métrica.")}
        comoSeLee={textoComoSeLee(info)}
        formula={info?.formula}
      />
    </span>
  );
}
