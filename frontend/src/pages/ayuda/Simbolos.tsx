/**
 * Sección «Símbolos» de `/ayuda`: leyenda de
 * estados y de monitores generada desde `lib/iconos.ts`, más las tres
 * cifras de cada tarjeta de monitor. Como el artboard `Indicadores.dc.html`:
 * dos columnas en una `Card`. No se filtra con el buscador (a diferencia de
 * conceptos y métricas): se oculta mientras hay una búsqueda, porque es
 * vocabulario fijo, no un resultado de texto.
 */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { colorEstado } from "@/components/vigia";
import { ETIQUETA_ESTADO, ETIQUETA_MONITOR, DESCRIPCION_MONITOR } from "@/lib/metrics";
import { GLIFO_ESTADO, ICONO_MONITOR } from "@/lib/iconos";
import type { EstadoMotor, MonitorType } from "@/api/types";

const FRASE_ESTADO: Record<EstadoMotor, string> = {
  ok: "Dentro de umbral.",
  aviso: "Cerca del umbral, o severidad media en una alerta.",
  alerta: "Fuera de umbral, o severidad alta en una alerta.",
  inestable: "Valor frágil: la muestra que lo sostiene es pequeña.",
  sin_datos: "Sin evaluación todavía.",
};

const ORDEN_ESTADOS: EstadoMotor[] = ["ok", "aviso", "alerta", "inestable", "sin_datos"];
const ORDEN_MONITORES: MonitorType[] = ["fairness", "quality", "drift", "cross", "explain"];

export interface SimbolosProps {
  oculto: boolean;
}

export function Simbolos({ oculto }: SimbolosProps) {
  if (oculto) {
    return null;
  }
  return (
    <section id="simbolos" className="flex scroll-mt-20 flex-col gap-3">
      <h2 className="text-sm font-semibold">Símbolos</h2>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Vocabulario común</CardTitle>
          <p className="text-xs text-muted-foreground">
            Los mismos símbolos en la tarjeta de modelo, el cuadro de mando, los monitores y esta
            ayuda.
          </p>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-6 pt-0 sm:grid-cols-2">
          <div className="flex flex-col gap-3">
            <span className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
              Estados
            </span>
            {ORDEN_ESTADOS.map((estado) => {
              const Glifo = GLIFO_ESTADO[estado];
              return (
                <div key={estado} className="flex items-start gap-3">
                  <span
                    className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full"
                    style={{ background: colorEstado(estado, "relleno") }}
                  >
                    <Glifo className="size-3.5" style={{ color: "var(--state-on-fill)" }} />
                  </span>
                  <span className="text-sm">
                    <span className="font-medium">{ETIQUETA_ESTADO[estado]}</span>
                    <span className="block text-xs text-muted-foreground">
                      {FRASE_ESTADO[estado]}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
          <div className="flex flex-col gap-3">
            <span className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
              Monitores
            </span>
            {ORDEN_MONITORES.map((monitor) => {
              const Icono = ICONO_MONITOR[monitor];
              return (
                <div key={monitor} className="flex items-start gap-3">
                  <Icono
                    className="mt-0.5 size-4 shrink-0"
                    strokeWidth={1.5}
                    style={{ color: "var(--muted-foreground)" }}
                  />
                  <span className="text-sm">
                    <span className="font-medium">{ETIQUETA_MONITOR[monitor]}</span>
                    <span className="block text-xs text-muted-foreground">
                      {DESCRIPCION_MONITOR[monitor]}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Las tres cifras de cada monitor</CardTitle>
        </CardHeader>
        <CardContent className="pt-0 text-sm text-muted-foreground">
          <p>
            Cada tarjeta de monitor del cuadro enseña tres cifras del último lote evaluado:{" "}
            <span className="font-medium text-foreground">Alertas</span> (severidad alta abiertas),{" "}
            <span className="font-medium text-foreground">Avisos</span> (severidad media abiertas) y{" "}
            <span className="font-medium text-foreground">Correctas</span> (comprobaciones dentro de
            umbral). La luz de la tarjeta de modelo enseña esa misma cifra cuando el monitor está en
            alerta o en aviso.
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
