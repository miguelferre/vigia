/**
 * Elegir la fila de la explicación local. Se escribe el id del
 * registro (el de la columna de id del fichero, `external_id`) y se resuelve
 * al número de fila del proyecto que pide el servidor; el número sigue
 * disponible para quien lo conozca. Resuelve entre los primeros 500 registros
 * del lote (el máximo de una página de la API).
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { ListResponse, Record_ } from "@/api/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { textoRangoFila } from "./lanzar-textos";

const LIMITE = 500;

/** Registros del lote con su id de fichero, para resolver id a número de fila. */
export function useRegistrosConId(batchId: number | null): Record_[] {
  const q = useQuery({
    queryKey: qk.records(batchId, { limit: LIMITE }),
    queryFn: () => api.get<ListResponse<Record_>>(`/batches/${batchId}/records?limit=${LIMITE}`),
    enabled: batchId !== null,
    staleTime: 60_000,
  });
  return q.data?.items ?? [];
}

/** Número de fila (`seq`) del registro con ese id, o `null` si no está entre los cargados. */
export function seqDeId(registros: readonly Record_[], id: string): number | null {
  const buscado = id.trim();
  if (buscado === "") return null;
  return registros.find((r) => r.external_id === buscado)?.seq ?? null;
}

interface Props {
  batchId: number | null;
  rowSeq: string;
  onRowSeq: (valor: string) => void;
  rango: { min: number; max: number } | null;
}

export function CampoFilaLocal({ batchId, rowSeq, onRowSeq, rango }: Props) {
  const registros = useRegistrosConId(batchId);
  const [idTexto, setIdTexto] = useState("");
  const hayIds = registros.some((r) => r.external_id !== null && r.external_id !== "");
  const resuelto = seqDeId(registros, idTexto);
  const sinResolver = idTexto.trim() !== "" && resuelto === null;

  const cambiarId = (valor: string) => {
    setIdTexto(valor);
    onRowSeq(valor.trim() === "" ? "" : String(seqDeId(registros, valor) ?? ""));
  };
  const cambiarNumero = (valor: string) => {
    setIdTexto("");
    onRowSeq(valor);
  };

  return (
    <div className="flex flex-wrap items-start gap-3">
      {hayIds ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="row-id">Id del registro (alternativa al número de fila)</Label>
          <Input
            id="row-id"
            className="w-44"
            list="row-id-lista"
            value={idTexto}
            onChange={(e) => cambiarId(e.target.value)}
            placeholder={registros.find((r) => r.external_id)?.external_id ?? ""}
            autoComplete="off"
          />
          <datalist id="row-id-lista">
            {registros.map((r) => (r.external_id ? <option key={r.seq} value={r.external_id} /> : null))}
          </datalist>
          <span className="text-xs text-muted-foreground" aria-live="polite">
            {resuelto !== null
              ? `Es la fila ${resuelto} del proyecto.`
              : sinResolver
                ? `Ese id no está entre los primeros ${LIMITE} registros del lote; escribe el número de fila.`
                : "El id de la columna de id de tu fichero."}
          </span>
        </div>
      ) : null}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="row-seq">Número de fila (explicación local)</Label>
        <Input
          id="row-seq"
          className="w-32"
          inputMode="numeric"
          value={rowSeq}
          onChange={(e) => cambiarNumero(e.target.value)}
          placeholder={rango ? String(rango.min) : "p. ej. 12"}
        />
        {batchId !== null ? <span className="text-xs text-muted-foreground">{textoRangoFila(rango)}</span> : null}
      </div>
    </div>
  );
}
