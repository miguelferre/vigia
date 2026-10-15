"""Deterministic telemetry: measuring criterion erosion (deskilling) from usage logs.

No LLM. Turns a usage-log CSV into the three time series discussed for the SERGAS fracture
deployment and summarizes them:
  - reality (ground_truth), the human's decision and the model's output over time;
  - human<->model AGREEMENT per window (convergence) vs the human's ACCURACY against reality
    (the gap that should not stop improving);
  - the RESCUE rate: on the cases the model gets wrong, how often the human still gets it
    right -- the capability that deskilling erodes first.

It is the objective complement to the end-user testimony (README: "the direction the product
grows in"): the interview captures what the person perceives; this captures the drift the
person does not. It maps to guideline IX-2 (deskilling). The output is a Markdown summary meant
to be attached to a dossier as a DOCUMENT source (aggregated, no personal data), so a review can
cite it as evidence with a real locus.

Everything here is deterministic and reproducible: the summary carries no wall-clock timestamp,
and the signal it reports is something to INVESTIGATE, never a diagnosis.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

REQUIRED_COLUMNS = ("date", "human_decision", "model_output", "ground_truth")


@dataclass(frozen=True)
class Record:
    """One decision event. `truth` is None when the real outcome is not yet known (lag)."""

    date: date
    human: str
    model: str
    truth: str | None


@dataclass(frozen=True)
class WindowMetrics:
    """The three signals over one time window. Rates are None when undefined (no rows / no gt)."""

    start: date
    end: date
    n: int
    n_with_gt: int
    agreement_rate: float | None  # mean(human == model): convergence
    human_accuracy: float | None  # mean(human == truth): the gap with reality
    model_accuracy: float | None  # mean(model == truth): context
    rescue_rate: float | None     # among model-wrong rows, mean(human == truth): the sharp one


@dataclass(frozen=True)
class Trends:
    """OLS slope per window index (None when fewer than 2 defined points)."""

    agreement_slope: float | None
    human_accuracy_slope: float | None
    model_accuracy_slope: float | None
    rescue_slope: float | None


@dataclass(frozen=True)
class DeskillingSignal:
    fired: bool
    reason: str


# --------------------------------------------------------------------------- #
# Loading (deterministic, strict).
# --------------------------------------------------------------------------- #
def _norm(value: str | None) -> str:
    """Categorical normalization: trim + casefold, so 'Yes' and 'yes ' compare equal."""
    return (value or "").strip().casefold()


def load_records(path: str | Path) -> list[Record]:
    """Reads and validates the usage-log CSV, sorted by date. Raises ValueError on bad input.

    Header must contain: date, human_decision, model_output, ground_truth. `date` is ISO
    (YYYY-MM-DD); human_decision/model_output are required; ground_truth may be blank (unknown
    outcome). Values are categorical and compared by normalized equality (no fixed vocabulary).
    """
    text = Path(path).read_text(encoding="utf-8-sig")  # tolerate a BOM
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise ValueError("Empty CSV: expected a header row.")
    header = [h.strip() for h in reader.fieldnames]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(
            f"CSV missing required column(s): {missing}. Expected header: {list(REQUIRED_COLUMNS)}."
        )
    records: list[Record] = []
    for i, row in enumerate(reader, start=2):  # line 1 is the header
        raw_date = (row.get("date") or "").strip()
        try:
            d = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Row {i}: bad date {raw_date!r} (expected YYYY-MM-DD).") from None
        human, model = _norm(row.get("human_decision")), _norm(row.get("model_output"))
        if not human or not model:
            raise ValueError(f"Row {i}: human_decision and model_output must be non-empty.")
        records.append(Record(date=d, human=human, model=model, truth=_norm(row.get("ground_truth")) or None))
    if not records:
        raise ValueError("CSV has a header but no data rows.")
    records.sort(key=lambda r: r.date)
    return records


# --------------------------------------------------------------------------- #
# Metrics.
# --------------------------------------------------------------------------- #
def _rate(flags: list[bool]) -> float | None:
    return (sum(1 for f in flags if f) / len(flags)) if flags else None


def _window_metrics(recs: list[Record], start: date, end: date) -> WindowMetrics:
    with_gt = [r for r in recs if r.truth is not None]
    model_wrong = [r for r in with_gt if r.model != r.truth]
    return WindowMetrics(
        start=start,
        end=end,
        n=len(recs),
        n_with_gt=len(with_gt),
        agreement_rate=_rate([r.human == r.model for r in recs]),
        human_accuracy=_rate([r.human == r.truth for r in with_gt]),
        model_accuracy=_rate([r.model == r.truth for r in with_gt]),
        rescue_rate=_rate([r.human == r.truth for r in model_wrong]),
    )


def compute_windows(records: list[Record], n_windows: int = 4) -> list[WindowMetrics]:
    """Splits the records into `n_windows` of equal calendar span and computes the metrics of each.

    Equal span (not equal count) keeps windows interpretable as time periods; a window may end up
    with few or zero records, which `render_summary_md` flags rather than hides.
    """
    if n_windows < 1:
        raise ValueError("n_windows must be >= 1.")
    if not records:
        raise ValueError("No records to window.")
    records = sorted(records, key=lambda r: r.date)
    lo, hi = records[0].date, records[-1].date
    span = (hi - lo).days

    if span == 0:  # a single calendar day -> a single window
        return [_window_metrics(list(records), lo, hi)]

    width = span / n_windows
    buckets: list[list[Record]] = [[] for _ in range(n_windows)]
    for r in records:
        idx = min(n_windows - 1, int((r.date - lo).days / width))
        buckets[idx].append(r)

    windows: list[WindowMetrics] = []
    for i in range(n_windows):
        start = lo + timedelta(days=int(round(i * width)))
        end = hi if i == n_windows - 1 else lo + timedelta(days=int(round((i + 1) * width)))
        windows.append(_window_metrics(buckets[i], start, end))
    return windows


def _slope(series: list[float | None]) -> float | None:
    """OLS slope of the defined points against their window index. None if < 2 points."""
    pts = [(i, y) for i, y in enumerate(series) if y is not None]
    if len(pts) < 2:
        return None
    n = len(pts)
    sx = sum(x for x, _ in pts)
    sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts)
    sxy = sum(x * y for x, y in pts)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    return (n * sxy - sx * sy) / denom


def compute_trends(windows: list[WindowMetrics]) -> Trends:
    return Trends(
        agreement_slope=_slope([w.agreement_rate for w in windows]),
        human_accuracy_slope=_slope([w.human_accuracy for w in windows]),
        model_accuracy_slope=_slope([w.model_accuracy for w in windows]),
        rescue_slope=_slope([w.rescue_rate for w in windows]),
    )


def deskilling_signal(trends: Trends, *, eps: float = 0.02) -> DeskillingSignal:
    """Composite, threshold-based flag: human<->model agreement rising WHILE the human's own
    accuracy stalls/falls or the rescue rate falls. It is a prompt to INVESTIGATE, not a verdict.
    """
    a, h, r = trends.agreement_slope, trends.human_accuracy_slope, trends.rescue_slope
    if a is None or (h is None and r is None):
        return DeskillingSignal(False, "Insufficient windows with ground truth to assess a trend.")
    converging = a > eps
    human_stalls = h is not None and h <= 0
    rescue_falls = r is not None and r < -eps
    if converging and (human_stalls or rescue_falls):
        why = []
        if human_stalls:
            why.append("the human's own accuracy is not improving")
        if rescue_falls:
            why.append("the rescue rate is falling")
        return DeskillingSignal(
            True,
            "Human and model are converging while " + " and ".join(why)
            + " -- a pattern consistent with criterion erosion. Investigate; not a diagnosis.",
        )
    if not converging:
        return DeskillingSignal(False, "Human and model are not converging over the period.")
    return DeskillingSignal(False, "Convergence present, but the human's accuracy/rescue rate holds.")


# --------------------------------------------------------------------------- #
# Rendering (deterministic Markdown, attachable to a dossier).
# --------------------------------------------------------------------------- #
def _fmt(x: float | None) -> str:
    return f"{x:.2f}" if x is not None else "n/a"


def _fmt_slope(x: float | None) -> str:
    return f"{x:+.3f}/win" if x is not None else "n/a"


def render_summary_md(
    windows: list[WindowMetrics],
    trends: Trends,
    signal: DeskillingSignal,
    *,
    source_label: str = "usage logs",
    min_n: int = 30,
) -> str:
    """Deterministic Markdown summary. No timestamp: same input -> byte-identical output."""
    lines: list[str] = []
    lines.append("# Usage-telemetry summary (deterministic, aggregated)")
    lines.append("")
    lines.append(f"- **Source:** {source_label}")
    lines.append(f"- **Windows:** {len(windows)} (equal calendar span)")
    total = sum(w.n for w in windows)
    total_gt = sum(w.n_with_gt for w in windows)
    lines.append(f"- **Events:** {total} ({total_gt} with known ground truth)")
    lines.append("")
    lines.append("| Window | Dates | n | n(gt) | Agreement H<->M | Human acc. | Model acc. | Rescue |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, w in enumerate(windows, 1):
        lines.append(
            f"| {i} | {w.start.isoformat()}..{w.end.isoformat()} | {w.n} | {w.n_with_gt} | "
            f"{_fmt(w.agreement_rate)} | {_fmt(w.human_accuracy)} | {_fmt(w.model_accuracy)} | "
            f"{_fmt(w.rescue_rate)} |"
        )
    lines.append("")
    lines.append("**Trends (OLS slope per window):**")
    lines.append(f"- Agreement H<->M: {_fmt_slope(trends.agreement_slope)} (convergence if rising)")
    lines.append(f"- Human accuracy: {_fmt_slope(trends.human_accuracy_slope)} (the gap with reality)")
    lines.append(f"- Rescue rate: {_fmt_slope(trends.rescue_slope)} (human catches a wrong model)")
    lines.append("")
    verdict = "SIGNAL" if signal.fired else "no signal"
    lines.append(f"**Deskilling signal (IX-2): {verdict}.** {signal.reason}")

    low = [i + 1 for i, w in enumerate(windows) if w.n < min_n]
    no_gt = [i + 1 for i, w in enumerate(windows) if w.n_with_gt == 0]
    if low:
        lines.append("")
        lines.append(f"> Caution: window(s) {low} have fewer than {min_n} events; their rates are noisy.")
    if no_gt:
        lines.append("")
        lines.append(f"> Caution: window(s) {no_gt} have no ground truth; accuracy/rescue are undefined there.")
    lines.append("")
    lines.append(
        "> Aggregated telemetry, no personal data. This is an objective complement to the end-user "
        "testimony, not a substitute; the signal is something to investigate, not a diagnosis."
    )
    return "\n".join(lines) + "\n"


def summarize(
    path: str | Path, *, n_windows: int = 4, min_n: int = 30, eps: float = 0.02, source_label: str | None = None
) -> str:
    """Convenience end-to-end: CSV path -> Markdown summary. Deterministic, no LLM."""
    records = load_records(path)
    windows = compute_windows(records, n_windows=n_windows)
    trends = compute_trends(windows)
    signal = deskilling_signal(trends, eps=eps)
    return render_summary_md(
        windows, trends, signal, source_label=source_label or f"usage logs ({Path(path).name})", min_n=min_n
    )
