/**
 * Una entrada de la guía de uso: propósito, pasos numerados, botón «Ir a la
 * pantalla», chips de conceptos relacionados y el aviso de «estado» cuando
 * lo trae (entradas 9 y 11, funcionalidad que llega en una versión
 * posterior). `<details>` sin controlar salvo por el `open` inicial: React
 * no vuelve a forzarlo tras el primer render, así que el usuario puede
 * cerrar y volver a abrir cualquier entrada con normalidad.
 */

import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { EntradaGuia, Glosario } from "@/api/queries-contenido";

function textoConcepto(entrada: { descripcion?: string; definicion?: string } | undefined): string {
  return entrada?.definicion ?? entrada?.descripcion ?? "Sin definición todavía.";
}

/** Ruta con `:id` resuelto al proyecto de sesión, o deshabilitada si no hay ninguno. */
function resolverRuta(ruta: string, projectId: number | null): { href: string | null; motivo?: string } {
  if (!ruta.includes(":id")) return { href: ruta };
  if (projectId === null) {
    return { href: null, motivo: "Abre un modelo para ir directamente a esta pantalla." };
  }
  return { href: ruta.replace(":id", String(projectId)) };
}

export interface GuiaEntradaProps {
  entrada: EntradaGuia;
  abierta: boolean;
  glosario: Glosario | undefined;
  projectId: number | null;
}

export function GuiaEntrada({ entrada, abierta, glosario, projectId }: GuiaEntradaProps) {
  const { href, motivo } = resolverRuta(entrada.ruta, projectId);
  return (
    <details id={`guia-${entrada.id}`} className="scroll-mt-20 text-md" open={abierta || undefined}>
      <summary className="cursor-pointer font-semibold text-tertiary select-none">
        {entrada.titulo}
      </summary>
      <div className="mt-2 flex flex-col gap-3">
        <p className="text-tertiary">{entrada.para_que}</p>
        <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
          {entrada.pasos.map((paso, i) => (
            <li key={i}>{paso}</li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild={href !== null} type="button" variant="outline" size="sm" disabled={href === null} title={motivo}>
            {href !== null ? <Link to={href}>Ir a la pantalla</Link> : <span>Ir a la pantalla</span>}
          </Button>
          {entrada.ver_tambien.map((clave) => {
            const concepto = glosario?.[clave];
            return (
              <Popover key={clave}>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className="inline-flex h-[22px] items-center rounded-full border border-border px-2 text-xs font-medium hover:bg-muted"
                  >
                    {concepto?.etiqueta ?? clave}
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-80 text-sm">
                  <p className="mb-1 font-semibold">{concepto?.etiqueta ?? clave}</p>
                  <p className="text-muted-foreground">{textoConcepto(concepto)}</p>
                </PopoverContent>
              </Popover>
            );
          })}
          {entrada.estado ? (
            <span
              className="inline-flex h-[22px] items-center rounded-full px-2 text-xs font-medium"
              style={{ background: "var(--state-warn-fill)" }}
            >
              {entrada.estado}
            </span>
          ) : null}
        </div>
      </div>
    </details>
  );
}
