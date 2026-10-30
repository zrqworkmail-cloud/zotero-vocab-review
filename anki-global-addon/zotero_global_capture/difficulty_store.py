"""Keep local selection weights without altering Anki scheduling data."""
import json
import os
import tempfile
from pathlib import Path


def load(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, int) or not 0 <= v <= 20 for k, v in data.items()):
            raise ValueError('Invalid difficulty data')
        return data
    except (OSError, ValueError, TypeError) as error:
        raise ValueError('Unable to read difficulty data') from error


def record(path, card_id, hints, wrong_letters, failed_checks, ease):
    path = Path(path)
    data = load(path)
    key = str(card_id)
    old = data.get(key, 0)
    if ease == 1:
        delta = max(1, min(10, hints * 2 + wrong_letters + failed_checks * 2))
        data[key] = min(20, old + delta)
    elif not hints and not wrong_letters and not failed_checks:
        if old <= 1:
            data.pop(key, None)
        else:
            data[key] = old - 1
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            name = handle.name
            json.dump(data, handle, ensure_ascii=False, sort_keys=True)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
