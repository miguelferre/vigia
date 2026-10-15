/**
 * Sección «Guía de uso» de `/ayuda`: las 12
 * entradas de `guia-uso.json` (`useGuiaUso`) en un acordeón, arriba de
 * Símbolos. El buscador de la página la filtra igual que Conceptos y
 * Métricas (`filtrarGuia` en `agrupar.ts`). La entrada cuyo id coincide con
 * el hash `#guia-N` se abre sola y la página se desplaza a ella; como en una
 * SPA el salto nativo del navegador no espera al contenido asíncrono, el
 * desplazamiento se reintenta a mano (`ancla.ts`).
 */

import { useEffect } from "react";
import { useLocation } from "react-router";

import { useGlosario, useGuiaUso } from "@/api/queries-contenido";
import { useSession } from "@/session/session";

import { filtrarGuia } from "./agrupar";
import { GuiaEntrada } from "./GuiaEntrada";
import { idDeHash, programarScrollAGuia } from "./ancla";

export interface GuiaUsoProps {
  busqueda: string;
}

export function GuiaUso({ busqueda }: GuiaUsoProps) {
  const guiaQ = useGuiaUso();
  const glosarioQ = useGlosario();
  const { projectId } = useSession();
  const { hash } = useLocation();

  // Qué entrada abre el acordeón se deriva del hash en cada render, no de un
  // efecto: solo el desplazamiento (una interacción con el DOM externo a
  // React) necesita efecto, para reintentar hasta que el elemento exista.
  const anclaAbierta = idDeHash(hash);
  useEffect(() => {
    if (anclaAbierta !== null) programarScrollAGuia(anclaAbierta);
  }, [anclaAbierta]);

  const entradas = filtrarGuia(guiaQ.data?.entradas, busqueda);
  const conBusqueda = busqueda.trim().length > 0;

  return (
    <section id="guia" className="scroll-mt-20 flex flex-col gap-3">
      <h2 className="text-sm font-semibold">Guía de uso</h2>
      <p className="text-sm text-muted-foreground">
        Cómo usar Vigía paso a paso: qué necesitas, cómo se crea un modelo, se sube la línea
        base, se configuran los monitores y se investiga una alerta.
      </p>
      {guiaQ.isLoading ? (
        <p className="text-sm text-muted-foreground">Cargando la guía…</p>
      ) : entradas.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {conBusqueda ? "Sin entradas de la guía para esta búsqueda." : "Guía de uso no disponible."}
        </p>
      ) : (
        <div className="flex flex-col divide-y divide-border rounded-md border border-border px-4">
          {entradas.map((entrada) => (
            <div key={entrada.id} className="py-3">
              <GuiaEntrada
                entrada={entrada}
                abierta={anclaAbierta === entrada.id}
                glosario={glosarioQ.data}
                projectId={projectId}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
