/**
 * Campos del paso 1 de «Crear modelo» (partido de `nuevo-modelo-dialog.tsx`
 * para quedar por debajo de 9 KB): firmante, nombre, dominio, tipo de
 * modelo, etapa (sin valor preseleccionado) y privacidad.
 */

import { ETIQUETA_ROL } from "@/session/session";
import { capacidades, type TipoTarea } from "@/lib/tipo-tarea";
import type { Rol } from "@/api/types";
import { ETIQUETA_MODELO_SIMULADO, MODEL_KIND_SIMULADO } from "@/components/vigia/DemoGuiada/contrato";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfiguracionPrivacidadCampos } from "./configuracion-privacidad";
import { ETAPAS, TEXTO_ALTA, TIPOS_TAREA } from "./alta-textos";
import { ETIQUETA_DOMINIO } from "./etiquetas";
import { Ayuda } from "./mapeo-controles";

export const MODEL_KIND_EXTERNO = "external_files";
export const MODEL_KIND_EJECUTABLE = "executable";

export interface FormModelo {
  /** La primera pregunta del alta. */
  taskType: TipoTarea;
  nombreActor: string;
  name: string;
  domain: string;
  favorableLabel: string;
  storeFeatures: boolean;
  modelKind: string;
  /** Una de `ETAPAS` o vacío mientras no se haya elegido. */
  etapa: string;
}

interface Props {
  valores: FormModelo;
  onCambiar: (parcial: Partial<FormModelo>) => void;
  precargaDemo: boolean;
  actorValido: boolean;
  rol: Rol;
  /** Texto de la sesión que no vale como firma. */
  actorAnonimo: string;
}

export function CamposModelo({ valores: v, onCambiar, precargaDemo, actorValido, rol, actorAnonimo }: Props) {
  const caps = capacidades(v.taskType);
  // El simulador no tiene regresión; al cambiar a ese tipo se vuelve a ficheros externos.
  const elegirTipo = (taskType: TipoTarea) =>
    onCambiar(
      !capacidades(taskType).modeloSimulado && v.modelKind === MODEL_KIND_SIMULADO
        ? { taskType, modelKind: MODEL_KIND_EXTERNO }
        : { taskType },
    );
  return (
    <div className="flex flex-col gap-4">
      {precargaDemo ? (
        <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          Precargado para la demo: la etiqueta favorable 1 significa «derivar».
        </p>
      ) : null}
      {precargaDemo ? null : (
        <fieldset className="flex flex-col gap-2" data-testid="alta-tipo-tarea">
          <legend className="text-sm font-medium">Resultado que da el modelo</legend>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="radiogroup" aria-describedby="np-tipo-ayuda">
            {TIPOS_TAREA.map((t, i) => (
              <label
                key={t.valor}
                // Con tres tarjetas, la tercera ocupa las dos columnas.
                className={`flex cursor-pointer flex-col gap-0.5 rounded-md border p-3 text-sm ${
                  v.taskType === t.valor ? "border-primary bg-primary/5" : "border-border"
                } ${i === TIPOS_TAREA.length - 1 && i % 2 === 0 ? "sm:col-span-2" : ""}`}
              >
                <span className="flex items-center gap-2 font-medium">
                  <input
                    type="radio"
                    name="np-tipo-tarea"
                    value={t.valor}
                    checked={v.taskType === t.valor}
                    onChange={() => elegirTipo(t.valor)}
                  />
                  {t.etiqueta}
                </span>
                <span className="text-xs text-muted-foreground">{t.ayuda}</span>
              </label>
            ))}
          </div>
          <Ayuda id="np-tipo-ayuda">{TEXTO_ALTA.tipoTarea}</Ayuda>
        </fieldset>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="np-actor">Firmante del alta</Label>
        <Input
          id="np-actor"
          value={v.nombreActor}
          placeholder="Tu nombre"
          autoFocus={!actorValido}
          autoComplete="off"
          aria-describedby="np-actor-ayuda"
          onChange={(e) => onCambiar({ nombreActor: e.target.value })}
        />
        <Ayuda id="np-actor-ayuda">
          {`${TEXTO_ALTA.firmante} Rol de la sesión: ${ETIQUETA_ROL[rol]}. «${actorAnonimo}» no vale.`}
        </Ayuda>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="np-name">Nombre</Label>
        <Input id="np-name" value={v.name} onChange={(e) => onCambiar({ name: e.target.value })} autoFocus={actorValido} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="np-domain">Dominio</Label>
        <Select value={v.domain} onValueChange={(domain) => onCambiar({ domain })}>
          <SelectTrigger id="np-domain" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(ETIQUETA_DOMINIO).map(([clave, etiqueta]) => (
              <SelectItem key={clave} value={clave}>
                {etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className={precargaDemo ? "grid grid-cols-1 gap-4 sm:grid-cols-2" : "grid grid-cols-1 gap-4"}>
        {precargaDemo ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="np-fav">Valor favorable</Label>
            <Input
              id="np-fav"
              type="number"
              value={v.favorableLabel}
              onChange={(e) => onCambiar({ favorableLabel: e.target.value })}
            />
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="np-kind">Tipo de modelo</Label>
          <Select value={v.modelKind} onValueChange={(modelKind) => onCambiar({ modelKind })}>
            <SelectTrigger id="np-kind" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={MODEL_KIND_EXTERNO}>Ficheros externos</SelectItem>
              {caps.ofreceEjecutable ? <SelectItem value={MODEL_KIND_EJECUTABLE}>Ejecutable (ONNX)</SelectItem> : null}
              {caps.modeloSimulado || precargaDemo ? (
                <SelectItem value={MODEL_KIND_SIMULADO}>{ETIQUETA_MODELO_SIMULADO}</SelectItem>
              ) : null}
            </SelectContent>
          </Select>
        </div>
      </div>
      {v.modelKind === MODEL_KIND_SIMULADO ? (
        <p className="text-xs text-muted-foreground">
          El modelo simulado es el único con explicaciones y laboratorio en la demo; los demás despliegues se
          vigilan a partir de los ficheros que subas.
        </p>
      ) : v.modelKind === MODEL_KIND_EJECUTABLE ? (
        <p className="text-xs text-muted-foreground" data-testid="alta-modelo-ejecutable">
          Subirás el modelo ONNX después, en Versiones. Vigía lo ejecuta para predecir y explicar.
        </p>
      ) : (
        // El fichero del modelo no es un paso pendiente del alta.
        <p className="text-xs text-muted-foreground" data-testid="alta-modelo-opcional">
          El fichero del modelo (ONNX) es opcional, y se sube después en Versiones. Sin él solo se pierde la
          explicabilidad: la deriva, la equidad y la calidad se vigilan con los ficheros de predicciones que subas.
        </p>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="np-etapa">Etapa</Label>
        <Select value={v.etapa} onValueChange={(etapa) => onCambiar({ etapa })}>
          <SelectTrigger id="np-etapa" className="w-full" aria-describedby="np-etapa-ayuda">
            <SelectValue placeholder={TEXTO_ALTA.etapaPlaceholder} />
          </SelectTrigger>
          <SelectContent>
            {ETAPAS.map((e) => (
              <SelectItem key={e.valor} value={e.valor}>
                {e.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Ayuda id="np-etapa-ayuda">{TEXTO_ALTA.etapa}</Ayuda>
      </div>
      <ConfiguracionPrivacidadCampos
        storeFeatures={v.storeFeatures}
        setStoreFeatures={(storeFeatures) => onCambiar({ storeFeatures })}
      />
    </div>
  );
}
