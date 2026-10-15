/**
 * Límite de error de React: evita que un fallo de render en una pantalla
 * (`<Outlet>` de `AppShell`) desmonte la aplicación entera (§6.2, §6.3).
 *
 * Solo las clases de componente pueden implementar `componentDidCatch` /
 * `getDerivedStateFromError`; no hay equivalente en componentes de función.
 */

import { AlertTriangleIcon, RefreshCwIcon } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";

export interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Sin console.log: se deja constancia en el atributo data- para depurar
    // en el DOM sin ensuciar la consola del navegador.
    this.setState({ error });
    void info;
  }

  private reintentar = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-destructive px-6 py-12 text-center"
        data-error-boundary="true"
      >
        <AlertTriangleIcon className="size-8 text-destructive" aria-hidden="true" />
        <p className="font-semibold">Esta pantalla ha fallado</p>
        <p className="max-w-prose text-sm text-muted-foreground">
          Vuelve a intentarlo. Si se repite, abre otra pantalla y vuelve a esta; el detalle técnico
          está plegado aquí debajo por si hace falta contarlo.
        </p>
        <details className="max-w-prose text-left text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none text-center">Detalle técnico</summary>
          <pre className="mt-2 max-h-40 overflow-auto rounded-md border border-border bg-muted/40 p-2 font-mono whitespace-pre-wrap">
            {error.message}
          </pre>
        </details>
        <Button variant="outline" onClick={this.reintentar}>
          <RefreshCwIcon className="size-4" aria-hidden="true" />
          Reintentar
        </Button>
      </div>
    );
  }
}
