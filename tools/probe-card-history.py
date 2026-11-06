"""Read-only: when did the learner actually meet this word, and what is the due pile made of?

The card on screen says 到期复习 for a word the user does not remember studying, so the two
questions are separate: what does Anki's own schedule say about this card (queue / due / reps
/ lapses / when it was first answered), and how many of the cards that are due right now have
ever been answered at all.

Opens the live collection with `mode=ro` only; SQLite readers do not block a running Anki,
and nothing here writes.
"""
import json
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def connect():
    """A running Anki holds the write lock in bursts; retry instead of giving up."""
    import os
    root = os.path.expandvars(r'%APPDATA%\Anki2')
    for name in os.listdir(root):
        path = os.path.join(root, name, 'collection.anki2')
        if os.path.isfile(path):
            return sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    raise SystemExit('no collection found')


def rows(db, sql, args=()):
    """A live Anki locks the collection in bursts while it saves ratings; retry the read."""
    for attempt in range(20):
        try:
            return list(db.execute(sql, args))
        except sqlite3.OperationalError as error:
            if 'locked' not in str(error) or attempt == 19:
                raise
            time.sleep(1.5)


def front_index(db, model_name):
    """Which position in notes.flds holds the word, for this note type."""
    for mid, fname, flds in rows(db, 'select id, name, flds from models'):
        if model_name in fname:
            for index, field in enumerate(json.loads(flds)):
                if field['name'] in ('单词', 'Word', 'word'):
                    return mid, index, field['name']
    raise SystemExit('note type not found')


def day_start(now=None):
    """Anki rolls the day at 4am; use the same boundary or 'today' means the wrong pile."""
    now = now or time.time()
    shifted = time.localtime(now - 4 * 3600)
    return int(time.mktime((shifted.tm_year, shifted.tm_mon, shifted.tm_mday, 4, 0, 0, 0, 0, -1)))


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else 'jeopardize'
    tag = sys.argv[2] if len(sys.argv) > 2 else 'zvr_cet6_full'
    db = connect()
    mid, index, field_name = front_index(db, '四六级单词模板')
    print('note type mid=%s  word field #%d (%s)' % (mid, index, field_name))

    cards = rows(db,
        'select c.id, c.nid, c.queue, c.type, c.due, c.ivl, c.reps, c.lapses, c.factor,'
        ' c.created, c.mod, c.did, c.left, n.flds from cards c join notes n on n.id=c.nid'
        ' where n.mid=? and n.tags like ?', (mid, '%' + tag + '%'))
    print('book cards: %d' % len(cards))
    wanted = [row for row in rows if row[12].split('\x1f')[index].strip().lower() == word.lower()]
    if not wanted:
        print('no card whose %s is exactly %r' % (field_name, word))
        return
    start = day_start()
    for card_id, nid, queue, ctype, due, ivl, reps, lapses, factor, created, mod, did, left, flds in wanted:
        deck = rows(db, 'select name from decks where id=?', (did,))[0][0]
        first = rows(db, 'select min(date), count(*) from revlog where cid=?', (card_id,))[0]
        print('\n=== %s  cid=%s' % (word, card_id))
        print('  deck=%s queue=%s type=%s due=%s ivl=%s reps=%s lapses=%s left=%s ease=%d%%' % (
            deck, queue, ctype, due, ivl, reps, lapses, left, factor / 10))
        print('  created=%s  last-modified=%s' % (
            time.strftime('%Y-%m-%d %H:%M', time.localtime(created)),
            time.strftime('%Y-%m-%d %H:%M', time.localtime(mod))))
        print('  first answer=%s  answers total=%s' % (
            time.strftime('%Y-%m-%d %H:%M', time.localtime(first[0])) if first[0] else 'never',
            first[1]))
        print('  revlog (newest first):')
        for when, rating, last_ivl, new_ivl, ms in rows(
                db, 'select date, rating, lastIvl, ivl, time from revlog where cid=?'
                    ' order by date desc limit 12', (card_id,)):
            print('    %s  rating=%s  %s->%sd  %dms' % (
                time.strftime('%Y-%m-%d %H:%M', time.localtime(when)), rating, last_ivl, new_ivl, ms))

    now = int(time.time())
    day0 = rows(db, 'select crt from col')[0][0]
    today = (day_start(now) - day0) // 86400

    def is_due(row):
        """queue 1/3 counts down in seconds, queue 2 in day numbers — never compare them alike."""
        queue, due = row[2], row[4]
        return (due <= now) if queue in (1, 3) else (due <= today) if queue == 2 else False

    due_now = [row for row in cards if is_due(row)]
    seen = sum(1 for row in due_now if row[6] > 0)
    once = sum(1 for row in due_now if row[6] == 1)
    never = sum(1 for row in due_now if row[6] == 0)
    today_only = sum(1 for row in due_now if (row[4] >= start if row[2] in (1, 3) else row[4] == today))
    print('\n=== the pile that is due right now (book tag only)')
    print('  due=%d  answered at least once=%d  never answered=%d  seen exactly once=%d' % (
        len(due_now), seen, never, once))
    print('  of those, cards whose next step lands inside today (4am boundary): %d' % today_only)
    buckets = {}
    for row in due_now:
        buckets[min(row[6], 5)] = buckets.get(min(row[6], 5), 0) + 1
    print('  reps histogram (5 means 5+): %s' % sorted(buckets.items()))


main()
