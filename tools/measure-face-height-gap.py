"""Measure the height each face asks for, before and after a flip.

The flip checks started failing with 'the answer left dead height: 513 of 544' once the hint
row became two lines, so this prints the numbers for both faces and names the widgets that
still claim space when their contents are hidden.
"""
import io, os

TEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                    'tests', 'windows-question-audio.py'))
head = io.open(TEST, encoding='utf-8').read().split('# 1. ')[0]
env = {'__name__': '__main__', '__file__': TEST}
exec(compile(head, TEST, 'exec'), env)
app = env['app']

for mode in ('listening', 'typing'):
    dialog = env['card'](mode)
    dialog.show()
    app.processEvents()
    print('%-10s front   height %d  sizeHint %d' % (mode, dialog.height(),
                                                    dialog.layout().sizeHint().height()))
    dialog.reveal(True)
    app.processEvents()
    print('%-10s answer  height %d  sizeHint %d  gap %d'
          % (mode, dialog.height(), dialog.layout().sizeHint().height(),
             dialog.height() - dialog.layout().sizeHint().height()))
    print('   dialog minimum %d  layout minimum %d  layout max %s'
          % (dialog.minimumSize().height(), dialog.layout().minimumSize().height(),
             dialog.layout().maximumSize().height()))
    main = dialog.layout()
    for index in range(main.count()):
        item = main.itemAt(index)
        widget = item.widget()
        inner = item.layout()
        label = (type(widget).__name__ + ':' + (widget.objectName() or '')
                 if widget is not None else ('layout:' + str(index) if inner else 'spacer'))
        shown = widget.isVisible() if widget is not None else 'n/a'
        print('   item %2d %-28s h=%3d min=%3d visible=%s'
              % (index, label, item.sizeHint().height(), item.minimumSize().height(), shown))
    dialog.fit_card_height()
    app.processEvents()
    print('   after explicit fit_card_height: height %d (hint %d)'
          % (dialog.height(), dialog.layout().sizeHint().height()))
    dialog.deleteLater()
    app.processEvents()
os._exit(0)
