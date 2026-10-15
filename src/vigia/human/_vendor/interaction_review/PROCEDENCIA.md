# Procedencia de la copia de `interaction_review`

Copia incluida de `interaction_review` dentro de Vigía
(`vigia.human._vendor.interaction_review`).

| Dato | Valor |
| --- | --- |
| Origen | paquete `interaction_review`, carpeta `src/interaction_review/` |
| Commit de origen | `dcb0ca8363195fe7803793f0fa59cddaf869402d` |
| Licencia | MIT, `Copyright (c) 2026 Miguel Ferreiro García` (`LICENSE`) |
| Datos de terceros | `guidelines/eticas/` (Eticas AI Risk Taxonomy v3.0.0, CC BY 4.0): `LICENSE` y `CITATION.cff` intactos, `ATTRIBUTION.md` sin la remisión a un ADR (cambio 4); `taxonomy.yaml` y `mappings.yaml` sin cambios |

## Qué contiene la copia

- 23 módulos `.py`: `__init__`, `dedup`, `eticas`, `ingest`, `llm`, `metrics`,
  `prompts`, `regulatory`, `report`, `router`, `schemas`, `telemetry`;
  `approaches/` (`__init__`, `_generator`, `a4_agent`, `b0_checklist`,
  `b1_single_prompt`, `b1x_exhaustivo`, `b2_few_shot`, `p3_neutral`, `p3_pipeline`);
  `guidelines/` (`__init__`, `loader`).
- 9 ficheros de datos que el código carga con `Path(__file__)`:
  `guidelines/hax18.yaml`, `pair.yaml`, `ix.yaml`, `regulatory_map.yaml`;
  `guidelines/eticas/taxonomy.yaml`, `mappings.yaml`, `LICENSE`, `ATTRIBUTION.md`,
  `CITATION.cff`.
- Sin copiar: `cli.py`, `mcp_server.py`, `runner.py`, `smart_ingest.py`, `judge.py`,
  `ablation.py`, `dedup_llm.py`, `templates/` ni `data/examples/`.
- `report_html.py` no se copia: Vigía dibuja el informe con
  `vigia.human.informe_revision.dibujar`.

## Cambios hechos en la copia

1. **Imports internos relativos.** Ningún módulo importa `interaction_review`
   como paquete de primer nivel y ninguno toca `sys.path`. Ficheros tocados:
   `approaches/__init__.py`, `approaches/_generator.py`, `approaches/a4_agent.py`,
   `approaches/b0_checklist.py`, `approaches/b1_single_prompt.py`,
   `approaches/b1x_exhaustivo.py`, `approaches/b2_few_shot.py`,
   `approaches/p3_neutral.py`, `approaches/p3_pipeline.py`, `dedup.py`,
   `guidelines/__init__.py`, `guidelines/loader.py`, `ingest.py`, `metrics.py`,
   `prompts.py`, `regulatory.py`, `report.py`, `router.py`.
2. **Versión como constante.** `__init__.py`: `__version__ = "0.1.0"`. Vigía lee la
   constante, no los metadatos de ninguna distribución.
3. **Tildes en los YAML cuyo texto sale en el informe.** `guidelines/hax18.yaml`,
   `pair.yaml`, `ix.yaml` y `regulatory_map.yaml`: solo cambian letras (acentos y
   `ñ`) de títulos, descripciones, ejemplos, remediaciones, notas y nombres de grupo, y
   los interrogativos. Los identificadores y el texto inglés de los títulos entre
   paréntesis no se tocan. Los datos de Eticas no se tocan.

4. **Referencias a documentos de decisión.** Se quitan de comentarios, docstrings y
   textos las remisiones a documentos del origen que no viajan con la copia
   (`ADR-n`, `docs/adr/`), en `approaches/_generator.py`, `dedup.py`, `eticas.py`,
   `llm.py`, `metrics.py`, `prompts.py`, `regulatory.py`, `report.py`, `schemas.py` y
   `guidelines/eticas/ATTRIBUTION.md`.

No hay más cambios: ni lógica, ni nombres, ni los textos en inglés de `report.py` o
de los enfoques.

## Ruff

La carpeta `src/vigia/human/_vendor` está en `extend-exclude` de `[tool.ruff]` en
`pyproject.toml`: la copia no se reformatea ni se corrige con `ruff --fix`.
