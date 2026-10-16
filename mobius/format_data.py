from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

BanRestriction = Literal["", "limited", "semi-limited"]
DeckZone = Literal["main+side", "main", "extra", "side"]

DEFAULT_DECK_ZONE: DeckZone = "main+side"

DECK_ZONE_LABELS: dict[DeckZone, str] = {
    "main+side": "Main + Side",
    "main": "Main",
    "extra": "Extra",
    "side": "Side",
}

DEFAULT_FORMAT = "yugi-kaiba"
ALL_DECKS_LABEL = "All decks"


def format_all_decks_label(deck_count: int) -> str:
    return f"All decks ({deck_count})"

BAN_MULTIPLIER = {
    "": 1.0,
    "limited": 3.0,
    "semi-limited": 1.5,
}


@dataclass(frozen=True)
class CardUsageRow:
    name: str
    raw_usage: int
    raw_usage_pct: float
    ban_status: BanRestriction
    weighted_usage: float
    weighted_usage_pct: float


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def format_library_dir() -> Path:
    return project_root() / "data" / "format_library"


def catalog_name_to_stem(name: str) -> str:
    return name.casefold()


def _load_formats_catalog() -> list[dict]:
    path = format_library_dir() / "formats.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_format_dates_by_stem() -> dict[str, Optional[str]]:
    dates: dict[str, Optional[str]] = {}
    for entry in _load_formats_catalog():
        name = entry.get("name")
        if not name:
            continue
        dates[catalog_name_to_stem(str(name))] = entry.get("date")
    return dates


def load_format_display_names() -> dict[str, str]:
    labels: dict[str, str] = {}
    for entry in _load_formats_catalog():
        name = entry.get("name")
        if not name:
            continue
        labels[catalog_name_to_stem(str(name))] = str(name)
    return labels


def format_label(stem: str) -> str:
    return load_format_display_names().get(stem, stem.replace("-", " ").title())


