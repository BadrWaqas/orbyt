"""The diagnostic figure for one facility.

Top: the stack image. Bottom: the stacked curve with its fit, the same curve for each wind
quarter, and a summary. A source seen from four sides should give four similar curves, so the
quarter panel is the quick check for neighbours and uneven background.

Colours follow the web app's dark tokens. The stack image is diverging (blue below the
background, amber above, dark at zero) because the background is subtracted. Series are told
apart by line style and label as well as colour.
"""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SURFACE = "#0d1218"
RAISED = "#161d26"
TEXT = "#f2f4f7"
TEXT_2 = "#aab2bd"
GRID = "#2a3440"
AMBER = "#ffb02e"
BLUE = "#7cc4ff"
DIVERGING = LinearSegmentedColormap.from_list("orbyt_div", ["#4a8fd1", "#1a2430", "#ffb02e"])
# Four series in a fixed order (N, E, S, W), checked for colour-blind separation on this surface.
SECTOR_STYLE = {
    "N": ("#3987e5", "-"),
    "E": ("#d95926", "--"),
    "S": ("#199e70", "-."),
    "W": ("#c98500", ":"),
}


def _style(ax: Any) -> None:
    ax.set_facecolor(RAISED)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=9)
    ax.xaxis.label.set_color(TEXT_2)
    ax.yaxis.label.set_color(TEXT_2)


def _legend(ax: Any, **kw: Any) -> None:
    ax.legend(facecolor=RAISED, edgecolor=GRID, labelcolor=TEXT_2, fontsize=9, **kw)


def _series(values: list) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in values], dtype=float)


def _summary_lines(doc: dict) -> list[str]:
    obs, rep = doc["observed"], doc["reported_t_yr"]
    lines = [*textwrap.wrap(doc["name"], 40), ""]
    if obs:
        lines += [
            f"Satellite estimate  {obs['nox_t_yr']:,.0f} t NOx/yr",
            f"95% interval        {obs['lo']:,.0f} to {obs['hi']:,.0f}",
        ]
    else:
        lines += ["Satellite estimate  no fit"]
    if rep:
        lines.append(f"Reported (EEA)      {rep:,.0f} t NOx/yr")
        if doc["ratio"]:
            lines.append(f"Ratio               {doc['ratio']:.2f}")
    if obs:
        lines.append(f"Lifetime            {obs['lifetime_h']:.1f} h")
    d = doc["days"]
    lines += ["", f"Days used {d['used']} of {d['cached']} (calm {d['dropped']['calm']})"]
    failed = doc["gates_failed"]
    lines.append("Gates failed: " + ("none" if not failed else ""))
    lines += [f"  {g}" for g in failed]
    lines += ["", "Inconclusive, not a published number" if failed else "Passes every gate"]
    return lines


def draw_diagnostic(
    path: Path,
    doc: dict,
    flux: np.ndarray,
    t_hours: np.ndarray,
    yr_km: np.ndarray,
    half_width_km: np.ndarray,
) -> Path:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(flux, axis=0) * 1e6  # micromol per m per s
        vmax = float(np.nanpercentile(np.abs(mean), 99)) if np.isfinite(mean).any() else 1.0
    fig = plt.figure(figsize=(13, 7.6), facecolor=SURFACE)
    gs = fig.add_gridspec(
        2, 3, height_ratios=[1.3, 1], width_ratios=[1, 1, 0.9], hspace=0.4, wspace=0.24
    )
    ax_img = fig.add_subplot(gs[0, :])
    ax_curve, ax_sec, ax_txt = (fig.add_subplot(gs[1, i]) for i in range(3))
    for ax in (ax_img, ax_curve, ax_sec):
        _style(ax)

    im = ax_img.pcolormesh(
        t_hours, yr_km, mean, cmap=DIVERGING, vmin=-(vmax or 1.0), vmax=vmax or 1.0, shading="auto"
    )
    ax_img.plot(t_hours, half_width_km, color=TEXT, lw=1, ls="--", label="integration fan")
    ax_img.plot(t_hours, -half_width_km, color=TEXT, lw=1, ls="--")
    flank_km = doc["constants"]["flank_km"]
    ax_img.axhline(flank_km, color=TEXT_2, lw=0.9, ls=":", label="background flanks start")
    ax_img.axhline(-flank_km, color=TEXT_2, lw=0.9, ls=":")
    ax_img.axvline(0, color=TEXT, lw=0.8, alpha=0.6)
    ax_img.set_xlabel("travel time from the source, hours (wind speed times time gives distance)")
    ax_img.set_ylabel("crosswind distance, km")
    ax_img.set_title(
        f"Stack of {flux.shape[0]} days, flux density with each day's background plane removed",
        color=TEXT,
    )
    _legend(ax_img, loc="upper right")
    cb = fig.colorbar(im, ax=ax_img, pad=0.01)
    cb.set_label("micromol per m per s", color=TEXT_2)
    cb.ax.tick_params(colors=TEXT_2, labelsize=9)
    cb.outline.set_edgecolor(GRID)

    prof = _series(doc["profile"]["flux_mol_s"])
    ok = np.isfinite(prof)
    ax_curve.plot(t_hours[ok], prof[ok], "o", ms=3.5, color=BLUE, label="stacked flux")
    fit = doc["profile"]["fit"]
    if fit:
        label = f"EMG fit, r2 {fit['r2']:.2f}"
        ax_curve.plot(t_hours, fit["curve_mol_s"], "-", lw=2, color=AMBER, label=label)
        ax_curve.axvline(fit["t0"], color=AMBER, lw=0.8, ls=":")
    ax_curve.axhline(0, color=GRID, lw=0.8)
    ax_curve.set_xlabel("travel time from the source, hours")
    ax_curve.set_ylabel("flux through the fan, mol/s")
    ax_curve.set_title("Stacked flux and fit, all days", color=TEXT, fontsize=11)
    _legend(ax_curve)

    drawn = 0
    for sec in doc.get("sectors", []):
        if sec["flux_mol_s"] is None:
            continue
        colour, ls = SECTOR_STYLE[sec["wind_from"]]
        label = f"wind from {sec['wind_from']}, {sec['n_days']} days"
        ax_sec.plot(t_hours, _series(sec["flux_mol_s"]), color=colour, ls=ls, lw=1.8, label=label)
        drawn += 1
    ax_sec.axhline(0, color=GRID, lw=0.8)
    ax_sec.set_xlabel("travel time from the source, hours")
    ax_sec.set_ylabel("flux through the fan, mol/s")
    ax_sec.set_title("Same curve by wind quarter", color=TEXT, fontsize=11)
    if drawn:
        _legend(ax_sec)

    ax_txt.set_facecolor(SURFACE)
    ax_txt.axis("off")
    ax_txt.text(
        0,
        1,
        "\n".join(_summary_lines(doc)),
        va="top",
        ha="left",
        color=TEXT,
        fontsize=10,
        family="monospace",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path
