"""The data contract of /data/v1 (PLAN.md 2.5 and Appendix B), as Pydantic models.

This file is the one source of truth. ``orbyt.core.publish`` exports it as JSON Schema into
``schemas/`` and the web app's TypeScript types are generated from that schema, so the pipeline
and the site cannot drift apart. Every model forbids unknown keys: a field that is written but
not declared here fails validation instead of reaching the site unseen.

Optional keys are left out of the JSON when they have no value. ``None`` is kept only where the
value is known to be missing (a claimed value of null, a gate that stopped an estimate).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Basis(StrEnum):
    """How a reported number was obtained, as the register says."""

    measured = "measured"
    calculated = "calculated"
    estimated = "estimated"
    stated = "stated"
    unknown = "unknown"


class Verdict(StrEnum):
    higher = "higher"
    consistent = "consistent"
    lower = "lower"
    inconclusive = "inconclusive"
    unpaired = "unpaired"


class Grade(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class SubjectKind(StrEnum):
    facility = "facility"
    cluster = "cluster"


class IntervalBasis(StrEnum):
    """What ``lo`` and ``hi`` cover. ``sampling`` is the bootstrap over days only (PLAN.md 4.7)."""

    sampling = "sampling"
    total = "total"


class Subject(Model):
    id: str
    kind: SubjectKind
    name: str  # exactly as the register has it, often with the operator
    display_name: str | None
    operator: str | None
    sector: str
    country: str  # ISO 3166-1 alpha-2
    city: str | None
    lat: float
    lon: float
    # The JSON key is "register". The attribute has another name because ``register`` is a
    # method of Pydantic's base class.
    register_: str = Field(alias="register")
    register_id: str


class Period(Model):
    label: str
    start: str
    end: str
    note: str | None = None  # set when the year differs from the dataset's target year


class Claimed(Model):
    value: float
    unit: str
    basis: Basis
    source: str
    n_facilities: int | None = None  # facilities summed in the footprint total


class Observed(Model):
    value: float
    lo: float
    hi: float
    unit: str
    method: str
    n_days: int | None = None
    lifetime_h: float | None = None
    interval_basis: IntervalBasis | None = None


class Ratio(Model):
    value: float
    lo: float
    hi: float


class Detection(Model):
    """Whether the footprint is big enough for the method to measure reliably (METHODS.md 7)."""

    footprint_t: float
    footprint_km: float
    min_reliable_t: float
    reliable: bool  # false means "below reliable detection"


class ClusterNeighbour(Model):
    """The largest register source 20 to 60 km away. It is not in the footprint total."""

    name: str
    reported_t: float
    distance_km: float


class ClusterInfo(Model):
    """Set on a finding whose subject is a cluster: the reported total sums several facilities,
    or a source just outside the 20 km footprint was left out (PLAN.md 1.7 fallback)."""

    n_facilities: int
    neighbour: ClusterNeighbour | None = None


class Finding(Model):
    id: str
    module: str
    subject: Subject
    period: Period
    claimed: Claimed | None
    observed: Observed | None
    ratio: Ratio | None
    verdict: Verdict | None
    grade: Grade | None
    detection: Detection | None = None
    cluster: ClusterInfo | None = None
    validation_site: bool | None = None  # a US plant from the validation (PLAN.md 1.7)


class FindingsPayload(Model):
    module: str
    period: str  # the target year
    source: str
    count: int
    latest_year_countries: dict[str, int]
    showcase: str | None = None  # the subject to open on "explore"
    findings: list[Finding]


class ReportedPoint(Model):
    year: int
    value: float  # tonnes of NOx expressed as NO2
    basis: Basis


class PlumeFit(Model):
    q: float
    tau: float
    sigma: float
    t0: float
    b: float
    r2: float


class PlumeProfileData(Model):
    """The stacked curve F(t) and its EMG fit (PLAN.md 4.3)."""

    t_h: list[float]
    flux_mol_s: list[float | None]
    fit_mol_s: list[float | None]
    fit: PlumeFit


class DayRow(Model):
    date: str
    wind_ms: float
    wind_dir_deg: float  # direction the wind blows from, clockwise from north
    frame: int | None  # position in the flipbook sheet, null for a day too cloudy to show


class StackGeometry(Model):
    width: int
    height: int
    t_h: tuple[float, float]
    crosswind_km: tuple[float, float]
    full_scale_umol_m2: float
    mean_wind_ms: float
    fan_half_width_km: list[float]
    n_days: int


class FlipbookSheet(Model):
    frame_w: int
    frame_h: int
    columns: int
    rows: int
    n_frames: int
    half_km: float
    full_scale_umol_m2: float


class Evidence(Model):
    stack_image: str
    flipbook: str
    stack: StackGeometry
    flipbook_sheet: FlipbookSheet


class ValidationYear(Model):
    year: int
    estimate_t: float | None
    lo: float | None
    hi: float | None
    passed: bool
    gates_failed: list[str]
    days: int | None
    monitors_at_pass_t: float | None
    monitors_t: float | None
    footprint_t: float | None
    ratio_at_pass: float | None
    ratio_footprint: float | None


class ValidationDetail(Model):
    tier: int
    unmonitored_t: float
    unmonitored_largest: str
    u_sys: float
    years: list[ValidationYear]


class FootprintMember(Model):
    register_id: str
    name: str
    reported_t: float


class PeriodObserved(Model):
    value: float
    lo: float
    hi: float
    n_days: int | None
    lifetime_h: float


class PeriodComparison(Model):
    """One register year against its calendar-year estimate. Numbers only when it passed."""

    year: int
    reported_t: float | None
    members: list[FootprintMember]
    status: Verdict
    reason: str | None
    observed: PeriodObserved | None
    ratio: Ratio | None
    gates_failed: list[str]


class Comparison(Model):
    u_sys: float
    verdict_reason: str | None
    flags: list[str]  # "coast", "terrain"
    periods: list[PeriodComparison]


class RollingWindow(Model):
    """The estimate for one rolling 12-month window. Not paired with the register."""

    start: str
    end: str
    label: str
    calendar_year: int | None
    n_days: int
    passed: bool
    value: float | None
    lo: float | None
    hi: float | None
    gates_failed: list[str]


class FindingDetail(Model):
    id: str
    reported_series: list[ReportedPoint]
    sources: list[str]
    validation: ValidationDetail | None = None
    observed: Observed | None = None
    profile: PlumeProfileData | None = None
    days: list[DayRow] | None = None
    evidence: Evidence | None = None
    comparison: Comparison | None = None
    rolling: list[RollingWindow] | None = None


class ModuleEntry(Model):
    id: str
    title: str
    hue: str
    status: str
    method_version: str
    base: str


class Manifest(Model):
    built_at: str
    data_version: str
    commit: str
    modules: list[ModuleEntry]


class Contract(Model):
    """Every public document, so one schema file holds every definition."""

    manifest: Manifest
    findings: FindingsPayload
    finding_detail: FindingDetail
