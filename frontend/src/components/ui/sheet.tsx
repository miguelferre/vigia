"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { XIcon } from "lucide-react"
import { Dialog as SheetPrimitive } from "radix-ui"

function Sheet({ ...props }: React.ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />
}

function SheetTrigger({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Trigger>) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />
}

function SheetClose({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Close>) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />
}

function SheetPortal({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Portal>) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />
}

function SheetOverlay({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay
      data-slot="sheet-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className
      )}
      {...props}
    />
  )
}

function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  onOpenAutoFocus,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & {
  side?: "top" | "right" | "bottom" | "left"
  showCloseButton?: boolean
}) {
  const contentRef = React.useRef<HTMLDivElement>(null)

  // sin esto Radix enfoca el primer elemento enfocable del sheet (p.ej.
  // un TooltipTrigger de la primera fila). Antes evitaba que ese foco abriera
  // un tooltip con `delayDuration={0}` (el retardo por
  // defecto pasa a 300 ms, así que un foco de apertura ya no lo dispara);
  // se mantiene porque sigue siendo el foco correcto de accesibilidad al
  // abrir el panel, el título y no un control interno cualquiera. Foco al
  // título si lo hay; si no, al propio contenido (con `tabIndex=-1` más
  // abajo). Un `onOpenAutoFocus` explícito del que llama tiene prioridad.
  const enfocarAlAbrir =
    onOpenAutoFocus ??
    ((event: Event) => {
      event.preventDefault()
      const contenedor = contentRef.current
      if (!contenedor) return
      const titulo = contenedor.querySelector<HTMLElement>('[data-slot="sheet-title"]')
      ;(titulo ?? contenedor).focus()
    })

  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Content
        ref={contentRef}
        data-slot="sheet-content"
        tabIndex={-1}
        onOpenAutoFocus={enfocarAlAbrir}
        className={cn(
          // abre 300 ms con la curva de cajón de Radix
          // Vaul (cubic-bezier 0.32/0.72/0/1); cierra 200 ms ease-out.
          "fixed z-50 flex flex-col gap-4 bg-background shadow-lg transition data-[state=closed]:animate-out data-[state=closed]:duration-200 data-[state=closed]:ease-out data-[state=open]:animate-in data-[state=open]:duration-300 data-[state=open]:ease-[cubic-bezier(0.32,0.72,0,1)]",
          side === "right" &&
            "inset-y-0 right-0 h-full w-3/4 border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-sm",
          side === "left" &&
            "inset-y-0 left-0 h-full w-3/4 border-r data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left sm:max-w-sm",
          side === "top" &&
            "inset-x-0 top-0 h-auto border-b data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top",
          side === "bottom" &&
            "inset-x-0 bottom-0 h-auto border-t data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
          className
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close className="absolute top-4 right-4 rounded-xs opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none data-[state=open]:bg-secondary">
            <XIcon className="size-4" />
            <span className="sr-only">Close</span>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </SheetPortal>
  )
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-1.5 p-4", className)}
      {...props}
    />
  )
}

function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn("mt-auto flex flex-col gap-2 p-4", className)}
      {...props}
    />
  )
}

function SheetTitle({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      // Foco por defecto al abrir el sheet (ver SheetContent): sin
      // `tabIndex` un `<h2>` no es enfocable.
      tabIndex={-1}
      className={cn("font-semibold text-foreground outline-none", className)}
      {...props}
    />
  )
}

function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
}
