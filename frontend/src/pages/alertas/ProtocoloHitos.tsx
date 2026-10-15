/**
 * Protocolo por hitos de una alerta, vista completa (artboard
 * `Protocolo`): conector vertical, círculo por estado, tarjeta
 * con tres columnas por paso (paso y descripción; entregables; responsable,
 * plazo y quién lo hizo) y navegación «Anterior / Siguiente paso» que
 * desplaza y enfoca la tarjeta correspondiente.
 *
 * El artboard dibuja un botón «Ver detalle» por paso: no hay destino real
 * (no hay una pantalla por hito), así que aquí se omite en vez de enlazar
 * a algo que no existe.
 *
 * `ProtocoloHitosCompacto` (mismos datos, cinco filas) vive en
 * `ProtocoloHitosCompacto.tsx`, y la fila de esta vista en `FilaProtocolo.tsx`,
 * para no pasar de 9 KB en este fichero.
 */

import { useRef, useState } from "react";
import { CheckIcon, Eye, FileText, Flag, Info, Scale, Search } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { FilaProtocolo } from "./FilaProtocolo";
import type { PasoProtocolo, ProtocoloHitoEstandar, ProtocoloHitoStatus } from "./useProtocoloHitos";

// Los cinco estándar; un hito extra (`status: "informativo"`) no tiene
// icono propio y usa `Info` (ver `iconoHito`).
export const ICONO_HITO: Record<ProtocoloHitoEstandar, typeof Flag> = {
  deteccion: Flag,
  triaje: Search,
  investigacion: FileText,
  decision: Scale,
  seguimiento: Eye,
};

export const ETIQUETA_HITO_STATUS: Record<ProtocoloHitoStatus, string> = {
  done: "Completado",
  current: "En curso",
  pending: "Pendiente",
  informativo: "Informativo",
};

/** Icono del paso: el de su hito estándar, o `Info` para un hito extra. */
export function iconoHito(key: string): typeof Flag {
  return (ICONO_HITO as Record<string, typeof Flag>)[key] ?? Info;
}

/** Color del paso listo para `style` (círculo, aro de entregable). */
function colorHito(status: ProtocoloHitoStatus): string {
  return `var(${status === "done" ? "--state-ok" : status === "current" ? "--state-unstable" : "--border"})`;
}

/** Círculo de la línea de tiempo o del entregable. Un hito informativo
 * no tiene progreso que marcar: aro discontinuo, sin relleno. */
export function MarcaHito({ status, size = 20 }: { status: ProtocoloHitoStatus; size?: number }) {
  const color = colorHito(status);
  if (status === "informativo") {
    return (
      <span
        className="rounded-full border-[1.5px] border-dashed"
        style={{ width: size, height: size, borderColor: color }}
        aria-hidden="true"
      />
    );
  }
  if (status === "pending") {
    return (
      <span
        className="rounded-full border-[1.5px]"
        style={{ width: size, height: size, borderColor: color }}
        aria-hidden="true"
      />
    );
  }
  if (status === "current") {
    return (
      <span
        className="flex items-center justify-center rounded-full border-2 bg-card"
        style={{ width: size, height: size, borderColor: color }}
        aria-hidden="true"
      >
        <span className="rounded-full" style={{ width: size * 0.4, height: size * 0.4, background: color }} />
      </span>
    );
  }
  return (
    <span
      className="flex items-center justify-center rounded-full"
      style={{ width: size, height: size, background: color }}
      aria-hidden="true"
    >
      <CheckIcon className="text-white" style={{ width: size * 0.55, height: size * 0.55 }} strokeWidth={2.4} />
    </span>
  );
}

export interface ProtocoloHitosProps {
  pasos: PasoProtocolo[];
  cargando: boolean;
  /** Segmento de `/monitores/:tipo` del monitor que define este protocolo: sin enlace si no se conoce. */
  rutaMonitor?: string;
}

export function ProtocoloHitos({ pasos, cargando, rutaMonitor }: ProtocoloHitosProps) {
  const [activo, setActivo] = useState(() => {
    const actual = pasos.findIndex((p) => p.status === "current");
    return actual >= 0 ? actual : 0;
  });
  const refs = useRef<Array<HTMLDivElement | null>>([]);

  const irA = (indice: number) => {
    const clamped = Math.max(0, Math.min(pasos.length - 1, indice));
    setActivo(clamped);
    const nodo = refs.current[clamped];
    nodo?.scrollIntoView({ behavior: "smooth", block: "center" });
    nodo?.focus();
  };

  if (cargando) {
    return <p className="text-sm text-tertiary">Cargando protocolo…</p>;
  }
  if (pasos.length === 0) {
    return <p className="text-sm text-tertiary">Sin pasos de protocolo definidos.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative grid grid-cols-[32px_minmax(0,1fr)] gap-x-3 gap-y-2.5">
        <div className="absolute top-2.5 bottom-2.5 left-[15px] w-px bg-border" aria-hidden="true" />
        {pasos.map((paso, i) => (
          <FilaProtocolo
            key={paso.key}
            paso={paso}
            activo={activo === i}
            cardRef={(nodo) => {
              refs.current[i] = nodo;
            }}
          />
        ))}
      </div>

      <div className="flex items-center justify-between">
        <Button type="button" variant="outline" onClick={() => irA(activo - 1)} disabled={activo <= 0}>
          Anterior
        </Button>
        <Button type="button" onClick={() => irA(activo + 1)} disabled={activo >= pasos.length - 1}>
          Siguiente paso
        </Button>
      </div>

      {/* El protocolo ya se edita por monitor, en su hoja de configuración. */}
      <p className="text-xs text-tertiary">
        Protocolo de este monitor; se edita en su configuración, con motivo.{" "}
        {rutaMonitor ? (
          <Link to={`/monitores/${rutaMonitor}#configurar`} className="text-link hover:underline">
            Editar protocolo
          </Link>
        ) : (
          <Link to="/ayuda?q=protocolo" className="text-link hover:underline">
            Qué es el protocolo
          </Link>
        )}
      </p>
    </div>
  );
}

export default ProtocoloHitos;
