/**
 * Diapositiva 10 (cierre): camino de la demo en cinco estaciones y, debajo, el
 * botón «Ejecutar la demo» dibujado; el enlace real se monta encima (ver
 * `EnlaceDemo`).
 */

import { Link } from "react-router";

import { Figura, Tx, Rc, Ci, Tr, Ic } from "./primitivas";

const ETIQUETA =
  "Camino de la demo. Cinco estaciones numeradas llevan de registrar un modelo a seguir la pista hasta la causa y actuar; al final está Vigía y el botón para ejecutar la demo.";

export function D10({ className }: { className?: string }) {
  return (
    <div className="relative w-full">
      <Figura className={className} etiqueta={ETIQUETA}>
        <Tr d="M60 120H156C196 120 196 220 236 220H332C372 220 372 120 412 120H512" sw={3} dash="6 6" />
        <Ci x={60} y={120} r={32} />
        <Ic n="cpu" x={45} y={105} z={30} sw={2} />
        <Ci x={36} y={92} r={11} c="bg" solid />
        <Ci x={36} y={92} r={11} />
        <Tx x={36} y={97} s={14} w={700} a="middle">1</Tx>
        <Ci x={156} y={120} r={32} c="v" f="v" />
        <Ic n="db" x={141} y={105} z={30} c="v" sw={2} />
        <Ci x={132} y={92} r={11} c="bg" solid />
        <Ci x={132} y={92} r={11} c="v" />
        <Tx x={132} y={97} s={14} w={700} c="v" a="middle">2</Tx>
        <Ci x={236} y={220} r={32} c="t" f="t" />
        <Ic n="users" x={221} y={205} z={30} c="t" sw={2} />
        <Ci x={212} y={192} r={11} c="bg" solid />
        <Ci x={212} y={192} r={11} c="t" />
        <Tx x={212} y={197} s={14} w={700} c="t" a="middle">3</Tx>
        <Ci x={332} y={220} r={32} c="m" f="m" />
        <Ic n="alert" x={317} y={205} z={30} c="m" sw={2} />
        <Ci x={308} y={192} r={11} c="bg" solid />
        <Ci x={308} y={192} r={11} c="m" />
        <Tx x={308} y={197} s={14} w={700} c="m" a="middle">4</Tx>
        <Ci x={412} y={120} r={32} c="v" f="v" />
        <Ic n="search" x={397} y={105} z={30} c="v" sw={2} />
        <Ci x={388} y={92} r={11} c="bg" solid />
        <Ci x={388} y={92} r={11} c="v" />
        <Tx x={388} y={97} s={14} w={700} c="v" a="middle">5</Tx>
        <Ci x={530} y={120} r={36} c="v" solid />
        <Ci x={530} y={120} r={20} c="bg" solid />
        <Ci x={530} y={120} r={10} c="v" solid />
        <Rc x={180} y={316} w={240} h={52} c="v" f="v" r={12} sw={2.5} />
        <Tx x={300} y={349} s={20} w={700} c="v" a="middle">Ejecutar la demo</Tx>
      </Figura>
      <EnlaceDemo />
    </div>
  );
}

/** Enlace real sobre el botón dibujado (x 180 a 420, y 316 a 368 de 600 x 420). */
function EnlaceDemo() {
  return (
    <Link
      to="/demo?paso=0"
      aria-label="Ejecutar la demo"
      className="absolute rounded-xl outline-offset-2 hover:bg-[color-mix(in_srgb,var(--chart-1)_10%,transparent)] focus-visible:outline-2 focus-visible:outline-[var(--ring)]"
      style={{ left: "30%", top: "75.24%", width: "40%", height: "12.38%" }}
    />
  );
}

export default D10;
