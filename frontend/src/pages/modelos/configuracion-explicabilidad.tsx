/**
 * Campos de explicabilidad automática de la pestaña «Configuración»:
 * `explain_auto` y `explain_method`. Aparte de
 * `configuracion.tsx` para no superar los 10 KB de ese fichero.
 *
 * Con un modelo `executable` sin artefacto subido, la explicación
 * automática no puede calcular nada (`check_explainable` da 409); en vez de
 * dejarlo fallar en silencio tras cada lote, se avisa aquí dónde subirlo.
 *
 * Corrección: `projectId` ahora se acepta como prop opcional (el proyecto de
 * la ruta, no el de la cabecera). `ConfiguracionTab` (`configuracion.tsx`,
 * fuera de esta frontera) todavía no la pasa: hasta que lo haga, el
 * componente sigue cayendo en `useSession`/`useProject`, que puede no
 * coincidir con el proyecto que se está editando si se cambia el selector
 * de la cabecera sin navegar.
 */

import { Link } from "react-router";

import { useProject } from "@/api/queries";
import { useSession } from "@/session/session";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface ExplicabilidadAutomaticaCamposProps {
  /** Proyecto de la ruta (`/modelos/:id`). Si se omite, cae en el de la sesión. */
  projectId?: number | null;
  explainAuto: boolean;
  setExplainAuto: (valor: boolean) => void;
  explainMethod: "permutation" | "shap";
  setExplainMethod: (valor: "permutation" | "shap") => void;
}

export function ExplicabilidadAutomaticaCampos({
  projectId: projectIdProp,
  explainAuto,
  setExplainAuto,
  explainMethod,
  setExplainMethod,
}: ExplicabilidadAutomaticaCamposProps) {
  const { projectId: projectIdSesion } = useSession();
  const projectId = projectIdProp ?? projectIdSesion;
  const { data: proyecto } = useProject(projectId);
  const versionActiva = proyecto?.versions.find((v) => v.is_active);
  const sinArtefacto = !!versionActiva && versionActiva.model_kind !== "sim_logistic" && !versionActiva.artifact_sha256;

  return (
    <div className="flex flex-col gap-2">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={explainAuto}
          onChange={(e) => setExplainAuto(e.target.checked)}
        />
        Explicación automática tras cada lote
      </label>
      {explainAuto && sinArtefacto && proyecto ? (
        <p className="pl-6 text-xs text-muted-foreground">
          El fichero del modelo (ONNX) es opcional: sin él solo se pierde la explicabilidad, así que
          la explicación automática no calculará nada. Si quieres explicaciones, súbelo en{" "}
          <Link className="text-link hover:underline" to={`/modelos/${proyecto.id}#versiones`}>
            Versiones
          </Link>
          .
        </p>
      ) : null}
      {explainAuto ? (
        <div className="flex flex-col gap-1.5 pl-6">
          <Label htmlFor="cfg-explain-method">Método</Label>
          <Select value={explainMethod} onValueChange={(v) => setExplainMethod(v as "permutation" | "shap")}>
            <SelectTrigger id="cfg-explain-method" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="permutation">Permutación</SelectItem>
              <SelectItem value="shap">SHAP (más preciso y más lento)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      ) : null}
    </div>
  );
}

export default ExplicabilidadAutomaticaCampos;
