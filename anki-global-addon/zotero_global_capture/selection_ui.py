"""The 词组 picker: an ordered, checkable book list with per-book tag subsets.

Step 5 of docs/superpowers/specs/2026-11-05-multi-book-tag-selection-design.md. One row per
book that really exists in the account: checkbox, name, a one-line summary, ↑↓ to set the
handover order, and ▾ to expand the tags actually carried by that book's cards. Checking no
tag means the whole book; checking tags studies their union, with （无标签）as a first-class
row. Unchecking a book keeps its tag subset, so re-checking never makes the user re-pick.

All counting is asynchronous: the structure renders immediately and numbers fill in when
the worker threads answer — the settings dialog is the one place the plug-in may not feel
slow. Tag counts are read only when a row expands (one getTags + one batched multi, measured
0.36 s for 30 tags / 5211 cards); the per-book 新词/到期 line is whole-book on purpose, the
subset's own numbers sit on the tag checkboxes.
"""

import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .review_logic import UNTAGGED, book_availability, book_tag_counts, book_untagged_count


class _Stats(QObject):
    """Worker→UI marshalling. Qt drops the connections when the picker dies with the
    dialog; the emit itself is guarded at the call site because the emitter can outlive
    the picker inside the thread closure."""

    stats = pyqtSignal(str, object)
    tags = pyqtSignal(str, object)


class _BookRow(QWidget):
    def __init__(self, book, subset, picker):
        super().__init__(picker)
        self.book = book
        # Ordered so the saved subset reads back the way it was picked. [] = whole book.
        self.subset = list(subset)
        self._picker = picker
        self._stats_text = ''
        self._tags_loaded = False
        self.setObjectName('selectionRow')
        self.setProperty('bookId', book['id'])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        line = QHBoxLayout()
        line.setSpacing(6)
        self.check = QCheckBox(book['name'])
        self.check.setObjectName('selectionBook')
        self.check.setToolTip('范围：%s' % (book.get('tag') or ('牌组 ' + book.get('deck', ''))))
        self.check.toggled.connect(self._picker._row_changed)
        line.addWidget(self.check)
        self.summary = QLabel()
        self.summary.setObjectName('selectionSummary')
        self.summary.setToolTip('新词/到期是整本统计；展开后每个标签旁的数字是该标签的卡片数。')
        line.addWidget(self.summary, 1)
        self.up = QPushButton('↑')
        self.up.setObjectName('selectionUp')
        self.up.setToolTip('上移：先学这本')
        self.up.setFixedWidth(28)
        self.up.clicked.connect(lambda _checked=False: self._picker._move(self, -1))
        line.addWidget(self.up)
        self.down = QPushButton('↓')
        self.down.setObjectName('selectionDown')
        self.down.setToolTip('下移：后学这本')
        self.down.setFixedWidth(28)
        self.down.clicked.connect(lambda _checked=False: self._picker._move(self, 1))
        line.addWidget(self.down)
        self.expand = QPushButton('▾')
        self.expand.setObjectName('selectionExpand')
        self.expand.setToolTip('展开：只学这本里勾选的标签')
        self.expand.setCheckable(True)
        self.expand.setFixedWidth(28)
        self.expand.toggled.connect(self._expanded)
        line.addWidget(self.expand)
        layout.addLayout(line)
        self.panel = QWidget()
        self.panel.setObjectName('selectionTags')
        self.panel_layout = QVBoxLayout(self.panel)
        self.panel_layout.setContentsMargins(24, 2, 0, 2)
        self.panel_layout.setSpacing(2)
        self.panel.hide()
        layout.addWidget(self.panel)
        self._update_summary()

    def _update_summary(self):
        base = '标签 %d 项' % len(self.subset) if self.subset else '整本'
        self.summary.setText(base + self._stats_text)

    def set_stats(self, availability):
        if availability is None:
            return
        self._stats_text = ' · 新词 %d · 到期 %d' % (availability[0], availability[1])
        self._update_summary()

    def _expanded(self, expanded):
        self.expand.setText('▴' if expanded else '▾')
        self.panel.setVisible(expanded)
        if expanded and not self._tags_loaded:
            self._tags_loaded = True
            loading = QLabel('标签统计中…')
            loading.setObjectName('selectionTagsLoading')
            self.panel_layout.addWidget(loading)
            self._picker._load_tags(self)

    def build_tags(self, counts, untagged):
        while self.panel_layout.count():
            item = self.panel_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        hint = QLabel('不勾 = 整本；勾选后只学这些标签的合集。')
        hint.setObjectName('selectionTagsHint')
        self.panel_layout.addWidget(hint)
        listed = list(counts)
        known = {tag for tag, _count in listed}
        # A saved tag whose cards are gone is still listed, checked, counted zero (spec §9) —
        # dropping it would silently widen the subset to the whole book.
        for tag in self.subset:
            if tag != UNTAGGED and tag not in known:
                listed.append((tag, 0))
        listed.append((UNTAGGED, untagged))
        for start in range(0, len(listed), 3):
            line = QHBoxLayout()
            line.setSpacing(10)
            for tag, count in listed[start:start + 3]:
                box = QCheckBox('%s (%d)' % (tag, count))
                box.setObjectName('selectionTag')
                box.setProperty('tag', tag)
                box.setChecked(tag in self.subset)
                box.toggled.connect(lambda checked, name=tag: self._tag_toggled(name, checked))
                line.addWidget(box)
            line.addStretch(1)
            self.panel_layout.addLayout(line)

    def _tag_toggled(self, tag, checked):
        if checked and tag not in self.subset:
            self.subset.append(tag)
        elif not checked and tag in self.subset:
            self.subset.remove(tag)
        self._update_summary()
        self._picker.changed.emit()