def slice_formats_by_range(
    formats: list[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> list[str]:
    if not start and not end:
        return list(formats)
    if start and start not in formats:
        raise ValueError(f"Unknown start format: {start}")
    if end and end not in formats:
        raise ValueError(f"Unknown end format: {end}")
    i0 = formats.index(start) if start else 0
    i1 = formats.index(end) if end else len(formats) - 1
    if i0 > i1:
        i0, i1 = i1, i0
    return formats[i0 : i1 + 1]


@dataclass(frozen=True)
class DeckTypeCardUsage:
    deck_type: str
    decks_processed: int
    card_usage: int


@dataclass(frozen=True)
class CardFormatUsagePoint:
    format_stem: str
    format_label: str
    format_date: Optional[str]
    raw_usage: int
    raw_usage_pct: float
    weighted_usage: float
    weighted_usage_pct: float
    pct_denominator: int
    ban_status: BanRestriction
    deck_types: tuple[DeckTypeCardUsage, ...]


def deck_type_usage_for_card(
    card_name: str, format_stem: str
) -> tuple[DeckTypeCardUsage, ...]:
    data = load_usage_file(format_stem)
    items: list[DeckTypeCardUsage] = []
    for deck_type, info in (data.get("deck_types") or {}).items():
        decks = int((info or {}).get("count") or 0)
        card_usage = 0
        for entry in (info or {}).get("main") or []:
            if entry.get("name") == card_name:
                card_usage = int(entry.get("count") or 0)
                break
        if card_usage > 0:
            items.append(
                DeckTypeCardUsage(
                    deck_type=str(deck_type),
                    decks_processed=decks,
                    card_usage=card_usage,
                )
            )
    items.sort(key=lambda row: (-row.card_usage, row.deck_type.casefold()))
    return tuple(items)


def card_usage_in_format(card_name: str, format_stem: str) -> Optional[CardFormatUsagePoint]:
    pool = set(load_pool_card_names(format_stem))
    if card_name not in pool:
        return None
    counts = load_usage_counts(format_stem)
    raw = int(counts.get(card_name, 0))
    ban_status: BanRestriction = load_ban_restrictions(format_stem).get(card_name, "")
    mult = BAN_MULTIPLIER[ban_status]
    weighted = raw * mult
    denom = usage_pct_denominator(format_stem)
    raw_pct = (raw / denom * 100.0) if denom else 0.0
    weighted_pct = (weighted / denom * 100.0) if denom else 0.0
    dates = load_format_dates_by_stem()
    return CardFormatUsagePoint(
        format_stem=format_stem,
        format_label=format_label(format_stem),
        format_date=dates.get(format_stem),
        raw_usage=raw,
        raw_usage_pct=raw_pct,
        weighted_usage=weighted,
        weighted_usage_pct=weighted_pct,
        pct_denominator=denom,
        ban_status=ban_status,
        deck_types=deck_type_usage_for_card(card_name, format_stem),
    )


def collect_card_usage_timeline(
    card_name: str,
    *,
    start_format: Optional[str] = None,
    end_format: Optional[str] = None,
    only_used: bool = True,
) -> list[CardFormatUsagePoint]:
    """Usage points in chronological format order."""
    all_formats = list_formats_with_usage()
    if start_format or end_format:
        candidates = slice_formats_by_range(all_formats, start_format, end_format)
    else:
        candidates = all_formats

    points: list[CardFormatUsagePoint] = []
    for stem in candidates:
        point = card_usage_in_format(card_name, stem)
        if point is None:
            continue
        if only_used and point.raw_usage <= 0:
            continue
        points.append(point)
    return points


def list_formats_with_usage() -> list[str]:
    """Pool names that have both a pool file and a usage JSON file."""
    base = format_library_dir()
    pools = base / "pools"
    usage = base / "usage"
    names: list[str] = []
    for usage_file in usage.glob("*.json"):
        stem = usage_file.stem
        if (pools / f"{stem}.txt").is_file():
            names.append(stem)
    dates = load_format_dates_by_stem()

    def sort_key(stem: str) -> tuple[int, str, str]:
        if stem not in dates:
            return (2, "", stem)
        date = dates[stem]
        if not date:
            return (1, "", stem)
        return (0, str(date), stem)

    return sorted(names, key=sort_key)


def load_pool_card_names(format_name: str) -> list[str]:
    path = format_library_dir() / "pools" / f"{format_name}.txt"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def load_usage_file(format_name: str) -> dict:
    path = format_library_dir() / "usage" / f"{format_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def usage_pct_denominator(format_name: str, deck_type: Optional[str] = None) -> int:
    """Max copy slots for pct: tournament deck count × 3."""
    return load_decks_processed(format_name, deck_type) * 3


def load_decks_processed(format_name: str, deck_type: Optional[str] = None) -> int:
    data = load_usage_file(format_name)
    if deck_type:
        info = (data.get("deck_types") or {}).get(deck_type) or {}
        return int(info.get("count") or 0)
    return int(data.get("decks_processed") or 0)


def list_deck_types(format_name: str) -> list[tuple[str, int]]:
    """Deck type name and number of decks processed for that type."""
    data = load_usage_file(format_name)
    deck_types = data.get("deck_types") or {}
    items: list[tuple[str, int]] = []
    for name, info in deck_types.items():
        items.append((str(name), int((info or {}).get("count") or 0)))
    items.sort(key=lambda pair: (-pair[1], pair[0].casefold()))
    return items


def _usage_block(data: dict, deck_type: Optional[str]) -> dict:
    if deck_type:
        return (data.get("deck_types") or {}).get(deck_type) or {}
    return data


def _usage_section_lists(block: dict, deck_zone: DeckZone) -> list[list]:
    if deck_zone == "main":
        return [block.get("main") or []]
    if deck_zone == "side":
        return [block.get("side") or []]
    if deck_zone == "extra":
        return [block.get("extra") or []]
    return [block.get("main") or [], block.get("side") or []]


@dataclass(frozen=True)
class CardCopyBreakdown:
    decks_total: int
    copy_0: int
    copy_1: int
    copy_2: int
    copy_3: int

    def pct(self, count: int) -> float:
        if not self.decks_total:
            return 0.0
        return count / self.decks_total * 100.0


def _merge_entry_copies(tallies: dict[int, int], entry: dict) -> None:
    for key, value in (entry.get("copies") or {}).items():
        copies = int(key)
        if 0 <= copies <= 3:
            tallies[copies] = tallies.get(copies, 0) + int(value or 0)


def card_copy_breakdown(
    format_name: str,
    card_name: str,
    *,
    deck_type: Optional[str] = None,
    deck_zone: DeckZone = DEFAULT_DECK_ZONE,
) -> CardCopyBreakdown:
    """How many decks ran 0–3 copies of the card in the selected zone view."""
    decks_total = load_decks_processed(format_name, deck_type)
    data = load_usage_file(format_name)
    block = _usage_block(data, deck_type)
    tallies = {0: 0, 1: 0, 2: 0, 3: 0}
    found = False
    for section in _usage_section_lists(block, deck_zone):
        for entry in section:
            if entry.get("name") != card_name:
                continue
            found = True
            _merge_entry_copies(tallies, entry)
    used = tallies[1] + tallies[2] + tallies[3]
    if not found:
        tallies[0] = decks_total
    else:
        tallies[0] = max(0, decks_total - used)
    return CardCopyBreakdown(
        decks_total=decks_total,
        copy_0=tallies[0],
        copy_1=tallies[1],
        copy_2=tallies[2],
        copy_3=tallies[3],
    )


def format_copy_breakdown_block(
    breakdown: CardCopyBreakdown, *, heading: str
) -> list[str]:
    lines = [heading]
    for copies in (0, 1, 2, 3):
        count = (
            breakdown.copy_0
            if copies == 0
            else breakdown.copy_1
            if copies == 1
            else breakdown.copy_2
            if copies == 2
            else breakdown.copy_3
        )
        lines.append(f"  {copies} copies: {count} ({breakdown.pct(count):.1f}%)")
    return lines


def card_copy_breakdown_all_zones_text(
    format_name: str,
    card_name: str,
    *,
    deck_type: Optional[str] = None,
) -> str:
    blocks: list[str] = []
    for zone in ("main+side", "main", "extra", "side"):
        bd = card_copy_breakdown(
            format_name, card_name, deck_type=deck_type, deck_zone=zone
        )
        label = DECK_ZONE_LABELS[zone]
        blocks.extend(
            format_copy_breakdown_block(
                bd, heading=f"{label} ({bd.decks_total} decks):"
            )
        )
        blocks.append("")
    return "\n".join(blocks).rstrip()


def format_zone_usage_lines(
    format_name: str,
    card_name: str,
    *,
    deck_type: Optional[str] = None,
) -> list[str]:
    """Raw copy totals per deck zone (same % denominator as the main table)."""
    denom = usage_pct_denominator(format_name, deck_type)
    lines = ["Usage by deck zone (raw / decks×3):"]
    for zone in ("main+side", "main", "extra", "side"):
        raw = load_usage_counts(format_name, deck_type, deck_zone=zone).get(
            card_name, 0
        )
        pct = (raw / denom * 100.0) if denom else 0.0
        lines.append(
            f"  {DECK_ZONE_LABELS[zone]}: {raw:,} ({pct:.2f}%)"
        )
    return lines


def load_usage_counts(
    format_name: str,
    deck_type: Optional[str] = None,
    deck_zone: DeckZone = DEFAULT_DECK_ZONE,
) -> dict[str, int]:
    data = load_usage_file(format_name)
    block = _usage_block(data, deck_type)
    counts: dict[str, int] = {}
    for section in _usage_section_lists(block, deck_zone):
        for entry in section:
            name = entry.get("name")
            if not name:
                continue
            counts[name] = counts.get(name, 0) + int(entry.get("count") or 0)
    return counts


def load_ban_restrictions(format_name: str) -> dict[str, BanRestriction]:
    path = format_library_dir() / "ban" / f"{format_name}_ban.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, BanRestriction] = {}
    for entry in data.get("limited") or []:
        name = entry.get("cardName") or (entry.get("card") or {}).get("name")
        if name:
            result[name] = "limited"
    for entry in data.get("semiLimited") or []:
        name = entry.get("cardName") or (entry.get("card") or {}).get("name")
        if name:
            result[name] = "semi-limited"
    return result


def build_format_rows(
    format_name: str,
    deck_type: Optional[str] = None,
    deck_zone: DeckZone = DEFAULT_DECK_ZONE,
) -> list[CardUsageRow]:
    pool = load_pool_card_names(format_name)
    usage = load_usage_counts(format_name, deck_type, deck_zone)
    bans = load_ban_restrictions(format_name)
    denom = usage_pct_denominator(format_name, deck_type)
    rows: list[CardUsageRow] = []
    for name in pool:
        raw = usage.get(name, 0)
        ban_status: BanRestriction = bans.get(name, "")
        mult = BAN_MULTIPLIER[ban_status]
        weighted = raw * mult
        raw_pct = (raw / denom * 100.0) if denom else 0.0
        weighted_pct = (weighted / denom * 100.0) if denom else 0.0
        rows.append(
            CardUsageRow(
                name=name,
                raw_usage=raw,
                raw_usage_pct=raw_pct,
                ban_status=ban_status,
                weighted_usage=weighted,
                weighted_usage_pct=weighted_pct,
            )
        )
    return rows
