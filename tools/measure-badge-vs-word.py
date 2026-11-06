"""Where did the badge actually land on the real cards? Measured, not argued.

The learner reported 「庆祝徽章位置不对，会挡住单词」. Offscreen the answer face puts the badge
centre at height/2 and the word row at y 89-139, which do not touch — so either the live
geometry differs, or the sighting came from a shape I have not reconstructed. This measures
the frames the capture tool already caught: the badge's own gold/magenta pixels give its
true bounding box, and the word row is the widest band of near-white glyphs in the top third.

Read-only: it opens PNGs and prints numbers.
"""
import glob
import os
import sys

from PIL import Image

CAPTURES = sys.argv[1:] or ['shots5/answer*.png', 'shots/after*.png']


def is_badge(rgb):
    r, g, b = rgb
    gold = r > 190 and g > 130 and b < 150 and (r - b) > 60
    magenta = r > 150 and b > 90 and g < 120 and (r - g) > 60
    return gold or magenta


def is_glyph(rgb):
    r, g, b = rgb
    return r > 200 and g > 200 and b > 200


def rows_with(path):
    im = Image.open(path).convert('RGB')
    w, h = im.size
    data = im.load()
    badge_top = badge_bottom = None
    glyph_rows = {}
    for y in range(0, h):
        badge_pixels = 0
        glyph_pixels = 0
        for x in range(0, w, 2):
            rgb = data[x, y]
            if is_badge(rgb):
                badge_pixels += 1
            if is_glyph(rgb):
                glyph_pixels += 1
        if badge_pixels >= 3:
            if badge_top is None:
                badge_top = y
            badge_bottom = y
        if y < h * 0.55:
            glyph_rows[y] = glyph_pixels
    return w, h, badge_top, badge_bottom, glyph_rows


def word_row(glyph_rows, h):
    """The band of bright glyph pixels in the upper half that is widest — the answer word."""
    best, best_run = None, 0
    ys = sorted(glyph_rows)
    run = []
    for y in ys:
        if glyph_rows[y] >= 6:
            run.append(y)
        else:
            if run and sum(glyph_rows[y] for y in run) / len(run) > best_run and len(run) >= 6:
                best_run = sum(glyph_rows[y] for y in run) / len(run)
                best = (run[0], run[-1])
            run = []
    if run and len(run) >= 6:
        avg = sum(glyph_rows[y] for y in run) / len(run)
        if avg > best_run:
            best_run, best = avg, (run[0], run[-1])
    return best


def files():
    out = []
    for pattern in CAPTURES:
        out.extend(sorted(glob.glob(pattern)))
    return out


print('%-22s %-10s %-14s %-14s %s' % ('capture', 'card', 'badge y', 'word y', 'verdict'))
for path in files():
    if not os.path.exists(path):
        continue
    w, h, top, bottom, glyph_rows = rows_with(path)
    word = word_row(glyph_rows, h)
    if top is None:
        print('%-22s %-10s %-14s %-14s %s' % (os.path.basename(path), '%dx%d' % (w, h),
                                              '-', '-', '没有徽章像素（这一帧没庆祝）'))
        continue
    if word is None:
        verdict = '单词行未识别'
    elif top <= word[1] and bottom >= word[0]:
        verdict = '遮挡 %d px' % (min(bottom, word[1]) - max(top, word[0]))
    else:
        verdict = '干净（相距 %d px）' % (top - word[1] if top > word[1] else word[0] - bottom)
    print('%-22s %-10s %-14s %-14s %s' % (os.path.basename(path), '%dx%d' % (w, h),
                                          '%d-%d' % (top, bottom),
                                          '%d-%d' % word if word else '-', verdict))
