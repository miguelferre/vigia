/**
 * Barra lateral.
 *
 * Sobre la navegación por grupos, colapsable a solo iconos, se
 * añaden tres piezas: la tarjeta de proyecto activo y su
 * versión, el buscador con atajo `Ctrl K` (`useAtajoBusqueda`, hacia
 * `/ayuda?q=`) y un recuento de alertas abiertas por monitor junto a cada
 * entrada de Vigilancia.
 *
 * Los recuentos leen `useAlerts(projectId, "abierta,en_observacion,reconocida")`,
 * la misma cadena de estados "abierta" que usaba `AlertasRejilla` (retirada
 * en el punto 5 de esta fila): así los números de aquí y los que aparecían
 * ahí no se desalinean con un criterio distinto.
 */

import { useEffect, useMemo, useState } from "react";
import { NavLink } from "react-router";
import { SearchIcon } from "lucide-react";

import { Input } from "@/components/ui/input";
import { ApiError } from "@/api/client";
import { useAlerts, useProject } from "@/api/queries";
import { useAtajoBusqueda } from "@/hooks/useAtajoBusqueda";
import { NAVEGACION } from "@/layout/nav";
import { useSession } from "@/session/session";
import type { MonitorType } from "@/api/types";
import { cn } from "@/lib/utils";

// (RecuentosAlertas se define más abajo, junto al hook que la produce.)

export interface SidebarProps {
  colapsada: boolean;
  /** Se llama al pulsar una entrada (para cerrar el panel en móvil). */
  onNavegar?: () => void;
}

/** Entradas de "Vigilancia" con recuento propio: la etiqueta del monitor debe
 * coincidir con el `MonitorType` que agrupa `useAlerts`. */
const MONITOR_DE_ETIQUETA: Record<string, MonitorType> = {
  Equidad: "fairness",
  Calidad: "quality",
  Deriva: "drift",
};

interface RecuentosAlertas {
  porMonitor: Partial<Record<MonitorType, number>>;
  total: number;
}

function useRecuentosPorMonitor(projectId: number | null): RecuentosAlertas {
  const { data } = useAlerts(projectId, "abierta,en_observacion,reconocida");
  return useMemo(() => {
    const porMonitor: Partial<Record<MonitorType, number>> = {};
    for (const alerta of data?.items ?? []) {
      porMonitor[alerta.monitor_type] = (porMonitor[alerta.monitor_type] ?? 0) + 1;
    }
    return { porMonitor, total: data?.items.length ?? 0 };
  }, [data]);
}

function TarjetaProyecto({ colapsada }: { colapsada: boolean }) {
  const { projectId, setProjectId } = useSession();
  const { data: proyecto, error } = useProject(projectId);
  // El proyecto que la sesión recordaba ya no existe (otra base de datos en el
  // mismo origen, o borrado desde otra pestaña): se olvida, para que ninguna
  // pantalla siga pidiéndolo.
  useEffect(() => {
    if (error instanceof ApiError && error.status === 404) setProjectId(null);
  }, [error, setProjectId]);
  if (!proyecto || colapsada) return null;

  const version = proyecto.versions.find((v) => v.id === proyecto.active_version_id);

  return (
    <div className="mx-3 mt-3 flex flex-col gap-0.5 rounded-md border border-border bg-muted/40 px-3 py-2">
      <span className="truncate text-sm font-semibold" title={proyecto.name}>
        {proyecto.name}
      </span>
      <span className="truncate text-xs text-muted-foreground">
        {version ? `Versión ${version.label}` : "Sin versión activa"}
        {proyecto.is_demo ? " · sintético" : ""}
      </span>
    </div>
  );
}

function Buscador({ colapsada }: { colapsada: boolean }) {
  const [texto, setTexto] = useState("");
  useAtajoBusqueda(texto);
  if (colapsada) return null;
  return (
    <div className="relative mx-3 mt-3">
      <SearchIcon
        className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder="Buscar"
        aria-label="Buscar en la ayuda"
        className="h-8 pl-8 text-sm"
      />
      <kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 rounded border border-border px-1 text-xs text-tertiary">
        Ctrl K
      </kbd>
    </div>
  );
}

export function Sidebar({ colapsada, onNavegar }: SidebarProps) {
  const { projectId } = useSession();
  const recuentos = useRecuentosPorMonitor(projectId);

  return (
    <nav aria-label="Navegación principal" className="flex flex-col gap-5 py-1">
      <TarjetaProyecto colapsada={colapsada} />
      <Buscador colapsada={colapsada} />

      {NAVEGACION.map((grupo) => {
        return (
          <div key={grupo.titulo} className="flex flex-col gap-1">
            {!colapsada ? (
              <p className="px-3 pb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                {grupo.titulo}
              </p>
            ) : (
              <div className="mx-3 mb-1 border-t border-border" aria-hidden="true" />
            )}
            <EntradasGrupo grupo={grupo} colapsada={colapsada} recuentos={recuentos} onNavegar={onNavegar} />
          </div>
        );
      })}
    </nav>
  );
}

function EntradasGrupo({
  grupo,
  colapsada,
  recuentos,
  onNavegar,
}: {
  grupo: (typeof NAVEGACION)[number];
  colapsada: boolean;
  recuentos: RecuentosAlertas;
  onNavegar?: () => void;
}) {
  return (
    <>
      {grupo.entradas.map((entrada) => {
        const Icono = entrada.icono;
        const monitorType = MONITOR_DE_ETIQUETA[entrada.etiqueta];
        const recuento = monitorType
          ? recuentos.porMonitor[monitorType]
          : entrada.etiqueta === "Alertas"
            ? recuentos.total
            : undefined;
        const contenido = (
          <>
            <Icono className="size-4 shrink-0" aria-hidden="true" />
            {!colapsada ? <span className="truncate">{entrada.etiqueta}</span> : null}
            {!colapsada && typeof recuento === "number" && recuento > 0 ? (
              <span className="ml-auto text-xs tabular-nums text-muted-foreground">{recuento}</span>
            ) : null}
          </>
        );
        const base = "mx-2 flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors";
        return (
          <NavLink
            key={entrada.etiqueta}
            to={entrada.a}
            end={entrada.exacta}
            onClick={onNavegar}
            title={colapsada ? entrada.etiqueta : undefined}
            className={({ isActive }) =>
              cn(base, isActive ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-muted")
            }
          >
            {contenido}
          </NavLink>
        );
      })}
    </>
  );
}
