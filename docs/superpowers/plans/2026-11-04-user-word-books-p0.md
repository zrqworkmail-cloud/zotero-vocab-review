# 用户自建词组（P0）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户把自己的一份单词表（粘贴或文件）变成一本可选、可弹卡、可导出分享的词书，库里已有的词只打标签，库里没有的词按"内置词典 → 在线查 → 查不到就跳过"补建笔记。

**Architecture:** 词组 = 一个 Anki 标签（`zvr_book_<id>`）+ 一份名单文件（`user_files/books/<id>.json`），登记进 `cfg['study_books']` 后现有选卡/进度/计划/弹卡逻辑一行不改就能认它。写入编排放在新模块 `word_book_build.py`，文本解析在 `word_lists.py`，文件与目录登记在 `word_book_store.py`，全库词索引抽成共用的 `note_index.py`。UI 只在设置页和「词书与词表管理」子菜单里加入口。

**Tech Stack:** Python 3.12 + Anki 26.9.3 自带 PyQt6（`D:\Program Files (x86)\Anki\app_packages`）、AnkiConnect（127.0.0.1:8765，必须绕代理）、unittest/pytest、`node --test`、离屏 Qt 检查（`QT_QPA_PLATFORM=offscreen`）。

**Spec:** `docs/superpowers/specs/2026-11-04-user-word-books-design.md` — 本计划实现 §11 的 P0；P1（从现有标签/牌组选取 + verify-state 认识用户词组）与 P2（Zotero 端导出词表）各自另开计划。

## Global Constraints

每个任务的隐含要求都包含下面每一条，值取自 spec，逐字照抄：

- 不删笔记、不删牌组：代码里**不允许出现** `deleteNotes`、`deleteNotesWithReview`、`deleteDeck` 的调用路径（spec §7、§13）。
- 绝不在 Qt 槽函数里同步调 AnkiConnect 或网络；整批写入走 `mw.taskman.run_in_background`，并用代次令牌丢弃"用户已关掉对话框"之后的旧任务（spec §4）。
- 每个写批次前检查 `api('getActiveProfile', {})` 未变，变了立即停止并报告"此前已新增 N 词"（spec §8）。
- 词组文件必须带 `source` 与 `license`；导入界面强制填一句来源（spec §3.2、§12.2）。
- 导出默认**只含单词与元数据，不含释义**；勾选含释义时文件里写一行"含第三方词典释义，请勿公开分发"（spec §12.2）。
- 在线查词：串行、每词间隔 0.3 秒、连续 3 次失败即停止并把剩余词进 `pending`（spec §6.5、§8）。
- 不给用户可填的东西加软上限；要挡就把 Anki 的真实每日新词额度量化显示出来（spec §3.3、§13.2）。
- 第一次登记用户词组时必须先物化当前生效目录：`cfg['study_books'] = study_books(cfg) + [新词组]`，否则内置六本词书会从单选列表消失（spec §3.1）。
- 新配置键 `books_online_lookup`（默认 True）与 `books_deck_prefix`（默认 `自定义词组`）同时进 `DEFAULTS` 与出厂 `config.json`。
- 三套闸门必须全绿才算完成：`python -m pytest tests -q`（当前 266 passed）、`node --test tests/plugin.test.cjs`（26）、`python tests/run-windows-checks.py`（21/22 起步，本计划会加新检查）。
- 离屏 Qt 检查必须用 Anki 自带 PyQt6 路径、预加载 `segoeui.ttf` 与 `msyh.ttc`、一个进程只有一个 `QApplication`、并 stub 掉 `ReviewDialog.speak_many`。
- **提交（git commit）需要用户明确授权，本会话尚未授权。** 每个任务末尾的 Commit 步骤在执行前先向用户确认一次；未获授权则把改动留在工作区并说明。
- 部署方式：先 `mkdir deployment-backups/pre-deploy-<YYYYMMDD-HHMMSS>` 备份将被覆盖的文件，再把分支里的文件拷到 `%APPDATA%\Anki2\addons21\zotero_global_capture`（扁平目录，不是包目录），然后 `python tools/restart-anki.py --wait 300` 走托盘退出协议重启，最后 `python tools/verify-state.py` 确认 deployed/loaded 两层。

---

### Task 1: 抽出共用的全库词索引 `note_index.py`

现状：`core_import.import_missing` 和 `cet6_books.setup_books` 各写了一遍"扫全部笔记 → 按 `正面` 建 casefold 索引 + lemma 别名"。用户词组要第三次用，必须先抽出来（spec §4）。这一步是**重构，不改行为**：`tests/test_core_import.py` 与 `tests/test_cet6_books.py` 一条断言都不许改。

**Files:**
- Create: `anki-global-addon/zotero_global_capture/note_index.py`
- Modify: `anki-global-addon/zotero_global_capture/core_import.py:19-29`（那段建索引的循环）
- Modify: `anki-global-addon/zotero_global_capture/cet6_books.py:24-38`（同上）
- Test: `tests/test_note_index.py`

**Interfaces:**
- Consumes: `review_logic.clean_text(value) -> str`、`review_logic.unambiguous_lemma(word) -> str`
- Produces:
  - `word_index(api, cfg) -> {'exact': {casefold_word: [note]}, 'lemma': {casefold_lemma: [note]}}`
  - `find_note(index, word) -> note | None`（多个匹配时取 `noteId` 最小者）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_note_index.py`：

```python
import importlib.util
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'anki-global-addon', 'zotero_global_capture')


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SRC, name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BookApi:
    """Only what the index needs: findNotes + notesInfo, in 200-item pages."""

    def __init__(self, notes):
        self.notes = notes
        self.calls = []

    def __call__(self, action, params):
        self.calls.append((action, params))
        if action == 'findNotes':
            return [n['noteId'] for n in self.notes]
        if action == 'notesInfo':
            wanted = set(params['notes'])
            return [n for n in self.notes if n['noteId'] in wanted]
        raise AssertionError('unexpected action %s' % action)


CFG = {'model': '四六级单词模板', 'front_field': '正面'}


def note(note_id, word, tags=()):
    return {'noteId': note_id, 'tags': list(tags),
            'fields': {'正面': {'value': word}}}


class WordIndex(unittest.TestCase):
    def test_indexes_the_front_field_casefolded(self):
        index = load('note_index').word_index(BookApi([note(1, 'Notion'), note(2, 'method')]), CFG)
        self.assertEqual(sorted(index['exact']), ['method', 'notion'])

    def test_strips_html_and_trailing_capture_counts(self):
        api = BookApi([note(1, '<b>synthesize</b><br>Zotero 收录次数: 3')])
        index = load('note_index').word_index(api, CFG)
        self.assertIn('synthesize', index['exact'])

    def test_lemma_alias_points_at_the_original_note(self):
        api = BookApi([note(7, 'achieves')])
        index = load('note_index').word_index(api, CFG)
        self.assertIn('achieve', index['lemma'])
        self.assertEqual(index['lemma']['achieve'][0]['noteId'], 7)

    def test_find_note_prefers_the_lowest_note_id(self):
        api = BookApi([note(9, 'signal'), note(3, 'Signal')])
        module = load('note_index')
        self.assertEqual(module.find_note(module.word_index(api, CFG), 'SIGNAL')['noteId'], 3)

    def test_find_note_returns_none_for_an_unknown_word(self):
        api = BookApi([note(3, 'signal')])
        module = load('note_index')
        self.assertIsNone(module.find_note(module.word_index(api, CFG), 'notion'))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_note_index.py -q`
Expected: FAIL — `FileNotFoundError`/`ModuleNotFoundError` 指向 `note_index.py`（模块还不存在）。

- [ ] **Step 3: 写最小实现**

创建 `anki-global-addon/zotero_global_capture/note_index.py`：

```python
"""One shared index of the words this collection already holds.

`core_import` and `cet6_books` each built this loop themselves; the user word books need the
same thing a third time, so the copy lives here once. The index is keyed two ways on purpose:
`exact` matches the word as written in the note, `lemma` matches an unambiguous base form, so
a list containing "achieve" finds the note whose front field says "achieves" — and a form with
several possible lemmas stays in `exact` only, which is the safe direction (no false match).
"""

from .review_logic import clean_text, unambiguous_lemma

PAGE = 200


def word_index(api, cfg):
    model = str(cfg['model']).replace('\\', '\\\\').replace('"', '\\"')
    ids = api('findNotes', {'query': 'note:"%s"' % model}) or []
    exact, lemma = {}, {}
    for start in range(0, len(ids), PAGE):
        for note in api('notesInfo', {'notes': ids[start:start + PAGE]}) or []:
            raw = clean_text((note.get('fields') or {}).get(cfg['front_field'], {}).get('value', '')).casefold()
            if not raw:
                continue
            exact.setdefault(raw, []).append(note)
            base = unambiguous_lemma(raw).casefold()
            if base != raw:
                lemma.setdefault(base, []).append(note)
    return {'exact': exact, 'lemma': lemma}


def find_note(index, word):
    key = str(word or '').casefold()
    matches = index['exact'].get(key) or index['lemma'].get(key) or []
    return min(matches, key=lambda item: item['noteId']) if matches else None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_note_index.py -q`
Expected: PASS（5 条）。

- [ ] **Step 5: 把两处旧实现换成调用**

`core_import.py` 中，把从 `ids = api('findNotes', ...)` 到 `missing = [...]` 之前的索引代码替换为：

```python
    from .note_index import word_index
    index = word_index(api, cfg)
    existing = set(index['exact']) | set(index['lemma'])
