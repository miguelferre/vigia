/**
 * Lo que pasa con los lotes cuando llegan etiquetas tardías.
 * Un fichero de etiquetas no crea lote: añade la verdad a lotes ya ingeridos
 * y su calidad hay que calcularla de nuevo. El trabajo de ingesta devuelve
 * `lotes_con_verdad`, `lotes_reevaluados`, `lotes_a_reevaluar` y un motivo
 * con ids de lote: aquí se dice, con la numeración de la interfaz, qué lotes
 * se reevaluaron y, si no, se
 * ofrece «Evaluar estos lotes», que lanza `POST /batches/{id}/evaluate` con
 * `feedback_tardio` lote a lote, como el runner.
 */

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, mensajeDeError } from "@/api/client";
import { useBatches } from "@/api/queries-datos";
import type { Job } from "@/api/types";
import { Button } from "@/components/ui/button";
import { numeroLote } from "@/lib/fases";
import {
  fraseReevaluados,
  frasePendientes,
  listaDeLotes,
  type NombreDeLote,
  type ResultadoTardias,
} from "./subida-tardias-textos";

const esLista = (v: unknown): v is number[] => Array.isArray(v) && v.every((x) => typeof x === "number");

interface Props {
  projectId: number;
  resultado: ResultadoTardias | null;
}

export function AvisoEtiquetasTardias({ projectId, resultado }: Props) {
  const queryClient = useQueryClient();
  const hechos = esLista(resultado?.lotes_reevaluados) ? resultado.lotes_reevaluados : [];
  const pendientes = esLista(resultado?.lotes_a_reevaluar) ? resultado.lotes_a_reevaluar : [];
  const [enCurso, setEnCurso] = useState(false);
  const [lanzados, setLanzados] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  // La API devuelve ids de lote; la interfaz numera con `numeroLote(seq)` y la fase.
  const batchesQ = useBatches(hechos.length + pendientes.length > 0 ? projectId : null);
  const nombre = useMemo<NombreDeLote>(() => {
    const lotes = batchesQ.data?.items ?? [];
    return (id) => {
      const b = lotes.find((x) => x.id === id);
      if (!b) return `#${id}`;
      return b.phase_label ? `${numeroLote(b.seq)} (${b.phase_label})` : numeroLote(b.seq);
    };
  }, [batchesQ.data]);

  const restantes = pendientes.filter((i) => !lanzados.includes(i));
  const frase = fraseReevaluados(hechos, nombre);
  if (!frase && pendientes.length === 0) return null;

  const evaluar = async () => {
    setEnCurso(true);
    setError(null);
    const ok: number[] = [];
    const fallos: string[] = [];
    // Uno a uno y en orden: un fallo no para los demás (interfaz fijada §1).
    for (const id of restantes) {
      try {
        await api.post<Job>(`/batches/${id}/evaluate`, { trigger: "feedback_tardio" });
        ok.push(id);
      } catch (e) {
        fallos.push(`lote ${nombre(id)}: ${mensajeDeError(e)}`);
      }
    }
    setLanzados([...lanzados, ...ok]);
    setError(fallos.length > 0 ? fallos.join(" ") : null);
    setEnCurso(false);
    void queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    void queryClient.invalidateQueries({ queryKey: ["state"] });
  };

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm" data-testid="etiquetas-tardias">
      {frase ? <p data-testid="lotes-reevaluados">{frase}</p> : null}
      {pendientes.length > 0 ? (
        <>
          <p className="text-muted-foreground" data-testid="lotes-a-reevaluar">
            {frasePendientes(pendientes, nombre)}
          </p>
          {lanzados.length > 0 ? (
            <p role="status">
              {lanzados.length === 1 ? "Evaluación en curso del lote" : "Evaluación en curso de los lotes"}{" "}
              {listaDeLotes(lanzados, nombre)}.
            </p>
          ) : null}
          {error ? (
            <p className="text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          {restantes.length > 0 ? (
            <Button type="button" className="w-fit" disabled={enCurso} onClick={() => void evaluar()}>
              Evaluar estos lotes
            </Button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
