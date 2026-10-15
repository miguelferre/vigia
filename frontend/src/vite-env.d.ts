/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Tema por build: `miguel` solo la estética personal; `todos` (por defecto) todas
   * las que haya; otro nombre, solo esa estética (tema único).
   */
  readonly VITE_TEMA?: string;
}
