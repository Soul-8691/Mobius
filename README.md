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

Plot one card’s usage across formats (line chart; **Y-axis** = ban-weighted count as % of that format’s **decks processed × 3**; point color = ban status, shade = relative weighted usage). Hover a dot for raw/weighted counts vs that cap and per–deck-type usage.

```bash
py -3.9 graph_card_usage.py "Monster Reborn"
py -3.9 graph_card_usage.py "Honest" --start yugi-kaiba --end cat -o honest.png
```

Format stems match pool filenames (e.g. `yugi-kaiba`, `cat`). Only formats where the card has usage &gt; 0 are plotted (including within a `--start` / `--end` range). Tooltips are not available when saving with `-o`.

Formats appear in the dropdown when a pool file exists under `data/format_library/pools/` and a matching usage file exists under `data/format_library/usage/`. Usage counts come from the top-level `main` array in each usage JSON; pool cards without an entry count as zero. Limited and Semi-Limited cards (from `data/format_library/ban/{format}_ban.json`) multiply usage by 3 and 1.5 respectively.

On first run, the app downloads the full [YGOPRODeck v7 card database](https://db.ygoprodeck.com/api/v7/cardinfo.php) to `data/cache/ygopro/card_database.json` and loads stats from that file (no per-card API calls in the table). To refresh manually:

```bash
py -3.9 download_ygopro_database.py
```

Card images (100×100 cropped art) are still cached under `data/cache/ygopro/images/` and download on demand for visible rows only.
