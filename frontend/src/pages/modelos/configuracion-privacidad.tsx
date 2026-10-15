/**
 * Campo «guardar variables de entrada» de la pestaña «Configuración». Aparte de `configuracion.tsx` para no superar los 10 KB de
 * ese fichero.
 *
 * La casilla «los datos ya vienen desidentificados» se retira:
 * Vigía no pseudonimiza ni detecta columnas identificadoras, así
 * que no hay nada que marcar aquí.
 */

import { useTextosPantalla } from "@/api/queries-contenido";

export interface ConfiguracionPrivacidadCamposProps {
  storeFeatures: boolean;
  setStoreFeatures: (valor: boolean) => void;
}

export function ConfiguracionPrivacidadCampos({
  storeFeatures,
  setStoreFeatures,
}: ConfiguracionPrivacidadCamposProps) {
  const textos = useTextosPantalla();
  const ayudaStoreFeatures = textos.data?.modelos?.guardar_variables_ayuda ?? "";

  return (
    <div className="flex flex-col gap-1">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={storeFeatures}
          onChange={(e) => setStoreFeatures(e.target.checked)}
        />
        Guardar las variables de entrada de cada registro
      </label>
      {ayudaStoreFeatures ? (
        <p className="pl-6 text-xs text-muted-foreground">{ayudaStoreFeatures}</p>
      ) : null}
    </div>
  );
}

export default ConfiguracionPrivacidadCampos;
