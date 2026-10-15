/**
 * Formulario de «Crear modelo» de `/modelos` (partido de `index.tsx` para no
 * superar 9 KB; los campos del paso 1 viven en `nuevo-modelo-dialog-campos.tsx`).
 * Con `precargaDemo` (`?demo=crear`, contrato.ts) arranca con
 * `PRECARGA_CREAR_DEMO`: nombre, dominio reuma, tipo simulado y etiqueta
 * favorable 1 = «derivar» (paso 1 de la demo guiada); crea de un tirón, sin
 * el paso «Datos» de abajo (la demo no tiene fichero de ejemplo que leer) y
 * con la etapa en desarrollo.
 *
 * Alta real: un segundo paso «Datos» (`alta-datos.tsx`) entre el
 * formulario y la creación, que añade `mapping_template`/`acepta_feedback`
 * al cuerpo de `POST /api/projects`. La etapa de despliegue se elige en el
 * paso 1, sin valor preseleccionado.
 *
 * El nombre de quien da de alta se pide al empezar, antes del primer
 * evento del diario (`POST /api/projects` ya es un evento), no a mitad del
 * alta en el primer `MotivoDialog`.
 */

import { useState } from "react";

import { setActorHeaders } from "@/api/client";
import type { ProjectCreate } from "@/api/types";
import { ACTOR_ANONIMO, useSession } from "@/session/session";
import { Button } from "@/components/ui/button";
import { PRECARGA_CREAR_DEMO } from "@/components/vigia/DemoGuiada/contrato";
import {
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import PasoDatos, { type PasoDatosResultado } from "./alta-datos";
import { TEXTO_ALTA } from "./alta-textos";
import { CamposModelo, MODEL_KIND_EXTERNO, type FormModelo } from "./nuevo-modelo-dialog-campos";

export interface NuevoModeloDialogProps {
  onCrear: (cuerpo: ProjectCreate) => void | Promise<void>;
  /** `?demo=crear`: precarga el formulario con `PRECARGA_CREAR_DEMO`. */
  precargaDemo?: boolean;
  /** Nombres ya usados: la precarga de la demo elige uno libre (el backend da 409 si se repite). */
  nombresExistentes?: readonly string[];
}

/** «Derivación a Digestivo (demo)», «… (demo) 2», «… (demo) 3»: la segunda pasada de la demo no choca. */
function nombreLibre(base: string, existentes: readonly string[]): string {
  if (!existentes.includes(base)) return base;
  let n = 2;
  while (existentes.includes(`${base} ${n}`)) n += 1;
  return `${base} ${n}`;
}

export function NuevoModeloDialog({
  onCrear,
  precargaDemo = false,
  nombresExistentes = [],
}: NuevoModeloDialogProps) {
  const { actor, role, setActor } = useSession();
  const [form, setForm] = useState<FormModelo>({
    taskType: "binary",
    nombreActor: actor === ACTOR_ANONIMO ? "" : actor,
    name: precargaDemo ? nombreLibre(PRECARGA_CREAR_DEMO.name, nombresExistentes) : "",
    domain: precargaDemo ? PRECARGA_CREAR_DEMO.domain : "libre",
    favorableLabel: precargaDemo ? String(PRECARGA_CREAR_DEMO.favorable_label) : "1",
    storeFeatures: true,
    modelKind: precargaDemo ? PRECARGA_CREAR_DEMO.model_kind : MODEL_KIND_EXTERNO,
    // La demo crea en desarrollo; el alta real exige elegir.
    etapa: precargaDemo ? "desarrollo" : "",
  });
  const [enviando, setEnviando] = useState(false);
  const nombreActor = form.nombreActor.trim();
  const actorValido = nombreActor.length > 0 && nombreActor !== ACTOR_ANONIMO;
  // La demo crea de un tirón (sin paso «Datos»); el alta real pasa
  // por él antes de mandar `POST /api/projects`.
  const [paso, setPaso] = useState<"modelo" | "datos">("modelo");

  // La demo guiada sigue sin exigir nombre; el alta real, firmante y etapa.
  const puedeCrear =
    form.name.trim().length > 0 && !enviando && (precargaDemo || (actorValido && form.etapa !== ""));

  const crear = async (extra?: PasoDatosResultado) => {
    setEnviando(true);
    try {
      const cuerpo: ProjectCreate = {
        name: form.name.trim(),
        domain: form.domain.trim() || "libre",
        // El tipo es la primera pregunta del alta; la demo es binaria.
        task_type: precargaDemo ? "binary" : form.taskType,
        // La clase favorable se pide una sola vez. En el alta real es
        // la del paso «Datos» (en la plantilla); si es numérica, se copia
        // aquí, y si es texto o no hay plantilla, `Project.favorable_label`
        // se queda en 1 hasta que se congele la línea base, que lo
        // resincroniza con el mapeo (`proyecto.favorable_sincronizado`). El
        // campo de este formulario solo existe en la demo, que no tiene
        // paso «Datos».
        // Multiclase: el conjunto favorable vive en la plantilla (lista); aquí queda el 1 de compatibilidad.
        favorable_label:
          typeof extra?.mapping_template?.favorable_label === "number"
            ? extra.mapping_template.favorable_label
            : precargaDemo && form.favorableLabel.trim() !== ""
              ? Number(form.favorableLabel)
              : 1,
        store_features: form.storeFeatures,
        model_kind: (form.modelKind.trim() || MODEL_KIND_EXTERNO) as ProjectCreate["model_kind"],
        deployment_stage: form.etapa as ProjectCreate["deployment_stage"],
        acepta_feedback: extra?.acepta_feedback ?? true,
        mapping_template: extra?.mapping_template ?? null,
        // La unidad y el rango favorable van también fuera de la plantilla, para el alta sin plantilla.
        ...(extra?.regresion
          ? { target_unit: extra.regresion.target_unit, favorable_ranges: extra.regresion.favorable_ranges }
          : {}),
      };
      await onCrear(cuerpo);
    } finally {
      setEnviando(false);
    }
  };

  const confirmar = async () => {
    if (!puedeCrear) return;
    if (actorValido) {
      // Las cabeceras de actor se fijan ya: el `POST` siguiente puede salir
      // antes de que el efecto de la sesión las actualice.
      setActor(nombreActor);
      setActorHeaders({ actor: nombreActor, role });
    }
    if (precargaDemo) {
      await crear();
      return;
    }
    setPaso("datos");
  };

  if (paso === "datos") {
    return (
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Datos del modelo</DialogTitle>
          <DialogDescription>{TEXTO_ALTA.descripcionDatos}</DialogDescription>
        </DialogHeader>
        <PasoDatos
          tipo={form.taskType}
          onAtras={() => setPaso("modelo")}
          onOmitir={(regresion) => void crear(regresion ? { mapping_template: null, acepta_feedback: true, regresion } : undefined)}
          onContinuar={(r) => void crear(r)}
        />
      </DialogContent>
    );
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Crear modelo</DialogTitle>
        <DialogDescription>{TEXTO_ALTA.descripcionPaso1}</DialogDescription>
      </DialogHeader>
      <CamposModelo
        valores={form}
        onCambiar={(parcial) => setForm((f) => ({ ...f, ...parcial }))}
        precargaDemo={precargaDemo}
        actorValido={actorValido}
        rol={role}
        actorAnonimo={ACTOR_ANONIMO}
      />
      <DialogFooter>
        <Button onClick={() => void confirmar()} disabled={!puedeCrear}>
          {precargaDemo ? "Crear despliegue" : "Continuar"}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
