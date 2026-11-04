"""One lever per signal: the word is made loud either by the render stage or by the player.

The user's verdict on the first loud version was 好难听, and the reason was arithmetic: the
render stage pushed the word to full scale and the mpv filter then asked for ×3 on top of
that, so Anki's limiter spent the whole word squashing a signal that had nowhere left to go.
These checks run the real wiring from `__init__.py` against stubs, so the two stages can
never both be busy on the same audio again.
"""

import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'anki-global-addon' / 'zotero_global_capture'
source = PACKAGE / '__init__.py'

stub_package = types.ModuleType('zotero_global_capture')
stub_package.__path__ = [str(PACKAGE)]
sys.modules.setdefault('zotero_global_capture', stub_package)


def load(name):
    spec = importlib.util.spec_from_file_location('zotero_global_capture.' + name, PACKAGE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audio_volume = load('audio_volume')
speech = load('speech')

WANTED = ('apply_review_volume', 'log_tts_routing', 'tts_tag')

MPV_ARGS = ['mpv.exe', '--idle', '--af-add=lavfi=[apad=pad_dur=0.150]']


class Player:
    """One of Anki's mpv handles: it records the argument list it is left with."""

    def __init__(self):
        self.args = list(MPV_ARGS)


class SapiPlayer(Player):
    """Anki's SAPI player: it owns a speaker and speaks straight to the sound card."""

    def __init__(self):
        Player.__init__(self)
        self.speaker = object()


class Wiring(unittest.TestCase):
    def setUp(self):
        self.players = [SapiPlayer()]
        self.chosen = self.players[0]
        av_player = types.SimpleNamespace(players=self.players, play_tags=lambda tags: None,
                                          _best_player_for_tag=lambda tag: self.chosen)
        aqt = types.ModuleType('aqt')
        aqt.sound = types.ModuleType('aqt.sound')
        aqt.sound.av_player = av_player
        anki = types.ModuleType('anki')
        anki.sound = types.ModuleType('anki.sound')
        anki.sound.TTSTag = lambda **kw: types.SimpleNamespace(**kw)
        anki.sound.SoundOrVideoTag = lambda **kw: types.SimpleNamespace(**kw)
        names = ('aqt', 'aqt.sound', 'anki', 'anki.sound')
        saved = {name: sys.modules.get(name) for name in names}
        sys.modules.update({'aqt': aqt, 'aqt.sound': aqt.sound, 'anki': anki, 'anki.sound': anki.sound})
        self.addCleanup(self.restore, saved)
        self.av_player = av_player
        self.notes = []
        scope = {'audio_volume': audio_volume, 'speech': speech, 'settings': self.settings,
                 'log_runtime': self.notes.append, 'speech_routing': {'via_file': False},
                 'volume_control': audio_volume.VolumeControl()}
        tree = ast.parse(source.read_text(encoding='utf-8'))
        for name in WANTED:
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
        self.scope = scope

    @staticmethod
    def restore(saved):
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def use_player(self, player):
        self.chosen = player
        self.players = [player]
        self.av_player.players = self.players

    def settings(self):
        return {'review_volume': self.volume}

    def test_a_word_rendered_by_the_plug_in_leaves_the_player_alone(self):
        # This machine: SAPI answers the word, so `speech` owns its loudness and the mpv
        # filter must stay neutral. Both at once is what sounded distorted.
        self.volume = 300
        self.scope['log_tts_routing']()
        self.assertTrue(self.scope['speech_routing']['via_file'], 'SAPI has to be seen as the direct speaker')
        self.scope['apply_review_volume']()
        self.assertEqual(self.players[0].args, MPV_ARGS,
                         'no gain filter may reach the player while the render stage owns the word')
        self.assertIn('via-file=True', self.notes[-1])

    def test_a_word_anki_already_plays_through_mpv_gets_the_player_gain(self):
        self.volume = 300
        player = Player()
        self.use_player(player)
        self.scope['log_tts_routing']()
        self.assertFalse(self.scope['speech_routing']['via_file'])
        self.scope['apply_review_volume']()
        self.assertIn('--af-add=lavfi=[volume=3.00,alimiter=limit=0.95]', player.args)

    def test_a_neutral_dial_touches_neither_stage(self):
        self.volume = 100
        player = Player()
        self.use_player(player)
        self.scope['apply_review_volume']()
        self.assertEqual(player.args, MPV_ARGS)


if __name__ == '__main__':
    unittest.main()
