"""Ratio, interval, verdict and grade (PLAN.md 4.8), with no input or output.

    s_boot  = (ln(hi) - ln(lo)) / 3.92          bootstrap interval of the estimate, as a log sd
    s_total = sqrt(s_boot^2 + u_sys^2)          u_sys is the systematic term from the US validation
    R       = observed / reported_in_footprint
    R_lo, R_hi = R * exp(-/+ 1.96 * s_total)

A period is "higher" when R_lo is above ``higher_min``, "lower" when R_hi is below ``lower_max``,
"consistent" otherwise, "inconclusive" when a quality gate failed or the estimate has no interval,
and "unpaired" when the register has no value for it.

The verdict of a subject is about its headline period, the latest one the register covers. A
"higher" or "lower" headline needs ``min_periods`` separate periods that pass every gate and
exceed in the same direction. An exceeding headline that no second period confirms is
"inconclusive", not "consistent": its interval excludes consistency in one year, so the label
"consistent with reported" would say more than the data do. The constants are in config.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log, sqrt
from typing import Any

# Verdicts that carry a number, and so a grade.
CALLS = ("higher", "consistent", "lower")


@dataclass(frozen=True)
class Rules:
    """The constants of PLAN.md 4.8 and 4.8's grade, read from config.yaml (``verdict``)."""

    u_sys: float
    higher_min: float
    lower_max: float
    min_periods: int
    grade_a_min_days: int


def rules_from_config(cfg: dict[str, Any]) -> Rules:
    v = cfg["verdict"]
    return Rules(
        u_sys=v["u_sys"],
        higher_min=v["higher_min_ratio"],
        lower_max=v["lower_max_ratio"],
        min_periods=v["min_periods"],
        grade_a_min_days=v["grade"]["a_min_days"],
    )


@dataclass(frozen=True)
class Ratio:
    value: float
    lo: float
    hi: float
    s_boot: float
    s_total: float


@dataclass(frozen=True)
class PeriodCall:
    """What one period says. ``ratio`` is set whenever an interval exists, used or not."""

    label: str
    status: str  # higher, consistent, lower, inconclusive, unpaired
    ratio: Ratio | None = None
    reason: str | None = None


def sigma_boot(lo: float | None, hi: float | None) -> float | None:
    """The bootstrap interval as a log standard deviation, or None when it cannot be."""
    if lo is None or hi is None or not (isfinite(lo) and isfinite(hi)) or lo <= 0 or hi <= lo:
        return None
    return (log(hi) - log(lo)) / 3.92


def ratio_interval(
    observed: float | None,
    lo: float | None,
    hi: float | None,
    reported: float | None,
    u_sys: float,
) -> Ratio | None:
    """R and its 95% interval with the systematic term, or None without an estimate or interval."""
    s = sigma_boot(lo, hi)
    if s is None or not observed or observed <= 0 or not reported or reported <= 0:
        return None
    st = sqrt(s * s + u_sys * u_sys)
    r = observed / reported
    return Ratio(r, r * exp(-1.96 * st), r * exp(1.96 * st), s, st)


def call_period(
    label: str,
    observed: float | None,
    lo: float | None,
    hi: float | None,
    reported: float | None,
    gates_failed: list[str],
    rules: Rules,
) -> PeriodCall:
    """One period against the register's footprint total for it."""
    if reported is None or reported <= 0:
        return PeriodCall(label, "unpaired", reason="the register has no value for this period")
    if observed is None:
        return PeriodCall(label, "inconclusive", reason="no estimate")
    r = ratio_interval(observed, lo, hi, reported, rules.u_sys)
    if gates_failed:
        return PeriodCall(label, "inconclusive", r, "failed: " + ", ".join(gates_failed))
    if r is None:
        return PeriodCall(label, "inconclusive", None, "no bootstrap interval")
    if r.lo > rules.higher_min:
        return PeriodCall(label, "higher", r)
    if r.hi < rules.lower_max:
        return PeriodCall(label, "lower", r)
    return PeriodCall(label, "consistent", r)


def combine(calls: list[PeriodCall], rules: Rules) -> tuple[str, str | None]:
    """The verdict of a subject and the reason when it is inconclusive.

    ``calls`` run from the oldest register year to the newest. The headline is the newest period
    that is paired with a register value.
    """
    paired = [c for c in calls if c.status != "unpaired"]
    if not paired:
        return "unpaired", None
    head, others = paired[-1], paired[:-1]
    if head.status == "consistent":
        return "consistent", None
    if head.status == "inconclusive":
        return "inconclusive", head.reason
    agree = 1 + sum(c.status == head.status for c in others)
    if agree >= rules.min_periods:
        return head.status, None
    return (
        "inconclusive",
        f"{head.status} than reported in {head.label} only, no second period confirms it",
    )


def grade(
    verdict: str,
    n_days: int | None,
    n_facilities: int,
    flags: list[str],
    rules: Rules,
    cluster: bool = False,
) -> str | None:
    """A, B or C for a verdict that carries a number, else None.

    A: every gate passes, at least ``grade_a_min_days`` days and no flag. B: one flag, or fewer
    days (the gate floor is 40). C: a cluster, that is several facilities summed or a footprint
    that failed the sources check and was kept as a cluster (``cluster``). Two flags also give C,
    the plan does not say what two flags give and C is the cautious reading.
    """
    if verdict not in CALLS:
        return None
    if cluster or n_facilities > 1 or len(flags) >= 2:
        return "C"
    if flags or n_days is None or n_days < rules.grade_a_min_days:
        return "B"
    return "A"
