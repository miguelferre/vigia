/**
 * Paso «Datos» del alta: el usuario elige un fichero de
 * ejemplo, se leen sus columnas en el navegador (`alta-sniff.ts`, sin subirlo)
 * y se reparte el papel de cada una con selectores: identificador, etiqueta
 * con su valor favorable (la única vez que se pide la clase favorable),
 * predicción, probabilidad, fecha, variables y, opcional, atributo protegido.
 * Una vista previa de cinco filas enseña el papel de cada columna. Se manda
 * como `mapping_template` en `POST /api/projects` (`nuevo-modelo-dialog.tsx`).
 */

import { useState } from "react";

import type { MappingTemplate } from "@/api/queries-alta";
import { capacidades, type TipoTarea } from "@/lib/tipo-tarea";
import { AvisoSinProbabilidad } from "./aviso-sin-probabilidad";
import { FicheroEjemplo } from "./alta-datos-fichero";
import { PieAlta } from "./alta-datos-pie";
import { CamposIdentidad, type ColumnasAlta } from "./alta-datos-campos";
import { useMulticlaseAlta } from "./alta-datos-multiclase";
import { useRegresionAlta, type RegresionAlta } from "./alta-regresion";
import { favorableValido as validoPorTipo, sinProbabilidad } from "./alta-tipo";
import { construirPlantilla, PROTEGIDO_VACIO, type ProtegidoAlta } from "./alta-plantilla";
import { CamposProtegido } from "./alta-protegido";
import { COLUMNAS_VACIAS, proponerColumnas } from "./alta-propuesta";
import { marcadaPorDefecto, papelesDeColumna, type AsignacionAlta } from "./alta-roles";
import { leerColumnasEjemplo, valoresDistintos, type ColumnasEjemplo } from "./alta-sniff";
import { AYUDA_ALTA, TEXTO_ALTA } from "./alta-textos";
import { VariablesAlta } from "./alta-variables";
import { VistaPreviaAlta } from "./alta-vista-previa";
import { Ayuda, SelectorColumna } from "./mapeo-controles";

export interface PasoDatosResultado {
  mapping_template: MappingTemplate | null;
  acepta_feedback: boolean;
  /** Unidad y rango favorable de la regresión; también sin plantilla. */
  regresion?: RegresionAlta;
}

interface Props {
  /** La primera pregunta del alta; en multiclase se marcan clases en vez de un valor favorable. */
  tipo?: TipoTarea;
  onAtras: () => void;
  /** Sin fichero de ejemplo a mano: crear el despliegue sin plantilla. */
  onOmitir: (regresion?: RegresionAlta) => void;
  onContinuar: (r: PasoDatosResultado) => void;
}

