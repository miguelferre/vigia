/**
 * Acciones del editor de protocolo: restablecer la
 * plantilla, añadir/quitar/mover un hito extra y recalcular su clave
 * mientras es nuevo. Aparte de `configuracion-protocolo.tsx` para no
 * superar 9 KB en ese fichero.
 */

import { useState } from "react";

import { api, mensajeDeError } from "@/api/client";
import type { components } from "@/api/schema";
import type { HitoProtocoloEdit } from "./tipos";
import type { ProtocoloEditor } from "./configuracion-protocolo";

type ProtocoloPaso = components["schemas"]["ProtocoloPaso"];
type ContenidoProtocoloHitos = components["schemas"]["ContenidoProtocoloHitos"];

/** `GET /content/protocolo-hitos` no trae `responsable` ni `plazo_dias`: quedan vacíos. */
function plantillaAHitos(pasos: ProtocoloPaso[]): HitoProtocoloEdit[] {
  return [...pasos]
    .sort((a, b) => a.orden - b.orden)
    .map((p) => ({
      key: p.key,
      titulo: p.titulo,
      descripcion: p.descripcion,
      entregables: [...p.entregables],
      responsable: "",
      plazoDiasTexto: "",
    }));
}

/** `slug` de un título para la `key` de un hito extra nuevo, con sufijo
 * numérico si colisiona con otra clave ya en uso. */
export function generarClaveHito(titulo: string, clavesEnUso: ReadonlySet<string>): string {
  const base =
    titulo
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || "hito";
  if (!clavesEnUso.has(base)) return base;
  let sufijo = 2;
  while (clavesEnUso.has(`${base}_${sufijo}`)) sufijo += 1;
  return `${base}_${sufijo}`;
}

export interface AccionesProtocolo {
  restableciendo: boolean;
  errorPlantilla: string | null;
  restablecerPlantilla: () => void;
  cambiarHito: (idx: number, siguiente: HitoProtocoloEdit) => void;
  añadirHito: () => void;
  quitarHito: (idx: number) => void;
  moverHito: (idx: number, delta: number) => void;
}

export function useAccionesProtocolo(editor: ProtocoloEditor): AccionesProtocolo {
  const [restableciendo, setRestableciendo] = useState(false);
  const [errorPlantilla, setErrorPlantilla] = useState<string | null>(null);
  // Claves de hitos añadidos con «Añadir hito»: mientras sigan aquí, el
  // título recalcula la `key` al escribir.
  const [clavesNuevas, setClavesNuevas] = useState<Set<string>>(new Set());

  const restablecerPlantilla = () => {
    setRestableciendo(true);
    setErrorPlantilla(null);
    api
      .get<ContenidoProtocoloHitos>("/content/protocolo-hitos")
      .then((contenido) => {
        editor.setHitos(plantillaAHitos(contenido.pasos));
        setClavesNuevas(new Set());
      })
      .catch((e) => setErrorPlantilla(mensajeDeError(e)))
      .finally(() => setRestableciendo(false));
  };

  const cambiarHito = (idx: number, siguiente: HitoProtocoloEdit) => {
    const actual = editor.hitos[idx];
    let hito = siguiente;
    if (clavesNuevas.has(actual.key) && siguiente.titulo !== actual.titulo) {
      const otrasClaves = new Set(editor.hitos.filter((_, i) => i !== idx).map((h) => h.key));
      const nuevaClave = generarClaveHito(siguiente.titulo, otrasClaves);
      hito = { ...siguiente, key: nuevaClave };
      setClavesNuevas((prev) => {
        const siguienteSet = new Set(prev);
        siguienteSet.delete(actual.key);
        siguienteSet.add(nuevaClave);
        return siguienteSet;
      });
    }
    editor.setHitos(editor.hitos.map((h, i) => (i === idx ? hito : h)));
  };

  const añadirHito = () => {
    const clave = generarClaveHito("Hito nuevo", new Set(editor.hitos.map((h) => h.key)));
    const hito: HitoProtocoloEdit = {
      key: clave,
      titulo: "Hito nuevo",
      descripcion: "",
      entregables: [],
      responsable: "",
      plazoDiasTexto: "",
    };
    editor.setHitos([...editor.hitos, hito]);
    setClavesNuevas((prev) => new Set(prev).add(clave));
  };

  const quitarHito = (idx: number) => {
    const clave = editor.hitos[idx].key;
    editor.setHitos(editor.hitos.filter((_, i) => i !== idx));
    setClavesNuevas((prev) => {
      const siguienteSet = new Set(prev);
      siguienteSet.delete(clave);
      return siguienteSet;
    });
  };

  // Mover un hito extra: nunca a la posición 0 («Detección»).
  const moverHito = (idx: number, delta: number) => {
    const destino = idx + delta;
    if (destino < 1 || destino >= editor.hitos.length) return;
    const copia = [...editor.hitos];
    const [movido] = copia.splice(idx, 1);
    copia.splice(destino, 0, movido);
    editor.setHitos(copia);
  };

  return { restableciendo, errorPlantilla, restablecerPlantilla, cambiarHito, añadirHito, quitarHito, moverHito };
}
