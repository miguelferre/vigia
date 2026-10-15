/** Vista previa del protocolo de respuesta de un monitor (partida de `configuracion-campos.tsx` por tamaño). */

/** Vista previa mínima de markdown: párrafos y listas con "- ", sin librería. */
export function VistaPreviaProtocolo({ texto }: { texto: string }) {
  if (!texto.trim()) return <p className="text-sm text-muted-foreground">—</p>;
  const bloques = texto.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="flex flex-col gap-2 text-sm">
      {bloques.map((bloque, idx) => {
        const lineas = bloque.split("\n").map((l) => l.trim()).filter(Boolean);
        const esLista = lineas.every((l) => l.startsWith("- ") || l.startsWith("* "));
        if (esLista) {
          return (
            <ul key={idx} className="list-disc pl-5">
              {lineas.map((l, i) => (
                <li key={i}>{l.replace(/^[-*]\s+/, "")}</li>
              ))}
            </ul>
          );
        }
        return <p key={idx}>{lineas.join(" ")}</p>;
      })}
    </div>
  );
}
