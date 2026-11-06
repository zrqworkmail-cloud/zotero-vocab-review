"""Assemble tests/windows-mnemonic-block.py: audio harness + the mnemonic body."""
import io, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SOURCE = os.path.join(ROOT, 'tests', 'windows-question-audio.py')
BODY = r'C:\tmp\mnemonic_body.py'
DEST = os.path.join(ROOT, 'tests', 'windows-mnemonic-block.py')

LINES = [
    'The card paints the mnemonic block from the shipped table, and stays silent without a row.',
    '',
    'The harness is copied from windows-question-audio.py so the stubbed speech, the config and',
    'the import dance cannot drift. What is pinned is the visible half of the 2026-11-06 change:',
    'a word the table knows gets the block with its decomposition inside, and a word it does not',
    'know gets no block at all -- not an empty frame.',
]
DOC = '"""' + '\n'.join(LINES) + '\n"""\n'

head = io.open(SOURCE, encoding='utf-8').read().split('# 1. ')[0]
if head.lstrip().startswith('"""'):
    head = head.split('"""', 2)[2].lstrip('\n')
glue = ('from zotero_global_capture.review_logic import mnemonic_for as env_mnemonic, '
        'question_mnemonic as env_question_mnemonic\n')
io.open(DEST, 'w', encoding='utf-8', newline='\n').write(
    DOC + head + glue + io.open(BODY, encoding='utf-8').read())
print('wrote', DEST)
