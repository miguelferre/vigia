/**
 * Auditoría (ruta `/auditoria`):
 * dossier del sistema y revisión contra las 32 directrices del paquete
 * (válidas para cualquier sector). Cuatro anclas: nuevo,
 * dossiers, revisión, informe. Rol `cliente`: `EmptyState` sin llamar a la
 * API (ninguna capacidad nueva).
 */

import { useState } from "react";
import { useLocation, useSearchParams } from "react-router";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorDeConsulta, InfoTooltip, PageHeader, SinProyecto } from "@/components/vigia";
import { useCan, useSession } from "@/session/session";
import { useTitulo } from "@/hooks/useTitulo";
import { useGlosario } from "@/api/queries-contenido";
import { useDossier, useDossierReview, useDossiers } from "@/api/queries-auditoria";
import { SeccionAlta } from "./SeccionAlta";
import { LanzarRevision } from "./LanzarRevision";
import { Hallazgos } from "./Hallazgos";
import { Crosswalk } from "./Crosswalk";
import { Informe } from "./Informe";

const ANCLAS = ["nuevo", "dossiers", "revision", "informe"] as const;

function useDesplazarHash(): string {
  const { hash } = useLocation();
  const [aplicado, setAplicado] = useState<string | null>(null);
  if (hash && hash !== aplicado) {
    setAplicado(hash);
    const id = hash.slice(1);
    if ((ANCLAS as readonly string[]).includes(id)) {
      window.setTimeout(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 0);
    }
  }
  return hash;
}

export default function AuditoriaIndex() {
  useTitulo("Auditoría");
  const { projectId, role } = useSession();
  const puedeLeer = useCan("registros");
  const puedeEscribir = useCan("config");
  const hash = useDesplazarHash();

  const [params, setParams] = useSearchParams();
  const dossierIdParam = params.get("dossier");
  const dossierId = dossierIdParam ? Number(dossierIdParam) : null;
  const [jobActivo, setJobActivo] = useState<number | null>(null);
  const [reviewId, setReviewId] = useState<number | null>(null);
  const seleccionarDossier = (id: number) => {
    const siguiente = new URLSearchParams(params);
    siguiente.set("dossier", String(id));
    setParams(siguiente, { replace: true });
    setJobActivo(null);
    setReviewId(null);
  };
  const dossierDetalle = useDossier(dossierId, { enabled: dossierId !== null && role !== "cliente" });
  const dossiersLista = useDossiers(projectId, { enabled: projectId !== null && role !== "cliente" });
  const glosario = useGlosario();

  // Al abrir un dossier (URL directa o recarga) sin revisión elegida, se
  // selecciona la última terminada para que hallazgos e informe salgan sin
  // un clic más; derivado en el render (patrón de `explicabilidad/index.tsx`).
  const [dossierVisto, setDossierVisto] = useState<number | null>(null);
  if (dossierDetalle.data && dossierId !== dossierVisto) {
    setDossierVisto(dossierId);
    if (reviewId === null) {
      const terminada = [...dossierDetalle.data.reviews].reverse().find((r) => r.status === "terminada");
      if (terminada && terminada.id !== null) setReviewId(terminada.id);
    }
  }

  if (role === "cliente") {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Auditoría" />
        <EmptyState
          titulo="No disponible para este rol"
          descripcion="La auditoría del sistema no está disponible para el rol cliente."
        />
      </div>
    );
  }

  if (projectId === null) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Auditoría" />
        <SinProyecto que="su auditoría" />
      </div>
    );
  }

  if (!puedeLeer) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Auditoría" />
        <EmptyState titulo="No disponible para este rol" descripcion="Este rol no tiene acceso a la auditoría." />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        titulo="Auditoría"
        descripcion={
          <span className="inline-flex items-center gap-1.5">
            Dossier del sistema y revisión contra las 32 directrices del paquete, válidas para cualquier
            sector.
            {glosario.data?.dossier ? (
              <InfoTooltip
                titulo={glosario.data.dossier.etiqueta}
                queMide={glosario.data.dossier.definicion}
              />
            ) : null}
          </span>
        }
      />

      {dossiersLista.isError ? (
        <ErrorDeConsulta
          que="los dossiers"
          error={dossiersLista.error}
          onReintentar={() => void dossiersLista.refetch()}
        />
      ) : null}

      {dossierDetalle.isError ? (
        <ErrorDeConsulta
          que="el dossier"
          error={dossierDetalle.error}
          onReintentar={() => void dossierDetalle.refetch()}
        />
      ) : null}

      <SeccionAlta
        projectId={projectId}
        puedeEscribir={puedeEscribir}
        dossierId={dossierId}
        dossierDetalle={dossierDetalle.data}
        dossierDetalleCargando={dossierDetalle.isLoading}
        hayDossiers={(dossiersLista.data?.total ?? 0) > 0}
        altaAbiertaPorHash={hash === "#nuevo"}
        tooltipDossier={glosario.data?.revision_dossier}
        onSeleccionarDossier={seleccionarDossier}
        reviewSeleccionada={reviewId}
        onSeleccionarRevision={setReviewId}
        onCreado={(dossier) => dossier.id !== null && seleccionarDossier(dossier.id)}
      />

      {dossierId !== null && dossierDetalle.data && puedeEscribir ? (
        <section id="revision" className="scroll-mt-20">
          <LanzarRevision
            dossierId={dossierId}
            jobActivo={jobActivo}
            dossier={dossierDetalle.data}
            onLanzada={setJobActivo}
            onTerminada={(id) => {
              setJobActivo(null);
              setReviewId(id);
            }}
          />
        </section>
      ) : null}

      {reviewId !== null ? (
        <section id="informe" className="scroll-mt-20 flex flex-col gap-6">
          <h2 className="text-md font-semibold">Crosswalk, hallazgos e informe</h2>
          <RevisionDetalle reviewId={reviewId} />
        </section>
      ) : null}
    </div>
  );
}

function RevisionDetalle({ reviewId }: { reviewId: number }) {
  const revision = useDossierReview(reviewId);
  const glosario = useGlosario();
  const crosswalkGlosario = glosario.data?.crosswalk;

  // Un fallo de la consulta no se queda en «Cargando» para siempre.
  if (revision.isError) {
    return <ErrorDeConsulta que="la revisión" error={revision.error} onReintentar={() => void revision.refetch()} />;
  }
  if (revision.isLoading || !revision.data) {
    return <p className="text-sm text-muted-foreground">Cargando la revisión…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Hallazgos</CardTitle>
        </CardHeader>
        <CardContent>
          <Hallazgos revision={revision.data} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5 text-sm">
            Crosswalk
            <InfoTooltip
              titulo={crosswalkGlosario?.etiqueta ?? "Crosswalk"}
              queMide={
                crosswalkGlosario?.definicion ??
                "Correspondencia entre los hallazgos de la revisión y las referencias regulatorias de cada marco."
              }
            />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Crosswalk crosswalk={revision.data.crosswalk} />
        </CardContent>
      </Card>
      {revision.data.status === "terminada" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Informe</CardTitle>
          </CardHeader>
          <CardContent>
            <Informe reviewId={reviewId} />
          </CardContent>
        </Card>
      ) : (
        <p className="text-sm text-muted-foreground">El informe estará disponible cuando la revisión termine.</p>
      )}
    </div>
  );
}
