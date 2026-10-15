/**
 * Navegador (`Brush` de recharts) bajo la gráfica de severidad: mini área
 * del total por tramo dentro del propio `Brush` (su «panorama», el patrón
 * documentado de recharts) con la ventana visible acotable a mano. La
 * ventana es estado local del panel (`index.tsx`), no la URL (evita un
 * refetch en cada arrastre); los dos gráficos de arriba reciben ya el
 * recorte.
 */

import { Area, AreaChart, Brush, ResponsiveContainer, XAxis } from "recharts";

import type { SeriesGranularity } from "@/api/types";
import { extremoRango, type Fila } from "./formato";

export interface NavegadorProps {
  filas: Fila[];
  granularidad: SeriesGranularity;
  inicio: number;
  fin: number;
  onCambio: (inicio: number, fin: number) => void;
}

export function Navegador({ filas, granularidad, inicio, fin, onCambio }: NavegadorProps) {
  const primeraVisible = filas[inicio];
  const ultimaVisible = filas[fin];
  const nVisibles = fin - inicio + 1;
  const unidad = granularidad === "batch" ? "lote" : "tramo";

  // Con un solo tramo el Brush no tiene nada que acotar: queda una franja
  // vacía sin traveller que arrastrar. Se oculta y se avisa en su lugar.
  if (filas.length <= 1) {
    return (
      <p className="text-xs text-muted-foreground">
        Un solo {unidad} en el rango: nada que navegar.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Navegador: total de alertas en todo el rango · arrastra los extremos para acotar</span>
        {primeraVisible && ultimaVisible ? (
          <span className="tabular-nums">
            Rango: {extremoRango(primeraVisible, granularidad)} a {extremoRango(ultimaVisible, granularidad)} ·{" "}
            {nVisibles} {unidad}
            {nVisibles === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
      {/* El Brush guarda dentro la escala de su serie, y
          cuando entra un lote nuevo con el cuadro abierto la reusa con datos
          de otra longitud: el fondo y los dos travellers salen como
          `<rect x="NaN">` y `<line x1="NaN">` en consola. La `key` con la
          granularidad y el número de tramos lo remonta limpio, que es lo
          único que lo evita (probado: ni acotar los índices ni esperar a que
          el contenedor mida bastan). */}
      <div className="h-11 w-full">
        <ResponsiveContainer width="100%" height={44}>
          {/* El chart anfitrión solo aloja el Brush (sin área propia ni ejes
              visibles); tiene que ser un AreaChart porque el panorama comparte
              su nombre de chart y `Area` no pinta dentro de un LineChart. */}
          <AreaChart key={`${granularidad}-${filas.length}`} data={filas} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <XAxis dataKey="etiqueta" hide />
            <Brush
              dataKey="etiqueta"
              height={44}
              y={0}
              travellerWidth={6}
              stroke="var(--primary)"
              fill="var(--card)"
              startIndex={inicio}
              endIndex={fin}
              tickFormatter={() => ""}
              onChange={(rango: { startIndex?: number; endIndex?: number }) => {
                if (rango.startIndex === undefined || rango.endIndex === undefined) return;
                onCambio(rango.startIndex, rango.endIndex);
              }}
            >
              <AreaChart>
                <Area
                  type="linear"
                  dataKey="total"
                  stroke="var(--primary)"
                  strokeWidth={1.5}
                  fill="var(--primary)"
                  fillOpacity={0.12}
                  isAnimationActive={false}
                  dot={false}
                />
              </AreaChart>
            </Brush>
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
