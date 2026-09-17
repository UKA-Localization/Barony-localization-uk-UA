"""Add missing translation punctuation; preserve existing glyphs and metrics.

Requires fonttools and Pillow; normal mod builds have no new dependencies.
"""
import argparse
import copy
import json
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from barony import REPO, read_strings_tsv

FONTS = REPO / 'assets/fonts'
STEPS = {'alphbeta.ttf':75, 'kongtext.ttf':64, 'pixel_maz.ttf':32,
         'pixel_maz_large.ttf':144, 'pixel_maz_multiline.ttf':32,
         'PixelMaz_monospace.ttf':32, 'pixelmix.ttf':128,
         'pixelmix_bold.ttf':128, 'scream.ttf':128}
SUPPORTED = set('«»–—№\u0301~')


def used_characters():
    chars = Counter()
    for row in read_strings_tsv():
        chars.update(row[3] or row[2])
    for path in (REPO / 'translation/files').rglob('*.txt'):
        chars.update(path.read_text(encoding='utf-8-sig'))
    return {c for c in chars if not c.isspace() and unicodedata.category(c)[0] != 'C'}


def outline(font, name):
    pen = RecordingPen()
    font.getGlyphSet()[name].draw(pen)
    return pen.value


def glyph(cells, unit, dx=0, dy=0):
    pen = TTGlyphPen(None)
    edges = set()
    for x,y in cells:
        pts=[(x,y),(x,y+1),(x+1,y+1),(x+1,y)]
        for a,b in zip(pts,pts[1:]+pts[:1]):
            if (b,a) in edges: edges.remove((b,a))
            else: edges.add((a,b))
    while edges:
        a,b=min(edges);start=a
        pen.moveTo((round(a[0]*unit+dx),round(a[1]*unit+dy)))
        while True:
            edges.remove((a,b));pen.lineTo((round(b[0]*unit+dx),round(b[1]*unit+dy)))
            if b==start: break
            a,b=min(e for e in edges if e[0]==b)
        pen.closePath()
    return pen.glyph()


