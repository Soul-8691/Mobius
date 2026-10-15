from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

from mobius.format_data import (
    ALL_DECKS_LABEL,
    BAN_MULTIPLIER,
    DEFAULT_FORMAT,
    CardUsageRow,
    build_format_rows,
    list_deck_types,
    list_formats_with_usage,
)
from mobius.ygopro import CardInfo, YgoProDeckClient

ROW_HEIGHT = 104
VISIBLE_BUFFER = 4

COLUMNS = (
    "name",
    "weighted_usage",
    "raw_usage",
    "ban",
    "type",
    "attribute",
    "race",
    "level",
    "atk",
    "def",
)

COLUMN_LABELS = {
    "name": "Name",
    "weighted_usage": "Weighted",
    "raw_usage": "Usage",
    "ban": "Ban",
    "type": "Type",
    "attribute": "Attr",
    "race": "Race",
    "level": "Level",
    "atk": "ATK",
    "def": "DEF",
}

SORT_KEYS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "name": lambda r: r["name"].lower(),
    "weighted_usage": lambda r: (r["weighted_usage"], r["name"].lower()),
    "raw_usage": lambda r: (r["raw_usage"], r["name"].lower()),
    "ban": lambda r: (r["ban_sort"], r["name"].lower()),
    "type": lambda r: (r["type_key"], r["name"].lower()),
    "attribute": lambda r: (r["attribute_key"], r["name"].lower()),
    "race": lambda r: (r["race_key"], r["name"].lower()),
    "level": lambda r: (r["level_key"], r["name"].lower()),
    "atk": lambda r: (r["atk_key"], r["name"].lower()),
    "def": lambda r: (r["def_key"], r["name"].lower()),
}


def _stat_sort_key(value: Optional[int]) -> Tuple[int, int]:
    if value is None:
        return (1, 0)
    return (0, value)


def _ban_label(status: str) -> str:
    if status == "limited":
        return "Limited"
    if status == "semi-limited":
        return "Semi-Limited"
    return ""


def _ban_sort_key(status: str) -> int:
    order = {"limited": 0, "semi-limited": 1, "": 2}
    return order.get(status, 2)


class UsageStatsApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Mobius — Format Card Usage")
        self.geometry("1200x720")
        self.minsize(900, 500)

        self._client = YgoProDeckClient()
        self._formats = list_formats_with_usage()
        self._rows: List[CardUsageRow] = []
        self._usage_by_name: Dict[str, CardUsageRow] = {}
        self._display_rows: List[dict[str, Any]] = []
        self._photo_refs: dict[str, tk.PhotoImage] = {}
        self._sort_column = "weighted_usage"
        self._sort_reverse = True
        self._fetch_cancel = threading.Event()
        self._fetch_thread: Optional[threading.Thread] = None
        self._fetch_queue: set[str] = set()
        self._fetch_queue_lock = threading.Lock()
        self._load_gen = 0
        self._load_after_id: Optional[str] = None
        self._query_var = tk.StringVar()
        self._query_var.trace_add("write", lambda *_: self._on_query_change())
        self._deck_type_var = tk.StringVar(value=ALL_DECKS_LABEL)
        self._deck_type_labels: List[str] = [ALL_DECKS_LABEL]
        self._deck_type_key_by_label: Dict[str, Optional[str]] = {
            ALL_DECKS_LABEL: None
        }
        self._tooltip_win: Optional[tk.Toplevel] = None
        self._tooltip_row: Optional[str] = None
        self._tooltip_after_id: Optional[str] = None

        self._build_ui()
        if self._formats:
            initial = (
                DEFAULT_FORMAT
                if DEFAULT_FORMAT in self._formats
                else self._formats[0]
            )
            self._format_var.set(initial)
            self._load_format(initial)
        else:
            messagebox.showwarning(
                "No formats",
                "No formats found with both a pool file and usage data.",
            )

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Format:").pack(side=tk.LEFT)
        self._format_var = tk.StringVar()
        combo = ttk.Combobox(
            top,
            textvariable=self._format_var,
            values=self._formats,
            state="readonly",
            width=28,
        )
        combo.pack(side=tk.LEFT, padx=(4, 16))
        combo.bind("<<ComboboxSelected>>", self._on_format_change)

        ttk.Label(top, text="Deck type:").pack(side=tk.LEFT)
        self._deck_type_combo = ttk.Combobox(
            top,
            textvariable=self._deck_type_var,
            values=self._deck_type_labels,
            state="readonly",
            width=26,
        )
        self._deck_type_combo.pack(side=tk.LEFT, padx=(4, 16))
        self._deck_type_combo.bind("<<ComboboxSelected>>", self._on_deck_type_change)

        ttk.Label(top, text="Search name:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self._query_var, width=32).pack(
            side=tk.LEFT, padx=(4, 16)
        )

        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(top, textvariable=self._status_var).pack(side=tk.LEFT)

        style = ttk.Style(self)
        style.configure("Card.Treeview", rowheight=ROW_HEIGHT, indent=0)
        style.configure("Card.Treeview.Heading", font=("Segoe UI", 9, "bold"))
        # Drop the tree expander gutter so art sits flush at the row start.
        style.layout(
            "Card.Treeview.Item",
            [
                (
                    "Treeitem.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            ("Treeitem.image", {"side": "left", "sticky": ""}),
                            ("Treeitem.text", {"side": "left", "sticky": "w"}),
                        ],
                    },
                )
            ],
        )

        tree_frame = ttk.Frame(self, padding=(8, 0, 8, 8))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self._tree = ttk.Treeview(
            tree_frame,
            columns=COLUMNS,
            show="tree headings",
            style="Card.Treeview",
            selectmode="browse",
        )
        self._tree.heading("#0", text="Art")
        self._tree.column("#0", width=100, minwidth=100, stretch=False, anchor=tk.CENTER)

        for col in COLUMNS:
            self._tree.heading(
                col,
                text=COLUMN_LABELS[col],
                command=lambda c=col: self._set_sort(c),
            )
            width = 90
            if col == "name":
                width = 220
            elif col == "type":
                width = 140
            self._tree.column(col, width=width, anchor=tk.W)

        self._vsb = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self._tree.yview
        )
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(
            yscrollcommand=self._on_yscroll,
            xscrollcommand=hsb.set,
        )

        self._tree.grid(row=0, column=0, sticky="nsew")
        self._vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self._tree.bind("<Configure>", lambda _e: self._schedule_visible_load())
        self._tree.bind("<Motion>", self._on_tree_motion)
        self._tree.bind("<Leave>", lambda _e: self._hide_desc_tooltip())

        self._placeholder = self._client.placeholder_photo(self)

    def _on_yscroll(self, first: str, last: str) -> None:
        self._vsb.set(first, last)
        self._hide_desc_tooltip()
        self._schedule_visible_load()

    def _hide_desc_tooltip(self) -> None:
        if self._tooltip_after_id is not None:
            self.after_cancel(self._tooltip_after_id)
            self._tooltip_after_id = None
        if self._tooltip_win is not None:
            self._tooltip_win.destroy()
            self._tooltip_win = None
        self._tooltip_row = None

    def _on_tree_motion(self, event: tk.Event) -> None:
        row_id = self._tree.identify_row(event.y)
        if not row_id or row_id == "none":
            self._hide_desc_tooltip()
            return
        if row_id == self._tooltip_row and self._tooltip_win is not None:
            return
        self._hide_desc_tooltip()
        self._tooltip_row = row_id
        x, y = event.x_root, event.y_root

        def show() -> None:
            self._tooltip_after_id = None
            if self._tooltip_row != row_id:
                return
            info = self._client.get_cached_info(row_id)
            if not info or not info.desc.strip():
                return
            win = tk.Toplevel(self)
            win.wm_overrideredirect(True)
            win.attributes("-topmost", True)
            frame = tk.Frame(
                win,
                background="#ffffe1",
                highlightbackground="#666666",
                highlightthickness=1,
                padx=10,
                pady=8,
            )
            frame.pack()
            tk.Label(
                frame,
                text=info.name,
                font=("Segoe UI", 9, "bold"),
                background="#ffffe1",
                anchor=tk.W,
                justify=tk.LEFT,
            ).pack(anchor=tk.W)
            tk.Label(
                frame,
                text=info.desc,
                font=("Segoe UI", 9),
                background="#ffffe1",
                wraplength=440,
                anchor=tk.W,
                justify=tk.LEFT,
            ).pack(anchor=tk.W)
            win.update_idletasks()
            px = x + 16
            py = y + 16
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            ww = win.winfo_width()
            wh = win.winfo_height()
            if px + ww > sw:
                px = max(0, sw - ww - 8)
            if py + wh > sh:
                py = max(0, y - wh - 8)
            win.geometry(f"+{px}+{py}")
            self._tooltip_win = win

        self._tooltip_after_id = self.after(350, show)

    def _on_format_change(self, _event: object = None) -> None:
        name = self._format_var.get()
        if name:
            self._load_format(name)

    def _on_deck_type_change(self, _event: object = None) -> None:
        self._reload_usage_rows()

    def _selected_deck_type(self) -> Optional[str]:
        label = self._deck_type_var.get()
        return self._deck_type_key_by_label.get(label)

    def _refresh_deck_type_choices(self, format_name: str) -> None:
        labels = [ALL_DECKS_LABEL]
        key_by_label: Dict[str, Optional[str]] = {ALL_DECKS_LABEL: None}
        for name, count in list_deck_types(format_name):
            label = f"{name} ({count})"
            labels.append(label)
            key_by_label[label] = name
        self._deck_type_labels = labels
        self._deck_type_key_by_label = key_by_label
        self._deck_type_combo.configure(values=labels)
        self._deck_type_var.set(ALL_DECKS_LABEL)

    def _on_query_change(self) -> None:
        self._refresh_table()
        self._schedule_visible_load()

    def _load_format(self, format_name: str) -> None:
        self._load_gen += 1
        self._fetch_cancel.set()
        with self._fetch_queue_lock:
            self._fetch_queue.clear()
        if self._fetch_thread and self._fetch_thread.is_alive():
            self._fetch_thread.join(timeout=0.5)
        self._fetch_cancel = threading.Event()

        self._status_var.set(f"Loading {format_name}…")
        self.update_idletasks()

        self._refresh_deck_type_choices(format_name)
        self._reload_usage_rows(show_status=False)
        self._update_status_line()
        self._schedule_visible_load()

    def _reload_usage_rows(self, show_status: bool = True) -> None:
        format_name = self._format_var.get()
        if not format_name:
            return
        deck_type = self._selected_deck_type()
        self._rows = build_format_rows(format_name, deck_type)
        self._usage_by_name = {r.name: r for r in self._rows}
        self._rebuild_display_rows()
        self._refresh_table()
        if show_status:
            self._update_status_line()
        self._schedule_visible_load()

    def _update_status_line(self) -> None:
        format_name = self._format_var.get()
        deck_label = self._deck_type_var.get()
        self._status_var.set(
            f"{format_name} · {deck_label}: {len(self._rows)} pool cards"
        )

    def _schedule_visible_load(self) -> None:
        if self._load_after_id is not None:
            self.after_cancel(self._load_after_id)
        self._load_after_id = self.after(80, self._load_visible_cards)

    def _visible_tree_iids(self) -> List[str]:
        children = self._tree.get_children()
        if not children:
            return []

        top_frac, _bottom_frac = self._tree.yview()
        start = max(0, int(top_frac * len(children)) - VISIBLE_BUFFER)
        view_rows = max(1, self._tree.winfo_height() // ROW_HEIGHT + 1)
        end = min(len(children), start + view_rows + VISIBLE_BUFFER * 2)

        visible: List[str] = []
        for iid in children[start:end]:
            if self._tree.bbox(iid):
                visible.append(iid)
        if not visible:
            visible = list(children[start:end])
        return visible

    def _load_visible_cards(self) -> None:
        self._load_after_id = None
        visible = self._visible_tree_iids()
        self._refresh_visible_photos(visible, download=True)

        to_fetch = [
            name for name in visible if self._client.get_cached_info(name) is None
        ]
        if not to_fetch:
            return

        self._enqueue_card_fetch(to_fetch)

    def _enqueue_card_fetch(self, names: List[str]) -> None:
        with self._fetch_queue_lock:
            for name in names:
                if self._client.get_cached_info(name) is None:
                    self._fetch_queue.add(name)
            start_worker = self._fetch_thread is None or not self._fetch_thread.is_alive()

        if start_worker:
            gen = self._load_gen
            self._fetch_cancel.clear()
            self._fetch_thread = threading.Thread(
                target=self._fetch_worker,
                args=(gen,),
                daemon=True,
            )
            self._fetch_thread.start()

    def _fetch_worker(self, gen: int) -> None:
        while not self._fetch_cancel.is_set() and gen == self._load_gen:
            with self._fetch_queue_lock:
                batch: List[str] = []
                while self._fetch_queue and len(batch) < 15:
                    batch.append(self._fetch_queue.pop())

            if not batch:
                break

            def on_batch(fetched: List[str]) -> None:
                self.after(0, lambda f=fetched: self._on_cards_fetched(f, gen))

            self._client.ensure_cards(
                batch,
                on_batch=on_batch,
                cancel_event=self._fetch_cancel,
            )

    def _on_cards_fetched(self, names: List[str], gen: int) -> None:
        if gen != self._load_gen:
            return
        for name in names:
            self._sync_display_row(name)
        visible = set(self._visible_tree_iids())
        for name in names:
            if name in visible and self._tree.exists(name):
                self._update_tree_row(name, download=True)
        shown = len(self._filtered_rows())
        self._status_var.set(
            f"{self._format_var.get()}: {shown} shown — loaded details for visible rows"
        )
        self._schedule_visible_load()

    def _sync_display_row(self, name: str) -> None:
        usage = self._usage_by_name.get(name)
        if not usage:
            return
        info = self._client.get_cached_info(name)
        display = self._row_to_display(usage, info)
        for i, row in enumerate(self._display_rows):
            if row["name"] == name:
                self._display_rows[i] = display
                return
        self._display_rows.append(display)

    def _rebuild_display_rows(self) -> None:
        built: List[dict[str, Any]] = []
        for row in self._rows:
            info = self._client.get_cached_info(row.name)
            built.append(self._row_to_display(row, info))
        self._display_rows = built

    def _row_to_display(
        self, row: CardUsageRow, info: Optional[CardInfo]
    ) -> dict[str, Any]:
        mult = BAN_MULTIPLIER[row.ban_status]
        return {
            "name": row.name,
            "raw_usage": row.raw_usage,
            "weighted_usage": row.weighted_usage,
            "ban": _ban_label(row.ban_status),
            "ban_status": row.ban_status,
            "ban_sort": _ban_sort_key(row.ban_status),
            "mult": mult,
            "info": info,
            "type": info.type if info else "",
            "attribute": info.attribute or "" if info else "",
            "race": info.race if info else "",
            "level": info.level if info else None,
            "atk": info.atk if info else None,
            "def": info.def_ if info else None,
            "type_key": (info.type if info else "").lower(),
            "attribute_key": (info.attribute or "" if info else "").lower(),
            "race_key": (info.race if info else "").lower(),
            "level_key": _stat_sort_key(info.level if info else None),
            "atk_key": _stat_sort_key(info.atk if info else None),
            "def_key": _stat_sort_key(info.def_ if info else None),
        }

    def _display_row_by_name(self, name: str) -> Optional[dict[str, Any]]:
        for row in self._display_rows:
            if row["name"] == name:
                return row
        usage = self._usage_by_name.get(name)
        if not usage:
            return None
        row = self._row_to_display(usage, self._client.get_cached_info(name))
        self._display_rows.append(row)
        return row

    def _set_sort(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = column != "name"
        self._refresh_table()
        self._schedule_visible_load()

    def _filtered_rows(self) -> List[dict[str, Any]]:
        q = self._query_var.get().strip().casefold()
        rows = self._display_rows
        if q:
            rows = [r for r in rows if q in r["name"].casefold()]
        key_fn = SORT_KEYS[self._sort_column]
        return sorted(rows, key=key_fn, reverse=self._sort_reverse)

    def _refresh_table(self) -> None:
        self._hide_desc_tooltip()
        for item in self._tree.get_children():
            self._tree.delete(item)
        for row in self._filtered_rows():
            self._insert_row(row)

    def _values_tuple(self, row: dict) -> Tuple[Any, ...]:
        level = row["level"] if row["level"] is not None else "—"
        atk = row["atk"] if row["atk"] is not None else "—"
        def_ = row["def"] if row["def"] is not None else "—"
        weighted = row["weighted_usage"]
        if weighted != int(weighted):
            weighted_str = f"{weighted:.1f}"
        else:
            weighted_str = str(int(weighted))
        return (
            row["name"],
            weighted_str,
            row["raw_usage"],
            row["ban"],
            row["type"] or "—",
            row["attribute"] or "—",
            row["race"] or "—",
            level,
            atk,
            def_,
        )

    def _photo_for_row(
        self, row: dict[str, Any], *, download: bool
    ) -> tk.PhotoImage:
        info: Optional[CardInfo] = row.get("info")
        name = row["name"]
        if info:
            photo = self._client.get_photo(
                self, info.id, info.image_url_cropped, download=download
            )
            if photo:
                self._photo_refs[name] = photo
                return photo
        self._photo_refs[name] = self._placeholder
        return self._placeholder

    def _insert_row(self, row: dict[str, Any]) -> None:
        photo = self._photo_for_row(row, download=False)
        self._tree.insert(
            "",
            tk.END,
            iid=row["name"],
            text="",
            image=photo,
            values=self._values_tuple(row),
        )

    def _update_tree_row(self, name: str, *, download: bool) -> None:
        if not self._tree.exists(name):
            return
        row = self._display_row_by_name(name)
        if not row:
            return
        photo = self._photo_for_row(row, download=download)
        self._tree.item(name, image=photo, values=self._values_tuple(row))

    def _refresh_visible_photos(
        self, visible_iids: List[str], *, download: bool
    ) -> None:
        for name in visible_iids:
            if not self._tree.exists(name):
                continue
            row = self._display_row_by_name(name)
            if not row or not row.get("info"):
                continue
            photo = self._photo_for_row(row, download=download)
            if photo is not self._placeholder:
                self._tree.item(name, image=photo, values=self._values_tuple(row))


def run_app() -> None:
    app = UsageStatsApp()
    app.mainloop()