class SelectionPicker(QWidget):
    """value() is the ordered study_selection the settings page saves."""

    changed = pyqtSignal()

    def __init__(self, books, entries, api, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName('studySelection')
        self._api = api
        self._cfg = dict(cfg or {})
        self._stats = _Stats()
        self._stats.stats.connect(self._stats_ready)
        self._stats.tags.connect(self._tags_ready)
        self._rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        by_id = {book['id']: book for book in books}
        ordered = []
        seen = set()
        for entry in entries:
            book = by_id.get(entry['book']['id'])
            # A saved book that is not in this account any more is not re-selected — the
            # same rule the single-book list enforced.
            if book is not None and book['id'] not in seen:
                seen.add(book['id'])
                ordered.append((book, entry.get('tags') or [], True))
        for book in books:
            if book['id'] not in seen:
                ordered.append((book, [], False))
        for book, subset, checked in ordered:
            row = _BookRow(book, subset, self)
            row.check.setChecked(checked)
            self._rows.append(row)
            layout.addWidget(row)
        layout.addStretch(1)
        self._refresh_arrows()
        self._start_stats()

    def value(self):
        return [{'book': row.book['id'], 'tags': list(row.subset)}
                for row in self._rows if row.check.isChecked()]

    def _row_changed(self, *_args):
        self.changed.emit()

    def _move(self, row, delta):
        index = self._rows.index(row)
        target = index + delta
        if not 0 <= target < len(self._rows):
            return
        self._rows[index], self._rows[target] = self._rows[target], self._rows[index]
        layout = self.layout()
        layout.removeWidget(row)
        layout.insertWidget(target, row)
        self._refresh_arrows()
        self.changed.emit()

    def _refresh_arrows(self):
        for index, row in enumerate(self._rows):
            row.up.setEnabled(index > 0)
            row.down.setEnabled(index < len(self._rows) - 1)

    def _emit(self, signal, *payload):
        try:
            signal.emit(*payload)
        except RuntimeError:
            pass  # the dialog closed and took the picker with it

    def _start_stats(self):
        def work():
            for row in list(self._rows):
                pinned = dict(self._cfg)
                pinned.pop('_selection_index', None)
                pinned['study_selection'] = [{'book': row.book['id'], 'tags': []}]
                try:
                    value = book_availability(self._api, pinned)
                except Exception:
                    value = None
                self._emit(self._stats.stats, row.book['id'], value)
        threading.Thread(target=work, daemon=True).start()

    def _stats_ready(self, book_id, value):
        for row in self._rows:
            if row.book['id'] == book_id:
                row.set_stats(value)
                return

    def _load_tags(self, row):
        def work():
            counts = book_tag_counts(self._api, self._cfg, row.book)
            other = [tag for tag, _count in counts if tag != row.book.get('tag')]
            untagged = book_untagged_count(self._api, row.book, other)
            self._emit(self._stats.tags, row.book['id'], (counts, untagged))
        threading.Thread(target=work, daemon=True).start()

    def _tags_ready(self, book_id, payload):
        for row in self._rows:
            if row.book['id'] == book_id:
                row.build_tags(*payload)
                return