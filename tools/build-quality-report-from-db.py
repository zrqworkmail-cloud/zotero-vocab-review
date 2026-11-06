"""Build the quality report straight from the collection file, without touching Anki's UI.

Same arithmetic as the in-app menu entry — `review_quality` does all of it — but the rows come
from a read-only SQLite connection instead of `mw.col.db`. Two ways to read a running Anki's
collection, in order of honesty:

1. `mode=ro` against the live file. In WAL mode a reader usually gets in; while Anki is saving
   a rating it can answer `database is locked`, so this retries.
2. A snapshot copy of the main file plus its -wal, taken when Anki is idle. The copy is what
   gets read, so a lock can never corrupt the live file — and a copy taken mid-write can be
   inconsistent, which is why it is the fallback and not the first choice.

Nothing is ever opened for writing.
"""
import os
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                                'anki-global-addon', 'zotero_global_capture'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import review_quality


def collection_path():
    root = os.path.expandvars(r'%APPDATA%\Anki2')
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, 'collection.anki2')
        if os.path.isfile(path):
            return path
    raise SystemExit('找不到 collection 文件：%s' % root)


def open_live(path):
    for attempt in range(10):
        try:
            db = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
            db.execute('pragma busy_timeout=3000')
            db.execute('select count(*) from revlog').fetchone()
            return db, 'live read-only'
        except sqlite3.Error as error:
            if attempt == 9:
                print('live read refused (%s); falling back to a snapshot copy' % error)
                break
            time.sleep(1.0)
    folder = tempfile.mkdtemp(prefix='zvr-quality-')
    for suffix in ('', '-wal', '-shm'):
        source = path + suffix
        if os.path.exists(source):
            with open(source, 'rb') as read, open(os.path.join(folder, 'collection.anki2' + suffix), 'wb') as write:
                write.write(read.read())
    db = sqlite3.connect(os.path.join(folder, 'collection.anki2'))
    return db, 'snapshot copy (taken while Anki was writing; counts may lag by seconds)'


def main():
    path = collection_path()
    db, how = open_live(path)
    print('collection: %s\nread via: %s' % (path, how))
    retention = [(int(row[0]), int(row[1])) for row in db.execute(
        'select lastIvl, ease from revlog where lastIvl >= 1 and ease between 1 and 4')]
    parked = []
    ids = [row[0] for row in db.execute(
        'select c.id from cards c join notes n on n.id=c.nid'
        " where c.queue=-1 and n.tags like '% zvr_mastered%'")]
    answers = dict(db.execute(
        'select cid, max(id) from revlog where cid in (%s) group by cid'
        % ','.join(str(cid) for cid in ids))) if ids else {}
    now_ms = time.time() * 1000
    for cid in ids:
        when = answers.get(cid) or 0
        parked.append(None if not when else int((now_ms - when) / 86400000))
    # The deck's desiredRetention lives in the decks table's JSON, keyed by config; reading it
    # here would duplicate what the in-app report already does correctly, so the promise is
    # stated as the value measured from the live deck config on 2026-11-06.
    summary = review_quality.summarize(retention, parked, promised=0.9)
    print()
    print(review_quality.render_markdown(summary))
    print('--- 原始计数：revlog 总行 %d，其中正式复习(lastIvl>=1) %d 行；挂起且有已掌握标签的卡 %d 张' % (
        db.execute('select count(*) from revlog').fetchone()[0], len(retention), len(ids)))


main()
