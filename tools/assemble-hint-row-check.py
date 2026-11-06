"""Assemble tests/windows-hint-row.py from the audio check's harness plus the new body.

The preamble is copied rather than retyped so the fixture card, the stubbed speech and the
config cannot drift from windows-question-audio.py; only the docstring is rewritten.
"""
import io, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SOURCE = os.path.join(ROOT, 'tests', 'windows-question-audio.py')
BODY = r'C:\tmp\hint_body.py'
DEST = os.path.join(ROOT, 'tests', 'windows-hint-row.py')

DOC = '"""' + '''The hint row of the spelling and listening cards, laid out as the learner reads it.

Built on the same harness as windows-question-audio.py (its preamble is copied here, so the
fixture card, the stubbed speech and the config cannot drift from that check). What is pinned
is the 2026-11-06 redesign: aids as quiet text under the letter boxes, 检查拼写 as the only
filled control on its own line, the two ways out of a card together in the foot, and the
transcription one tap away for anyone who cannot hear the audio -- priced as a hint.
''' + '"""' + '\n'

head = io.open(SOURCE, encoding='utf-8').read().split('# 1. ')[0]
if head.lstrip().startswith('"""'):
    head = head.split('"""', 2)[2].lstrip('\n')
body = io.open(BODY, encoding='utf-8').read()
io.open(DEST, 'w', encoding='utf-8', newline='\n').write(DOC + head + body)
print('wrote', DEST)
