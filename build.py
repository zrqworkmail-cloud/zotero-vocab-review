"""Build a reproducible XPI and Zotero update manifest, without contacting GitHub."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

FILES = ('manifest.json', 'bootstrap.js', 'lemma-data.js', 'prefs.xhtml', 'prefs.js', 'icons/icon-48.png', 'icons/icon-96.png', 'LICENSE', 'THIRD-PARTY-NOTICES.md')


def build_release(root, repository, output):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Repository must be owner/name')
    manifest = json.loads((root / 'manifest.json').read_text())
    version = manifest['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-beta\.\d+)?', version):
        raise ValueError('Expected x.y.z or x.y.z-beta.n version')
    if f'const PLUGIN_VERSION = "{version}";' not in (root / 'bootstrap.js').read_text():
        raise ValueError('Source and manifest versions differ')
    feed = 'updates-beta.json' if '-beta.' in version else 'updates.json'
    manifest['homepage_url'] = f'https://github.com/{repository}'
    compatibility = manifest['applications']['zotero']
    compatibility['update_url'] = f'https://raw.githubusercontent.com/{repository}/updates/{feed}'
    output.mkdir(parents=True, exist_ok=True)
    package = output / f'zotero-vocab-review-{version}.xpi'
    with ZipFile(package, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            data = (json.dumps(manifest, indent=2) + '\n').encode() if name == 'manifest.json' else (root / name).read_bytes()
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    (output / 'SHA256SUMS').write_text(f'{digest}  {package.name}\n')
    update = {'version': version, 'update_link': f'https://github.com/{repository}/releases/download/v{version}/{package.name}',
              'update_hash': f'sha256:{digest}', 'applications': {'zotero': {
                  key: compatibility[key] for key in ('strict_min_version', 'strict_max_version')}}}
    (output / feed).write_text(json.dumps({'addons': {compatibility['id']: {'updates': [update]}}}, indent=2) + '\n')
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, help='GitHub owner/repository')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    print(build_release(root, args.repository, args.output or root / 'dist'))
