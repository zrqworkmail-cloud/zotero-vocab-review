"""Build lexicon/mnemonics.tsv from the locally supplied KyleBing dumps.

Why a table instead of generating text: the dataset already carries a root
decomposition + mnemonic per word (`content.word.content.remMethod.val`) under a
BSD-3-Clause licence, and it is on this machine. 6874 of 13159 entries have one. Shipping
that is honest and reviewable; inventing 5000 etymologies is neither.

The output is one line per word, `word<TAB>mnemonic`, sorted, with the longer variant kept
when 四级 and 六级 disagree. Values were checked to contain no tabs or newlines.

    python tools/build-mnemonics-lexicon.py [source-dir]
"""
import io, json, os, shutil, sys

SOURCE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    '..', 'zotero-vocab-review', 'english-vocabulary-KyleBing'))
FILES = ('六级-完整.jsonl', '四级-完整.jsonl')
OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                       'anki-global-addon', 'zotero_global_capture', 'lexicon'))
OUT = os.path.join(OUT_DIR, 'mnemonics.tsv')


def clean(value):
    return ' '.join(str(value or '').split()).strip()


table = {}
counts = {}
for name in FILES:
    path = os.path.join(SOURCE, name)
    if not os.path.exists(path):
        raise SystemExit('missing source file: %s' % path)
    total = hits = 0
    with io.open(path, encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            total += 1
            word = clean(item.get('headWord'))
            content = item.get('content', {}).get('word', {}).get('content', {})
            entry = content.get('remMethod') or {}
            value = clean(entry.get('val'))
            if not word or not value:
                continue
            hits += 1
            if '\t' in value or '\n' in value:
                raise SystemExit('tab/newline slipped into %s: %r' % (word, value))
            best = table.get(word.casefold(), '')
            if len(value) > len(best):
                table[word.casefold()] = value
    counts[name] = (total, hits)

with io.open(OUT, 'w', encoding='utf-8', newline='\n') as stream:
    for word in sorted(table):
        stream.write('%s\t%s\n' % (word, table[word]))

licence = os.path.join(SOURCE, 'LICENSE')
if os.path.exists(licence):
    shutil.copyfile(licence, os.path.join(OUT_DIR, 'KYLEBING_LICENSE'))

print('source:', SOURCE)
for name, (total, hits) in counts.items():
    print('  %-16s %5d entries, %5d with 记忆法' % (name, total, hits))
print('wrote %s: %d words, %.1f KB' % (OUT, len(table), os.path.getsize(OUT) / 1024.0))
print('licence copied to KYLEBING_LICENSE' if os.path.exists(licence) else 'NO LICENSE FOUND')
