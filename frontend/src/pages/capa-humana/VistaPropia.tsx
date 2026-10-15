/**
 * Bloque «Vista propia» (`#vista-propia`): solo con
 * `role === "clinico"` pide datos; con otro rol enseña una línea y deja el
 * ancla montada. Pseudónimo elegido, nunca escrito a mano.
 */

import type { ReactNode } from "react";
import { Area, CartesianGrid, ComposedChart, Line, Tooltip as RTooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChartContainer } from "@/components/ui/chart";
import { InfoTooltip } from "@/components/vigia";
import { useGlosario } from "@/api/queries-contenido";
import { useOverridesClinicians, useOverridesMe } from "@/api/queries-humana";
import { useSession } from "@/session/session";
import { formatoFecha } from "@/lib/metrics";

export function VistaPropia({ projectId }: { projectId: number }) {
  const { role, clinicianPseudonym, setClinicianPseudonym } = useSession();
  const glosario = useGlosario();
  const entrada = glosario.data?.override;

  const cabecera = (
    <div className="flex items-center gap-2">
      <CardTitle>Vista propia</CardTitle>
      {entrada ? <InfoTooltip titulo="Vista propia" queMide="Tus decisiones frente a la media y el rango del equipo." /> : null}
    </div>
  );

  if (role !== "clinico") {
    return (
      <Card id="vista-propia" className="scroll-mt-20">
        <CardHeader>{cabecera}</CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">La vista propia se abre con el rol Profesional.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <VistaPropiaProfesional
      projectId={projectId}
      cabecera={cabecera}
      pseudonimo={clinicianPseudonym}
      setPseudonimo={setClinicianPseudonym}
    />
  );
}

function VistaPropiaProfesional({
  projectId,
  cabecera,
  pseudonimo,
  setPseudonimo,
}: {
  projectId: number;
  cabecera: ReactNode;
  pseudonimo: string | null;
  setPseudonimo: (p: string | null) => void;
}) {
  const clinicos = useOverridesClinicians(projectId, undefined);
  const me = useOverridesMe(projectId, pseudonimo, undefined);

  const serie = (me.data?.windows ?? []).map((w) => ({
    periodo: formatoFecha(w.start),
    mia: w.mine.override_rate,
    media: w.service.override_rate,
    p25: w.service.p25,
    p75: w.service.p75,
  }));

  return (
    <Card id="vista-propia" className="scroll-mt-20">
      <CardHeader>
        {cabecera}
        <div className="flex items-center gap-2 pt-1">
          <span className="text-sm text-muted-foreground">Pseudónimo del profesional</span>
          <Select value={pseudonimo ?? ""} onValueChange={(v) => setPseudonimo(v || null)}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Elegir" />
            </SelectTrigger>
            <SelectContent>
              {(clinicos.data?.clinicians ?? []).map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {!pseudonimo ? (
          <p className="text-sm text-muted-foreground">Elige tu pseudónimo para ver tus curvas frente al equipo.</p>
        ) : serie.length > 0 ? (
          <ChartContainer config={{ mia: { label: "Propia", color: "var(--chart-1)" }, media: { label: "Media", color: "var(--chart-2)" } }} className="h-64">
            <ComposedChart data={serie}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="periodo" fontSize={11} />
              <YAxis fontSize={11} />
              <RTooltip />
              <Area dataKey="p75" stroke="none" fill="var(--chart-3)" fillOpacity={0.15} />
              <Area dataKey="p25" stroke="none" fill="var(--card)" fillOpacity={1} />
              <Line type="monotone" dataKey="media" name="Media del equipo" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="mia" name="Propia" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ChartContainer>
        ) : (
          <p className="text-sm text-muted-foreground">Sin datos para este pseudónimo.</p>
        )}
      </CardContent>
    </Card>
  );
}
