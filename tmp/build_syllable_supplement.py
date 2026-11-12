"""Build lexicon/syllables_supplement.txt from the full Moby Hyphenator II.

The shipped syllables.txt is a 25k common-word filter; 104 shipped-book words
are missing from it. This extracts the written syllable breaks for the words
the full public-domain Moby list covers. Words it does not cover are verified
against dictionaries separately and appended by hand with their sources.

Source: tmp/mhyph.txt, downloaded 2026-11-10 from
https://raw.githubusercontent.com/elitejake/Moby-Project/main/Moby%20Hyphenator%20II/mhyph.txt
(Grady Ward's Moby Hyphenator II, public domain; 187,175 entries, latin-1,
syllable separator byte 0xA5).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
missing = [w.strip() for w in (ROOT / 'tmp' / 'missing_syllables.txt').read_text(encoding='utf-8').splitlines() if w.strip()]

moby = {}
for line in (ROOT / 'tmp' / 'mhyph.txt').read_text(encoding='latin-1').splitlines():
    parts = line.strip().split('\xa5')
    if len(parts) > 1 and all(p.isalpha() for p in parts):
        moby.setdefault(''.join(parts).casefold(), tuple(p.casefold() for p in parts))

found = sorted((w, moby[w.casefold()]) for w in missing if w.casefold() in moby)
rest = [w for w in missing if w.casefold() not in moby]

header = """# Supplement to syllables.txt: written syllable breaks for shipped-book words
# the 25k common-word list misses. Same ';' format; the word is the parts joined.
# Section 1 - Moby Hyphenator II (Grady Ward, public domain), full 187,175-entry
# list via https://github.com/elitejake/Moby-Project ("Moby Hyphenator II/mhyph.txt"),
# retrieved 2026-11-10. Same lineage as syllables.txt. %d words.
""" % len(found)
body = '\n'.join(';'.join(parts) for _word, parts in found) + '\n'
out = ROOT / 'anki-global-addon' / 'zotero_global_capture' / 'lexicon' / 'syllables_supplement.txt'
out.write_text(header + body, encoding='utf-8')
print('wrote %s: %d divisions' % (out, len(found)))
print('still missing (%d): %s' % (len(rest), ', '.join(rest)))