/**
 * Cabecera de la tabla del paso «Umbrales» con una ayuda por columna: línea base, propuesta, umbral actual y origen. La de origen
 * lista los cinco valores. Con `Popover` y no con tooltip suelto para que
 * abra también con un toque en el móvil.
 */

import { InfoIcon } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TableHead, TableHeader, TableRow } from "@/components/ui/table";

import {
  AYUDA_COLUMNA_UMBRAL,
  EXPLICACION_ORIGEN_UMBRAL,
  ORIGENES_UMBRAL,
  etiquetaOrigenUmbral,
  type AyudaColumna,
} from "./alta-umbrales-textos";

export function AyudaColumnaUmbral({
  ayuda,
  conOrigenes = false,
  dominio,
}: {
  ayuda: AyudaColumna;
  conOrigenes?: boolean;
  dominio?: string;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Qué significa ${ayuda.titulo}`}
          className="inline-flex size-4 items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <InfoIcon className="size-3.5" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm font-normal whitespace-normal">
        <p className="mb-1 font-semibold">{ayuda.titulo}</p>
        <p className="text-muted-foreground">{ayuda.texto}</p>
        {conOrigenes ? (
          <ul className="mt-2 flex flex-col gap-1.5 text-xs">
            {ORIGENES_UMBRAL.map((o) => (
              <li key={o}>
                <span className="font-semibold">{etiquetaOrigenUmbral(o, dominio)}.</span>{" "}
                <span className="text-muted-foreground">{EXPLICACION_ORIGEN_UMBRAL[o]}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function Cabecera({ texto, ayuda, conOrigenes, dominio, ancho }: { texto: string; ayuda: AyudaColumna; conOrigenes?: boolean; dominio?: string; ancho: string }) {
  return (
    <TableHead className={ancho}>
      <span className="inline-flex items-center gap-1.5">
        {texto}
        <AyudaColumnaUmbral ayuda={ayuda} conOrigenes={conOrigenes} dominio={dominio} />
      </span>
    </TableHead>
  );
}

export function CabeceraUmbrales({ dominio }: { dominio?: string }) {
  return (
    <TableHeader>
      <TableRow>
        <TableHead className="w-[22%]">Métrica</TableHead>
        <Cabecera texto="Línea base" ayuda={AYUDA_COLUMNA_UMBRAL.lineaBase} ancho="w-[10%]" />
        <Cabecera texto="Propuesta" ayuda={AYUDA_COLUMNA_UMBRAL.propuesta} ancho="w-[14%]" />
        <Cabecera texto="Umbral actual" ayuda={AYUDA_COLUMNA_UMBRAL.umbral} ancho="w-[18%]" />
        <Cabecera texto="Origen y nota" ayuda={AYUDA_COLUMNA_UMBRAL.origen} conOrigenes dominio={dominio} ancho="w-[17%]" />
        <TableHead className="w-[19%] min-w-[9rem] whitespace-normal">Valor a guardar</TableHead>
      </TableRow>
    </TableHeader>
  );
}
