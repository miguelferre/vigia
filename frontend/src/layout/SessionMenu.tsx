/** Menú de sesión: nombre de actor editable y rol de trabajo. */

import { useState } from "react";
import { UserRoundIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ACTOR_ANONIMO, ETIQUETA_ROL, ROLES, useSession } from "@/session/session";
import type { Rol } from "@/api/types";

export function SessionMenu() {
  const { actor, role, setActor, setRole, esAnonimo } = useSession();
  const [borrador, setBorrador] = useState(actor);
  const [actorAntes, setActorAntes] = useState(actor);
  if (actor !== actorAntes) {
    setActorAntes(actor);
    setBorrador(actor);
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2" aria-label="Sesión">
          <UserRoundIcon className="size-4" aria-hidden="true" />
          <span className="max-w-32 truncate">{actor}</span>
          <span className="text-muted-foreground">· {ETIQUETA_ROL[role]}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sesion-actor">Actor</Label>
            <Input
              id="sesion-actor"
              value={borrador}
              autoComplete="off"
              onChange={(e) => setBorrador(e.target.value)}
              onBlur={() => setActor(borrador)}
              onKeyDown={(e) => {
                if (e.key === "Enter") setActor(borrador);
              }}
            />
            <p className="text-xs text-muted-foreground">
              {esAnonimo
                ? `Con «${ACTOR_ANONIMO}» no se pueden firmar cambios: escribe un nombre.`
                : "Es el nombre que queda en el diario de eventos."}
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sesion-rol">Rol</Label>
            <Select value={role} onValueChange={(v) => setRole(v as Rol)}>
              <SelectTrigger id="sesion-rol" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {ETIQUETA_ROL[r]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              El rol cliente oculta registros crudos, mapeos y configuración.
            </p>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
