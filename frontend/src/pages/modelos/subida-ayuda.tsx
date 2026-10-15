/**
 * Panel «qué se sube, cómo y qué pasa después» del primer paso de subida:
 * `GET /content/textos-pantalla` sección `subida_datos`. Partido de
 * `subida-dataset.tsx` para no superar 9 KB.
 *
 * Vigía no pseudonimiza. Solo queda `que_pasa_despues`, sin la
 * variante «desidentificado» (retirada con la casilla del mismo nombre).
 */

import { useTextosPantalla } from "@/api/queries-contenido";
import { EnlaceFormato } from "./subida-enlace-formato";
import { TEXTO_SUBIDA_POR_DEFECTO as TEXTO_POR_DEFECTO } from "./subida-textos";

export function SubidaAyudaPanel() {
  const { data } = useTextosPantalla();
  const textos = data?.subida_datos;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-muted/40 p-3 text-sm">
      <p>
        <strong>Qué subir.</strong> {textos?.que_subir ?? TEXTO_POR_DEFECTO.que_subir}
      </p>
      <p>
        <strong>Formatos.</strong> {textos?.formatos ?? TEXTO_POR_DEFECTO.formatos}{" "}
        <EnlaceFormato nuevaPestana className="text-sm" />
      </p>
      <p>
        <strong>Qué pasa después.</strong> {textos?.que_pasa_despues ?? TEXTO_POR_DEFECTO.que_pasa_despues}
      </p>
    </div>
  );
}
