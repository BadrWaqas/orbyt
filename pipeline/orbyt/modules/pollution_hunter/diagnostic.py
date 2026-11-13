"""The diagnostic figure for one facility: stack image, stacked curve with its fit, and a summary.

Colours follow the web app's dark tokens. The stack image is diverging (blue below the
background, amber above, grey at zero) because the background is subtracted. Series are told
apart by shape and label as well as colour.
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
FIT = "#f2f4f7"
DIVERGING = LinearSegmentedColormap.from_list("orbyt_div", ["#4a8fd1", "#1a2430", "#ffb02e"])


def _style(ax: Any) -> None:
    ax.set_facecolor(RAISED)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=9)
    ax.xaxis.label.set_color(TEXT_2)
    ax.yaxis.label.set_color(TEXT_2)
    ax.title.set_color(TEXT)


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
    fig = plt.figure(figsize=(12, 7.2), facecolor=SURFACE)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.35, 1], hspace=0.38, wspace=0.22)
    ax_img, ax_curve, ax_txt = (
        fig.add_subplot(gs[0, :]),
        fig.add_subplot(gs[1, 0]),
        fig.add_subplot(gs[1, 1]),
    )
    for ax in (ax_img, ax_curve):
        _style(ax)

    vmax = vmax or 1.0
    im = ax_img.pcolormesh(
        t_hours, yr_km, mean, cmap=DIVERGING, vmin=-vmax, vmax=vmax, shading="auto"
    )
    ax_img.plot(t_hours, half_width_km, color=TEXT_2, lw=1, ls="--", label="integration fan")
    ax_img.plot(t_hours, -half_width_km, color=TEXT_2, lw=1, ls="--")
    ax_img.axvline(0, color=TEXT, lw=0.8, alpha=0.6)
    ax_img.set_xlabel("travel time from the source, hours (wind speed times time gives distance)")
    ax_img.set_ylabel("crosswind distance, km")
    ax_img.set_title(
        f"Stack of {flux.shape[0]} days, flux density with each day's background removed"
    )
    ax_img.legend(
        loc="upper right", facecolor=RAISED, edgecolor=GRID, labelcolor=TEXT_2, fontsize=9
    )
    cb = fig.colorbar(im, ax=ax_img, pad=0.01)
    cb.set_label("micromol per m per s", color=TEXT_2)
    cb.ax.tick_params(colors=TEXT_2, labelsize=9)
    cb.outline.set_edgecolor(GRID)

    prof = np.array([np.nan if v is None else v for v in doc["profile"]["flux_mol_s"]], dtype=float)
    ok = np.isfinite(prof)
    ax_curve.plot(t_hours[ok], prof[ok], "o", ms=4, color=BLUE, label="stacked flux")
    fit = doc["profile"]["fit"]
    if fit:
        ax_curve.plot(
            t_hours,
            fit["curve_mol_s"],
            "-",
            lw=2,
            color=AMBER,
            label=f"EMG fit, r2 {fit['r2']:.2f}",
        )
        ax_curve.axvline(fit["t0"], color=AMBER, lw=0.8, ls=":")
    ax_curve.axhline(0, color=GRID, lw=0.8)
    ax_curve.set_xlabel("travel time from the source, hours")
    ax_curve.set_ylabel("flux through the fan, mol/s")
    ax_curve.set_title("Stacked flux and fit")
    ax_curve.legend(facecolor=RAISED, edgecolor=GRID, labelcolor=TEXT_2, fontsize=9)

    ax_txt.set_facecolor(SURFACE)
    ax_txt.axis("off")
    obs, rep = doc["observed"], doc["reported_t_yr"]
    lines = [*textwrap.wrap(doc["name"], 48), ""]
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
    lines.append("Gates failed: " + (", ".join(doc["gates_failed"]) or "none"))
    ax_txt.text(
        0, 1, "\n".join(lines), va="top", ha="left", color=TEXT, fontsize=11, family="monospace"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path