export default function PasoDatos({ tipo = "binary", onAtras, onOmitir, onContinuar }: Props) {
  const caps = capacidades(tipo);
  const multiclase = caps.favorables === "conjunto";
  const regresion = caps.rangoFavorable;
  const [sniff, setSniff] = useState<ColumnasEjemplo | null>(null);
  const [errorLectura, setErrorLectura] = useState<string | null>(null);
  const [aceptaFeedback, setAceptaFeedback] = useState(true);
  const [cols, setCols] = useState<ColumnasAlta>(COLUMNAS_VACIAS);
  const [favorableLabel, setFavorableLabel] = useState("");
  // Casillas que el usuario ha tocado; el resto sigue `marcadaPorDefecto`.
  const [decisiones, setDecisiones] = useState<Record<string, boolean>>({});
  const [protegido, setProtegido] = useState<ProtegidoAlta>(PROTEGIDO_VACIO);
  // Clases, conjunto favorable y probabilidad por clase.
  const mc = useMulticlaseAlta({ activo: multiclase, sniff, predictionCol: cols.predictionCol, labelCol: cols.labelCol });

  const onFile = async (file: File | null) => {
    setErrorLectura(null);
    setSniff(null);
    setCols(COLUMNAS_VACIAS);
    setFavorableLabel("");
    mc.reiniciar();
    setDecisiones({});
    setProtegido(PROTEGIDO_VACIO);
    if (!file) return;
    try {
      const leido = await leerColumnasEjemplo(file);
      if (leido.columnas.length === 0) {
        setErrorLectura("No se han reconocido columnas en el fichero: revisa que sea un CSV o TSV.");
        return;
      }
      setSniff(leido);
      // Regresión: no hay columna de probabilidad.
      setCols({ ...proponerColumnas(leido.columnas), ...(regresion ? { probabilityCol: "" } : {}) });
      mc.leerFichero(file, leido); // Clases de todo el fichero (hasta 5 MB)
    } catch {
      setErrorLectura("No se ha podido leer el fichero en el navegador.");
    }
  };

  const asignar = (parcial: Partial<ColumnasAlta>) => {
    setCols((prev) => ({ ...prev, ...parcial }));
    // El favorable elegido era de la columna de etiqueta anterior.
    if (parcial.labelCol !== undefined) setFavorableLabel("");
  };

  const columnas = sniff?.columnas ?? [];
  const filas = sniff?.filas ?? [];
  // Unidad y rango favorable; con la columna de predicción elegida, la vista previa del rango.
  const rg = useRegresionAlta({ activo: regresion, filas, predictionCol: cols.predictionCol });
  const { probabilidadPorColumna } = mc;
  const asignacion: AsignacionAlta = {
    ...cols,
    protectedCol: protegido.activo ? protegido.col : "",
    probabilidadPorColumna,
  };
  const valoresLabel = cols.labelCol && sniff ? valoresDistintos(filas, cols.labelCol) : [];
  const valoresProtegido = protegido.col && sniff ? valoresDistintos(filas, protegido.col) : [];
  const ocupadas = [
    cols.idCol,
    cols.labelCol,
    cols.predictionCol,
    cols.probabilityCol,
    cols.timestampCol,
    ...Object.keys(probabilidadPorColumna),
  ];
  const opcionesVariables = columnas.filter((c) => !ocupadas.includes(c));
  const marcadas = new Set(
    opcionesVariables.filter((c) => (c in decisiones ? decisiones[c] : marcadaPorDefecto(c, asignacion, filas))),
  );
  const papeles = Object.fromEntries(columnas.map((c) => [c, papelesDeColumna(c, asignacion, marcadas.has(c))]));

  const favorableValido = validoPorTipo(caps.favorables, {
    labelCol: cols.labelCol,
    favorableLabel,
    multiclaseValido: mc.valido,
    regresionValido: rg.valido,
  });
  const puedeContinuar = sniff !== null && favorableValido && (!aceptaFeedback || cols.idCol !== "");

  const continuar = () => {
    if (!puedeContinuar) return;
    const mapping_template = construirPlantilla({
      ...asignacion,
      favorableLabel,
      variables: Array.from(marcadas),
      protegido,
      multiclase: multiclase ? mc.plantilla : undefined,
      regresion: regresion ? rg.valores : undefined,
    });
    onContinuar({ mapping_template, acepta_feedback: aceptaFeedback, regresion: regresion ? rg.valores : undefined });
  };

  return (
    <div className="flex max-h-[calc(100dvh-15rem)] min-w-0 flex-col gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
        <FicheroEjemplo onFile={(f) => void onFile(f)} error={errorLectura} />
        {sniff ? (
          <>
            <VistaPreviaAlta columnas={columnas} filas={filas} papeles={papeles} />
            <CamposIdentidad
              columnas={columnas}
              aceptaFeedback={aceptaFeedback}
              onAceptaFeedback={setAceptaFeedback}
              cols={cols}
              onAsignar={asignar}
              favorableLabel={favorableLabel}
              onFavorableLabel={setFavorableLabel}
              valoresLabel={valoresLabel}
              multiclase={mc.campos}
              regresion={rg.campos}
            />
            <AvisoSinProbabilidad
              visible={sinProbabilidad(caps.probabilidad, {
                probabilityCol: cols.probabilityCol,
                multiclaseSinProbabilidad: mc.sinProbabilidad,
              })}
            />
            <SelectorColumna
              id="alta-timestamp-col"
              etiqueta="Columna de fecha (opcional)"
              valor={cols.timestampCol}
              onChange={(v) => asignar({ timestampCol: v })}
              columnas={columnas}
              ayuda={AYUDA_ALTA.fecha}
              ninguna="Ninguna"
            />
            <CamposProtegido
              columnas={columnas}
              filas={filas}
              valor={protegido}
              onCambiar={setProtegido}
              valoresProtegido={valoresProtegido}
            />
            <VariablesAlta
              opciones={opcionesVariables}
              marcadas={marcadas}
              filas={filas}
              onAlternar={(col, marcada) => setDecisiones((prev) => ({ ...prev, [col]: marcada }))}
              protegida={asignacion.protectedCol}
            />
          </>
        ) : null}
        {sniff ? null : rg.campos}
        <Ayuda id="alta-sin-plantilla-ayuda">{TEXTO_ALTA.sinPlantilla}</Ayuda>
      </div>
      <PieAlta
        onAtras={onAtras}
        onOmitir={() => onOmitir(regresion ? rg.valores : undefined)}
        onContinuar={continuar}
        puedeOmitir={rg.valido}
        puedeContinuar={puedeContinuar}
      />
    </div>
  );
}
