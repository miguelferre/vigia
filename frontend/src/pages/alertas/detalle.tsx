/**
 * Detalle de una alerta (`GET /alerts/{id}`, ruta `/alertas/:id`).
 *
 * Cabecera con enlaces al lote, al monitor y a la correlación en el diario;
 * el botón principal es siempre el siguiente hito del protocolo
 * (triaje, investigación o decisión, `protocolo.hitoActual` de
 * `useProtocoloHitos`), con "Cerrar con motivo" aparte, disponible en
 * cualquier etapa no cerrada; debajo, acciones, historial y protocolo en sus
 * propios ficheros. La descripción y las acciones de la cabecera viven en
 * `CabeceraAlertaDetalle.tsx`, los enlaces en `EnlacesAlertaDetalle.tsx`, los
 * datos en `useDatosAlertaDetalle.ts` y los cuatro diálogos en
 * `DialogosAlertaDetalle.tsx`, aparte para no pasar de 9 KB aquí.
 */

import { useState } from "react";
import { useLocation, useParams } from "react-router";
import { InfoIcon } from "lucide-react";

import { Alert as AlertBanner, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { BotonVolver, EmptyState, PageHeader } from "@/components/vigia";
import { useTitulo } from "@/hooks/useTitulo";
import { MONITOR_A_RUTA } from "@/lib/metrics";
import { Acciones } from "./acciones";
import { Historial } from "./historial";
import { Protocolo } from "./protocolo";
import { ProtocoloHitos } from "./ProtocoloHitos";
import { useDatosAlertaDetalle } from "./useDatosAlertaDetalle";
import { useProtocoloHitos } from "./useProtocoloHitos";
import { AccionesAlertaDetalle, DescripcionAlertaDetalle } from "./CabeceraAlertaDetalle";
import { DialogosAlertaDetalle, type DialogoAlertaDetalle } from "./DialogosAlertaDetalle";
import { EnlacesAlertaDetalle } from "./EnlacesAlertaDetalle";
import { QueSignificaCalculo } from "./QueSignificaCalculo";

export default function AlertaDetalle() {
  const { id } = useParams<{ id: string }>();
  const alertId = Number(id);
  // Qué diálogo del hito actual (o "cerrar", siempre disponible) está
  // abierto; los tres viven en `HitoDialogos.tsx`/`DialogoDecidir.tsx`, con
  // su propia mutación cada uno.
  const [dialogo, setDialogo] = useState<DialogoAlertaDetalle>(null);
  const location = useLocation();
  // El `<details>` del protocolo llega colapsado por defecto: con el ancla
  // `#protocolo` (paso 23 de la demo guiada, «De la alerta a la acción») se
  // abre solo, para que `programarScrollAAncla` encuentre algo visible a lo
  // que hacer scroll.
  // Ajuste en el render (no en un efecto), mismo patrón que la pestaña por
  // hash de modelos/detalle.tsx: sin `open` propio una vez que el humano lo
  // ha tocado a mano, para no reabrirlo si lo cierra.
  const [protocoloAbierto, setProtocoloAbierto] = useState(() => location.hash === "#protocolo");
  const [hashProtocoloAplicado, setHashProtocoloAplicado] = useState(location.hash === "#protocolo");
  if (location.hash === "#protocolo" && !hashProtocoloAplicado) {
    setHashProtocoloAplicado(true);
    setProtocoloAbierto(true);
  }

  const { alerta, evaluacion, lote, correlationId, cerrar } = useDatosAlertaDetalle(alertId);

  const protocolo = useProtocoloHitos(Number.isFinite(alertId) ? alertId : null);

  useTitulo(alerta.data ? `Alerta #${alerta.data.id}` : "Alerta");

  if (!Number.isFinite(alertId)) {
    return <EmptyState titulo="Alerta no válida" descripcion="El identificador de la ruta no es un número." />;
  }
  if (alerta.isLoading) {
    return <div data-loading="true" className="text-sm text-muted-foreground">Cargando alerta…</div>;
  }
  if (!alerta.data) {
    return <EmptyState titulo="Alerta no encontrada" descripcion={`No existe la alerta ${alertId}.`} />;
  }

  const a = alerta.data;
  const rutaMonitor = MONITOR_A_RUTA[a.monitor_type];
  // La medida de esta alerta en la última evaluación: en `sin_datos` trae un
  // motivo en lenguaje llano (cruzadas CX-1/5/6 sobre todo), que aquí se
  // enseña en vez de dejar la pantalla sin explicación.
  const medida = evaluacion.data?.measurements.find(
    (m) => m.metric_key === a.metric_key && m.group_code === a.group_code,
  );

  return (
    <div className="flex flex-col gap-6">
      <BotonVolver rutaPadre="/alertas" etiquetaPadre="Alertas" className="w-fit" />
      <PageHeader
        titulo={a.title}
        migas={[{ etiqueta: "Alertas", a: "/alertas" }, { etiqueta: `#${a.id}` }]}
        descripcion={<DescripcionAlertaDetalle alerta={a} lote={lote.data} protocolo={protocolo} />}
        acciones={
          <AccionesAlertaDetalle
            alerta={a}
            hitoActual={protocolo.hitoActual}
            onAbrirDialogoHito={setDialogo}
            onCerrarConMotivo={() => setDialogo("cerrar")}
          />
        }
      />

      <QueSignificaCalculo
        metricKey={a.metric_key}
        evaluacion={evaluacion.data}
        evaluacionCargando={evaluacion.isLoading}
        projectId={a.project_id}
      />

      <EnlacesAlertaDetalle alerta={a} rutaMonitor={rutaMonitor} correlationId={correlationId} />

      {medida?.state === "sin_datos" && medida.motivo ? (
        <AlertBanner>
          <InfoIcon />
          <AlertTitle>Sin datos suficientes</AlertTitle>
          <AlertDescription>{medida.motivo}</AlertDescription>
        </AlertBanner>
      ) : null}

      {a.status !== "retirada" ? <Acciones alertId={a.id ?? alertId} acciones={a.actions} /> : null}

      <details
        id="protocolo"
        className="scroll-mt-20 flex flex-col gap-3"
        open={protocoloAbierto}
        onToggle={(e) => setProtocoloAbierto(e.currentTarget.open)}
      >
        {/* Sin «solo lectura» aquí, que hablaba de toda la sección
            (hitos incluidos, con botones operables al lado en la cabecera);
            lo que es texto fijo se lee en su propio bloque, `Protocolo`. */}
        <summary className="cursor-pointer text-md font-semibold select-none">Protocolo</summary>
        <div className="mt-1 flex flex-col gap-3">
          <ProtocoloHitos pasos={protocolo.pasos} cargando={protocolo.cargando} rutaMonitor={rutaMonitor} />
          <Protocolo protocoloMd={a.protocolo_md} rutaMonitor={rutaMonitor} />
        </div>
      </details>

      <section className="flex flex-col gap-3">
        <h2 className="text-md font-semibold">Historial</h2>
        <Historial entradas={a.history} alerta={a} />
      </section>

      <DialogosAlertaDetalle
        alertId={a.id ?? alertId}
        dialogo={dialogo}
        onDialogoChange={setDialogo}
        onConfirmCerrar={async (cuerpo) => {
          await cerrar.mutateAsync(cuerpo);
        }}
      />
    </div>
  );
}
