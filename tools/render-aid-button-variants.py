"""Three ways to make the aid controls read as buttons, rendered on the real card.

The row was flattened to grey text in the approved mockup (variant D) and the learner now
says he cannot tell they are clickable. These are the three ways back, drawn with the card's
own stylesheet so what is chosen is what ships.

    python tools/render-aid-button-variants.py
"""
import io, os

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
OUT = os.path.join(os.environ.get('TEMP', '.'), 'aid-buttons')
os.makedirs(OUT, exist_ok=True)
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app = env['app']

VARIANTS = {
    'A-outline': ('描边小按钮：卡片默认按钮的样子，矮一号',
                  'QPushButton#aid { padding: 5px 11px; font-size: 12px; }'),
    'B-filled': ('浅底填充无边：像键帽，比主动作淡',
                 'QPushButton#aid { background: %s; border: 1px solid transparent;'
                 ' color: %s; padding: 5px 11px; font-size: 12px; }'
                 ' QPushButton#aid:hover { background: %s; }'),
    'C-underlined': ('文字加下划线：链接式，最轻，但仍然是"可点"',
                     'QPushButton#aid { border: none; background: transparent;'
                     ' text-decoration: underline; padding: 5px 8px; font-size: 12px; }'),
}
# The card's own stylesheet is theme-mapped, so a rule injected here has to carry the dark
# values itself -- a pale #eef2ff chip on a #171c2b card is not what variant B would ship.
THEME = {'dark': ('#34415d', '#dbe5f7', '#3d4a6b'), 'light': ('#eef2ff', '#27344d', '#e3eafd')}

for name, (caption, extra) in VARIANTS.items():
    dialog = env['card']('listening')
    dark = dialog.cfg.get('review_theme') == 'dark'
    fill, ink, hover = THEME['dark' if dark else 'light']
    dialog.setStyleSheet(dialog.styleSheet() + (extra % (fill, ink, hover)
                                                if '%s' in extra else extra))
    for button in (dialog.meaning_hint_button, dialog.hint_button,
                   dialog.phonetic_hint_button):
        button.setObjectName('aid')
        button.style().unpolish(button)
        button.style().polish(button)
    dialog.show()
    app.processEvents()
    image = dialog.grab().toImage()
    path = os.path.join(OUT, '%s.png' % name)
    image.save(path, 'PNG')
    print('%-14s %-14s %dx%d  aids %d x %d' % (
        name, caption[:14], image.width(), image.height(),
        dialog.hint_button.width(), dialog.hint_button.height()))
    dialog.deleteLater()
    app.processEvents()
print('wrote', OUT)
