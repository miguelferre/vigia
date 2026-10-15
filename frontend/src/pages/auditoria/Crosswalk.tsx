/**
 * Crosswalk de una revisión: tabla marco → referencia → directrices.
 */

import { EmptyState } from "@/components/vigia";
import type { DossierReviewDetalle } from "@/api/types";

export interface CrosswalkProps {
  crosswalk: DossierReviewDetalle["crosswalk"];
}

export function Crosswalk({ crosswalk }: CrosswalkProps) {
  const marcos = Object.entries(crosswalk);
  if (marcos.length === 0) {
    return <EmptyState titulo="Sin crosswalk" descripcion="Esta revisión no pidió crosswalk o no encontró referencias." />;
  }
  return (
    <div className="flex flex-col gap-4">
      {marcos.map(([marco, referencias]) => (
        <div key={marco} className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{marco}</h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Referencia</th>
                  <th className="px-3 py-2 font-medium">Directrices</th>
                </tr>
              </thead>
              <tbody>
                {referencias.map((r) => (
                  <tr key={r.ref} className="border-t border-border">
                    <td className="px-3 py-2 align-top font-medium">{r.ref}</td>
                    <td className="px-3 py-2 align-top">{r.guidelines.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
