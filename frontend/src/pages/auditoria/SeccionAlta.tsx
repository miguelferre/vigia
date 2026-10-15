/**
 * Alta de dossier (`Stepper`) y lista de dossiers (`ListaDossiers`) de
 * `/auditoria`: con dossiers ya
 * creados la lista va primero y el alta queda plegada en un `<details>`; con
 * cero dossiers, el alta abre como antes (sin plegar). Separado de
 * `index.tsx` solo para no pasar de 9 KB.
 */

import type { Dossier, DossierConReviews } from "@/api/types";
import { InfoTooltip } from "@/components/vigia";
import { Stepper } from "./Stepper";
import { ListaDossiers } from "./ListaDossiers";
import { ImportarDossier } from "./ImportarDossier";

export interface SeccionAltaProps {
  projectId: number;
  puedeEscribir: boolean;
  dossierId: number | null;
  dossierDetalle: DossierConReviews | undefined;
  dossierDetalleCargando: boolean;
  hayDossiers: boolean;
  altaAbiertaPorHash: boolean;
  tooltipDossier: { etiqueta: string; definicion: string } | undefined;
  onSeleccionarDossier: (id: number) => void;
  reviewSeleccionada: number | null;
  onSeleccionarRevision: (id: number) => void;
  onCreado: (dossier: Dossier) => void;
}

export function SeccionAlta({
  projectId,
  puedeEscribir,
  dossierId,
  dossierDetalle,
  dossierDetalleCargando,
  hayDossiers,
  altaAbiertaPorHash,
  tooltipDossier,
  onSeleccionarDossier,
  reviewSeleccionada,
  onSeleccionarRevision,
  onCreado,
}: SeccionAltaProps) {
  const alta = puedeEscribir ? (
    <section id="nuevo" className="scroll-mt-20 flex flex-col gap-6">
      <Stepper projectId={projectId} puedeCrear={puedeEscribir} onCreado={onCreado} />
      <ImportarDossier projectId={projectId} puedeCrear={puedeEscribir} onCreado={onCreado} />
    </section>
  ) : null;

  const lista = (
    <section id="dossiers" className="scroll-mt-20 flex flex-col gap-4">
      <h2 className="flex items-center gap-1.5 text-md font-semibold">
        Dossiers
        {tooltipDossier ? <InfoTooltip titulo={tooltipDossier.etiqueta} queMide={tooltipDossier.definicion} /> : null}
      </h2>
      <ListaDossiers
        projectId={projectId}
        dossierId={dossierId}
        detalle={dossierDetalle}
        detalleCargando={dossierDetalleCargando}
        onSeleccionarDossier={onSeleccionarDossier}
        reviewSeleccionada={reviewSeleccionada}
        onSeleccionarRevision={onSeleccionarRevision}
      />
    </section>
  );

  if (!hayDossiers) {
    return (
      <>
        {alta}
        {lista}
      </>
    );
  }

  return (
    <>
      {lista}
      {alta ? (
        <details className="flex flex-col gap-3" open={altaAbiertaPorHash}>
          <summary className="cursor-pointer text-md font-semibold select-none">Nuevo dossier</summary>
          <div className="mt-1">{alta}</div>
        </details>
      ) : null}
    </>
  );
}
