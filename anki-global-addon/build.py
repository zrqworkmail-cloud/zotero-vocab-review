"""Build the Windows global-capture Anki add-on ZIP."""

from pathlib import Path
import hashlib
import json
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "zotero_global_capture"
OUTPUT = ROOT / "dist" / "zotero_global_capture.zip"

# Anki manifest fields. Keep ADDON_VERSION in sync with the repository's
# manifest.json; test_anki_installer enforces that equality. Anki calls the
# display version "human_version"; an unknown "version" key would be ignored.
ADDON_VERSION = "0.4.0-beta.10"
# Anki's int_version() is YYMMPP (26.9.3 -> 260903). Only 26.9.3 is in the
# tested compatibility matrix; a negative max_point_version is a hard upper bound.
MIN_POINT_VERSION = 260903
MAX_POINT_VERSION = -260903
EXCLUDED_FILES = {"kyle_enrich.py", "kyle_books.py"}


def build():
    files = sorted(path for path in SOURCE.rglob("*")
                   if path.is_file() and path.name not in EXCLUDED_FILES
                   and "__pycache__" not in path.parts and "user_files" not in path.parts and path.suffix != ".pyc")
    if not files:
        raise RuntimeError("Anki add-on source directory is empty")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for path in files:
            name = path.relative_to(ROOT).as_posix()
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    installer = OUTPUT.with_suffix('.ankiaddon')
    manifest = {
        'package': 'zotero_global_capture',
        'name': '单词随身复习与全局划词',
        'human_version': ADDON_VERSION,
        'min_point_version': MIN_POINT_VERSION,
        'max_point_version': MAX_POINT_VERSION,
    }
    with ZipFile(installer, 'w', ZIP_DEFLATED) as archive:
        for name, data in [('manifest.json', (json.dumps(manifest, ensure_ascii=False) + '\n').encode('utf-8'))] + [
            (path.relative_to(SOURCE).as_posix(), path.read_bytes()) for path in files
        ]:
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    sums = ''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in (OUTPUT, installer))
    (OUTPUT.parent / "SHA256SUMS").write_text(sums, encoding="utf-8")
    print(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    build()
