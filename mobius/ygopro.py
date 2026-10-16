from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageTk

from mobius.format_data import project_root

CARDINFO_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
IMAGE_SIZE = (100, 100)
USER_AGENT = "Mobius/1.0 (local usage visualizer)"


@dataclass
class CardInfo:
    id: int
    name: str
    type: str
    atk: Optional[int]
    def_: Optional[int]
    level: Optional[int]
    race: str
    attribute: Optional[str]
    image_url_cropped: str
    desc: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> CardInfo:
        images = raw.get("card_images") or [{}]
        img = images[0]
        return cls(
            id=int(raw["id"]),
            name=str(raw["name"]),
            type=str(raw.get("type") or ""),
            atk=_optional_int(raw.get("atk")),
            def_=_optional_int(raw.get("def")),
            level=_optional_int(raw.get("level")),
            race=str(raw.get("race") or ""),
            attribute=raw.get("attribute"),
            image_url_cropped=str(
                img.get("image_url_cropped")
                or img.get("image_url_small")
                or img.get("image_url")
                or ""
            ),
            desc=str(raw.get("desc") or ""),
        )


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "?":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YgoProDeckClient:
    def __init__(self) -> None:
        root = project_root() / "data" / "cache" / "ygopro"
        self._cache_root = root
        self._database_path = root / "card_database.json"
        self._legacy_info_path = root / "cards_by_name.json"
        self._image_dir = root / "images"
        self._image_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._info_by_name: dict[str, dict[str, Any]] = {}
        self._database_loaded = False
        self._placeholder: Optional[ImageTk.PhotoImage] = None

    @property
    def database_loaded(self) -> bool:
        return self._database_loaded

    @property
    def database_path(self) -> Path:
        return self._database_path

    def ensure_card_database(self) -> int:
        """Load or download the full YGOPRODeck card database. Returns card count."""
        with self._lock:
            if self._database_path.is_file():
                count = self._load_database_file(self._database_path)
                self._database_loaded = True
                return count
        payload = self._download_full_database()
        with self._lock:
            count = self._index_payload(payload)
            self._database_loaded = True
            return count

    def _download_full_database(self) -> dict[str, Any]:
        self._cache_root.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            CARDINFO_URL,
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8"))
        tmp = self._database_path.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(self._database_path)
        return payload

    def _load_database_file(self, path: Path) -> int:
        payload = json.loads(path.read_text(encoding="utf-8"))
        count = self._index_payload(payload)
        self._merge_legacy_cache()
        return count

    def _index_payload(self, payload: dict[str, Any]) -> int:
        cards = payload.get("data") or []
        self._info_by_name = {}
        for raw in cards:
            name = raw.get("name")
            if name:
                self._info_by_name[str(name)] = raw
        return len(self._info_by_name)

    def _merge_legacy_cache(self) -> None:
        if not self._legacy_info_path.is_file():
            return
        try:
            legacy = json.loads(self._legacy_info_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for name, raw in legacy.items():
            self._info_by_name.setdefault(name, raw)

    def get_cached_info(self, name: str) -> Optional[CardInfo]:
        raw = self._info_by_name.get(name)
        if not raw:
            return None
        return CardInfo.from_api(raw)

    def placeholder_photo(self, master) -> ImageTk.PhotoImage:
        if self._placeholder is None:
            img = Image.new("RGB", IMAGE_SIZE, color=(60, 60, 60))
            self._placeholder = ImageTk.PhotoImage(img, master=master)
        return self._placeholder

    def image_cache_path(self, card_id: int) -> Path:
        return self._image_dir / f"{card_id}_cropped.png"

    def get_photo(
        self,
        master,
        card_id: int,
        image_url: str,
        *,
        download: bool = True,
    ) -> Optional[ImageTk.PhotoImage]:
        path = self.image_cache_path(card_id)
        try:
            if path.is_file():
                img = Image.open(path).convert("RGB")
            else:
                if not download or not image_url:
                    return None
                data = self._http_get(image_url)
                img = Image.open(BytesIO(data)).convert("RGB")
                img = img.resize(IMAGE_SIZE, Image.LANCZOS)
                path.parent.mkdir(parents=True, exist_ok=True)
                img.save(path, format="PNG")
            if img.size != IMAGE_SIZE:
                img = img.resize(IMAGE_SIZE, Image.LANCZOS)
            return ImageTk.PhotoImage(img, master=master)
        except (OSError, urllib.error.URLError, ValueError):
            return None

    def _http_get(self, url: str) -> bytes:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
