/**
 * Los pasos sin pantalla de la demo guiada (`tipo="diapositiva"`: el
 * 0 «Un caso de uso de la herramienta» y «Fin del caso») en el área principal
 * de `/demo?paso=N`, con `Escena` (kicker, título y frase). El final
 * no pinta el contrafactual con y sin gobernanza (vive en la
 * diapositiva 5 de la presentación); solo ofrece
 * «Ir al laboratorio», que es el paso siguiente: el paso opcional «Tras las
 * medidas» salió del guion. Los rótulos de los botones salen de lo que el
 * guion nombra entre « y » en `hace` (`citasDe`), nunca de cadenas fijas que
 * lo dupliquen.
 */

import type { PasoDemo } from "@/api/queries-contenido";
import { Button } from "@/components/ui/button";
import { Escena, useDemoGuiada } from "@/components/vigia";
import { citasDe } from "@/components/vigia/DemoGuiada/pasos";

export interface DiapositivaProps {
  paso: PasoDemo;
}

export function Diapositiva({ paso }: DiapositivaProps) {
  const demo = useDemoGuiada();
  const citas = citasDe(paso.hace);
  const esFinal = paso.id > 0;

  const acciones = esFinal ? (
    <Button type="button" onClick={demo.siguiente}>
      {citas[0] ?? "Ir al laboratorio"}
    </Button>
  ) : (
    <Button type="button" size="lg" onClick={() => demo.ir(paso.id + 1)}>
      {citas[0] ?? "Empezar"}
    </Button>
  );

  return (
    <Escena
      kicker={paso.kicker}
      titulo={paso.titulo}
      frase={paso.frase}
      accionSugerida={acciones}
      className="min-h-[calc(100vh-12rem)]"
    />
  );
}
