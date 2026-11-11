#!/usr/bin/env python3
"""Build a pixel-outline web font from the 12px (9pt) bitmap strike of the OFL Gulim.

Usage: python3 scripts/build-gulim-pixel.py [--src Gulim.ttf] [--out fonts/woff2]
The source is googlefonts/gulim sources/ttf/Gulim.ttf (OFL 1.1, HanYang I&C). The repo's built
fonts/ttf/bitmap files drop the hidden jamo bitmaps that 12px Hangul composites point to;
it is downloaded to build/Gulim.ttf when --src is not given.
Each lit pixel becomes a square of 100 units (unitsPerEm 1200), so the font draws the exact
9pt Gulim bitmap at 12px and whole-pixel enlargements at 24px, 36px, ... on every browser.
Writes GulimPixel.woff2 and GulimPixel-Bold.woff2 (Windows-style 1px emboldening).
"""
import argparse, os, sys, urllib.request
from fontTools.ttLib import TTFont
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

if '-h' in sys.argv or '--help' in sys.argv:
    print(__doc__.strip()); sys.exit(0)
ap = argparse.ArgumentParser()
ap.add_argument('--src'); ap.add_argument('--out', default='fonts/woff2')
args = ap.parse_args()
URL = 'https://raw.githubusercontent.com/googlefonts/gulim/HEAD/sources/ttf/Gulim.ttf'
src = args.src or os.path.join('build', 'Gulim.ttf')
if not os.path.exists(src):
    os.makedirs(os.path.dirname(src) or '.', exist_ok=True); urllib.request.urlretrieve(URL, src)

PX, U = 12, 100
f = TTFont(src)
eblc, ebdt = f['EBLC'], f['EBDT']
si = next(i for i, s in enumerate(eblc.strikes) if s.bitmapSizeTable.ppemY == PX)
strike, data = eblc.strikes[si], ebdt.strikeData[si]
asc, desc = strike.bitmapSizeTable.hori.ascender, strike.bitmapSizeTable.hori.descender
hmtx_src, upem_src = f['hmtx'].metrics, f['head'].unitsPerEm
submetrics = {n: sub.metrics for sub in strike.indexSubTables if hasattr(sub, 'metrics') for n in sub.names}

def metrics(name):
    g = data[name]
    m = getattr(g, 'metrics', None) or submetrics[name]
    bx = getattr(m, 'BearingX', getattr(m, 'horiBearingX', 0))
    by = getattr(m, 'BearingY', getattr(m, 'horiBearingY', 0))
    adv = getattr(m, 'Advance', getattr(m, 'horiAdvance', 0))
    return g, m, bx, by, adv

def pixels(name):
    """Lit pixels as (col, row) relative to the glyph box top-left, plus box metrics."""
    g, m, bx, by, adv = metrics(name)
    out = set()
    if hasattr(g, 'componentArray'):
        for c in g.componentArray:
            sub, _ = pixels(c.name)
            out |= {(x + c.xOffset, y + c.yOffset) for x, y in sub}
    else:
        for r in range(m.height):
            row = g.getRow(r, bitDepth=1, metrics=m)
            for x in range(m.width):
                if row[x >> 3] & (0x80 >> (x & 7)):
                    out.add((x, r))
    # The strike's own Advance is 1px short for ASCII (digits end flush against the next Hangul cell);
    # Windows lays out 9pt Gulim with the outline advance rounded to whole pixels, so use that.
    adv = round(hmtx_src[name][0] * PX / upem_src) if name in hmtx_src else adv
    return out, (bx, by, adv)

cmap = {cp: n for cp, n in f.getBestCmap().items() if n in data}
hangul = {n for cp, n in cmap.items() if 0xAC00 <= cp <= 0xD7A3 or 0x3131 <= cp <= 0x318E}
glyphs = {}
for cp, n in cmap.items():
    if n not in glyphs:
        glyphs[n] = pixels(n)

def build(bold):
    order = ['.notdef'] + sorted(glyphs)
    fb = FontBuilder(PX * U, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    glyf, hmtx = {}, {}
    fixed = [0]
    for n in order:
        pen = TTGlyphPen(None)
        if n == '.notdef':
            glyf[n], hmtx[n] = pen.glyph(), (PX // 2 * U, 0); continue
        px, (bx, by, adv) = glyphs[n]
        orig_adv = adv + (1 if bold and px else 0)
        if bold:
            px = px | {(x + 1, y) for x, y in px}; adv += 1 if px else 0
        if px:
            # The 9pt bitmaps let some glyphs touch their cell edge (했 starts at column 0, 가 and
            # parentheses end at the last column), so neighbours fuse. Every glyph keeps a blank
            # left column (shift right if needed). Hangul keeps its even 12px rhythm because the next
            # syllable's blank left column already separates it; other glyphs also keep a blank
            # right column so they never touch a following syllable.
            lo, hi = bx + min(x for x, _ in px), bx + max(x for x, _ in px)
            if lo < 1: bx += 1 - lo; hi += 1 - lo
            need = hi + 1 if n in hangul else hi + 2
            if adv < need: adv = need
            fixed[0] += (lo < 1) or (adv != orig_adv)
        rows = {}
        for x, y in px: rows.setdefault(y, []).append(x)
        for y, xs in rows.items():
            xs.sort(); start = prev = xs[0]
            for x in xs[1:] + [None]:
                if x is not None and x == prev + 1: prev = x; continue
                x0, x1 = (bx + start) * U, (bx + prev + 1) * U
                top, bot = (by - y) * U, (by - y - 1) * U
                pen.moveTo((x0, bot)); pen.lineTo((x0, top)); pen.lineTo((x1, top)); pen.lineTo((x1, bot)); pen.closePath()
                if x is not None: start = prev = x
        glyf[n] = pen.glyph(); hmtx[n] = (adv * U, bx * U)
    fb.setupGlyf(glyf); fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader(ascent=asc * U, descent=desc * U)
    style = 'Bold' if bold else 'Regular'
    fb.setupNameTable({'familyName': 'Gulim Pixel', 'styleName': style,
                       'copyright': 'Copyright 2024 The Gulim and Dotum Project Authors (https://github.com/googlefonts/gulim)',
                       'licenseDescription': 'SIL Open Font License 1.1', 'licenseInfoURL': 'https://openfontlicense.org'})
    fb.setupOS2(sTypoAscender=asc * U, sTypoDescender=desc * U, sTypoLineGap=0, usWinAscent=asc * U, usWinDescent=-desc * U,
                usWeightClass=700 if bold else 400, fsSelection=0x20 if bold else 0x40)
    fb.setupPost(); fb.font['head'].macStyle = 1 if bold else 0
    fb.font.flavor = 'woff2'
    out = os.path.join(args.out, f"GulimPixel{'-Bold' if bold else ''}.woff2")
    fb.save(out); print(out, f'{os.path.getsize(out) / 1024:.0f}KB', len(order), 'glyphs,', fixed[0], 'given a blank edge column')

build(False); build(True)
