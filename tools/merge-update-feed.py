"""Merge a release into an existing feed without discarding older compatible releases."""
import argparse
import json
from pathlib import Path


def merge_feed(generated, destination):
    incoming = json.loads(generated.read_text())
    current = json.loads(destination.read_text()) if destination.exists() else {'addons': {}}
    for plugin_id, payload in incoming['addons'].items():
        previous = current['addons'].get(plugin_id, {}).get('updates', [])
        versions = {entry['version']: entry for entry in previous}
        versions.update({entry['version']: entry for entry in payload['updates']})
        current['addons'][plugin_id] = {'updates': list(versions.values())}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(current, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('generated', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    merge_feed(args.generated, args.destination)
