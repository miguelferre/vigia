/**
 * Estado y campos multiclase del paso «Datos» del alta: clases
 * del fichero de ejemplo (más las añadidas a mano), conjunto favorable con
 * casillas y una columna de probabilidad por clase. Sale de `alta-datos.tsx`
 * por el límite de 9 KB; con `activo = false` no dibuja nada y no valida.
 */

import { useRef, useState } from "react";

import type { ColumnasEjemplo } from "./alta-sniff";
import { leerValoresClases, type ValoresClases } from "./alta-sniff-clases";
import { AYUDA_ALTA_MULTICLASE } from "./alta-textos";
import { motivoClasesNoValidas, motivoFavorablesNoValidos, probabilidadPorClase, sugerirClases } from "./clases-multiclase";
import { AnadirClase, ListaFavorables, probabilidadIncompleta, SelectoresProbabilidad } from "./clases-controles";
import { ANCLA_CLASE_FAVORABLE, EnlaceFormato } from "./subida-enlace-formato";

interface Entrada {
  activo: boolean;
  sniff: ColumnasEjemplo | null;
  predictionCol: string;
  labelCol: string;
}

export function useMulticlaseAlta({ activo, sniff, predictionCol, labelCol }: Entrada) {
  const [favorables, setFavorables] = useState<string[]>([]);
  const [clasesExtra, setClasesExtra] = useState<string[]>([]);
  const [probElegidas, setProbElegidas] = useState<Record<string, string>>({});
  // Valores distintos de todo el fichero (hasta 5 MB); `null` mientras se lee o si falla: valen las filas de la muestra.
  const [valoresClases, setValoresClases] = useState<ValoresClases | null>(null);
  const lecturaActual = useRef(0);

  const columnas = sniff?.columnas ?? [];
  const filas = sniff?.filas ?? [];
  const clasesSugeridas = activo && sniff ? sugerirClases(columnas, filas, predictionCol, labelCol, valoresClases?.valores) : [];
  const clases = [...clasesSugeridas, ...clasesExtra.filter((c) => !clasesSugeridas.includes(c))];
  const probAuto = activo ? probabilidadPorClase(columnas, clases) : {};
  const probCols: Record<string, string> = Object.fromEntries(
    clases.map((c) => [c, c in probElegidas ? probElegidas[c] : (probAuto[c] ?? "")]),
  );
  const probabilidadPorColumna: Record<string, string> = Object.fromEntries(
    Object.entries(probCols)
      .filter(([, col]) => col !== "")
      .map(([clase, col]) => [col, clase]),
  );
  const favorablesVigentes = favorables.filter((f) => clases.includes(f));
  const motivoClases = clases.length > 0 ? motivoClasesNoValidas(clases) : null;

  const reiniciar = () => {
    lecturaActual.current += 1;
    setValoresClases(null);
    setFavorables([]);
    setClasesExtra([]);
    setProbElegidas({});
  };

  /** Lee el fichero entero (hasta 5 MB) sin bloquear el formulario; una lectura vieja no pisa a la nueva. */
  const leerFichero = (file: File, leido: ColumnasEjemplo) => {
    if (!activo) return;
    const lectura = ++lecturaActual.current;
    void leerValoresClases(file, leido.columnas, leido.separador)
      .then((v) => lectura === lecturaActual.current && setValoresClases(v))
      .catch(() => undefined);
  };

  const campos = activo
    ? {
        favorables: (
          <div className="flex flex-col gap-3">
            <ListaFavorables
              idBase="alta-favorables"
              etiqueta="Clases favorables (obligatorio)"
              ayuda={`${AYUDA_ALTA_MULTICLASE.favorable} ${AYUDA_ALTA_MULTICLASE.clases}`}
              clases={clases}
              favorables={favorablesVigentes}
              onAlternar={(c) => setFavorables((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))}
            />
            {motivoClases ? (
              <p role="alert" className="text-xs text-destructive" data-testid="alta-clases-aviso">
                {motivoClases}
              </p>
            ) : null}
            <AnadirClase
              clases={clases}
              onAnadir={(c) => setClasesExtra((prev) => [...prev, c])}
              parcial={valoresClases?.parcial ?? true}
            />
            <EnlaceFormato
              texto="Cómo decidir las clases favorables"
              ancla={ANCLA_CLASE_FAVORABLE}
              nuevaPestana
              className="w-fit text-xs"
            />
          </div>
        ),
        probabilidades: (
          <SelectoresProbabilidad
            idBase="alta-prob"
            clases={clases}
            columnas={columnas}
            valores={probCols}
            onCambiar={(clase, col) => setProbElegidas((prev) => ({ ...prev, [clase]: col }))}
            ayuda={AYUDA_ALTA_MULTICLASE.probabilidad}
          />
        ),
      }
    : undefined;

  return {
    probabilidadPorColumna,
    valido:
      motivoClasesNoValidas(clases) === null &&
      motivoFavorablesNoValidos(clases, favorablesVigentes) === null &&
      !probabilidadIncompleta(clases, probCols),
    sinProbabilidad: !clases.some((c) => probCols[c] !== ""),
    plantilla: {
      clases,
      favorables: favorablesVigentes,
      probabilidades: clases.every((c) => probCols[c] !== "") ? clases.map((c) => probCols[c]) : [],
    },
    campos,
    reiniciar,
    leerFichero,
  };
}
