/**
 * Diapositiva 9: qué entra, qué sale y dónde vive; debajo, quién opera Vigía.
 */

import { Figura, Tx, Rc, Tr, Ic } from "./primitivas";

const ETIQUETA =
  "Qué entra, qué sale y dónde vive. Entran predicciones, etiquetas reales, registro de uso y desenlaces; Vigía los guarda en una carpeta local; salen cuadro de mando, alertas, diario, API y agente de IA; lo opera la interfaz, la línea de comandos o un agente.";

export function D09({ className }: { className?: string }) {
  return (
    <Figura className={className} etiqueta={ETIQUETA}>
      <Tr d="M172 168H214" sw={2.5} m="v" />
      <Tr d="M370 168H398" sw={2.5} m="v" />
      <Tr d="M292 320V242" sw={2.5} m="v" />
      <Tx x={90} y={28} s={15} w={700} c="mu" a="middle">Entradas desidentificadas</Tx>
      <Tx x={498} y={28} w={700} c="mu" a="middle">Salidas</Tx>
      <Rc x={8} y={44} w={164} h={248} r={10} />
      <Ic n="db" x={20} y={68} z={22} sw={2} />
      <Tx x={50} y={85} s={15} w={500}>Predicciones</Tx>
      <Ic n="check" x={20} y={124} z={22} sw={2} />
      <Tx x={50} y={141} s={15} w={500}>Etiquetas reales</Tx>
      <Ic n="users" x={20} y={180} z={22} sw={2} />
      <Tx x={50} y={197} s={15} w={500}>Registro de uso</Tx>
      <Ic n="pulse" x={20} y={236} z={22} sw={2} />
      <Tx x={50} y={253} s={15} w={500}>Desenlaces</Tx>
      <Rc x={214} y={96} w={156} h={144} c="v" f="v" r={12} sw={2.5} />
      <Ic n="lock" x={280} y={106} c="v" sw={2} />
      <Tx x={292} y={160} s={22} w={700} c="v" a="middle">Vigía</Tx>
      <Tx x={292} y={184} s={15} w={500} c="mu" a="middle">carpeta local</Tx>
      <Tx x={292} y={206} s={14} w={500} c="mu" a="middle">nada sale del equipo</Tx>
      <Rc x={400} y={44} w={192} h={248} c="t" r={10} />
      <Ic n="chart" x={410} y={56} z={20} c="t" sw={2} />
      <Tx x={438} y={72} s={14} w={500}>Cuadro de mando</Tx>
      <Ic n="alert" x={410} y={102} z={20} c="t" sw={2} />
      <Tx x={438} y={118} s={14} w={500}>Alertas con protocolo</Tx>
      <Ic n="doc" x={410} y={148} z={20} c="t" sw={2} />
      <Tx x={438} y={164} s={14} w={500}>Diario exportable</Tx>
      <Ic n="plug" x={410} y={194} z={20} c="t" sw={2} />
      <Tx x={438} y={210} s={14} w={500}>API abierta</Tx>
      <Ic n="cpu" x={410} y={240} z={20} c="t" sw={2} />
      <Tx x={438} y={256} s={14} w={500}>Agente de IA (MCP)</Tx>
      <Tx x={150} y={312} s={15} w={700} c="mu">Quién la opera</Tx>
      <Rc x={150} y={320} w={300} h={84} c="mu" r={10} />
      <Ic n="box" x={166} y={330} z={18} c="mu" sw={2} />
      <Tx x={194} y={345} s={14} w={500}>interfaz</Tx>
      <Ic n="term" x={166} y={354} z={18} c="mu" sw={2} />
      <Tx x={194} y={369} s={14} w={500}>línea de comandos</Tx>
      <Ic n="cpu" x={166} y={378} z={18} c="mu" sw={2} />
      <Tx x={194} y={393} s={14} w={500}>agente de IA por MCP</Tx>
    </Figura>
  );
}

export default D09;
