/**
 * Panel de ayuda junto al lanzador de explicaciones:
 * cómo elegir entre permutación y SHAP, y qué se ve en el ranking de
 * importancias. Fichero aparte para que `lanzar.tsx` no supere 9 KB.
 */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTextosPantalla } from "@/api/queries-contenido";

const METODOS_POR_DEFECTO =
  "Elige entre importancia por permutación, siempre disponible, y SHAP, más preciso pero no " +
  "siempre instalado en el equipo. Para explicar un caso concreto, Vigía usa LIME.";

const QUE_VES_POR_DEFECTO =
  "Un ranking de las características que más pesan en las predicciones del modelo, con su " +
  "importancia relativa; para un caso concreto, el sentido en el que cada característica " +
  "empujó la decisión.";

export function AyudaLanzar() {
  const textos = useTextosPantalla();
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="text-sm">Cómo elegir y qué ves</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm text-muted-foreground">
        <p>{textos.data?.explicabilidad?.metodos ?? METODOS_POR_DEFECTO}</p>
        <p>{textos.data?.explicabilidad?.que_ves ?? QUE_VES_POR_DEFECTO}</p>
      </CardContent>
    </Card>
  );
}

export default AyudaLanzar;
