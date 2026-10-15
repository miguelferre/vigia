"""Smoke test de interaction_review.

Ejecuta, sin LLM y sin red: carga de las 32 directrices (HAX-18 + PAIR-12 + IX-2),
validacion del dossier de demo, aproximacion B0 (checklist deterministico),
crosswalk regulatorio y render del informe HTML.

Pensado para correr con cualquier interprete que tenga vigia instalado
(el paquete interaction_review va vendorizado dentro de vigia), incluido el Python embebido del paquete final:

    python build/smoke_ir.py [--out DIR]

Sale con 0 si todo va bien, 1 si algo falla (ver campo "errors" del JSON).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Sin LLM: fijar ANTES de importar la copia vendorizada de interaction_review, por si algun approach
# mira el entorno al importarse (b0 no lo necesita, pero es defensivo y barato).
os.environ.setdefault("LLM_BACKEND", "none")
os.environ.pop("ANTHROPIC_API_KEY", None)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOSSIER = REPO_ROOT / "data" / "demo" / "dossier_demo.json"


def run_smoke(dossier_path: Path, out_dir: Path) -> dict:
    errors: list[str] = []
    t0 = time.monotonic()

    result: dict = {
        "ok": False,
        "ir_version": None,
        "guidelines_total": 0,
        "guidelines_by_source": {},
        "findings_total": 0,
        "html_bytes": 0,
        "elapsed_ms": 0,
        "python": sys.version.split()[0],
        "errors": errors,
    }

    try:
        from vigia.human._vendor.interaction_review import __version__ as ir_version
        from vigia.human._vendor.interaction_review import regulatory
        from vigia.human._vendor.interaction_review.approaches.b0_checklist import run as run_b0
        from vigia.human._vendor.interaction_review.guidelines import all_guidelines
        from vigia.human._vendor.interaction_review.schemas import Dossier, GuidelineCorpus
        from vigia.human.informe_revision import Revision, dibujar
    except Exception as exc:  # noqa: BLE001 - queremos capturar cualquier fallo de import
        errors.append(f"import: {exc!r}")
        result["elapsed_ms"] = round((time.monotonic() - t0) * 1000, 1)
        return result

    result["ir_version"] = ir_version

    try:
        guidelines = list(all_guidelines())
        result["guidelines_total"] = len(guidelines)
        by_source: dict[str, int] = {}
        for g in guidelines:
            key = g.corpus.value if isinstance(g.corpus, GuidelineCorpus) else str(g.corpus)
            by_source[key] = by_source.get(key, 0) + 1
        result["guidelines_by_source"] = by_source
    except Exception as exc:  # noqa: BLE001
        errors.append(f"guidelines: {exc!r}")
        guidelines = []

    try:
        data = json.loads(dossier_path.read_text(encoding="utf-8"))
        dossier = Dossier.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"dossier: {exc!r}")
        result["elapsed_ms"] = round((time.monotonic() - t0) * 1000, 1)
        return result

    findings = []
    if guidelines:
        try:
            findings = run_b0(dossier, guidelines)
            result["findings_total"] = len(findings)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"b0: {exc!r}")

    if findings:
        try:
            xwalk = regulatory.crosswalk(findings)
            if not xwalk:
                errors.append("crosswalk: vacio (se esperaban referencias)")
            unmapped = regulatory.unmapped_guidelines()
            if unmapped:
                errors.append(f"crosswalk: guidelines sin mapear: {unmapped}")
            unknown = regulatory.unknown_map_ids()
            if unknown:
                errors.append(f"crosswalk: ids desconocidos en el mapa: {unknown}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"crosswalk: {exc!r}")

    try:
        html = dibujar(Revision(dossier=dossier, findings=findings, approach="b0", incluir_crosswalk=True))
        result["html_bytes"] = len(html.encode("utf-8"))
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "smoke_findings_b0.html"
        out_path.write_text(html, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"informe: {exc!r}")

    result["elapsed_ms"] = round((time.monotonic() - t0) * 1000, 1)
    result["ok"] = not errors
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, default=DEFAULT_DOSSIER)
    parser.add_argument("--out", type=Path, default=None, help="Directorio de salida del HTML.")
    args = parser.parse_args()

    if args.out is not None:
        out_dir = args.out
        result = run_smoke(args.dossier, out_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="vigia_smoke_ir_") as tmp:
            result = run_smoke(args.dossier, Path(tmp))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
