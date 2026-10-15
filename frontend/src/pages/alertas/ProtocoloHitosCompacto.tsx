/**
 * Protocolo por hitos, vista compacta para el panel lateral:
 * cinco filas con círculo de estado y título, «n de 5» en cabecera. Mismos
 * datos que `ProtocoloHitos.tsx` (vista completa de `/alertas/:id`), sin la
 * tarjeta de tres columnas.
 */

import { MarcaHito } from "./ProtocoloHitos";
import type { PasoProtocolo } from "./useProtocoloHitos";

export interface ProtocoloHitosCompactoProps {
  pasos: PasoProtocolo[];
  cargando: boolean;
}

export function ProtocoloHitosCompacto({ pasos, cargando }: ProtocoloHitosCompactoProps) {
  if (cargando) {
    return <p className="text-sm text-tertiary">Cargando protocolo…</p>;
  }
  if (pasos.length === 0) {
    return <p className="text-sm text-tertiary">Sin pasos de protocolo definidos.</p>;
  }
  const hechos = pasos.filter((p) => p.status === "done").length;
  // El denominador es solo los hitos estándar, nunca "n de 6" con un
  // hito extra intercalado (`useProtocoloHitos.total`).
  const total = pasos.filter((p) => p.status !== "informativo").length;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold tracking-[.06em] text-tertiary uppercase">Protocolo</span>
        <span className="text-md text-tertiary">
          {hechos} de {total}
        </span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {pasos.map((paso) => (
          <li key={paso.key} className="flex items-center gap-2 text-md">
            <MarcaHito status={paso.status} size={14} />
            <span className={paso.status === "pending" || paso.status === "informativo" ? "text-tertiary" : undefined}>
              {paso.titulo}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default ProtocoloHitosCompacto;
