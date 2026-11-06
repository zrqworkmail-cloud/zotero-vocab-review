"""Proof that the ribbon really was eating the letters, and that the new layout does not.

Reverting `geometry`'s ribbon placement to the old `centre.y() + pixel * 0.80` fraction must
make `windows-card-motion.py` section 3d go red; this prints both numbers side by side so the
claim is arithmetic, not a screenshot.
"""
import importlib.util
import os
import sys
import types

BASE = r'D:\Program Files (x86)\Anki\app_packages'
sys.path.insert(0, BASE)
os.environ['PATH'] = ';'.join([os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'), os.path.dirname(BASE),
                               os.path.join(os.environ['SystemRoot'], 'System32')])
os.add_dll_directory(os.path.join(BASE, 'PyQt6', 'Qt6', 'bin'))
os.add_dll_directory(os.path.dirname(BASE))
import ctypes
ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))
os.environ['QT_PLUGIN_PATH'] = os.path.join(BASE, 'PyQt6', 'Qt6', 'plugins')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

app = QApplication([])
SOURCE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'anki-global-addon',
                                      'zotero_global_capture'))
package = types.ModuleType('zvr_probe')
package.__path__ = [SOURCE]
sys.modules['zvr_probe'] = package


def load(name):
    spec = importlib.util.spec_from_file_location('zvr_probe.' + name,
                                                  os.path.join(SOURCE, name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules['zvr_probe.' + name] = module
    spec.loader.exec_module(module)
    return module


card_motion = load('card_motion')
badge = load('candy_badge')
centre = QPoint(255, 270)
print('%-13s %6s %11s %11s %9s %11s' % ('word', 'pixel', 'word_bottom', 'OLD top',
                                         'overlap', 'NEW top'))
for tier in (1, 2, 3, 4):
    word = card_motion.tier_caption(tier)
    pixel = badge.fit_pixel(word, 510 * 0.78)
    geo = badge.geometry(word, pixel, centre)
    band = pixel * badge.RIBBON_HEIGHT * 2.2
    old_top = centre.y() + pixel * 0.80 - band
    print('%-13s %6.1f %11.1f %11.1f %9.1f %11.1f  %s'
          % (word, pixel, geo['word_bottom'], old_top, geo['word_bottom'] - old_top,
             geo['ribbon_top'], 'OLD COVERED THE LETTERS' if old_top < geo['word_bottom']
             else 'old was clear'))
