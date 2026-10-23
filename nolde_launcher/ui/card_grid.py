"""Virtualised card grid with a pool of reusable cards.

Only the cards near the visible area exist. When a card scrolls out of view it is not
destroyed: it goes into a pool and is re-bound to the next item that comes into view.
Creating and destroying widgets on every scroll step was the cause of the lag and of the
flicker in the catalog.
"""

from __future__ import annotations

import math
from typing import Callable, Hashable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QScrollArea, QWidget

from . import motion
from .widgets import COVER_W

GAP = 18
EXTRA_ROWS = 1   # rows kept built above and below the visible area
POOL_MAX = 48    # cards kept for re-use; more than a screen and a half at any size


class CardGrid(QScrollArea):
    def __init__(self, empty_text: str = "", card_width: int = COVER_W, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._keys: list[Hashable] = []
        self._factory: Callable[[Hashable], QWidget] | None = None
        self._binder: Callable[[QWidget, Hashable], None] | None = None
        self._cards: dict[Hashable, QWidget] = {}
        self._pool: list[QWidget] = []
        self._heights: dict[Hashable, int] = {}
        self._placed: dict[Hashable, tuple[int, int]] = {}  # last position of each shown card
        self._card_width = card_width
        self._row_height = 0
        self._columns = 1

        self.host = QWidget()  # no widget-level stylesheet: it would cascade into every card
        self.setWidget(self.host)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(180)
        self._idle.timeout.connect(lambda: motion.set_scrolling(False))

        self.empty = QLabel(empty_text)
        self.empty.setObjectName("Empty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.hide()

    # ----- public API -----

    @property
    def slot(self) -> int:
        return self._card_width + 24 + GAP

    @property
    def built_count(self) -> int:
        """Cards currently shown or kept ready. Used by tests and diagnostics."""
        return len(self._cards)

    @property
    def pool_count(self) -> int:
        return len(self._pool)

    @property
    def entry_count(self) -> int:
        return len(self._keys)

    def _on_scroll(self, _value: int) -> None:
        motion.set_scrolling(True)  # hover effects pause until the scroll settles
        self._idle.start()
        self._update_visible()

    def set_card_width(self, width: int) -> None:
        if width != self._card_width:
            self._card_width = width
            self._drop_all()
            self._relayout()

    def set_entries(self, keys: list[Hashable], factory: Callable[[Hashable], QWidget],
                    empty_text: str | None = None,
                    binder: Callable[[QWidget, Hashable], None] | None = None) -> None:
        """Replace the list. `factory` builds a new card; `binder` re-uses a pooled card for a
        new key (without it, every card is built from scratch)."""
        if empty_text is not None:
            self.empty.setText(empty_text)
        self._factory = factory
        self._binder = binder
        self._keys = list(keys)
        wanted = set(self._keys)
        for key in [k for k in self._cards if k not in wanted]:
            self._release(key)
        self._relayout()
        self.empty.setVisible(not self._keys)
        self.setVisible(bool(self._keys))

    def for_each(self, fn: Callable[[Hashable, QWidget], None]) -> None:
        """Apply `fn` to the cards that exist now (the visible ones)."""
        for key, card in list(self._cards.items()):
            fn(key, card)

    def refresh_all(self) -> None:
        """Rebuild every visible card, e.g. after its underlying data changed shape."""
        self._drop_all()
        self._relayout()

    # ----- internals -----

    @staticmethod
    def _card_height(card: QWidget) -> int:
        # Wrapped text makes a card taller at its real width. sizeHint() ignores that.
        if card.hasHeightForWidth():
            return card.heightForWidth(card.width())
        return card.sizeHint().height()

    def _acquire(self, key: Hashable) -> QWidget:
        if self._binder is not None and self._pool:
            card = self._pool.pop()
            self._binder(card, key)
            card.show()
            return card
        card = self._factory(key)
        card.setParent(self.host)  # parent first, so the card never appears as its own window
        return card

    def _release(self, key: Hashable) -> None:
        card = self._cards.pop(key)
        self._heights.pop(key, None)
        self._placed.pop(key, None)
        card.hide()
        if self._binder is not None and len(self._pool) < POOL_MAX:
            self._pool.append(card)
        else:
            card.deleteLater()

    def _drop_all(self) -> None:
        for key in list(self._cards):
            self._release(key)
        for card in self._pool:
            card.deleteLater()
        self._pool.clear()

    def _remeasure(self, new: list[tuple[Hashable, QWidget]]) -> bool:
        """Measure only the cards that were just bound. Returns True if the row height changed."""
        for key, card in new:
            self._heights[key] = self._card_height(card)
        if not self._heights:
            return False
        tallest = max(self._heights.values())
        new_row = tallest + GAP
        changed = new_row != self._row_height
        self._row_height = new_row
        targets = self._cards.values() if changed else [card for _, card in new]
        for card in targets:  # one height for every card keeps rows even
            card.setFixedHeight(tallest)
        return changed

    def _relayout(self) -> None:
        if not self._keys:
            self.host.resize(self.viewport().width(), 0)
            return
        self._columns = max(1, (self.viewport().width() - 14) // self.slot)
        if self._row_height == 0:
            self._row_height = 360  # placeholder until the first card has been measured
        rows = math.ceil(len(self._keys) / self._columns)
        self.host.resize(self._columns * self.slot, rows * self._row_height)
        self._update_visible()

    def _update_visible(self) -> None:
        if not self._keys or self._factory is None:
            return
        top = self.verticalScrollBar().value()
        view_h = self.viewport().height()
        rows = math.ceil(len(self._keys) / self._columns)
        first = max(0, top // self._row_height - EXTRA_ROWS)
        last = min(rows - 1, (top + view_h) // self._row_height + EXTRA_ROWS)
        indexes = range(first * self._columns, min(len(self._keys), (last + 1) * self._columns))
        wanted = {self._keys[i] for i in indexes}
        for key in [k for k in self._cards if k not in wanted]:
            self._release(key)
        new: list[tuple[Hashable, QWidget]] = []
        for index in indexes:
            key = self._keys[index]
            if key not in self._cards:
                card = self._acquire(key)
                self._cards[key] = card
                new.append((key, card))
        if self._remeasure(new) or new:
            rows = math.ceil(len(self._keys) / self._columns)
            self.host.resize(self._columns * self.slot, rows * self._row_height)
        # Move a card only when its slot changes. Moving on every scroll step forces a repaint of
        # every visible card, which is what made scrolling jerky.
        for index in indexes:
            key = self._keys[index]
            card = self._cards[key]
            pos = ((index % self._columns) * self.slot, (index // self._columns) * self._row_height)
            if self._placed.get(key) != pos:
                card.move(*pos)
                self._placed[key] = pos
            if card.isHidden():
                card.show()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()
