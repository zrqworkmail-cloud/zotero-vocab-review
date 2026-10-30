"""Build the Windows global-capture Anki add-on ZIP."""

from pathlib import Path
import hashlib
import json
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "zotero_global_capture"
OUTPUT = ROOT / "dist" / "zotero_global_capture.zip"


def build():
    files = sorted(path for path in SOURCE.rglob("*")
                   if path.is_file() and "__pycache__" not in path.parts and "user_files" not in path.parts and path.suffix != ".pyc")
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
    manifest = {'package': 'zotero_global_capture', 'name': '单词随身复习与全局划词'}
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
