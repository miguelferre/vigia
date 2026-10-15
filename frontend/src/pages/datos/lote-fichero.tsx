/**
 * El nombre del fichero de un lote junto a su número
 * («Lote #7 · lote-06.SINTETICO.csv»). El número cuenta desde 1 y el nombre
 * del fichero desde donde lo numerara quien lo subió, así que se ven juntos.
 * Recortado con puntos suspensivos; el nombre entero va en `title`.
 */

export function FicheroLote({ nombre, className = "" }: { nombre: string | null | undefined; className?: string }) {
  const limpio = nombre?.trim() ?? "";
  if (limpio === "") return null;
  return (
    <span className={`block min-w-0 max-w-[16rem] truncate ${className}`.trim()} title={limpio} data-testid="fichero-lote">
      {limpio}
    </span>
  );
}
