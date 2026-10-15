/**
 * Dialecto de CSV detectado en la subida: separador, decimal y
 * codificación de `Dataset.dialect` (`dialect_json`, migración 10). `null`
 * en JSON, XLSX o formatos sin dialecto que detectar: no pinta nada.
 */

import type { DatasetDialect } from "@/api/queries-alta";

const ETIQUETA_SEPARADOR: Record<string, string> = {
  ",": "coma",
  ";": "punto y coma",
  "\t": "tabulador",
};

const ETIQUETA_DECIMAL: Record<string, string> = {
  ",": "coma",
  ".": "punto",
};

const ETIQUETA_CODIFICACION: Record<string, string> = {
  "utf-8": "UTF-8",
  "utf-8-sig": "UTF-8 con BOM",
  cp1252: "Windows-1252 (cp1252)",
};

export function DialectoDetectado({ dialect }: { dialect: DatasetDialect | null | undefined }) {
  if (!dialect) return null;
  const separador = ETIQUETA_SEPARADOR[dialect.separator] ?? dialect.separator;
  const decimal = ETIQUETA_DECIMAL[dialect.decimal] ?? dialect.decimal;
  const codificacion = ETIQUETA_CODIFICACION[dialect.encoding] ?? dialect.encoding;
  return (
    <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
      Dialecto detectado: separador «{separador}», decimal «{decimal}», codificación {codificacion}.
    </p>
  );
}