```

`cet6_books.py` 中，把建 `exact` / `existing` 的整段循环替换为：

```python
    from .note_index import find_note, word_index
    index = word_index(api, cfg)
```

并把该文件里 `matches = exact.get(word) or existing.get(word, [])` 改成：

```python
            note = find_note(index, word)
            matches = [note] if note else []
```

（注意：`cet6_books` 原来取 `min(matches, key=noteId)`，`find_note` 就是同一规则，行为不变。）

- [ ] **Step 6: 跑回归**

Run: `python -m pytest tests/test_note_index.py tests/test_core_import.py tests/test_cet6_books.py -q`
Expected: PASS，三条文件全绿，且后两个文件的断言**一行都没改**。

- [ ] **Step 7: 跑全量三套闸门**

Run: `python -m pytest tests -q && node --test tests/plugin.test.cjs && python tests/run-windows-checks.py`
Expected: 271 passed / 26 pass / 22 检查全过。

- [ ] **Step 8: Commit（需用户授权）**

```bash
git add anki-global-addon/zotero_global_capture/note_index.py \
        anki-global-addon/zotero_global_capture/core_import.py \
        anki-global-addon/zotero_global_capture/cet6_books.py \
        tests/test_note_index.py
git commit -m "refactor: one shared word index for note lookups"
```

---

### Task 2: 名单文本解析 `word_lists.py`（粘贴入口的地基）

**Files:**
- Create: `anki-global-addon/zotero_global_capture/word_lists.py`
- Test: `tests/test_word_lists.py`

**Interfaces:**
- Consumes: 无（纯文本）
- Produces:
  - `normalize_word(value) -> str | None`
  - `parse_words(text) -> {'words': [str], 'dropped': [str]}`（`words` 去重保序、全部小写；`dropped` 是被丢弃的原样 token，供预览展示）

规则（spec §5.1、§8，歧义在此定死）：分隔符为换行、制表、逗号、分号、顿号、竖线；单词允许字母、连字符、撇号（`'` 与 `’`）与**最多两个空格**（收录 "random forest" 这类两三个词的术语），总长 ≤ 40；不含字母、纯数字、含 URL/引号包裹的整句的一律丢弃。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_word_lists.py`：

```python
import importlib.util
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'anki-global-addon', 'zotero_global_capture')
spec = importlib.util.spec_from_file_location('word_lists', os.path.join(SRC, 'word_lists.py'))
lists = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lists)


class Normalize(unittest.TestCase):
    def test_plain_words_are_lowercased_and_trimmed(self):
        self.assertEqual(lists.normalize_word('  Synthesize  '), 'synthesize')

    def test_wrapping_punctuation_is_stripped_not_rejected(self):
        self.assertEqual(lists.normalize_word('“run-way”,'), 'run-way')
        self.assertEqual(lists.normalize_word("don't"), "don't")

    def test_two_and_three_word_terms_are_allowed(self):
        self.assertEqual(lists.normalize_word('random forest'), 'random forest')
        self.assertEqual(lists.normalize_word('a bag of tricks'), 'a bag of tricks')
        self.assertIsNone(lists.normalize_word('this is a whole sentence about words'),
                          'four tokens is a sentence, not a term')

    def test_non_words_are_rejected(self):
        for value in ('', '   ', '123', '2026-11-04', 'https://x.com/y', '中文', None, 'a' * 60):
            self.assertIsNone(lists.normalize_word(value), value)


class Parse(unittest.TestCase):
    def test_splits_on_every_supported_separator(self):
        text = 'notion, method\nsignal; context\tmodel、rule|law'
        self.assertEqual(lists.parse_words(text)['words'],
                         ['notion', 'method', 'signal', 'context', 'model', 'rule', 'law'])

    def test_deduplicates_case_insensitively_and_keeps_order(self):
        self.assertEqual(lists.parse_words('Method method  METHOD notion')['words'],
                         ['method', 'notion'])

    def test_reports_dropped_tokens_instead_of_silently_losing_them(self):
        result = lists.parse_words('notion\n中文\n123\n')
        self.assertEqual(result['words'], ['notion'])
        self.assertEqual(result['dropped'], ['中文', '123'])

    def test_empty_input_is_not_an_error(self):
        self.assertEqual(lists.parse_words('')['words'], [])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_word_lists.py -q`
Expected: FAIL — 模块不存在。

- [ ] **Step 3: 写最小实现**

创建 `anki-global-addon/zotero_global_capture/word_lists.py`：

```python
"""Turning whatever the user pasted into a clean list of words.

Two rules are deliberate. A term may hold up to three words, because a paper's vocabulary list
is full of "random forest" and dropping those would quietly lose the words the user cares most
about. And anything that is *not* kept is reported back instead of vanishing: the preview
dialogue has to show "不像单词 7", otherwise the user can never tell a bad paste from a bug.
"""

import re

SEPARATORS = re.compile(r'[\n\r\t;,，、|]+')
WORD_SHAPE = re.compile(r"^[A-Za-z][A-Za-z'\u2019\-]*(?: [A-Za-z][A-Za-z'\u2019\-]*){0,2}$")
MAX_LENGTH = 40
EDGE_PUNCT = '\u201c\u201d"\'`\u300c\u300d.!??:\u2014-\u2026()\u3010\u3011[]{}'


def normalize_word(value):
    word = re.sub(r'\s+', ' ', str(value or '')).strip().strip(EDGE_PUNCT).strip()
    if len(word) < 1 or len(word) > MAX_LENGTH:
        return None
    if not re.search(r'[A-Za-z]', word):
        return None
    if not WORD_SHAPE.match(word):
        return None
    return word.lower()


def parse_words(text):
    words, dropped, seen = [], [], set()
    for token in SEPARATORS.split(str(text or '')):
        for piece in token.split():
            candidate = normalize_word(piece)
            if candidate is None:
                if piece.strip():
                    dropped.append(piece.strip())
                continue
            if candidate not in seen:
                seen.add(candidate)
                words.append(candidate)
    return {'words': words, 'dropped': dropped}
```

注意 `normalize_word('run-way')` 走的是同一个 `WORD_SHAPE`；`parse_words` 里按空格再切一层，是为了让"一行一个词"和"一行多个词"都能吃下，代价是 `random forest` 在按空格切分后会变成两个 token —— 因此实现改为**先整行试，失败再按空格拆**：

```python
def parse_words(text):
    words, dropped, seen = [], [], set()

    def keep(candidate, piece):
        if candidate is None:
            if piece.strip():
                dropped.append(piece.strip())
            return
        if candidate not in seen:
            seen.add(candidate)
            words.append(candidate)

    for token in SEPARATORS.split(str(text or '')):
        token = token.strip()
        if not token:
            continue
        whole = normalize_word(token)
        if whole is not None:
            keep(whole, token)
            continue
        for piece in token.split():
            keep(normalize_word(piece), piece)
    return {'words': words, 'dropped': dropped}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_word_lists.py -q`
Expected: PASS（9 条）。若 `test_two_and_three_word_terms_are_allowed` 失败，说明还在用第一版 `parse_words`，换成第二版。

- [ ] **Step 5: Commit（需用户授权）**

```bash
git add anki-global-addon/zotero_global_capture/word_lists.py tests/test_word_lists.py
git commit -m "feat: parse pasted word lists into a clean ordered list"
```

---

### Task 3: 文件名单解析（txt / csv 两列三列 / Zotero 的 word,count）

**Files:**
- Modify: `anki-global-addon/zotero_global_capture/word_lists.py`
- Test: `tests/test_word_lists.py`（追加类）

**Interfaces:**
- Consumes: `normalize_word`
- Produces: `parse_file_rows(rows) -> {'entries': [{'word','meaning','example'}], 'dropped': [str]}`，`rows` 是 `list[list[str]]`（调用方负责按 csv 读，编码 utf-8-sig 优先、失败退 gbk）。

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_word_lists.py`）

```python
class FileRows(unittest.TestCase):
    def test_one_column_is_just_words(self):
        result = lists.parse_file_rows([['notion'], ['method']])
        self.assertEqual([e['word'] for e in result['entries']], ['notion', 'method'])
        self.assertEqual(result['entries'][0]['meaning'], '')

    def test_three_columns_carry_meaning_and_example(self):
        result = lists.parse_file_rows([['run', 'v. 跑', 'Run faster.']])
        self.assertEqual(result['entries'],
                         [{'word': 'run', 'meaning': 'v. 跑', 'example': 'Run faster.'}])

    def test_a_header_row_is_skipped_not_ingested(self):
        result = lists.parse_file_rows([['word', 'meaning', 'example'], ['run', 'v. 跑', '']])
        self.assertEqual([e['word'] for e in result['entries']], ['run'])

    def test_zotero_export_word_count_is_read_and_count_ignored(self):
        result = lists.parse_file_rows([['synthesize', '12'], ['notion', '3']])
        self.assertEqual([e['word'] for e in result['entries']], ['synthesize', 'notion'])
        self.assertEqual(result['entries'][0]['meaning'], '')

    def test_junk_rows_are_dropped_and_reported(self):
        result = lists.parse_file_rows([['中文'], [], ['ok']])
        self.assertEqual([e['word'] for e in result['entries']], ['ok'])
        self.assertEqual(result['dropped'], ['中文'])
```

- [ ] **Step 2:** Run `python -m pytest tests/test_word_lists.py -q` → 新 5 条 FAIL（`AttributeError: parse_file_rows`）。

- [ ] **Step 3: 实现**（追加到 `word_lists.py`）

