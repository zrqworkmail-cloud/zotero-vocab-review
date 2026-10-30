"""Prepare an isolated Zotero test profile. Run only while that test instance is closed."""
import argparse
import json
import os
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--windows-root', help='Windows path to runtime-verification when running from WSL')
parser.add_argument('--startup-only', action='store_true', help='Only test startup and lemma data, without modifying Anki')
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
base = root / 'runtime-verification'
profile = base / 'profile'
marker = base / '.zvr-isolated-profile'
if profile.exists() and not marker.exists():
    raise SystemExit('Refusing to reuse an unmarked profile directory')
profile.mkdir(parents=True, exist_ok=True)
(profile / 'extensions').mkdir(exist_ok=True)
(base / 'data').mkdir(exist_ok=True)
marker.write_text('ZVR_ISOLATED_RUNTIME_TEST')
winbase = args.windows_root
if not winbase:
    winbase = str(base) if os.name == 'nt' else subprocess.check_output(['wslpath', '-w', str(base)], text=True).strip()
prefs = {
    'extensions.zotero.useDataDir': True, 'extensions.zotero.dataDir': winbase + '\\data',
    'extensions.zotero.firstRun2': False, 'extensions.zotero.sync.autoSync': False,
    'extensions.zotero.httpServer.enabled': True, 'extensions.zotero.httpServer.port': 23129,
    'extensions.autoDisableScopes': 0, 'extensions.update.enabled': False, 'app.update.auto': False,
    'toolkit.telemetry.enabled': False,
}
(profile / 'prefs.js').write_text('\n'.join(f'user_pref({json.dumps(k)}, {json.dumps(v)});' for k, v in prefs.items()) + '\n')
(base / 'fixture.pdf').write_bytes(b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n')
manifest = json.loads((root / 'manifest.json').read_text())
with ZipFile(profile / 'extensions' / (manifest['applications']['zotero']['id'] + '.xpi'), 'w', ZIP_DEFLATED) as archive:
    archive.write(root / 'manifest.json', 'manifest.json')
    test_script = 'tests/zotero-lemma-runtime.js' if args.startup_only else 'tests/zotero-runtime.js'
    archive.writestr('bootstrap.js', (root / 'bootstrap.js').read_text() + '\n' + (root / test_script).read_text())
    for name in ['lemma-data.js', 'prefs.xhtml', 'prefs.js', 'icons/icon-48.png', 'icons/icon-96.png', 'LICENSE']:
        archive.write(root / name, name)
print(base)
