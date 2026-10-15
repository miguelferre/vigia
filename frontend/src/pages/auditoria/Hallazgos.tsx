/**
 * Hallazgos de una revisión en tarjetas: severidad
 * con `StateBadge`, directrices como chips, y la cabecera de
 * reproducibilidad del paquete.
 */

import { StateBadge } from "@/components/vigia";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { DossierFinding, DossierReviewDetalle } from "@/api/types";

const ESTADO_POR_SEVERIDAD: Record<DossierFinding["severity"], "alerta" | "aviso" | "ok"> = {
  high: "alerta",
  medium: "aviso",
  low: "ok",
};

const ETIQUETA_SEVERIDAD: Record<DossierFinding["severity"], string> = {
  high: "Alta",
  medium: "Media",
  low: "Baja",
};

export interface HallazgosProps {
  revision: DossierReviewDetalle;
}

export function Hallazgos({ revision }: HallazgosProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>Paquete: {revision.package_version}</span>
        <span>Corpus: {revision.corpus_hash.slice(0, 12)}</span>
        {revision.llm_backend ? <span>Modelo: {revision.llm_backend}{revision.model ? ` (${revision.model})` : ""}</span> : null}
      </div>

      {revision.status === "error" ? (
        <p className="text-sm text-destructive">La revisión terminó con error.</p>
      ) : null}

      {revision.findings.length === 0 ? (
        <p className="text-sm text-muted-foreground">Sin hallazgos.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {revision.findings.map((hallazgo) => (
            <Card key={hallazgo.id}>
              <CardHeader className="flex flex-row items-start justify-between gap-3">
                <CardTitle className="text-sm">{hallazgo.title}</CardTitle>
                <StateBadge estado={ESTADO_POR_SEVERIDAD[hallazgo.severity]} texto={ETIQUETA_SEVERIDAD[hallazgo.severity]} size="sm" />
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                <div className="flex flex-wrap gap-1.5">
                  {hallazgo.guideline_ids.map((id) => (
                    <Badge key={id} variant="outline">{id}</Badge>
                  ))}
                  {hallazgo.merged_count > 1 ? (
                    <Badge variant="secondary">{hallazgo.merged_count} directrices agrupadas</Badge>
                  ) : null}
                </div>
                <p><span className="font-semibold">Dónde: </span>{hallazgo.locus}</p>
                <p><span className="font-semibold">Evidencia: </span>{hallazgo.evidence}</p>
                <p><span className="font-semibold">Por qué: </span>{hallazgo.rationale}</p>
                <p><span className="font-semibold">Recomendación: </span>{hallazgo.recommendation}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
