"""Regression against a font backup; run after extend_font_symbols.py --apply."""
import argparse,json
from pathlib import Path
import uharfbuzz as hb
from PIL import ImageFont
from fontTools.ttLib import TTFont
from extend_font_symbols import FONTS, used_characters, outline
from barony import REPO

p=argparse.ArgumentParser(description=__doc__);p.add_argument('before',type=Path);args=p.parse_args()
report={}
for path in sorted(FONTS.glob('*.ttf')):
    a,b=TTFont(args.before/path.name),TTFont(path)
    ca,cb=a.getBestCmap(),b.getBestCmap()
    preserved=[cp for cp,name in ca.items() if outline(a,name)]
    for cp in preserved:
        assert ca[cp]==cb[cp]
        assert outline(a,ca[cp])==outline(b,cb[cp]),(path.name,cp,'outline')
        assert a['hmtx'][ca[cp]]==b['hmtx'][cb[cp]],(path.name,cp,'metrics')
    assert a.getTableData('GSUB')==b.getTableData('GSUB')
    for size in (16,24,32,64):
        fa=ImageFont.truetype(str(args.before/path.name),size);fb=ImageFont.truetype(str(path),size)
        for cp in preserved:
            ma,mb=fa.getmask(chr(cp)),fb.getmask(chr(cp))
            assert ma.size==mb.size and bytes(ma)==bytes(mb),(path.name,size,cp,'raster')
    for char in used_characters():
        assert ord(char) in cb and outline(b,cb[ord(char)]),(path.name,char,'missing')
    font=hb.Font(hb.Face(path.read_bytes()));hb.ot_font_set_funcs(font)
    widths=[]
    for text in ('Викувати','Ви́кувати'):
        buf=hb.Buffer();buf.add_str(text);buf.guess_segment_properties();hb.shape(font,buf)
        assert all(i.codepoint for i in buf.glyph_infos)
        widths.append(sum(p.x_advance for p in buf.glyph_positions))
    assert widths[0]==widths[1],(path.name,'accent changed advance')
    report[path.name]={'existing_outlines_metrics_and_rasters_preserved':True,'missing_characters':0,
                       'new_or_filled':[f'U+{cp:04X}' for cp in cb if cp not in ca or (not outline(a,ca[cp]) and outline(b,cb[cp]))]}
out=REPO/'build/font-review';out.mkdir(parents=True,exist_ok=True)
(out/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PASS: all 9 fonts; complete coverage, preserved glyphs and GSUB, equal accented-word advance.')
