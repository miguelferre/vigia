/**
 * Diario de cuatro carriles (`/diario`).
 *
 * Filtros por carril, tipo de objeto, correlación, fecha y alcance de
 * proyecto; tabla paginada con fila expandible; modo en vivo por SSE
 * (`useDiarioEnVivo`, sobre el mismo flujo que invalida las consultas);
 * exportación con los mismos filtros (`/api/events/export`); anotación
 * humana desde la cabecera.
 *
 * Una sola vista: la línea de tiempo (hilo cronológico,
 * antes `LineaTiempoMes`) se retira porque enseñaba lo mismo que la
 * lista y su periodo propio de 30 días dejaba la pantalla vacía durante la
 * demo, cuyas fases están fechadas hasta seis semanas atrás.
 */

import { useState } from "react";
import { useSearchParams } from "react-router";

import { mensajeDeError } from "@/api/client";
import { PageHeader, SinProyecto } from "@/components/vigia";
import { useEvents, useProject } from "@/api/queries";
import { useBatches } from "@/api/queries-datos";
import { useTextosPantalla } from "@/api/queries-contenido";
import { useSession } from "@/session/session";
import { useTitulo } from "@/hooks/useTitulo";
import type { ActorKind } from "@/api/types";
import { AvisoFiltroProyecto } from "./AvisoFiltroProyecto";
import { Filtros } from "./Filtros";
import { Leyenda } from "./Leyenda";
import { RESPALDO_CARRILES } from "./diario-textos";
import { EventosTabla } from "./EventosTabla";
import { ExportarEventos } from "./ExportarEventos";
import { PaginacionEventos } from "./PaginacionEventos";
import { AnotacionHumana } from "./AnotacionHumana";
import { useDiarioEnVivo } from "./useDiarioEnVivo";

// La lista pagina de 50 en 50 (con 50, una reproducción de demo -unos 120
// eventos de modelo y sistema seguidos- dejaba el carril humano en cero
// aunque el usuario acabara de crearla, D4).
const LIMITE_LISTA = 50;

