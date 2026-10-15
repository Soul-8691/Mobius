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

Formats appear in the dropdown when a pool file exists under `data/format_library/pools/` and a matching usage file exists under `data/format_library/usage/`. Usage counts come from the top-level `main` array in each usage JSON; pool cards without an entry count as zero. Limited and Semi-Limited cards (from `data/format_library/ban/{format}_ban.json`) multiply usage by 3 and 1.5 respectively.

Card images (100×100 cropped art from YGOPRODeck) and API responses are cached under `data/cache/ygopro/` so each card is only downloaded once. Details and art load on demand for rows currently visible in the table (plus a small scroll buffer).
