/**
 * Paso «Umbrales» del alta (tras congelar la línea base): pestaña
 * «Umbrales» de `/modelos/:id` (`detalle.tsx`). Llama a `GET
 * /projects/{id}/thresholds/proposal` y enseña, por monitor y métrica, el
 * valor de la línea base, la propuesta y el umbral actual con su origen; el
 * usuario acepta la propuesta (origen `linea_base`) o escribe el del
 * fabricante o el del criterio del responsable con su nota, y se guarda con el
 * `PATCH` del monitor. Sin línea base congelada, 409: estado vacío que dice
 * qué hacer.
 *
 * Al confirmar, aunque no cambie nada, se guardan los umbrales y se
 * evalúa la línea base con ellos (`alta-umbrales-evaluar.ts`). Sin
 * propuesta para una métrica no se ofrece «Aceptar propuesta» y se enseña
 * el motivo (`alta-umbrales-fila.tsx`).
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Link } from "react-router";

import { ApiError, mensajeDeError } from "@/api/client";
import { qk, useProject } from "@/api/queries";
import { useThresholdsProposal } from "@/api/queries-alta";
import { useEvaluations } from "@/api/queries-evaluaciones";
import type { ActorBody } from "@/api/types";
import { EmptyState, MotivoDialog } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody } from "@/components/ui/table";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { etiquetaCriterio } from "@/pages/monitores/tipos";
import { CabeceraUmbrales } from "./alta-umbrales-cabecera";
import { FilaUmbral } from "./alta-umbrales-fila";
import { NotaUmbralesTipo } from "./alta-umbrales-nota";
import { NotaConjuntoUmbrales, conNotaDelConjunto, filasConNota, pideNota } from "./alta-umbrales-conjunto";
import { clave, guardarUmbralesMonitores, type Ediciones } from "./alta-umbrales-guardar";
import { useEvaluarLineaBase } from "./alta-umbrales-evaluar";
import { ETIQUETA_TAMANO_LOTE, textoLoteSimulado } from "./alta-umbrales-textos";
import { semillaEdiciones, edicionDeFila } from "./alta-umbrales-semilla";

interface Props {
  projectId: number;
}

export default function UmbralesTab({ projectId }: Props) {
  const { data: proyecto } = useProject(projectId);
  // Sin el tipo de tarea no se siembra ni se da formato a los valores.
  const { caps, unidad, cargando: cargandoTipo } = useTipoTarea(projectId);
  const [tamanoLoteTexto, setTamanoLoteTexto] = useState("1000");
  const tamanoLote = Number(tamanoLoteTexto) > 0 ? Number(tamanoLoteTexto) : 1000;
  const { data: propuesta, isLoading, error } = useThresholdsProposal(projectId, tamanoLote);
  const [ediciones, setEdiciones] = useState<Ediciones>({});
  const [semilla, setSemilla] = useState<number | null>(null);
  const [motivoAbierto, setMotivoAbierto] = useState(false);
  const [notaConjunto, setNotaConjunto] = useState("");
  const queryClient = useQueryClient();
  const evaluacion = useEvaluarLineaBase();
  // Esta pestaña sigue viva tras el alta: la línea base se evalúa al confirmar
  // solo si aún no tiene evaluación (sin duplicar evaluaciones ni alertas).
  const { data: evalsBase } = useEvaluations(
    propuesta ? projectId : null,
    propuesta ? { batch_id: propuesta.baseline_batch_id, limit: 1 } : undefined,
  );
  const lineaBaseSinEvaluar = !!evalsBase && evalsBase.total === 0;

  // Semilla de las ediciones al llegar la propuesta (o al cambiar el tamaño
  // de lote): ajuste de estado durante el render, no en un efecto (mismo
  // patrón que `datasetSincronizado` de `subida-dataset.tsx`).
  if (propuesta && !cargandoTipo && semilla !== propuesta.baseline_batch_id + tamanoLote) {
    setSemilla(propuesta.baseline_batch_id + tamanoLote);
    setEdiciones(semillaEdiciones(propuesta));
  }

  if (isLoading || (cargandoTipo && !error)) return <p className="text-sm text-muted-foreground">Cargando propuesta…</p>;

  if (error) {
    const sinLineaBase = error instanceof ApiError && error.status === 409;
    return (
      <EmptyState
        titulo={sinLineaBase ? "Sin línea base congelada" : "No se ha podido calcular la propuesta"}
        descripcion={
          sinLineaBase ? (
            <>
              La versión activa no tiene línea base congelada: la propuesta de umbrales se calcula
              sobre ella. Congélala primero en la pestaña Versiones.
            </>
          ) : (
            mensajeDeError(error)
          )
        }
        accion={
          sinLineaBase ? (
            <Button asChild size="sm" variant="outline">
              <Link to={`/modelos/${projectId}#versiones`}>Ir a Versiones</Link>
            </Button>
          ) : undefined
        }
      />
    );
  }

  if (!propuesta) return null;

  const guardar = async (cuerpo: ActorBody) => {
    await guardarUmbralesMonitores(propuesta, proyecto, conNotaDelConjunto(ediciones, notaConjunto), cuerpo);
    await queryClient.invalidateQueries({ queryKey: qk.monitors(projectId) });
    await queryClient.invalidateQueries({ queryKey: qk.project(projectId) });
    // La columna «Umbral actual» lee la propuesta, no los monitores.
    await queryClient.invalidateQueries({ queryKey: qk.thresholdsProposalDe(projectId) });
    toast.success("Umbrales guardados");
    // Aunque no haya cambiado ningún umbral, confirmar el paso evalúa
    // la línea base con los que hay.
    if (!lineaBaseSinEvaluar) return;
    try {
      await evaluacion.lanzar(propuesta.baseline_batch_id);
    } catch (err) {
      // Los umbrales ya están guardados: no se reintenta el PATCH desde el diálogo.
      toast.error(`Umbrales guardados, pero no se ha podido evaluar la línea base: ${mensajeDeError(err)}`);
    }
  };

  const nPropias = filasConNota(ediciones);
  const enConjunto = nPropias >= 2;
  const hayEdicionesConNotaFaltante = Object.values(conNotaDelConjunto(ediciones, notaConjunto)).some(
    (e) => pideNota(e) && e.nota.trim() === "",
  );

  return (
    <div className="flex flex-col gap-6 pt-4">
      <p className="text-sm text-muted-foreground">
        {textoLoteSimulado(propuesta.tamano_lote)}
      </p>
      <NotaUmbralesTipo proyecto={proyecto} />
      {lineaBaseSinEvaluar ? (
        <p className="text-sm text-muted-foreground">
          La línea base todavía no se ha evaluado con umbrales tuyos. Al guardar este paso, aunque no
          cambies nada, se guardan los umbrales y se evalúa la línea base con ellos.
        </p>
      ) : null}
      <div className="flex items-end gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="umbrales-tamano-lote">{ETIQUETA_TAMANO_LOTE}</Label>
          <Input
            id="umbrales-tamano-lote"
            type="number"
            className="w-40"
            value={tamanoLoteTexto}
            onChange={(e) => setTamanoLoteTexto(e.target.value)}
          />
        </div>
      </div>
      {propuesta.monitors.map((m) => (
        <div key={m.monitor_type} className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{ETIQUETA_MONITOR[m.monitor_type] ?? m.monitor_type}</h3>
          <Table className="table-fixed">
            <CabeceraUmbrales dominio={proyecto?.domain} />
            <TableBody>
              {m.propuestas.map((p) => {
                const k = clave(m.monitor_type, p);
                const e = edicionDeFila(ediciones, m.monitor_type, p);
                return (
                  <FilaUmbral
                    key={k}
                    propuesta={p}
                    edicion={e}
                    dominio={proyecto?.domain}
                    notaEnConjunto={enConjunto}
                    unidad={caps?.unidad ? unidad : undefined}
                    onCambiar={(sig) => setEdiciones((prev) => ({ ...prev, [k]: sig }))}
                  />
                );
              })}
            </TableBody>
          </Table>
        </div>
      ))}
      {enConjunto ? (
        <NotaConjuntoUmbrales cambiadas={nPropias} nota={notaConjunto} onCambiar={setNotaConjunto} />
      ) : null}
      <Button className="w-fit" onClick={() => setMotivoAbierto(true)}>
        Guardar umbrales
      </Button>
      {evaluacion.estado ? (
        <p role="status" className="text-sm text-muted-foreground">
          {evaluacion.estado}
        </p>
      ) : null}
      <MotivoDialog
        open={motivoAbierto}
        onOpenChange={setMotivoAbierto}
        titulo="Guardar umbrales"
        descripcion={
          hayEdicionesConNotaFaltante
            ? `Falta la nota de algún umbral de fabricante o ${etiquetaCriterio(proyecto?.domain)}: escríbela antes de guardar.`
            : undefined
        }
        etiquetaConfirmar="Guardar"
        deshabilitado={hayEdicionesConNotaFaltante}
        onConfirm={guardar}
      />
    </div>
  );
}