export default function Diario() {
  useTitulo("Diario");
  const { projectId } = useSession();
  const { data: proyecto } = useProject(projectId);
  const textos = useTextosPantalla();
  // En la columna «Objeto», un lote se nombra por su número, no por el `id` de la fila.
  const lotes = useBatches(projectId);
  const numeroDeLote = new Map<number, number>(
    (lotes.data?.items ?? []).flatMap((b) => (b.id !== null && b.seq !== null ? [[b.id, b.seq] as const] : [])),
  );

  const [actorKind, setActorKind] = useState<ActorKind | null>(null);
  const [objectType, setObjectType] = useState<string | null>(null);
  // `?correlation_id=` llega desde el detalle de una alerta.
  const [searchParams] = useSearchParams();
  const [correlationId, setCorrelationId] = useState(searchParams.get("correlation_id") ?? "");
  const [since, setSince] = useState("");
  const [soloProyecto, setSoloProyecto] = useState(true);
  const [enVivo, setEnVivo] = useState(true);
  const [offset, setOffset] = useState(0);

  // Cambiar cualquier filtro vuelve a la primera página. Se resuelve como
  // estado derivado en el render (no en un efecto) para no encadenar
  // renderizados: si la clave de filtro cambió desde el render anterior, la
  // página se reinicia aquí mismo.
  const claveFiltro = `${actorKind}|${objectType}|${correlationId}|${since}|${soloProyecto}`;
  const [claveFiltroAnterior, setClaveFiltroAnterior] = useState(claveFiltro);
  if (claveFiltro !== claveFiltroAnterior) {
    setClaveFiltroAnterior(claveFiltro);
    setOffset(0);
  }

  // `new Date("aaaa-mm-dd")` interpreta la fecha en UTC; con `T00:00:00` se
  // interpreta en la hora local, que es lo que espera el filtro "Desde".
  const sinceIso = since ? new Date(`${since}T00:00:00`).toISOString() : "";
  const proyectoIdFiltro = soloProyecto ? projectId : null;

  const { data, isPending, isError, error, refetch } = useEvents({
    actor_kind: actorKind,
    object_type: objectType,
    correlation_id: correlationId || null,
    since: sinceIso || null,
    project_id: proyectoIdFiltro,
    offset,
    limit: LIMITE_LISTA,
  });

  // `useDiarioEnVivo` también gestiona la pausa de invalidación SSE de la
  // raíz "events".
  const vivos = useDiarioEnVivo(enVivo, {
    actorKind,
    objectType,
    correlationId,
    since: sinceIso,
    projectId: proyectoIdFiltro,
  });

  const paginaItems = data?.items ?? [];
  const idsPagina = new Set(paginaItems.map((e) => e.id).filter((id): id is number => id !== null));
  const vivosNuevos =
    offset === 0 ? vivos.filter((e) => e.id !== null && !idsPagina.has(e.id)) : [];
  const eventos = [...vivosNuevos, ...paginaItems].slice(0, LIMITE_LISTA);
  const recienLlegados = new Set(
    vivosNuevos.map((e) => e.id).filter((id): id is number => id !== null),
  );

  // La anotación recién registrada entra por SSE en la primera página: si el
  // usuario estaba paginado, se vuelve al principio para que la vea.
  const volverAlPrincipio = () => setOffset(0);

  const total = data?.total ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo={soloProyecto && proyecto?.name ? `Diario de ${proyecto.name}` : "Diario"}
        descripcion={textos.data?.diario?.carriles ?? RESPALDO_CARRILES}
        acciones={
          // `items-start` porque la exportación es una columna (botones más
          // aviso) y «Anotar» quedaría centrado contra ella.
          <div className="flex flex-wrap items-start gap-2">
            <AnotacionHumana projectId={proyectoIdFiltro} onRegistrada={volverAlPrincipio} />
            <ExportarEventos
              filtros={{
                sinceIso,
                projectId: proyectoIdFiltro,
                proyectoNombre: proyecto?.name ?? null,
                actorKind,
                objectType,
                correlationId,
              }}
            />
          </div>
        }
      />

      {/* Sin modelo elegido el diario filtrado no tiene qué enseñar; el
          diario sin filtrar (eventos de sistema, antes del primer alta) sigue
          a la vista debajo del aviso. */}
      {projectId === null ? <SinProyecto que="su diario" /> : null}

      <Filtros
        actorKind={actorKind}
        onActorKindChange={setActorKind}
        objectType={objectType}
        onObjectTypeChange={setObjectType}
        correlationId={correlationId}
        onCorrelationIdChange={setCorrelationId}
        since={since}
        onSinceChange={setSince}
        soloProyecto={soloProyecto}
        onSoloProyectoChange={setSoloProyecto}
        proyectoNombre={proyecto?.name ?? null}
        enVivo={enVivo}
        onEnVivoChange={setEnVivo}
      />

      {soloProyecto && proyecto?.name ? (
        <AvisoFiltroProyecto proyectoNombre={proyecto.name} onQuitar={() => setSoloProyecto(false)} />
      ) : null}

      <Leyenda />

      <div className="flex flex-col gap-3" data-loading={isPending ? "true" : undefined}>
        <EventosTabla
          eventos={eventos}
          cargando={isPending}
          error={isError}
          mensajeDeError={isError ? mensajeDeError(error) : null}
          onReintentar={() => void refetch()}
          recienLlegados={recienLlegados}
          numeroDeLote={numeroDeLote}
          onCorrelacionClick={setCorrelationId}
        />

        {!isPending ? (
          <PaginacionEventos offset={offset} total={total} limite={LIMITE_LISTA} onChange={setOffset} />
        ) : null}
      </div>
    </div>
  );
}
