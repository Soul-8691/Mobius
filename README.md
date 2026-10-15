# Mobius

Yu-Gi-Oh! tournament usage stats visualizer.

## Setup

Requires Python 3.9+.

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

### Card usage timeline graph

Plot one card’s usage vs each format’s **top card** (line chart; **Y-axis** = ban-weighted count as % of that format’s highest weighted card — Limited ×3, Semi-Limited ×1.5; point color = ban status, shade = relative weighted usage). Hover a dot in the interactive window for raw/weighted counts vs peak, and per–deck-type usage.

```bash
py -3.9 graph_card_usage.py "Monster Reborn"
py -3.9 graph_card_usage.py "Honest" --start yugi-kaiba --end cat -o honest.png
```

Format stems match pool filenames (e.g. `yugi-kaiba`, `cat`). Only formats where the card has usage &gt; 0 are plotted (including within a `--start` / `--end` range). Tooltips are not available when saving with `-o`.

Formats appear in the dropdown when a pool file exists under `data/format_library/pools/` and a matching usage file exists under `data/format_library/usage/`. Usage counts come from the top-level `main` array in each usage JSON; pool cards without an entry count as zero. Limited and Semi-Limited cards (from `data/format_library/ban/{format}_ban.json`) multiply usage by 3 and 1.5 respectively.

Card images (100×100 cropped art from YGOPRODeck) and API responses are cached under `data/cache/ygopro/` so each card is only downloaded once. Details and art load on demand for rows currently visible in the table (plus a small scroll buffer).
