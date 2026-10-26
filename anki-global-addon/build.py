"""Build the Windows global-capture Anki add-on ZIP."""

from pathlib import Path
import hashlib
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "zotero_global_capture"
OUTPUT = ROOT / "dist" / "zotero_global_capture.zip"


def build():
    files = sorted(path for path in SOURCE.rglob("*") if path.is_file())
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
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    (OUTPUT.parent / "SHA256SUMS").write_text(f"{digest}  {OUTPUT.name}\n", encoding="utf-8")
    print(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    build()
