/**
 * Pie del paso «Datos» del alta: Atrás, Crear sin plantilla y Continuar
 * (partido de `alta-datos.tsx` por el límite de 9 KB). En regresión, una
 * unidad o un rango no válidos bloquean también «Crear sin plantilla».
 */

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";

interface Props {
  onAtras: () => void;
  onOmitir: () => void;
  onContinuar: () => void;
  puedeOmitir: boolean;
  puedeContinuar: boolean;
}

export function PieAlta({ onAtras, onOmitir, onContinuar, puedeOmitir, puedeContinuar }: Props) {
  return (
    <DialogFooter className="sm:justify-between">
      <div className="flex gap-2">
        <Button type="button" variant="outline" onClick={onAtras}>
          Atrás
        </Button>
        <Button type="button" variant="ghost" disabled={!puedeOmitir} onClick={onOmitir}>
          Crear sin plantilla
        </Button>
      </div>
      <Button onClick={onContinuar} disabled={!puedeContinuar}>
        Continuar
      </Button>
    </DialogFooter>
  );
}