```python
HEADER_WORDS = {'word', 'words', '单词', 'meaning', '释义', 'definition', 'example', '例句', 'count', '次数'}


def parse_file_rows(rows):
    """One, two or three columns: word, [meaning], [example].

    The second column of a Zotero export is an occurrence count, not a gloss, so a row whose
    second field is a bare number is read as word-only. That heuristic is why the format needs
    no explicit dialect switch.
    """
    entries, dropped, seen = [], [], set()
    for line, row in enumerate(rows):
        cells = [str(cell or '').strip() for cell in (row or [])]
        cells = [cell for cell in cells if cell != '']
        if not cells:
            continue
        if line == 0 and all(cell.lower() in HEADER_WORDS for cell in cells):
            continue
        word = normalize_word(cells[0])
        if word is None:
            dropped.append(' '.join(cells)[:40])
            continue
        meaning = cells[1] if len(cells) > 1 and not re.fullmatch(r'\d+', cells[1]) else ''
        example = cells[2] if len(cells) > 2 else (cells[1] if len(cells) > 1 and meaning == '' and len(cells[1]) > 40 else '')
        if word in seen:
            continue
        seen.add(word)
        entries.append({'word': word, 'meaning': meaning, 'example': example})
    return {'entries': entries, 'dropped': dropped}
```

- [ ] **Step 4:** Run `python -m pytest tests/test_word_lists.py -q` → PASS（14 条）。

- [ ] **Step 5: Commit（需授权）** `git add anki-global-addon/zotero_global_capture/word_lists.py tests/test_word_lists.py && git commit -m "feat: read word lists from txt and csv files"`

---

### Task 4: 词组文件与命名 `word_book_store.py`

**Files:**
- Create: `anki-global-addon/zotero_global_capture/word_book_store.py`
- Test: `tests/test_word_book_store.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `make_book_id(name, created) -> str`（`book_<slug>_<4hex>`）
  - `book_tag(bid) -> str`（`zvr_book_<bid>`）
  - `deck_name(prefix, name) -> str`（`<prefix> · <name>`）
  - `new_book(name, source, license, entries, created=None) -> dict`
  - `save_book(root, book)` / `load_book(root, bid)` / `iter_books(root)` / `book_path(root, bid)`
  - `BOOK_VERSION = 1`；读到 `version` > BOOK_VERSION 时抛 `ValueError('词组文件版本太新…')`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_word_book_store.py`：

```python
import importlib.util
import json
import os
import tempfile
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'anki-global-addon', 'zotero_global_capture')
spec = importlib.util.spec_from_file_location('word_book_store', os.path.join(SRC, 'word_book_store.py'))
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)

ENTRIES = [{'word': 'notion', 'meaning': 'n. 概念', 'example': ''},
           {'word': 'synthesize', 'meaning': '', 'example': ''}]


def book(**over):
    base = store.new_book('论文核心词', '自己整理的', 'self', ENTRIES,
                          created='2026-11-04T11:50:00')
    base.update(over)
    return base


class Naming(unittest.TestCase):
    def test_ascii_name_gets_a_readable_id(self):
        self.assertTrue(store.make_book_id('Paper Words', '2026-11-04T11:50:00').startswith('book_paper_words_'))

    def test_a_chinese_name_still_produces_a_unique_safe_id(self):
        first = store.make_book_id('论文核心词', '2026-11-04T11:50:00')
        second = store.make_book_id('论文核心词', '2026-11-04T11:50:01')
        self.assertRegex(first, r'^book_[0-9a-f]{4}$')
        self.assertNotEqual(first, second)

    def test_id_is_stable_for_the_same_name_and_time(self):
        self.assertEqual(store.make_book_id('X', '2026-11-04T11:50:00'),
                         store.make_book_id('x', '2026-11-04T11:50:00'))

    def test_tag_and_deck_are_derived_not_invented_per_call(self):
        item = book()
        self.assertEqual(store.book_tag(item['id']), 'zvr_book_' + item['id'])
        self.assertEqual(store.deck_name('自定义词组', item['name']), '自定义词组 · 论文核心词')


class Files(unittest.TestCase):
    def test_round_trip_keeps_words_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = book()
            store.save_book(tmp, item)
            again = store.load_book(tmp, item['id'])
            self.assertEqual(again['name'], '论文核心词')
            self.assertEqual([w['word'] for w in again['words']], ['notion', 'synthesize'])
            self.assertEqual(again['source'], '自己整理的')

    def test_the_file_name_is_the_id_so_a_rename_cannot_break_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = book()
            store.save_book(tmp, item)
            self.assertTrue(os.path.exists(store.book_path(tmp, item['id'])))
            item['name'] = '改名后'
            store.save_book(tmp, item)
            self.assertEqual(store.load_book(tmp, item['id'])['name'], '改名后')

    def test_iter_books_sorts_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = book(name='乙组'), book(name='甲组')
            store.save_book(tmp, a)
            store.save_book(tmp, b)
            self.assertEqual([item['name'] for item in store.iter_books(tmp)], ['乙组', '甲组'])

    def test_a_newer_file_version_is_refused_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = book(version=store.BOOK_VERSION + 1)
            store.save_book(tmp, item)
            with self.assertRaises(ValueError):
                store.load_book(tmp, item['id'])

    def test_words_default_to_noted_and_pending_is_preserved(self):
        item = store.new_book('n', 's', 'self',
                              [{'word': 'a', 'meaning': 'x', 'example': ''},
                               {'word': 'b', 'meaning': '', 'example': ''}],
                              created='2026-11-04T11:50:00')
        self.assertEqual([w['state'] for w in item['words']], ['noted', 'pending'])
```

- [ ] **Step 2:** Run `python -m pytest tests/test_word_book_store.py -q` → FAIL（模块不存在）。

- [ ] **Step 3: 实现**

创建 `anki-global-addon/zotero_global_capture/word_book_store.py`：

```python
"""Where a user's word book lives: its id, its tag, its deck, its file.

The id is generated once and never derived from the name again, because the name is the one
thing the user is allowed to change. Tag and deck are read off the stored id, so renaming a
book touches no card and no schedule. A Chinese name yields an empty slug, and then the hash
alone names the book — which is why the hash is over name *and* creation time, not name only.
"""

import hashlib
import json
import re
from pathlib import Path

BOOK_VERSION = 1


def _slug(name):
    value = str(name or '').strip().lower()
    value = re.sub(r'[^a-z0-9]+', '_', value).strip('_')
    return value[:32]


def make_book_id(name, created):
    digest = hashlib.sha1(('%s|%s' % (str(name or '').strip(), created)).encode('utf-8'))
    short = digest.hexdigest()[:4]
    slug = _slug(name)
    return 'book_%s_%s' % (slug, short) if slug else 'book_%s' % short


def book_tag(bid):
    return 'zvr_book_%s' % bid


def deck_name(prefix, name):
    return '%s · %s' % (str(prefix or '自定义词组').strip(), str(name or '').strip())


def new_book(name, source, license, entries, created=None):
    created = created or _now()
    bid = make_book_id(name, created)
    return {'version': BOOK_VERSION, 'id': bid, 'name': str(name or '').strip(),
            'tag': book_tag(bid), 'deck': deck_name('自定义词组', name),
            'created': created, 'updated': created,
            'source': str(source or '').strip(), 'license': str(license or 'self').strip(),
            'words': [{'word': item['word'], 'meaning': item.get('meaning', ''),
                       'example': item.get('example', ''),
                       'state': 'noted' if item.get('meaning') else 'pending'}
                      for item in (entries or [])]}


def _now():
    import datetime
    return datetime.datetime.now().isoformat(timespec='seconds')


def book_path(root, bid):
    return Path(str(root)) / 'books' / ('%s.json' % bid)


def save_book(root, book):
    path = book_path(root, book['id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(book, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def load_book(root, bid):
    data = json.loads(book_path(root, bid).read_text(encoding='utf-8'))
    version = int(data.get('version') or 1)
    if version > BOOK_VERSION:
        raise ValueError('词组文件版本为 %d，当前插件只支持到 %d，请升级插件后再导入。' % (version, BOOK_VERSION))
    data.setdefault('words', [])
    data.setdefault('tag', book_tag(data['id']))
    return data


def iter_books(root):
    folder = Path(str(root)) / 'books'
    found = []
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        try:
            found.append(load_book(root, path.stem))
        except (ValueError, OSError, json.JSONDecodeError):
            continue
    return sorted(found, key=lambda item: str(item.get('name') or ''))
```

- [ ] **Step 4:** Run `python -m pytest tests/test_word_book_store.py -q` → PASS（10 条）。

- [ ] **Step 5: Commit（需授权）** `git commit -m "feat: store user word books as files with stable ids"`

---

### Task 5: 把词组登记进目录（内置六本不许消失）

spec §3.1 的陷阱：`study_books(cfg)` 是"配置有就用配置"。第一次追加用户词组若只写那一条，内置词书全部消失。

**Files:**
- Modify: `anki-global-addon/zotero_global_capture/word_book_store.py`
- Test: `tests/test_word_book_store.py`（追加类）

**Interfaces:**
- Consumes: `review_logic.study_books(cfg)`
- Produces:
  - `register_book(cfg, book) -> dict`（返回**新的** cfg 副本，含完整目录）
  - `unregister_book(cfg, bid) -> dict`
  - `catalogue_entry(book) -> {'id','name','tag'}`

- [ ] **Step 1: 写失败测试**

