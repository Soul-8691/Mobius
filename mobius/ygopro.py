from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image, ImageTk

from mobius.format_data import project_root

CARDINFO_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
BATCH_SIZE = 15
REQUEST_INTERVAL = 0.12
IMAGE_SIZE = (100, 100)


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
        )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "?":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YgoProDeckClient:
    def __init__(self) -> None:
        root = project_root() / "data" / "cache" / "ygopro"
        self._info_path = root / "cards_by_name.json"
        self._image_dir = root / "images"
        self._image_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._info_by_name: dict[str, dict[str, Any]] = self._load_info_cache()
        self._placeholder: Optional[ImageTk.PhotoImage] = None

    def _load_info_cache(self) -> dict[str, dict[str, Any]]:
        if not self._info_path.is_file():
            return {}
        try:
            return json.loads(self._info_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_info_cache(self) -> None:
        self._info_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._info_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._info_by_name, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._info_path)

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
            headers={"User-Agent": "Mobius/1.0 (local usage visualizer)"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()

    def _fetch_cardinfo_batch(self, names: list[str]) -> list[dict[str, Any]]:
        if not names:
            return []
        query = urllib.parse.urlencode({"name": "|".join(names)})
        url = f"{CARDINFO_URL}?{query}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mobius/1.0 (local usage visualizer)"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return list(payload.get("data") or [])

    def ensure_cards(
        self,
        names: list[str],
        on_batch: Optional[Callable[[list], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        missing = [n for n in names if n not in self._info_by_name]
        if not missing:
            return
        for i in range(0, len(missing), BATCH_SIZE):
            if cancel_event and cancel_event.is_set():
                return
            batch = missing[i : i + BATCH_SIZE]
            try:
                cards = self._fetch_cardinfo_batch(batch)
            except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
                time.sleep(1.0)
                continue
            with self._lock:
                for raw in cards:
                    self._info_by_name[str(raw["name"])] = raw
                self._save_info_cache()
            if on_batch:
                on_batch([str(c["name"]) for c in cards])
            time.sleep(REQUEST_INTERVAL)
