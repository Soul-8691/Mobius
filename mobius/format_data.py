from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

BanRestriction = Literal["", "limited", "semi-limited"]

DEFAULT_FORMAT = "yugi-kaiba"

BAN_MULTIPLIER = {
    "": 1.0,
    "limited": 3.0,
    "semi-limited": 1.5,
}


@dataclass(frozen=True)
class CardUsageRow:
    name: str
    raw_usage: int
    ban_status: BanRestriction
    weighted_usage: float


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def format_library_dir() -> Path:
    return project_root() / "data" / "format_library"


def catalog_name_to_stem(name: str) -> str:
    return name.casefold()


def load_format_dates_by_stem() -> dict[str, Optional[str]]:
    path = format_library_dir() / "formats.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    dates: dict[str, Optional[str]] = {}
    for entry in data:
        name = entry.get("name")
        if not name:
            continue
        dates[catalog_name_to_stem(str(name))] = entry.get("date")
    return dates


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


def load_usage_counts(format_name: str) -> dict[str, int]:
    path = format_library_dir() / "usage" / f"{format_name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    main = data.get("main") or []
    counts: dict[str, int] = {}
    for entry in main:
        name = entry.get("name")
        if not name:
            continue
        counts[name] = int(entry.get("count") or 0)
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


def build_format_rows(format_name: str) -> list[CardUsageRow]:
    pool = load_pool_card_names(format_name)
    usage = load_usage_counts(format_name)
    bans = load_ban_restrictions(format_name)
    rows: list[CardUsageRow] = []
    for name in pool:
        raw = usage.get(name, 0)
        ban_status: BanRestriction = bans.get(name, "")
        mult = BAN_MULTIPLIER[ban_status]
        rows.append(
            CardUsageRow(
                name=name,
                raw_usage=raw,
                ban_status=ban_status,
                weighted_usage=raw * mult,
            )
        )
    return rows
