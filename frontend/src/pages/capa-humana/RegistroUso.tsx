/**
 * Bloque «Registro de uso» (`#registro-uso`): subida del diario con
 * la versión y la decisión favorable, resultado y avisos
 * (`registro-uso-resultado.tsx`), reglas cruzadas y descarga del acumulado.
 * La ayuda sale de `GET /api/content/registro-uso` (`registro-uso-ayuda.ts`).
 */

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MotivoDialog } from "@/components/vigia";
import { api, mensajeDeError } from "@/api/client";
import { useProject } from "@/api/queries";
import { useCan } from "@/session/session";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { EnlaceFormato } from "@/pages/modelos/subida-enlace-formato";
import type { UsageLogUploadResponse, ValorFavorable } from "@/api/types";
import { RESUMEN_RESERVA, useRegistroUsoAyuda } from "./registro-uso-ayuda";
import { EvaluarYDescargar } from "./registro-uso-evaluar";
import { DecisionRegistro, descripcionSubida, SinRangoCapaHumana } from "./registro-uso-decision";
import { FormatoRegistro } from "./registro-uso-formato";
import { ResultadoRegistro, type ResultadoSubida } from "./registro-uso-resultado";
import { SelectorVersionRegistro } from "./registro-uso-version";

export function RegistroUso({ projectId }: { projectId: number }) {
  const puedeConfig = useCan("config");
  const proyecto = useProject(projectId);
  const ayuda = useRegistroUsoAyuda().data;
  const versiones = proyecto.data?.versions ?? [];
  const activaId = proyecto.data?.active_version_id ?? null;
  const queryClient = useQueryClient();
  // La decisión del registro depende del tipo (favorable, nombres de clase o cifras).
  const tarea = useTipoTarea(projectId);
  const decision = tarea.caps?.decisionHumana;
  const sinCodificacion = decision !== undefined && decision !== "derivacion";

  const inputRef = useRef<HTMLInputElement>(null);
  const [versionId, setVersionId] = useState<string>("");
  const [favorable, setFavorable] = useState<ValorFavorable | null>(null);
  const [fichero, setFichero] = useState<File | null>(null);
  const [abiertoSubida, setAbiertoSubida] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoSubida | null>(null);

  const versionElegida = versionId !== "" ? Number(versionId) : activaId;
  const etiquetaVersion = (id: number | null) => versiones.find((v) => v.id === id)?.label ?? "activa";
  // Sin el tipo de tarea no se sabe si hay que declarar la favorable.
  const sinDeclarar = decision === undefined || (decision === "derivacion" && favorable === null);

  const subir = async () => {
    // Nunca salir en silencio; el diálogo enseña el motivo y no se cierra.
    if (!fichero) throw new Error("No hay ningún fichero elegido. Cierra este diálogo y elige un CSV.");
    if (sinDeclarar) throw new Error("Declara antes la decisión favorable del registro.");
    const subido = fichero;
    setSubiendo(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", subido);
      if (decision === "derivacion" && favorable !== null) form.append("valor_favorable", favorable);
      if (versionElegida !== null) form.append("model_version_id", String(versionElegida));
      const respuesta = await api.upload<UsageLogUploadResponse>(`/projects/${projectId}/usage-logs/upload`, form);
      setResultado({ respuesta, version: etiquetaVersion(versionElegida), nombre: subido.name });
      await queryClient.invalidateQueries({ queryKey: ["humana", projectId] });
    } catch (err) {
      setResultado(null);
      setError(mensajeDeError(err));
    } finally {
      setSubiendo(false);
      // Un fichero distinto del que se subió no se pierde.
      setFichero((actual) => (actual === subido ? null : actual));
      const otro = inputRef.current?.files?.[0];
      if (inputRef.current && (!otro || otro === subido)) inputRef.current.value = "";
    }
  };

  return (
    <Card id="registro-uso" className="scroll-mt-20">
      <CardHeader>
        <CardTitle>Registro de uso</CardTitle>
        <p className="text-sm text-muted-foreground">{ayuda?.resumen ?? RESUMEN_RESERVA}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {ayuda ? (
          // Sin el tipo de tarea no se dibuja el formato (no parpadea de binario a multiclase).
          tarea.cargando || decision === undefined || tarea.sinRango ? null : (
            <FormatoRegistro ayuda={ayuda} onError={setError} decision={decision} clases={tarea.clases} />
          )
        ) : (
          <EnlaceFormato />
        )}
        {tarea.sinRango ? (
          // Una regresión sin rango favorable no tiene capa humana.
          <SinRangoCapaHumana />
        ) : puedeConfig ? (
          <div className="flex flex-col gap-4 rounded-md border border-border p-3">
            {decision === undefined ? null : (
              <DecisionRegistro
                decision={decision}
                ayuda={ayuda}
                favorable={favorable}
                onElegir={setFavorable}
                clases={tarea.clases}
                favorables={tarea.favorables}
                unidad={tarea.unidad}
                rangos={tarea.rangos}
              />
            )}
            <div className="flex flex-wrap items-end gap-3">
              <SelectorVersionRegistro versiones={versiones} valor={versionId} activaId={activaId} onCambiar={setVersionId} />
              <input
                ref={inputRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                data-testid="registro-uso-fichero"
                disabled={subiendo}
                onChange={(e) => {
                  if (subiendo) return;
                  const f = e.target.files?.[0];
                  if (f) {
                    setFichero(f);
                    setAbiertoSubida(true);
                  }
                }}
              />
              <Button
                size="sm"
                variant="outline"
                disabled={sinDeclarar || subiendo}
                onClick={() => inputRef.current?.click()}
              >
                {subiendo ? "Subiendo…" : "Subir registro CSV"}
              </Button>
            </div>
          </div>
        ) : null}

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {resultado ? <ResultadoRegistro resultado={resultado} sinCodificacion={sinCodificacion} /> : null}

        <EvaluarYDescargar projectId={projectId} puedeEvaluar={puedeConfig && !tarea.sinRango} />
      </CardContent>

      <MotivoDialog
        open={abiertoSubida}
        onOpenChange={(v) => {
          setAbiertoSubida(v);
          if (!v && !subiendo) {
            setFichero(null);
            if (inputRef.current) inputRef.current.value = "";
          }
        }}
        titulo="Subir registro de uso"
        descripcion={descripcionSubida(decision, fichero?.name, etiquetaVersion(versionElegida), favorable)}
        onConfirm={async () => {
          await subir();
        }}
      />
    </Card>
  );
}
