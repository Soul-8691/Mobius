#!/usr/bin/env python3
"""Line graph of a card's usage share across Mobius formats."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from mobius.format_data import (
    BAN_MULTIPLIER,
    BanRestriction,
    CardFormatUsagePoint,
    collect_card_usage_timeline,
)

BAN_BASE_RGB = {
    "": (0.18, 0.62, 0.28),
    "semi-limited": (0.96, 0.82, 0.12),
    "limited": (0.94, 0.48, 0.08),
}

BAN_LEGEND = {
    "": "Unlimited",
    "semi-limited": "Semi-Limited",
    "limited": "Limited",
}


def _usage_intensity(values: Sequence[float], value: float) -> float:
    if not values:
        return 1.0
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return 1.0
    return (value - lo) / (hi - lo)


def _shade_color(ban_status: BanRestriction, intensity: float) -> Tuple[float, float, float]:
    base = BAN_BASE_RGB[ban_status]
    t = 0.25 + 0.75 * intensity
    return tuple(channel * t + (1.0 - t) for channel in base)


def _point_colors(points: List[CardFormatUsagePoint]) -> List[Tuple[float, float, float]]:
    pcts = [p.weighted_usage_pct for p in points]
    return [
        _shade_color(p.ban_status, _usage_intensity(pcts, p.weighted_usage_pct))
        for p in points
    ]


def _format_tooltip(point: CardFormatUsagePoint) -> str:
    mult = BAN_MULTIPLIER[point.ban_status]
    ban = BAN_LEGEND[point.ban_status]
    lines = [
        point.format_label,
        (
            f"Raw: {point.raw_usage:,} / {point.format_peak_raw:,} peak "
            f"({point.raw_usage_pct:.2f}%)"
        ),
        (
            f"Weighted (×{mult:g}): {point.weighted_usage:,.0f} / "
            f"{point.format_peak_weighted:,.0f} peak ({point.weighted_usage_pct:.2f}%)"
        ),
        f"Ban: {ban}",
    ]
    if point.deck_types:
        lines.append("")
        lines.append("Deck types:")
        for row in point.deck_types:
            lines.append(
                f"  {row.deck_type} ({row.decks_processed} decks): {row.card_usage:,}"
            )
    else:
        lines.append("")
        lines.append("Deck types: none")
    return "\n".join(lines)


def plot_card_usage_timeline(
    card_name: str,
    points: List[CardFormatUsagePoint],
    *,
    output: Optional[str] = None,
) -> None:
    if not points:
        print("No usage data to plot for this card and format selection.", file=sys.stderr)
        sys.exit(1)

    labels = [p.format_label for p in points]
    y = [p.weighted_usage_pct for p in points]
    colors = _point_colors(points)
    x = list(range(len(points)))

    fig, ax = plt.subplots(figsize=(max(10, len(points) * 0.45), 6))
    ax.plot(x, y, color="#888888", linewidth=1.5, alpha=0.55, zorder=1)
    scatter = ax.scatter(
        x, y, c=colors, s=90, edgecolors="#333333", linewidths=0.6, zorder=2
    )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Weighted usage (% of format peak card)")
    ax.set_xlabel("Format (chronological)")
    ax.set_title(f"{card_name} — usage across formats")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_ylim(bottom=0)

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=BAN_BASE_RGB[status],
            markeredgecolor="#333333",
            markersize=9,
            label=BAN_LEGEND[status],
        )
        for status in ("", "semi-limited", "limited")
    ]
    ax.legend(
        handles=legend_handles,
        title="Ban status",
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0,
    )
    fig.tight_layout(rect=(0, 0, 0.84, 1))

    if not output:
        annot = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(10, 0),
            textcoords="offset points",
            bbox=dict(boxstyle="round", facecolor="#ffffe1", edgecolor="#666666"),
            fontsize=8,
            family="Segoe UI",
            verticalalignment="top",
            horizontalalignment="left",
        )
        annot.set_visible(False)

        def on_motion(event) -> None:
            if event.inaxes is not ax:
                if annot.get_visible():
                    annot.set_visible(False)
                    fig.canvas.draw_idle()
                return
            contained, info = scatter.contains(event)
            if not contained:
                if annot.get_visible():
                    annot.set_visible(False)
                    fig.canvas.draw_idle()
                return
            index = int(info["ind"][0])
            point = points[index]
            annot.xy = (x[index], y[index])
            annot.set_text(_format_tooltip(point))
            annot.set_visible(True)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect("motion_notify_event", on_motion)

    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Wrote {output}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Graph how often a card appears in tournament decks across formats, "
            "as ban-weighted percentage of each format's most-used card."
        )
    )
    parser.add_argument("card", help="Exact card name")
    parser.add_argument(
        "--start",
        dest="start_format",
        metavar="FORMAT",
        help="First format stem (e.g. yugi-kaiba).",
    )
    parser.add_argument(
        "--end",
        dest="end_format",
        metavar="FORMAT",
        help="Last format stem (e.g. cat).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Save PNG to this path instead of opening an interactive window",
    )
    args = parser.parse_args()

    try:
        points = collect_card_usage_timeline(
            args.card,
            start_format=args.start_format,
            end_format=args.end_format,
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)

    plot_card_usage_timeline(args.card, points, output=args.output)


if __name__ == "__main__":
    main()
