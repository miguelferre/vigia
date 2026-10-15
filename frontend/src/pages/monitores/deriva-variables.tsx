/**
 * Panel de variables de deriva:
 * lista de `details.features[]` ordenada por la puntuación que entra en
 * `feature_drift_score` (KS o JS, antes por PSI), con la variable del
 * máximo resaltada y el histograma base frente a lote de la elegida (forma B).
 * Vive fijo en la tarjeta «Variables» del bloque
 * «Distribuciones» de `/monitores/deriva` (`DistribucionesDeriva.tsx`); el
 * panel de alertas lo sigue montando desde `CalculoMetrica.tsx`, sin `lotes`.
 *
 * Con `lotes`, la columna derecha añade la
 * pestaña «Lote a lote» (`ViolinLoteALote`), solo para variables numéricas;
 * sin `lotes` (el caso de `/alertas/:id`) no hay pestañas, como antes.
 *
 * `?variable=<col>` (enlace desde `/explicabilidad`) selecciona la fila al
 * montar; sin ella, la primera del ranking. `?vista=lote-a-lote` selecciona
 * la pestaña al montar, igual que `?variable`: ninguno de los dos se escribe
 * en la URL. Las categóricas no traen `psi` (solo numéricas, `core/drift.py`)
 * pero sí puntuación (JS), así que compiten en igualdad con las numéricas.
 * Una categórica sin ningún valor común con la línea base lleva la
 * marca «Sin categorías comunes con la base»; su puntuación sigue contando.
 */

import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { InfoTooltip } from "@/components/vigia";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGlosario, useGuionDemo } from "@/api/queries-contenido";
import type { EvaluationDetail, JsonObject } from "@/api/types";

import { TEXTO_SIN_COMUNES, claveDelMaximo, esNumerica, extraerVariables, rangoDeVariable } from "./deriva-variables-datos";
import type { FilaVariable } from "./deriva-variables-datos";
import { FilaLista } from "./deriva-variables-fila";
import { HistogramaVariable } from "./histograma-variable";
import { ViolinLoteALote } from "./ViolinLoteALote";
import type { LoteDeriva } from "./violin-lote-a-lote-datos";

type VistaVariable = "base-lote" | "lote-a-lote";

const AYUDA_LOTE_A_LOTE =
  "Una variable numérica a lo largo de los lotes evaluados: un violín por lote, la línea base destacada, el punto es la mediana y el PSI va contra la línea base. Solo para variables numéricas.";

/** Cabecera de la columna derecha con `lotes`: título y subtítulo según la pestaña activa. */
function CabeceraVariable({
  actual,
  vista,
  numerica,
  ayudaLoteALote,
}: {
  actual: FilaVariable;
  vista: VistaVariable;
  numerica: boolean;
  ayudaLoteALote: string;
}) {
  if (vista === "lote-a-lote") {
    return (
      <div>
        <div className="flex items-center gap-1.5">
          <h4 className="text-sm font-semibold">{actual.featureLabel}, lote a lote</h4>
          <InfoTooltip titulo="Deriva lote a lote" queMide={ayudaLoteALote} />
        </div>
        <p className="text-xs text-muted-foreground" title={actual.feature}>
          Numérica · un violín por lote, la línea base en teal
        </p>
      </div>
    );
  }
  return (
    <div>
      <h4 className="text-sm font-semibold">{actual.featureLabel}: línea base frente a lote</h4>
      <p className="text-xs text-muted-foreground" title={actual.feature}>
        {numerica ? "Numérica" : "Categórica"} · {rangoDeVariable(actual)}
      </p>
      {actual.sinValoresComunes ? (
        <p className="mt-1 text-xs text-muted-foreground">{TEXTO_SIN_COMUNES}</p>
      ) : null}
    </div>
  );
}

export interface DerivaVariablesProps {
  evaluacion: EvaluationDetail;
  /** Lotes para la pestaña «Lote a lote»; sin ella, sin pestañas (caso de `/alertas/:id`). */
  lotes?: LoteDeriva[];
}

export function DerivaVariables({ evaluacion, lotes }: DerivaVariablesProps) {
  const details = (evaluacion.result?.details as JsonObject | undefined) ?? null;
  const dominio = useGuionDemo().data?.dominio;
  const todas = useMemo(() => extraerVariables(details, dominio), [details, dominio]);
  const [searchParams] = useSearchParams();
  const inicial = searchParams.get("variable");
  const [seleccionada, setSeleccionada] = useState<string | null>(
    () => (inicial && todas.some((f) => f.feature === inicial) ? inicial : (todas[0]?.feature ?? null)),
  );
  const [vista, setVista] = useState<VistaVariable>(
    () => (searchParams.get("vista") === "lote-a-lote" ? "lote-a-lote" : "base-lote"),
  );
  const glosarioQ = useGlosario();
  const ayudaLoteALote = glosarioQ.data?.deriva_lote_a_lote?.definicion ?? AYUDA_LOTE_A_LOTE;
  const claveMaximo = claveDelMaximo(todas);
  const actual = todas.find((f) => f.feature === seleccionada) ?? todas[0] ?? null;
  const numerica = actual ? esNumerica(actual) : false;
  const vistaEfectiva: VistaVariable = numerica ? vista : "base-lote";

  if (todas.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin características en el resultado de esta evaluación.</p>;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,280px)_1fr]">
      <div className="flex max-h-[28rem] flex-col gap-1.5 overflow-y-auto pr-1">
        {todas.map((fila) => (
          <FilaLista
            key={fila.feature}
            fila={fila}
            activa={fila.feature === actual?.feature}
            esMaximo={fila.feature === claveMaximo}
            onSeleccionar={() => setSeleccionada(fila.feature)}
          />
        ))}
      </div>
      <div className="min-w-0">
        {!actual ? (
          <p className="text-sm text-muted-foreground">Elige una característica de la lista.</p>
        ) : !lotes ? (
          <HistogramaVariable variable={actual} />
        ) : (
          <Tabs value={vistaEfectiva} onValueChange={(v) => setVista(v as VistaVariable)}>
            <div className="flex items-start justify-between gap-3">
              <CabeceraVariable actual={actual} vista={vistaEfectiva} numerica={numerica} ayudaLoteALote={ayudaLoteALote} />
              <TabsList className="h-7">
                <TabsTrigger value="base-lote" className="text-xs px-2.5">
                  Línea base frente a lote
                </TabsTrigger>
                <TabsTrigger
                  value="lote-a-lote"
                  className="text-xs px-2.5"
                  disabled={!numerica}
                  title={numerica ? undefined : "Solo para variables numéricas"}
                >
                  Lote a lote
                </TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="base-lote">
              <HistogramaVariable variable={actual} sinTitulo />
            </TabsContent>
            <TabsContent value="lote-a-lote">
              <ViolinLoteALote feature={actual.feature} featureLabel={actual.featureLabel} lotes={lotes} />
            </TabsContent>
          </Tabs>
        )}
      </div>
    </div>
  );
}

export default DerivaVariables;
