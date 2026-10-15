/**
 * Campo del estado de despliegue de la pestaña «Configuración»: se edita solo aquí, no desde el chip de la tarjeta.
 * Aparte de `configuracion.tsx` para no superar los
 * 9 KB de ese fichero, como `configuracion-explicabilidad.tsx`.
 */

import type { DeploymentStage } from "@/api/types";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const ETIQUETA_DESPLIEGUE: Record<DeploymentStage, string> = {
  desarrollo: "Desarrollo",
  validacion: "Validación",
  produccion: "Producción",
  demo: "Demo",
};

export interface DespliegueCamposProps {
  deploymentStage: DeploymentStage;
  setDeploymentStage: (valor: DeploymentStage) => void;
}

export function DespliegueCampos({ deploymentStage, setDeploymentStage }: DespliegueCamposProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="cfg-deployment-stage">Estado de despliegue</Label>
      <Select value={deploymentStage} onValueChange={(v) => setDeploymentStage(v as DeploymentStage)}>
        <SelectTrigger id="cfg-deployment-stage" className="w-48">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(ETIQUETA_DESPLIEGUE) as DeploymentStage[]).map((valor) => (
            <SelectItem key={valor} value={valor}>
              {ETIQUETA_DESPLIEGUE[valor]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default DespliegueCampos;