```python
class Catalogue(unittest.TestCase):
    BUILT_IN = [{'id': 'cet6_core', 'name': '六级核心', 'tag': 'zvr_cet6_core'},
                {'id': 'literature', 'name': '文献单词', 'deck': '文献单词'}]

    def test_registering_the_first_user_book_keeps_every_built_in(self):
        cfg = {'study_book': 'cet6_core'}
        merged = store.register_book(cfg, book())
        ids = [item['id'] for item in merged['study_books']]
        self.assertIn('cet6_core', ids)
        self.assertIn('literature', ids)
        self.assertIn(store.make_book_id('论文核心词', '2026-11-04T11:50:00'), ids)

    def test_registering_twice_does_not_duplicate_the_entry(self):
        merged = store.register_book({'study_books': list(self.BUILT_IN)}, book())
        again = store.register_book(merged, book())
        self.assertEqual(len(again['study_books']), len(self.BUILT_IN) + 1)

    def test_the_original_cfg_is_not_mutated(self):
        cfg = {'study_books': list(self.BUILT_IN)}
        before = [item['id'] for item in cfg['study_books']]
        store.register_book(cfg, book())
        self.assertEqual([item['id'] for item in cfg['study_books']], before)

    def test_unregistering_removes_only_that_book(self):
        merged = store.register_book({'study_books': list(self.BUILT_IN)}, book())
        back = store.unregister_book(merged, merged['study_books'][-1]['id'])
        self.assertEqual([item['id'] for item in back['study_books']],
                         [item['id'] for item in self.BUILT_IN])

    def test_a_selected_book_is_never_left_pointing_at_nothing(self):
        merged = store.register_book({'study_books': list(self.BUILT_IN), 'study_book': 'cet6_core'}, book())
        self.assertEqual(store.unregister_book(merged, 'cet6_core')['study_book'], 'cet6_core')
```

- [ ] **Step 2:** Run → 5 条 FAIL（AttributeError）。

- [ ] **Step 3: 实现**（追加到 `word_book_store.py`；`from .review_logic import study_books` 放文件顶部）

```python
def catalogue_entry(book):
    return {'id': book['id'], 'name': book['name'], 'tag': book['tag']}


def register_book(cfg, book):
    """Materialise the catalogue in force, then append.

    `study_books(cfg)` falls back to the built-in tuple when the config has no list, so writing
    only the new entry would silently drop all six built-in books from the picker.
    """
    merged = dict(cfg or {})
    current = [dict(item) for item in study_books(cfg)]
    entry = catalogue_entry(book)
    if not any(item['id'] == entry['id'] for item in current):
        current.append(entry)
    merged['study_books'] = current
    return merged


def unregister_book(cfg, bid):
    merged = dict(cfg or {})
    current = [dict(item) for item in study_books(cfg)]
    merged['study_books'] = [item for item in current if item.get('id') != bid]
    return merged
```

- [ ] **Step 4:** Run → PASS（15 条）。
- [ ] **Step 5: Commit（需授权）** `git commit -m "fix: keep the built-in books when a user book is registered"`

---

### Task 6: 三分类 `classify`（谁只打标签、谁要建卡、谁进待补）

**Files:**
- Create: `anki-global-addon/zotero_global_capture/word_book_build.py`
- Test: `tests/test_word_book_build.py`

