/**
 * Traducción de nombres técnicos de característica a la etiqueta clínica del
 * dominio Digestivo.
 *
 * `DIAGNOSIS_MAPPING` es copia literal de `DIAGNOSIS_MAPPING` en
 * `src/vigia/sim/model.py`: código CIAP-2 de capítulo L (reuma, congelado) a nombre técnico plano de columna, p. ej.
 * "PC_Diagnosis_L15" -> "Knee_signs_symptoms". Hay que verificar la paridad
 * si `sim/model.py` cambia, igual que `METRIC_LABELS` en `metric-labels.ts`.
 *
 * El diccionario "dominio" que sirve `GET /api/content/demo`
 * (`useGuionDemo`) traduce por ese código de CIAP-2 a la etiqueta
 * clínica del capítulo D, no por el nombre plano que aparece en
 * `result.details.features[].feature`: `NOMBRE_A_CODIGO` es el puente entre
 * los dos.
 */

const DIAGNOSIS_MAPPING: Record<string, string> = {
  PC_Diagnosis_L01: "Neck_signs_symptoms",
  PC_Diagnosis_L02: "Dorsal_signs_symptoms",
  PC_Diagnosis_L03: "Lumbar_signs_symptoms",
  PC_Diagnosis_L04: "Thoracic_signs_symptoms",
  PC_Diagnosis_L05: "Flanks_armpits_signs_symptoms",
  PC_Diagnosis_L07: "Jaw_signs_symptoms",
  PC_Diagnosis_L08: "Shoulder_signs_symptoms",
  PC_Diagnosis_L09: "Arm_signs_symptoms",
  PC_Diagnosis_L10: "Elbow_signs_symptoms",
  PC_Diagnosis_L11: "Wrist_signs_symptoms",
  PC_Diagnosis_L12: "Hand_fingers_signs_symptoms",
  PC_Diagnosis_L13: "Hip_signs_symptoms",
  PC_Diagnosis_L14: "Thigh_leg_signs_symptoms",
  PC_Diagnosis_L15: "Knee_signs_symptoms",
  PC_Diagnosis_L16: "Ankle_signs_symptoms",
  PC_Diagnosis_L17: "Foot_toes_signs_symptoms",
  PC_Diagnosis_L18: "Muscle_pain",
  "PC_Diagnosis_L18.01": "Fibromyalgia",
  PC_Diagnosis_L19: "Other_unspecified_muscular_signs_symptoms",
  PC_Diagnosis_L20: "Unspecified_joint_signs_symptoms",
  PC_Diagnosis_L28: "Locomotor_system_disability",
  PC_Diagnosis_L29: "Other_locomotor_system_signs_symptoms",
  PC_Diagnosis_L83: "Neck_syndromes",
  PC_Diagnosis_L84: "Lumbar_thoracic_syndromes_without_irradiation",
  PC_Diagnosis_L85: "Acquired_spinal_deformities",
  PC_Diagnosis_L86: "Lumbar_thoracic_syndromes_with_irradiation",
  PC_Diagnosis_L87: "Bursitis_tendinitis_synovitis_unspecified",
  PC_Diagnosis_L88: "Rheumatoid_arthritis",
  "PC_Diagnosis_L88.01": "Ankylosing_spondylitis",
  PC_Diagnosis_L89: "Hip_osteoarthritis",
  PC_Diagnosis_L90: "Knee_arthrosis",
  PC_Diagnosis_L91: "Other_arthrosis",
  PC_Diagnosis_L92: "Shoulder_syndromes",
  PC_Diagnosis_L93: "Tennis_elbow",
  PC_Diagnosis_L94: "Osteochondrosis",
  PC_Diagnosis_L95: "Osteoporosis",
  PC_Diagnosis_L98: "Acquired_limb_deformities",
  PC_Diagnosis_L99: "Other_locomotor_diseases",
  PC_Diagnosis_T92: "Gout",
};

const NOMBRE_A_CODIGO: Record<string, string> = Object.fromEntries(
  Object.entries(DIAGNOSIS_MAPPING).map(([codigo, nombre]) => [nombre, codigo]),
);

/**
 * Etiqueta clínica de una característica, dado su nombre técnico
 * (`result.details.features[].feature`) y el diccionario "dominio" de
 * `useGuionDemo` (clave = código CIAP-2, valores del capítulo D).
 *
 * Repliegue: sin diccionario todavía cargado
 * (`staleTime: Infinity`, la petición puede no haber vuelto), sin código
 * conocido para ese nombre (p. ej. "Age" o "Previous_PC_episodes", que no
 * son diagnósticos), o sin entrada del capítulo D para ese código, se
 * devuelve `etiquetaActual` sin tocar: nunca vacío, nunca degrada una
 * traducción que ya hubiera. Por defecto `etiquetaActual` es el propio
 * nombre técnico, que es lo que se pintaba antes de esta traducción.
 */
export function etiquetaCaracteristica(
  nombreTecnico: string,
  dominio: Record<string, string> | undefined,
  etiquetaActual: string = nombreTecnico,
): string {
  if (!dominio) return etiquetaActual;
  const codigo = NOMBRE_A_CODIGO[nombreTecnico];
  if (!codigo) return etiquetaActual;
  return dominio[codigo] ?? etiquetaActual;
}

/**
 * Valor legible de una categoría binaria: toda variable
 * categórica del dominio es una marca de presencia de un diagnóstico
 * (`core/drift.py:407`, todas las columnas menos `Age` y
 * `Previous_PC_episodes` son categóricas), así que "0"/"1" en crudo se lee
 * como ausencia/presencia. Cualquier otro valor (una categórica con más de
 * dos niveles, si la hubiera) se devuelve tal cual.
 */
export function etiquetaValorCategoria(valor: string): string {
  if (valor === "0") return "Ausente";
  if (valor === "1") return "Presente";
  return valor;
}

/** Variables del simulador que no son diagnósticos. */
const VARIABLES_NO_DIAGNOSTICO: Record<string, string> = {
  Age: "Edad",
  Previous_PC_episodes: "Episodios previos en primaria",
};

/**
 * Nombre legible de cualquier variable del modelo: diagnósticos por
 * `etiquetaCaracteristica` con el diccionario de dominio, el resto por
 * `VARIABLES_NO_DIAGNOSTICO`; si no hay traducción, el nombre técnico con
 * guiones bajos convertidos en espacios.
 */
export function nombreVariable(
  nombreTecnico: string,
  dominio: Record<string, string> | undefined,
): string {
  const noDiagnostico = VARIABLES_NO_DIAGNOSTICO[nombreTecnico];
  if (noDiagnostico) return noDiagnostico;
  const traducido = etiquetaCaracteristica(nombreTecnico, dominio);
  if (traducido !== nombreTecnico) return traducido;
  return nombreTecnico.replace(/_/g, " ");
}
