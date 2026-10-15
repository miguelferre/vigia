/**
 * Campo «Fichero de ejemplo» del paso «Datos» del alta, con su error de
 * lectura (partido de `alta-datos.tsx` por el límite de 9 KB). El fichero no
 * se sube: solo se leen sus columnas en el navegador.
 */

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EnlaceFormato } from "./subida-enlace-formato";

export function FicheroEjemplo({ onFile, error }: { onFile: (file: File | null) => void; error: string | null }) {
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="alta-fichero">Fichero de ejemplo</Label>
        <Input id="alta-fichero" type="file" accept=".csv,.tsv,.txt" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
        <EnlaceFormato nuevaPestana className="w-fit text-xs" />
      </div>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </>
  );
}