**Interfaces:**
- Consumes: `note_index.word_index/find_note`、`lexicon/cet_core.json['dictionary']`、`lexicon/cet6_full.json['words']`
- Produces:
  - `bundled_glosses() -> {word: {'meaning','phonetic'}}`（两份内置表合并，cet_core 优先）
  - `classify(entries, index, glosses) -> {'tagged': [(word, note)], 'create': [(word, gloss)], 'pending': [word]}`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_word_book_build.py`：

```python
import importlib.util
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'anki-global-addon', 'zotero_global_capture')
spec = importlib.util.spec_from_file_location('word_book_build', os.path.join(SRC, 'word_book_build.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

INDEX = {'exact': {'notion': [{'noteId': 1, 'tags': []}]}, 'lemma': {'run': [{'noteId': 2, 'tags': []}]}}
GLOSS = {'synthesize': {'meaning': 'v. 合成', 'phonetic': 'sɪnθəsaɪz'}}


def entries(*words):
    return [{'word': word, 'meaning': '', 'example': ''} for word in words]


class Classify(unittest.TestCase):
    def test_an_existing_note_is_only_tagged(self):
        result = build.classify(entries('notion'), INDEX, GLOSS)
        self.assertEqual(result['tagged'], [('notion', INDEX['exact']['notion'][0])])
        self.assertEqual(result['create'], [])

    def test_a_lemma_hit_counts_as_existing(self):
        result = build.classify(entries('runs'), INDEX, GLOSS)
        self.assertEqual(result['tagged'][0][1]['noteId'], 2)

    def test_a_word_with_a_bundled_gloss_is_created(self):
        result = build.classify(entries('synthesize'), INDEX, GLOSS)
        self.assertEqual(result['create'], [('synthesize', GLOSS['synthesize'])])

    def test_a_word_with_nothing_available_is_pending_not_an_empty_card(self):
        result = build.classify(entries('schmuck'), INDEX, GLOSS)
        self.assertEqual(result['pending'], ['schmuck'])
        self.assertEqual(result['create'], [])

    def test_a_gloss_carried_by_the_imported_file_counts_as_creatable(self):
        result = build.classify([{'word': 'schmuck', 'meaning': 'n. 怪人', 'example': ''}], INDEX, {})
        self.assertEqual(result['create'], [('schmuck', {'meaning': 'n. 怪人', 'phonetic': ''})])

    def test_every_word_lands_in_exactly_one_bucket(self):
        result = build.classify(entries('notion', 'synthesize', 'schmuck'), INDEX, GLOSS)
        total = len(result['tagged']) + len(result['create']) + len(result['pending'])
        self.assertEqual(total, 3)


class Bundled(unittest.TestCase):
    def test_bundled_glosses_cover_a_known_core_word(self):
        glosses = build.bundled_glosses()
        self.assertIn('ability', glosses)
        self.assertTrue(glosses['ability']['meaning'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2:** Run → FAIL。

- [ ] **Step 3: 实现**

创建 `anki-global-addon/zotero_global_capture/word_book_build.py`：

```python
"""Deciding, per word, what a user book has to do — and then doing it.

Three buckets, and the order is the whole point: an existing note only gets a tag (no new card,
no schedule touched), a missing word with a gloss available gets a new note, and a missing word
with no gloss anywhere is left `pending` instead of becoming an empty card the learner then has
to look at. `pending` is written back to the book file, so the word is not lost — it is retried
next time, or once the user turns online lookup on.
"""

import json
import re
from pathlib import Path

from .note_index import find_note

LEXICON = Path(__file__).parent / 'lexicon'


def bundled_glosses():
    glosses = {}
    full = json.loads((LEXICON / 'cet6_full.json').read_text(encoding='utf-8'))
    for row in full.get('words') or []:
        word, phonetic, meaning = (list(row) + ['', '', ''])[:3]
        key = str(word or '').casefold()
        if key and meaning:
            glosses.setdefault(key, {'meaning': str(meaning), 'phonetic': str(phonetic or '')})
    core = json.loads((LEXICON / 'cet_core.json').read_text(encoding='utf-8'))
    for word, info in (core.get('dictionary') or {}).items():
        if isinstance(info, dict) and info.get('meaning'):
            glosses[str(word).casefold()] = {'meaning': str(info['meaning']),
                                             'phonetic': str(info.get('phonetic') or '')}
    return glosses


def classify(entries, index, glosses):
    tagged, create, pending = [], [], []
    for item in entries or []:
        word = str(item.get('word') or '').strip()
        if not word:
            continue
        note = find_note(index, word)
        if note is not None:
            tagged.append((word, note))
            continue
        gloss = (item.get('meaning') and {'meaning': item['meaning'],
                                          'phonetic': item.get('phonetic', '')}) or glosses.get(word.casefold())
        if gloss:
            create.append((word, gloss))
        else:
            pending.append(word)
    return {'tagged': tagged, 'create': create, 'pending': pending}
```

- [ ] **Step 4:** Run → PASS（7 条）。
- [ ] **Step 5: Commit（需授权）** `git commit -m "feat: classify book words into tag, create and pending"`

---

### Task 7: 写入编排 `build_book`（打标签、建卡、进度、账户保护）

**Files:**
- Modify: `anki-global-addon/zotero_global_capture/word_book_build.py`
- Test: `tests/test_word_book_build.py`（追加）

**Interfaces:**
- Consumes: `api(action, params)`、`cfg`（需 `model`/`front_field`/`back_field`）、`word_index`、`classify`
- Produces: `build_book(api, cfg, book, glosses, on_progress=None, is_stale=None, sleep=None) -> {'tagged','created','pending','failed','deck'}`；`book` 被就地更新 `words[].state` 与 `updated`。

- [ ] **Step 1: 写失败测试**

```python
class WriterApi:
    """Records every call so the test can assert on what was written, and nothing else."""

    def __init__(self, notes=None, profile='Profile A', fields=('正面', '解释', '音标'), fail_on=None):
        self.notes = notes or []
        self.profile = profile
        self.fields = list(fields)
        self.fail_on = fail_on or set()
        self.calls = []
        self.added = []
        self.tagged = []
        self.decks = []
        self.next_id = 100

    def __call__(self, action, params):
        self.calls.append((action, params))
        if action == 'getActiveProfile':
            return self.profile
        if action == 'modelFieldNames':
            return self.fields
        if action == 'findNotes':
            return [n['noteId'] for n in self.notes]
        if action == 'notesInfo':
            return self.notes
        if action == 'createDeck':
            self.decks.append(params['deck'])
            return 1
        if action == 'addTags':
            self.tagged.append((params['tags'], list(params['notes'])))
            return True
        if action == 'addNote':
            if action in self.fail_on:
                raise RuntimeError('Anki refused')
            self.next_id += 1
            self.added.append(params['note'])
            return self.next_id
        raise AssertionError('unexpected action %s' % action)


def fresh_book(words):
    entries = [{'word': word, 'meaning': '', 'example': ''} for word in words]
    return store.new_book('测试词组', 'self', 'self', entries, created='2026-11-04T11:50:00')


class BuildBook(unittest.TestCase):
    def setUp(self):
        self.api = WriterApi(notes=[{'noteId': 5, 'tags': [], 'fields': {'正面': {'value': 'notion'}}}])

    def test_existing_notes_are_tagged_and_no_note_is_created(self):
        book = fresh_book(['notion'])
        result = build.build_book(self.api, CFG, book, {})
        self.assertEqual(result['tagged'], 1)
        self.assertEqual(self.api.added, [])
        self.assertEqual([tags for tags, _ids in self.api.tagged], [book['tag']])

    def test_a_missing_word_with_a_gloss_creates_one_note_in_the_book_deck(self):
        book = fresh_book(['synthesize'])
        result = build.build_book(self.api, CFG, book,
                                  {'synthesize': {'meaning': 'v. 合成', 'phonetic': 'sɪnθəsaɪz'}})
        self.assertEqual(result['created'], 1)
        self.assertEqual(self.api.decks, [book['deck']])
        note = self.api.added[0]
        self.assertEqual(note['deckName'], book['deck'])
        self.assertEqual(note['tags'], [book['tag']])
        self.assertEqual(note['fields']['正面'], 'synthesize')
        self.assertEqual(note['fields']['解释'], 'v. 合成')
        self.assertEqual(note['fields']['音标'], 'sɪnθəsaɪz')

    def test_the_deck_is_created_once_not_per_word(self):
        book = fresh_book(['a', 'b', 'c'])
        glosses = {w: {'meaning': 'x', 'phonetic': ''} for w in ['a', 'b', 'c']}
        build.build_book(self.api, CFG, book, glosses)
        self.assertEqual(self.api.decks, [book['deck']])

    def test_a_word_with_no_gloss_is_pending_and_writes_nothing(self):
        book = fresh_book(['schmuck'])
        result = build.build_book(self.api, CFG, book, {})
        self.assertEqual(result['pending'], ['schmuck'])
        self.assertEqual(self.api.added, [])
        self.assertEqual(book['words'][0]['state'], 'pending')

    def test_a_refused_add_note_is_reported_not_raised(self):
        book = fresh_book(['synthesize'])
        self.api.fail_on = {'addNote'}
        result = build.build_book(self.api, CFG, book,
                                  {'synthesize': {'meaning': 'x', 'phonetic': ''}})
        self.assertEqual(result['failed'], ['synthesize'])

    def test_switching_profile_stops_the_run_and_keeps_what_was_done(self):
        book = fresh_book(['a', 'b', 'c'])
        glosses = {w: {'meaning': 'x', 'phonetic': ''} for w in ['a', 'b', 'c']}
        seen = {'n': 0}
        original = self.api.__call__

        def shifting(action, params):
            if action == 'getActiveProfile':
                seen['n'] += 1
                return 'Profile A' if seen['n'] < 3 else 'Profile B'
            return original(action, params)

        self.api.__call__ = shifting
        with self.assertRaises(RuntimeError):
            build.build_book(self.api, CFG, book, glosses)
        self.assertLessEqual(len(self.api.added), 2)

    def test_a_missing_back_field_is_a_clear_error_not_a_silent_empty_card(self):
        self.api.fields = ['正面']
        book = fresh_book(['synthesize'])
        with self.assertRaises(ValueError):
            build.build_book(self.api, CFG, book, {'synthesize': {'meaning': 'x', 'phonetic': ''}})

    def test_progress_is_reported_for_every_word_and_a_stale_run_stops(self):
        book = fresh_book(['a', 'b', 'c'])
        glosses = {w: {'meaning': 'x', 'phonetic': ''} for w in ['a', 'b', 'c']}
        seen = []
        build.build_book(self.api, CFG, book, glosses, on_progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen[-1], (3, 3))
        stopped = build.build_book(self.api, CFG, fresh_book(['d']), {'d': {'meaning': 'x', 'phonetic': ''}},
                                   is_stale=lambda: True)
        self.assertEqual(stopped['created'], 0)
```

- [ ] **Step 2:** Run → FAIL（`build_book` 不存在）。

- [ ] **Step 3: 实现**（追加到 `word_book_build.py`；顶部补 `import html`、`import time`）

```python
CFG_FIELDS = ('front_field', 'back_field')
BATCH = 200


def _fields(api, cfg):
    names = api('modelFieldNames', {'modelName': cfg['model']}) or []
    missing = [cfg[key] for key in CFG_FIELDS if cfg[key] not in names]
    if missing:
        raise ValueError('笔记类型缺少字段：%s。请在设置里改字段映射后重试。' % '、'.join(missing))
    return names


def build_book(api, cfg, book, glosses, on_progress=None, is_stale=None, sleep=None):
    """Tag what exists, create what has a gloss, leave the rest pending.

    Nothing here deletes: no `deleteNotes`, no `deleteDeck`. A word that already has a note is
    never moved into the book's deck, because that would rearrange the user's own organisation
    and touch their schedule.
    """
    names = _fields(api, cfg)
    profile = api('getActiveProfile', {})
    index = {'exact': {}, 'lemma': {}}
    from .note_index import word_index
    index = word_index(api, cfg)
    buckets = classify(book.get('words') or [], index, glosses or {})
    result = {'tagged': 0, 'created': 0, 'pending': list(buckets['pending']), 'failed': [],
              'deck': book['deck']}

    by_note = {}
    for _word, note in buckets['tagged']:
        if book['tag'] not in (note.get('tags') or []):
            by_note.setdefault(note['noteId'], True)
    ids = sorted(by_note)
    for start in range(0, len(ids), BATCH):
        if api('getActiveProfile', {}) != profile:
            raise RuntimeError('Anki 账户已切换，导入已停止。')
        api('addTags', {'notes': ids[start:start + BATCH], 'tags': book['tag']})
        result['tagged'] += len(ids[start:start + BATCH])

    states = {item['word']: item for item in book['words']}
    if buckets['create']:
        api('createDeck', {'deck': book['deck']})
        total = len(buckets['create'])
        for position, (word, gloss) in enumerate(buckets['create'], 1):
            if is_stale is not None and is_stale():
                break
            if position % 20 == 1 and api('getActiveProfile', {}) != profile:
                raise RuntimeError('Anki 账户已切换，导入已停止；此前已新增 %d 词。' % result['created'])
            values = {cfg['front_field']: html.escape(word),
                      cfg['back_field']: html.escape(gloss.get('meaning') or '').replace('\n', '<br>')}
            if '音标' in names and gloss.get('phonetic'):
                values['音标'] = html.escape(gloss['phonetic'])
            try:
                added = api('addNote', {'note': {'deckName': book['deck'], 'modelName': cfg['model'],
                                                 'fields': values,
                                                 'options': {'allowDuplicate': False},
                                                 'tags': [book['tag']}})
            except Exception:
                added = None
            if added:
                result['created'] += 1
                if word in states:
                    states[word]['state'] = 'noted'
                    states[word]['meaning'] = gloss.get('meaning') or ''
            else:
                result['failed'].append(word)
            if on_progress:
                on_progress(position, total)
    for word in buckets['pending']:
        if word in states:
            states[word]['state'] = 'pending'
    import datetime
    book['updated'] = datetime.datetime.now().isoformat(timespec='seconds')
    return result
```

- [ ] **Step 4:** Run → PASS（15 条）。若 `test_switching_profile_stops_the_run_and_keeps_what_was_done` 不稳，把检查频率从"每 20 词"改为"每次 addNote 前"，并在测试里断言 `len(self.api.added) <= 2` 保持不变。
- [ ] **Step 5: Commit（需授权）** `git commit -m "feat: build a user word book against Anki"`

---

### Task 8: 在线补释义（节流、连续失败即停、可关）

**Files:**
- Modify: `anki-global-addon/zotero_global_capture/word_book_build.py`
- Test: `tests/test_word_book_build.py`（追加）

**Interfaces:**
- Consumes: `dictionary(word) -> dict`（`__init__.py` 里已有的有道查询，返回含 `meaning`/`phonetic`）
- Produces: `gather_glosses(words, dictionary, enabled=True, throttle=0.3, sleep=time.sleep, max_failures=3) -> ({word: {'meaning','phonetic'}}, {'stopped': bool, 'failed': [word]})`

- [ ] **Step 1: 写失败测试**

```python
class GatherGlosses(unittest.TestCase):
    def api_ok(self, word):
        return {'meaning': 'n. %s' % word, 'phonetic': '/x/'}

    def test_offline_returns_nothing_and_calls_no_network(self):
        seen = []
        glosses, meta = build.gather_glosses(['a', 'b'], lambda w: seen.append(w) or self.api_ok(w),
                                             enabled=False, sleep=lambda _s: None)
        self.assertEqual(glosses, {})
        self.assertEqual(seen, [])
        self.assertFalse(meta['stopped'])

    def test_online_fills_every_word_with_a_gap_between_lookups(self):
        slept = []
        glosses, meta = build.gather_glosses(['a', 'b'], self.api_ok, sleep=slept.append)
        self.assertEqual(sorted(glosses), ['a', 'b'])
        self.assertEqual(slept, [0.3])          # 第一个词前不等待，词与词之间等待

    def test_a_word_without_a_meaning_counts_as_a_failure_and_is_left_out(self):
        glosses, meta = build.gather_glosses(['a'], lambda w: {}, sleep=lambda _s: None)
        self.assertEqual(glosses, {})
        self.assertEqual(meta['failed'], ['a'])

    def test_three_failures_in_a_row_stop_the_whole_lookup(self):
        calls = []

        def always_bad(word):
            calls.append(word)
            raise RuntimeError('429')

        glosses, meta = build.gather_glosses(['a', 'b', 'c', 'd', 'e'], always_bad, sleep=lambda _s: None)
        self.assertEqual(len(calls), 3)
        self.assertTrue(meta['stopped'])
        self.assertEqual(sorted(meta['failed']), ['a', 'b', 'c'])

    def test_a_success_resets_the_failure_streak(self):
        state = {'n': 0}

        def flaky(word):
            state['n'] += 1
            if state['n'] in (2, 3):
                raise RuntimeError('timeout')
            return self.api_ok(word)

        glosses, meta = build.gather_glosses(['w1', 'w2', 'w3', 'w4'], flaky, sleep=lambda _s: None)
        self.assertFalse(meta['stopped'])
        self.assertEqual(sorted(glosses), ['w1', 'w2', 'w3', 'w4'])
```

- [ ] **Step 2:** Run → FAIL。

- [ ] **Step 3: 实现**

```python
def gather_glosses(words, dictionary, enabled=True, throttle=0.3, sleep=None, max_failures=3):
    """Ask the online dictionary for the words the bundled tables could not cover.

    Serial, throttled, and stopped after three failures in a row: the endpoint is a public
    dictionary, not our service, and a rate limit mid-import must not turn into a hammer. A
    word that comes back empty is a miss, not an error, and stays `pending` in the book file.
    """
    sleep = sleep or time.sleep
    found, failed, streak = {}, [], 0
    if not enabled:
        return found, {'stopped': False, 'failed': list(words or [])}
    for position, word in enumerate(words or []):
        if position:
            sleep(throttle)
        try:
            info = dictionary(word) or {}
        except Exception:
            info = {}
        if info.get('meaning'):
            found[word] = {'meaning': str(info['meaning']), 'phonetic': str(info.get('phonetic') or '')}
            streak = 0
            continue
        failed.append(word)
        streak += 1
        if streak >= max_failures:
            rest = [item for item in list(words)[position + 1:] if item not in failed]
            return found, {'stopped': True, 'failed': failed + rest}
    return found, {'stopped': False, 'failed': failed}
```

- [ ] **Step 4:** Run → PASS（20 条）。
- [ ] **Step 5: Commit（需授权）** `git commit -m "feat: throttled online gloss lookup with a failure stop"`

---

### Task 9: 追加与删除（删除绝不碰笔记）

**Files:**
- Modify: `anki-global-addon/zotero_global_capture/word_book_build.py`、`word_book_store.py`
- Test: `tests/test_word_book_build.py`（追加）

**Interfaces:**
- Produces:
  - `append_words(api, cfg, book, words, glosses, on_progress=None, is_stale=None) -> 同 build_book 的返回`
  - `remove_book(api, cfg, book, root) -> {'untagged': n, 'kept_notes': True}`
  - `store.delete_book_file(root, bid) -> bool`

- [ ] **Step 1: 写失败测试**

```python
class Append(unittest.TestCase):
    def test_appending_only_handles_the_new_words(self):
        api = WriterApi(notes=[])
        book = fresh_book(['a'])
        build.build_book(api, CFG, book, {'a': {'meaning': 'x', 'phonetic': ''}})
        before = len(api.calls)
        result = build.append_words(api, CFG, book, ['b'], {'b': {'meaning': 'y', 'phonetic': ''}})
        self.assertEqual(result['created'], 1)
        self.assertEqual(book['words'][-1]['word'], 'b')
        self.assertGreater(len(api.calls), before)

    def test_appending_a_word_already_in_the_book_is_a_no_op(self):
        api = WriterApi(notes=[])
        book = fresh_book(['a'])
        build.build_book(api, CFG, book, {'a': {'meaning': 'x', 'phonetic': ''}})
        calls = len(api.calls)
        result = build.append_words(api, CFG, book, ['a'], {'a': {'meaning': 'x', 'phonetic': ''}})
        self.assertEqual(result['created'], 0)
        self.assertEqual(len(api.calls), calls)


class Remove(unittest.TestCase):
    def test_removing_a_book_writes_nothing_to_anki(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = WriterApi(notes=[{'noteId': 5, 'tags': ['zvr_book_x'],
                                    'fields': {'正面': {'value': 'notion'}}}])
            book = fresh_book(['notion'])
            book['tag'] = 'zvr_book_x'
            store.save_book(tmp, book)
            result = build.remove_book(book, tmp)
            self.assertEqual(result['kept_notes'], True)
            self.assertEqual(api.calls, [], 'removing a book must not write to Anki at all')
            self.assertFalse(store.book_path(tmp, book['id']).exists())

    def test_removal_works_even_for_a_book_with_no_notes_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = fresh_book(['notion'])
            store.save_book(tmp, book)
            self.assertEqual(build.remove_book(book, tmp)['untagged'], 0)
```

测试文件顶部需要 `import tempfile` 与 `import word_book_store as store`（沿用本文件已有的 `importlib` 加载方式：`store = load('word_book_store')`）。

- [ ] **Step 2:** Run → FAIL。

- [ ] **Step 3: 实现**

`word_book_store.py` 追加：

```python
def delete_book_file(root, bid):
    path = book_path(root, bid)
    if path.exists():
        path.unlink()
        return True
    return False
```

`word_book_build.py` 追加：

```python
def append_words(api, cfg, book, words, glosses, on_progress=None, is_stale=None):
    known = {item['word'] for item in book['words']}
    fresh = [word for word in (words or []) if word not in known]
    for word in fresh:
        book['words'].append({'word': word, 'meaning': '', 'example': '', 'state': 'pending'})
    if not fresh:
        return {'tagged': 0, 'created': 0, 'pending': [], 'failed': [], 'deck': book['deck']}
    subset = dict(book)
    subset['words'] = [{'word': word, 'meaning': '', 'example': ''} for word in fresh]
    result = build_book(api, cfg, subset, glosses, on_progress=on_progress, is_stale=is_stale)
    states = {item['word']: item['state'] for item in subset['words']}
    for item in book['words']:
        if item['word'] in states:
            item['state'] = states[item['word']]
    return result


def remove_book(book, root):
    """Drop the book file. Nothing in Anki is touched.

    Anki tags are global, and rewriting every note that carries this tag would mean writing to
    hundreds of notes to achieve nothing the user asked for — they chose "只移除词组，不动笔记".
    A leftover tag on old notes is inert: no book points at it any more, and the card picker
    selects by the catalogue entry, which is gone.
    """
    from . import word_book_store as store
    store.delete_book_file(root, book['id'])
    return {'untagged': 0, 'kept_notes': True, 'leftover_tag': book['tag']}
```

调用方（设置页/菜单）在 `remove_book` 之后再做 `cfg = unregister_book(cfg, book['id'])` 并保存配置——**登记移除与文件删除是两步，都不写 Anki**。

测试里 `test_removing_untags_and_never_deletes_notes_or_decks` 断言的是"删除词组对 Anki 零写操作"：

```python
class Remove(unittest.TestCase):
    def test_removing_a_book_writes_nothing_to_anki(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = WriterApi(notes=[{'noteId': 5, 'tags': ['zvr_book_x'],
                                    'fields': {'正面': {'value': 'notion'}}}])
            book = fresh_book(['notion'])
            book['tag'] = 'zvr_book_x'
            store.save_book(tmp, book)
            result = build.remove_book(book, tmp)
            self.assertEqual(result['kept_notes'], True)
            self.assertEqual(api.calls, [], 'removing a book must not write to Anki at all')
            self.assertFalse(store.book_path(tmp, book['id']).exists())

    def test_removal_works_even_for_a_book_with_no_notes_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = fresh_book(['notion'])
            store.save_book(tmp, book)
            self.assertEqual(build.remove_book(book, tmp)['untagged'], 0)
```

（`remove_book(book, root)` 因此**不接 api 参数**——一个用不到的参数就是"也许要写库"的邀请。Step 1 的测试代码已按这个签名写好。）

- [ ] **Step 4:** Run → PASS（25 条）。
- [ ] **Step 5: Commit（需授权）** `git commit -m "feat: append words to a book; removing a book never touches notes"`

---

### Task 10: 导出与导入词组文件

**Files:**
- Modify: `word_book_store.py`
- Test: `tests/test_word_book_store.py`（追加）

**Interfaces:**
- Produces: `export_book(book, path, include_meanings=False) -> dict`（返回写出的 dict，便于断言）、`import_book(path) -> book dict`（校验必备字段，`version` 过新则抛错）

- [ ] **Step 1: 写失败测试**

```python
class Share(unittest.TestCase):
    def test_export_defaults_to_words_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'out.json')
            written = store.export_book(book(), path)
            self.assertEqual([w['word'] for w in written['words']], ['notion', 'synthesize'])
            self.assertNotIn('meaning', written['words'][0])
            self.assertFalse(os.path.exists(path + '. meanings'))

    def test_an_explicit_full_export_carries_the_warning_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'out.json')
            written = store.export_book(book(), path, include_meanings=True)
            self.assertEqual(written['words'][0]['meaning'], 'n. 概念')
            self.assertIn('请勿公开分发', written['notice'])

    def test_import_round_trips_a_words_only_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'out.json')
            store.export_book(book(), path)
            again = store.import_book(path)
            self.assertEqual(again['name'], '论文核心词')
            self.assertEqual(again['source'], '自己整理的')

    def test_import_refuses_a_file_without_a_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'bad.json')
            item = book()
            item['source'] = ''
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(item, handle, ensure_ascii=False)
            with self.assertRaises(ValueError):
                store.import_book(path)

    def test_import_refuses_a_future_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'new.json')
            item = book()
            item['version'] = store.BOOK_VERSION + 3
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(item, handle, ensure_ascii=False)
            with self.assertRaises(ValueError):
                store.import_book(path)
```

测试文件顶部补 `import json`、`import tempfile`。

- [ ] **Step 2:** Run → FAIL。

- [ ] **Step 3: 实现**

```python
FULL_EXPORT_NOTICE = '含第三方词典释义，仅供自用备份，请勿公开分发。'


def export_book(book, path, include_meanings=False):
    """Shareable by default: words and metadata, no glosses.

    A word list is the user's own selection; the definitions beside it came from a dictionary
    someone else maintains. Exporting the pair and calling it shareable would be passing on
    content we do not own, so the full form exists only as a labelled personal backup.
    """
    words = []
    for item in book.get('words') or []:
        row = {'word': item['word'], 'state': item.get('state', 'pending')}
        if include_meanings:
            row['meaning'] = item.get('meaning', '')
            row['example'] = item.get('example', '')
        words.append(row)
    data = {'version': BOOK_VERSION, 'id': book['id'], 'name': book['name'],
            'created': book.get('created', ''), 'source': book.get('source', ''),
            'license': book.get('license', 'self'), 'words': words}
    if include_meanings:
        data['notice'] = FULL_EXPORT_NOTICE
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return data


def import_book(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    version = int(data.get('version') or 1)
    if version > BOOK_VERSION:
        raise ValueError('词组文件版本为 %d，当前插件只支持到 %d，请升级插件后再导入。' % (version, BOOK_VERSION))
    for key in ('name', 'words'):
        if not data.get(key):
            raise ValueError('词组文件缺少 %s 字段，无法导入。' % key)
    if not str(data.get('source') or '').strip():
        raise ValueError('词组文件没有来源说明（source），无法导入；请在创建时填写来源。')
    created = data.get('created') or _now()
    book = new_book(data['name'], data['source'], data.get('license') or 'unknown',
                    [{'word': row.get('word'), 'meaning': row.get('meaning', ''),
                      'example': row.get('example', '')} for row in data['words']],
                    created=created)
    book['id'] = data.get('id') or book['id']
    book['tag'] = book_tag(book['id'])
    book['deck'] = data.get('deck') or deck_name('自定义词组', book['name'])
    return book
```

- [ ] **Step 4:** Run → PASS（20 条 store 测试）。
- [ ] **Step 5: Commit（需授权）** `git commit -m "feat: export and import shareable word books"`

---

### Task 11: 设置页 UI（新建词组 → 预览 → 确认；我的词组管理；在线开关）

**Files:**
- Modify: `anki-global-addon/zotero_global_capture/__init__.py`（`DEFAULTS`、设置对话框、保存字典）
- Test: `tests/windows-word-books.py`（离屏 Qt）

**Interfaces:**
- Consumes: `word_lists.parse_words`、`word_book_store.new_book/save_book/register_book`、`word_book_build.build_book/gather_glosses`、`note_index.word_index`、模块级 `dictionary(word)`、`api(...)`、`mw.taskman.run_in_background`
- Produces: `BookWizardDialog(cfg, root, api, dictionary, on_done)`、`MyBooksPanel(cfg, root, on_change)`；配置键 `books_online_lookup`、`books_deck_prefix`

- [ ] **Step 1: 写失败测试**

创建 `tests/windows-word-books.py`，头部沿用现有离屏 harness（照抄 `tests/windows-spelling-hints.py` 的前 27 行 bootstrap，把 stub 的名字元组补上 `QPlainTextEdit`、`QFormLayout`、`QDialogButtonBox`、`QCheckBox`），并在 bootstrap 之后补上这段夹具：

```python
import tempfile
from pathlib import Path
from zotero_global_capture import word_book_store as store
from zotero_global_capture.book_dialog import preview_counts, BookWizardDialog

root_path = Path(tempfile.mkdtemp())
root = str(root_path)
cfg = {'model': '四六级单词模板', 'front_field': '正面', 'back_field': '解释',
       'books_online_lookup': True,
       'study_books': [{'id': 'cet6_core', 'name': '六级核心', 'tag': 'zvr_cet6_core'}]}
api = WriterApiStub()   # 见下：只实现 getActiveProfile / modelFieldNames / findNotes / notesInfo


class WriterApiStub:
    def __init__(self):
        self.calls = []

    def __call__(self, action, params):
        self.calls.append((action, params))
        if action == 'getActiveProfile':
            return 'Profile A'
        if action == 'modelFieldNames':
            return ['正面', '解释', '音标']
        if action == 'findNotes':
            return [1]
        if action == 'notesInfo':
            return [{'noteId': 1, 'tags': [], 'fields': {'正面': {'value': 'notion'}}}]
        raise AssertionError('unexpected action %s' % action)
```

（`WriterApiStub` 的定义要放在 `api = WriterApiStub()` 之前——Python 是顺序执行的。）

然后是要断言的六段：

```python
from zotero_global_capture.book_dialog import preview_counts, BookWizardDialog

# 1. 预览必须在任何写操作之前给出四个数
text = 'notion, synthesize\n中文\nschmuck\n'
preview = preview_counts(text, index={'exact': {'notion': [{'noteId': 1, 'tags': []}]}, 'lemma': {}},
                         glosses={'synthesize': {'meaning': 'v. 合成', 'phonetic': ''}})
assert preview == {'total': 3, 'tagged': 1, 'create': 1, 'pending': 1, 'dropped': ['中文']}, preview

# 2. 对话框：填名字与来源才能确认
dialog = BookWizardDialog(cfg, root, api=api, dictionary=lambda w: None)
dialog.name.setText('')
dialog.source.setText('')
assert dialog.can_confirm() is False, '名字和来源是必填的'
dialog.name.setText('我的词组')
assert dialog.can_confirm() is False
dialog.source.setText('自己整理的')
assert dialog.can_confirm() is True

# 3. 粘贴后预览数字出现在对话框里，且此时只有"读"操作，没有任何写操作
api.calls.clear()
dialog.words.setPlainText('notion, synthesize\nschmuck')
dialog.refresh_preview()
assert '共 3' in dialog.preview.text() and '待补 1' in dialog.preview.text(), dialog.preview.text()
assert [call[0] for call in api.calls] and not any(
    call[0] in ('addNote', 'addTags', 'createDeck') for call in api.calls), api.calls

# 4. 确认才真的建：词组文件落盘，配置目录里内置词书一个不少
saved = []
dialog.on_done = lambda book, cfg2: saved.append((book, cfg2))
dialog.confirm_import()
assert saved, '确认后必须回调'
book, merged = saved[0]
assert book['name'] == '我的词组' and book['source'] == '自己整理的'
ids = [b['id'] for b in merged['study_books']]
assert 'cet6_core' in ids and book['id'] in ids

# 5. 取消 = 什么都不写
before = list(root_path.glob('books/*.json'))
dialog2 = BookWizardDialog(cfg, root, api=lambda *a: None, dictionary=lambda w: None)
dialog2.words.setPlainText('notion')
dialog2.reject()
assert list(root_path.glob('books/*.json')) == before

# 6. 在线查词关掉时，预览把可建的词算进待补
offline = preview_counts('schmuck synthesize', index={'exact': {}, 'lemma': {}},
                         glosses={}, online=False)
assert offline['create'] == 0 and offline['pending'] == 2, offline
print('Qt: 词组向导先预览后写入，来源必填，取消不写库，内置词书不丢')
```

- [ ] **Step 2:** Run `python tests/windows-word-books.py` → FAIL（`book_dialog` 不存在）。

- [ ] **Step 3: 实现**

创建 `anki-global-addon/zotero_global_capture/book_dialog.py`（把对话框从 `__init__.py` 分离出去，因为 `__init__.py` 已经 1900+ 行）：

```python
"""The word-book wizard: preview before it writes, source is mandatory.

The preview exists because this is the one place the plug-in writes notes into the user's
collection in bulk. Showing 共 137 · 已有 96 · 新建 34 · 待补 5 · 忽略 2 *before* any write is
what makes "只移除词组，不动笔记" and "查不到就跳过" verifiable by the person doing it.
"""

from aqt.qt import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                    QPlainTextEdit, QPushButton, QVBoxLayout, Qt)

from .word_book_build import classify
from .word_book_store import new_book, register_book, save_book
from .word_lists import parse_words


def preview_counts(text, index, glosses, online=True):
    parsed = parse_words(text)
    entries = [{'word': word, 'meaning': '', 'example': ''} for word in parsed['words']]
    buckets = classify(entries, index, glosses if online else {})
    return {'total': len(entries), 'tagged': len(buckets['tagged']),
            'create': len(buckets['create']), 'pending': len(buckets['pending']),
            'dropped': parsed['dropped']}


class BookWizardDialog(QDialog):
    def __init__(self, cfg, root, api, dictionary, on_done=None, parent=None):
        super().__init__(parent)
        self.cfg, self.root, self.api, self.dictionary = dict(cfg), root, api, dictionary
        self.on_done = on_done
        self.setObjectName('bookWizard')
        self.setWindowTitle('新建词组')
        self.resize(560, 460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText('例如：论文核心词')
        self.source = QLineEdit()
        self.source.setPlaceholderText('必填：这份词表是怎么来的（自己整理 / 某书附录 / 网络词表…）')
        self.online = QCheckBox('库里没有的词，允许向有道词典在线查询释义')
        self.online.setChecked(bool(cfg.get('books_online_lookup', True)))
        form.addRow('词组名称', self.name)
        form.addRow('来源', self.source)
        form.addRow(self.online)
        layout.addLayout(form)
        self.words = QPlainTextEdit()
        self.words.setPlaceholderText('一行一个单词，或用逗号、制表符分隔')
        layout.addWidget(self.words)
        self.preview = QLabel('粘贴后点「预览」')
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        self.preview_button = QPushButton('预览')
        self.preview_button.setObjectName('previewBook')
        self.preview_button.clicked.connect(self.refresh_preview)
        self.confirm_button = QPushButton('创建并导入')
        self.confirm_button.setObjectName('confirmBook')
        self.confirm_button.clicked.connect(self.confirm_import)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(self.preview_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.confirm_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.last = None

    def can_confirm(self):
        return bool(self.name.text().strip()) and bool(self.source.text().strip())

    def refresh_preview(self):
        from .note_index import word_index
        from .word_book_build import bundled_glosses
        index = word_index(self.api, self.cfg)
        self.last = preview_counts(self.words.toPlainText(), index, bundled_glosses(),
                                   online=self.online.isChecked())
        self.preview.setText('共 %d 个词 · 库里已有 %d（只打标签）· 需新建 %d · 待补 %d · 不像单词 %d'
                             % (self.last['total'], self.last['tagged'], self.last['create'],
                                self.last['pending'], len(self.last['dropped'])))
        return self.last

    def confirm_import(self):
        if not self.can_confirm():
            self.preview.setText('词组名称和来源都要填。')
            return False
        preview = self.refresh_preview()
        entries = [{'word': word, 'meaning': '', 'example': ''} for word in parse_words(self.words.toPlainText())['words']]
        book = new_book(self.name.text(), self.source.text(), 'self', entries)
        merged = register_book(self.cfg, book)
        save_book(self.root, book)
        if self.on_done:
            self.on_done(book, merged)
        self.accept()
        return True
```

`__init__.py` 里 `DEFAULTS` 补两键、设置页在「我的词组」区放一个「新建词组…」按钮打开这个对话框、保存字典里写回 `study_books`/`books_online_lookup`/`books_deck_prefix`：

```python
    "books_online_lookup": True,
    "books_deck_prefix": "自定义词组",
```

- [ ] **Step 4:** Run `python tests/windows-word-books.py` → PASS（6 段）。
- [ ] **Step 5:** Run `python tests/run-windows-checks.py` → 23/23 全过（新检查计入）。
- [ ] **Step 6: Commit（需授权）** `git commit -m "feat: word book wizard with a preview before it writes"`

---

### Task 12: 菜单入口、README、出厂配置

**Files:**
- Modify: `__init__.py`（`menu_action()` 的「词书与词表管理」子菜单）
- Modify: `anki-global-addon/README.md`
- Modify: `anki-global-addon/zotero_global_capture/config.json`
- Test: `tests/windows-tools-menu.py`（追加断言）

- [ ] **Step 1: 改离屏检查，让它先红**

在 `tests/windows-tools-menu.py` 的"维护七项"断言之后追加：

```python
# 用户词组的三项必须在「词书与词表管理」子菜单里，顶层仍然只有两条
for label in ('新建词组…', '导入词组文件…', '导出当前词组…'):
    assert label in manage_labels, (label, manage_labels)
assert len(top_labels) == 2, top_labels
assert len(manage_labels) == 10, manage_labels   # 原 7 项 + 新 3 项
```

Run: `python tests/windows-tools-menu.py` → FAIL。

- [ ] **Step 2: 实现菜单**

`__init__.py` 的 `menu_action()` 里，在 `manage = review_menu.addMenu("词书与词表管理")` 之后追加三项，处理函数分别打开 `BookWizardDialog`、`QFileDialog.getOpenFileName` + `import_book`、`QFileDialog.getSaveFileName` + `export_book`：

```python
    new_book_action = manage.addAction("新建词组…")
    new_book_action.triggered.connect(lambda: open_book_wizard())
    import_book_action = manage.addAction("导入词组文件…")
    import_book_action.triggered.connect(lambda: import_book_dialog())
    export_book_action = manage.addAction("导出当前词组…")
    export_book_action.triggered.connect(lambda: export_book_dialog())
```

三个函数都只做"取文件路径 → 调 `word_book_store` → 用 `show_feedback` 报结果"，写入走 `mw.taskman.run_in_background`，**槽里不同步调 api**（Global Constraints）。

- [ ] **Step 3:** Run `python tests/windows-tools-menu.py` → PASS；`python tests/run-windows-checks.py` → 23/23。

- [ ] **Step 4: README 与出厂配置**

`README.md` 在词书段落后加一段（内容照 spec §0/§5/§7 的口径）：用户可自建词组，四种入口，已有词只打标签、缺词按内置→在线→跳过，删除只移除词组不动笔记，导出默认不含释义。`config.json` 补 `"books_online_lookup": true, "books_deck_prefix": "自定义词组"`。

- [ ] **Step 5:** Run `python -m pytest tests -q && node --test tests/plugin.test.cjs` → 全绿。
- [ ] **Step 6: Commit（需授权）** `git commit -m "feat: word book menu entries and documentation"`

---

### Task 13: 全量验证、部署、加载、文档回灌

**Files:**
- Modify: `AUDIT-2026-10-30.md`（新增 §9.38）
- Modify: `HANDOFF.md`（§3 现状、§4 已拍板新增一条）

- [ ] **Step 1: 三套闸门**

```bash
python -m pytest tests -q                 # 期望 ≥ 291 passed
node --test tests/plugin.test.cjs         # 26 pass
python tests/run-windows-checks.py        # 23/23
```

- [ ] **Step 2: 部署**

```bash
STAMP=$(date +%Y%m%d-%H%M%S)
DEST="$APPDATA/Anki2/addons21/zotero_global_capture"
BK="deployment-backups/pre-deploy-$STAMP"; mkdir -p "$BK"
for f in __init__.py review_popup.py config.json; do cp "$DEST/$f" "$BK/$f"; done
SRC=anki-global-addon/zotero_global_capture
cp "$SRC"/note_index.py "$SRC"/word_lists.py "$SRC"/word_book_store.py \
   "$SRC"/word_book_build.py "$SRC"/book_dialog.py "$SRC"/__init__.py \
   "$SRC"/core_import.py "$SRC"/cet6_books.py "$SRC"/config.json "$DEST"/
python tools/verify-state.py | sed -n '/== deployed/,/== config/p'
```
Expected: 所有文件 match（除 `kyle_enrich.py` 仍 ABSENT，属已知）。

- [ ] **Step 3: 重启并确认加载**

```bash
python tools/restart-anki.py --wait 300
python tools/verify-state.py | sed -n '/== loaded/,/== config/p'
```
Expected: `closed politely in N s`（走托盘协议，无强杀）；`after restart` 计数与 baseline 一致；loaded 层显示"add-on start 晚于所有安装文件"。

- [ ] **Step 4: 真机冒烟（用户参与，5 分钟）**

请用户在 Anki 里：工具 → 单词随身复习 → 词书与词表管理 → 新建词组… → 粘 20 个词（含 2 个库里已有的、2 个查不到释义的）→ 预览 → 创建 → 设置里选中该词组 → 立即弹出一张。验收点：眉标显示新词书名与进度；预览数字与实际相符；待补的词没有变成空卡；删除词组后笔记与复习进度都在。

- [ ] **Step 5: 文档回灌**

AUDIT 新增 §9.38：做了什么、为什么这么分（三个新模块的职责边界）、踩到的事实（`study_books` 覆盖陷阱、`findCards` 分页、有道限流停止阈值）、测试与部署时间戳、待真屏验收项。HANDOFF §3 顶部加一条本轮摘要，§4 加一条已拍板：**"删词组只移除标签登记与文件，绝不调用 deleteNotes/deleteDeck；已有笔记不移动牌组"**。

- [ ] **Step 6: Commit（需授权）** `git commit -m "docs: record user word books (AUDIT §9.38)"`

---

## Self-Review 记录

- **Spec 覆盖**：P0 条目（粘贴、文件、build_book、追加/删除、在线开关、导出/导入、UI、菜单）分别由 Task 2/3、3、6–8、9、8、10、11、12 覆盖；§5.3（现有标签/牌组）与 §9 的 verify-state 认识用户词组属 P1，本计划不含，已在标题下声明。
- **占位符**：无 TBD/TODO。Task 9 的 `remove_book` 定成 `remove_book(book, root)`，不接 `api` —— 用不到的参数就是"也许要写库"的邀请，测试 `api.calls == []` 把这条钉住。
- **类型一致性**：`classify` 返回 `{'tagged','create','pending'}`（Task 6）与 `build_book` 消费一致；`build_book` 返回 `{'tagged','created','pending','failed','deck'}`（Task 7）被 Task 9 的 `append_words` 原样透传；`store.new_book/register_book/save_book/import_book/export_book` 的签名在 Task 4/5/10 之间一致；`preview_counts` 的返回键与 Task 11 测试断言一致。
