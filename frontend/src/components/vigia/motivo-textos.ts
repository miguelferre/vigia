/**
 * Textos de ayuda del motivo de `MotivoDialog`: un
 * ejemplo de motivo por acción y el mínimo de caracteres que pide la interfaz.
 * La API y el MCP no cambian (su mínimo sigue siendo no vacío); es la
 * interfaz la que pide un motivo que se entienda en el diario.
 */

/** Mínimo de caracteres del motivo en la interfaz. */
export const MOTIVO_MINIMO = 10;

export const EJEMPLO_MOTIVO = {
  anotar: "El comité acordó revisar el umbral de equidad con el próximo lote; queda constancia aquí.",
  cerrarAlerta: "La caída era un desfase del lote de marzo; ya está corregido y la métrica volvió a su umbral.",
  observarAlerta: "Reconocida por el equipo responsable; se vigila el próximo lote antes de decidir.",
  triaje: "Revisada por el responsable del modelo: afecta a un solo grupo y se investiga esta semana.",
  investigacion: "Se contrastó con el lote anterior: el desvío viene de la nueva sede y no del modelo.",
  decision: "Se mantiene el modelo y se baja el umbral un 5 % hasta el próximo lote, por criterio del comité.",
  accionAlerta: "Se avisó al proveedor tras la revisión del martes; la referencia queda en el correo.",
  moverRiesgo: "La probabilidad baja de alta a media porque el sesgo apareció solo en un lote.",
  seguimientoRiesgo: "Se reconoce el riesgo y se revisa con cada lote nuevo durante un mes.",
  cerrarRiesgo: "El modelo se reentrenó y los dos lotes siguientes volvieron a su umbral.",
  nuevoRiesgo: "Alta manual a petición del comité de seguridad tras la revisión trimestral.",
  registrarRiesgo: "La alerta de equidad sigue sin explicación y afecta a las decisiones de un grupo.",
} as const;

/**
 * Frase de ayuda bajo el campo Motivo. Sin ejemplo propio de la acción solo
 * dice el mínimo: un ejemplo genérico no describe la mayoría de los diálogos.
 */
export function ayudaMotivo(ejemplo?: string): string {
  const minimo = `Mínimo ${MOTIVO_MINIMO} caracteres.`;
  return ejemplo ? `Ejemplo: «${ejemplo}» ${minimo}` : minimo;
}
