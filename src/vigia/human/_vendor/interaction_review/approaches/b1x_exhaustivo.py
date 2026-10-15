"""B1x - Single EXHAUSTIVE prompt (ablation: is p3's advantage structure or quantity?).

Same as B1 (a single pass, no blocks) but pushing the number of findings to the
maximum. If B1x gets close to p3, p3's advantage was generating MORE (quantity), not its
decomposition into blocks (structure). If B1x stays below, the structure contributes.
"""

from __future__ import annotations

from ._generator import generate
from ..schemas import Dossier, Finding, Guideline

_PUSH = (
    "IMPORTANTE: se EXHAUSTIVO al maximo en esta UNICA respuesta. Recorre TODAS las areas "
    "de interaccion y reporta el MAYOR numero posible de problemas reales y anclados (apunta a "
    "20 o mas si existen), sin repetir y sin inventar genericos. No te limites a unos pocos."
)


def run(dossier: Dossier, guidelines: list[Guideline]) -> list[Finding]:
    return generate(dossier, guidelines, few_shot=False, label="b1x", extra=_PUSH)
