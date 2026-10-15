/**
 * Diálogo de actor y motivo.
 *
 * Toda mutación que el backend registra con `ActorBody` pasa por aquí: el
 * actor viene prellenado de la sesión y se puede corregir, el motivo es
 * obligatorio y el rol sale de la sesión. Si el actor sigue siendo `anonimo`
 * hay que escribir un nombre antes de confirmar.
 */

import { useState } from "react";
import type { ReactNode } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ACTOR_ANONIMO, ETIQUETA_ROL, useSession } from "@/session/session";
import { mensajeDeError } from "@/api/client";
import type { ActorBody } from "@/api/types";

import { MOTIVO_MINIMO, ayudaMotivo } from "./motivo-textos";

export interface MotivoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  titulo: string;
  descripcion?: ReactNode;
  /** Texto del botón de confirmación. */
  etiquetaConfirmar?: string;
  /** Contenido adicional del formulario (campos propios del carril). */
  children?: ReactNode;
  /** Se llama con el cuerpo listo para la API. Puede ser asíncrono. */
  onConfirm: (cuerpo: ActorBody) => void | Promise<void>;
  /** Motivo sugerido al abrir. */
  motivoInicial?: string;
  /** Deshabilita el botón de confirmar (validación del carril). */
  deshabilitado?: boolean;
  /** Ejemplo de motivo para esta acción (`EJEMPLO_MOTIVO`), como ayuda bajo el campo. */
  ejemplo?: string;
}

export function MotivoDialog({
  open,
  onOpenChange,
  titulo,
  descripcion,
  etiquetaConfirmar = "Confirmar",
  children,
  onConfirm,
  motivoInicial = "",
  deshabilitado = false,
  ejemplo,
}: MotivoDialogProps) {
  const { actor, role, setActor } = useSession();
  const [nombre, setNombre] = useState(actor === ACTOR_ANONIMO ? "" : actor);
  const [motivo, setMotivo] = useState(motivoInicial);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Al abrirse, el formulario se rellena desde la sesion. Se ajusta en el
  // render (patron de React para estado derivado) en vez de en un efecto.
  const [abiertoAntes, setAbiertoAntes] = useState(open);
  if (open !== abiertoAntes) {
    setAbiertoAntes(open);
    if (open) {
      setNombre(actor === ACTOR_ANONIMO ? "" : actor);
      setMotivo(motivoInicial);
      setEnviando(false);
      setError(null);
    }
  }

  const nombreValido = nombre.trim().length > 0 && nombre.trim() !== ACTOR_ANONIMO;
  const motivoValido = motivo.trim().length >= MOTIVO_MINIMO;
  const puedeConfirmar = nombreValido && motivoValido && !deshabilitado && !enviando;

  const confirmar = async () => {
    if (!puedeConfirmar) return;
    setEnviando(true);
    setError(null);
    try {
      setActor(nombre.trim());
      await onConfirm({ actor: nombre.trim(), role, motivo: motivo.trim() });
      onOpenChange(false);
    } catch (err) {
      // No se cierra el dialogo: el motivo y el actor quedan para reintentar.
      setError(mensajeDeError(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>
            {descripcion ?? "Queda registrado en el diario de eventos con tu nombre y el motivo."}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="motivo-actor">Actor</Label>
            <Input
              id="motivo-actor"
              value={nombre}
              placeholder="Nombre de quien firma la acción"
              autoComplete="off"
              onChange={(e) => setNombre(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Rol de la sesión: {ETIQUETA_ROL[role]}. Escribe un nombre: «{ACTOR_ANONIMO}» no vale
              para firmar.
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="motivo-texto">Motivo</Label>
            <Textarea
              id="motivo-texto"
              value={motivo}
              rows={3}
              className="field-sizing-fixed h-20 resize-none overflow-y-auto"
              placeholder="Por qué se hace este cambio"
              aria-describedby="motivo-ayuda"
              onChange={(e) => setMotivo(e.target.value)}
            />
            <p id="motivo-ayuda" className="text-xs text-muted-foreground">
              {ayudaMotivo(ejemplo)}
            </p>
          </div>
          {children}
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={enviando}>
            Cancelar
          </Button>
          <Button onClick={() => void confirmar()} disabled={!puedeConfirmar}>
            {etiquetaConfirmar}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
