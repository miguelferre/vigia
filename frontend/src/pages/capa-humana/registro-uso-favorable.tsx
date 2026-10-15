/**
 * Declaración obligatoria de la decisión favorable del registro de uso
 * (partida de `RegistroUso.tsx`): cuatro opciones y qué pasa con cada
 * una. El texto de cada opción sale de `GET /content/registro-uso`.
 */

import type { ValorFavorable } from "@/api/types";
import {
  FRASE_D155_RESERVA,
  OPCIONES_FAVORABLE,
  PREGUNTA_FAVORABLE_RESERVA,
  type RegistroUsoAyuda,
} from "./registro-uso-ayuda";

interface Props {
  ayuda: RegistroUsoAyuda | undefined;
  favorable: ValorFavorable | null;
  onElegir: (valor: ValorFavorable) => void;
}

export function FavorableRegistro({ ayuda, favorable, onElegir }: Props) {
  const codificacion = ayuda?.codificacion;
  const invierte = favorable === "no-refer" || favorable === "0";
  const significa = codificacion?.opciones.find((o) => o.valor === favorable)?.significa;
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium">{codificacion?.pregunta ?? PREGUNTA_FAVORABLE_RESERVA}</legend>
      <p className="text-xs text-muted-foreground">{codificacion?.frase ?? FRASE_D155_RESERVA}</p>
      <div className="flex flex-wrap gap-x-5 gap-y-2" role="radiogroup" aria-required="true">
        {OPCIONES_FAVORABLE.map((valor) => (
          <label key={valor} className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="radio"
              name="valor-favorable"
              value={valor}
              checked={favorable === valor}
              onChange={() => onElegir(valor)}
            />
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{valor}</code>
          </label>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        {favorable === null
          ? "Elige una opción para poder subir el fichero."
          : (significa ??
            (invierte
              ? "El registro usa la codificación contraria: al subirlo se recodifican las tres columnas."
              : "El registro se guarda tal cual está."))}
      </p>
    </fieldset>
  );
}