def extend(path, missing):
    font=TTFont(path); before=copy.deepcopy(font); cmap=font.getBestCmap()
    unit=STEPS[path.name]
    cap=font['glyf'][cmap[ord('Н')]]; small=font['glyf'][cmap[ord('о')]]
    height=round(cap.yMax/unit); lower=round(small.yMax/unit)
    width=round((cap.xMax-cap.xMin)/unit)
    stem=3 if path.name=='kongtext.ttf' else 2 if path.name in ('alphbeta.ttf','pixelmix_bold.ttf','scream.ttf') or unit==32 else 1
    bearing=font['hmtx'][cmap[ord('н')]][0]-font['glyf'][cmap[ord('н')]].xMax
    order=list(font.getGlyphOrder()); new={}
    for char in sorted(missing):
        cells=set(); dx=dy=0
        if char in '–—':
            bar=font['glyf'][cmap[ord('-')]]
            w=width if char=='–' else 2*width
            for x in range(w):
                for y in range(max(1,round((bar.yMax-bar.yMin)/unit))): cells.add((x,y))
            dy=round(bar.yMin/unit)*unit
        elif char in '«»':
            h=max(3,lower if lower%2 else lower-1); depth=h//2
            for y in range(h):
                x=abs(y-depth)
                for shift in (0,depth+stem+1):
                    cells.update((x+shift+k,y) for k in range(stem))
            if char=='»':
                right=max(x for x,y in cells);cells={(right-x,y) for x,y in cells}
            dy=max(0,(lower-h)//2)*unit
        elif char=='№':
            nw=max(width,2*stem+3)
            for y in range(height):
                cells.update((x,y) for x in list(range(stem))+list(range(nw-stem,nw)))
                xx=round((nw-stem)*(height-1-y)/(height-1))
                cells.update((x,y) for x in range(xx,xx+stem))
            ow=max(3,height//2); start=nw+1; bottom=height-ow
            cells.update((start+x,bottom+y) for x in range(ow) for y in range(ow)
                         if x in (0,ow-1) or y in (0,ow-1))
            cells.update((start+x,bottom-2) for x in range(ow))
        elif char=='~':
            pattern='.##..#/##.##./#..##.'
            cells={(x,2-y) for y,row in enumerate(pattern.split('/')) for x,c in enumerate(row) if c=='#'}
            dy=(lower//2)*unit
        else:
            cells={(0,0),(1,1)}
            if stem>1: cells|={(1,0),(2,1)}
            ref=font['glyf'][cmap[ord('и')]]; aw=font['hmtx'][cmap[ord('и')]][0]
            dx=round(((ref.xMin+ref.xMax)/2-aw)/unit)*unit-unit
            dy=(lower+1)*unit
        name=f'uni{ord(char):04X}.added'
        font['glyf'][name]=glyph(cells,unit,dx,dy)
        font['glyf'][name].recalcBounds(font['glyf'])
        g=font['glyf'][name]
        font['hmtx'][name]=(0 if char=='\u0301' else g.xMax+int(bearing),g.xMin)
        order.append(name);new[ord(char)]=name
    font.setGlyphOrder(order)
    for table in font['cmap'].tables:
        if table.isUnicode(): table.cmap.update(new)
    if 0x301 in new:
        # Explicit mark attachment; retain every existing substitution table.
        saved={tag:copy.deepcopy(font[tag]) for tag in ('GSUB','GPOS','GDEF') if tag in font}
        if 'GPOS' in saved: raise ValueError('Existing GPOS needs an explicit merge')
        mark=font['glyf'][new[0x301]]
        features=[f'markClass {new[0x301]} <anchor {(mark.xMin+mark.xMax)//2} {mark.yMin}> @ACUTE;', 'feature mark {']
        for cp,name in cmap.items():
            if chr(cp).isalpha() and cp<0x500:
                g=font['glyf'][name]
                if g.numberOfContours:
                    features.append(f'pos base {name} <anchor {(g.xMin+g.xMax)//2} {g.yMax+unit}> mark @ACUTE;')
        features.append('} mark;')
        addOpenTypeFeaturesFromString(font,'\n'.join(features))
        for tag in ('GSUB','GDEF'):
            if tag in saved: font[tag]=saved[tag]
    for cp,name in before.getBestCmap().items():
        if cp in new: continue  # Replace an empty placeholder only.
        assert font.getBestCmap()[cp]==name
        assert outline(font,name)==outline(before,name)
        assert font['hmtx'][name]==before['hmtx'][name]
    font.save(path)
    after=TTFont(path)
    for tag in ('hhea','OS/2'):
        for attr in ('ascent','descent','lineGap','sTypoAscender','sTypoDescender','sTypoLineGap','usWinAscent','usWinDescent'):
            if hasattr(before[tag],attr): assert getattr(before[tag],attr)==getattr(after[tag],attr)
    return [f'U+{ord(c):04X}' for c in sorted(missing)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(); chars=used_characters(); report={}
    missing={}
    for p in sorted(FONTS.glob('*.ttf')):
        font=TTFont(p); cmap=font.getBestCmap()
        missing[p]={c for c in chars if ord(c) not in cmap or not outline(font,cmap[ord(c)])}
    unknown=set().union(*missing.values())-SUPPORTED
    if unknown: raise SystemExit(f'Need designs for: {sorted(unknown)}')
    backup=Path.home()/'Documents/Codex/backups'/('barony-symbols-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    if args.apply and any(missing.values()):
        backup.mkdir(parents=True)
        for p in missing: (backup/p.name).write_bytes(p.read_bytes())
        print('Backup:',backup)
    for p,chars_missing in missing.items():
        report[p.name]=extend(p,chars_missing) if args.apply and chars_missing else [f'U+{ord(c):04X}' for c in sorted(chars_missing)]
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not args.apply and any(missing.values()): raise SystemExit(1)

if __name__=='__main__': main()
