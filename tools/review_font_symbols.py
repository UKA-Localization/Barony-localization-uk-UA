"""All Unicode glyphs, before/after, with automatic outline/metric highlighting."""
from pathlib import Path
import argparse, json, math, html
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from barony import REPO as ROOT
from extend_font_symbols import FONTS as OUTPUT, outline as outlines
PROOF = ROOT / 'build/font-review'
UK = '«»–—№~и́'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('before',type=Path)
    p.add_argument('--output',type=Path,default=PROOF)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    label=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',16)
    title=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',23)
    index=[]; report={}
    for path in sorted(OUTPUT.glob('*.ttf')):
        oldpath=args.before/path.name
        a,b=TTFont(oldpath),TTFont(path)
        ca,cb=a.getBestCmap(),b.getBestCmap()
        changed=[]
        def different(code):
            if code not in ca or code not in cb: return True
            return outlines(a,ca[code])!=outlines(b,cb[code]) or a['hmtx'][ca[code]]!=b['hmtx'][cb[code]]
        codes=sorted(set(ca)|set(cb))
        for code in codes:
            if different(code): changed.append(code)
        report[path.name]={'unicode_count':len(codes),'changed':[f'U+{c:04X}' for c in changed],
                          'changed_characters':''.join(chr(c) for c in changed)}
        cap=a['glyf'][ca[ord('H')]].yMax
        size=round(26*a['head'].unitsPerEm/cap)
        fa,fb=ImageFont.truetype(str(oldpath),size),ImageFont.truetype(str(path),size)
        for subset,name in [(codes,'all'),([ord(c) for c in UK],'uk')]:
            cols=12; cellw=116; cellh=132
            im=Image.new('RGB',(cols*cellw+32,116+math.ceil(len(subset)/cols)*cellh),'#151b23')
            d=ImageDraw.Draw(im)
            d.text((16,12),f'{path.name}  |  {len(subset)} symbols  |  {len(changed)} changed',font=title,fill='#e7edf5')
            d.text((16,48),'У кожній комірці: БУЛО зверху / СТАЛО знизу. Зміни: помаранчевий → зелений.',font=label,fill='#ccd4e0')
            for i,code in enumerate(subset):
                x=16+(i%cols)*cellw; y=102+(i//cols)*cellh
                altered=code in changed
                d.rectangle((x,y,x+cellw-5,y+cellh-6),outline='#55796b' if altered else '#29323c')
                d.text((x+6,y+3),f'U+{code:04X}',font=label,fill='#b9c5d2')
                for baseline,face,cmap,color in [(y+64,fa,ca,'#ffbf88'),(y+111,fb,cb,'#73e3b5')]:
                    d.line((x+5,baseline,x+cellw-10,baseline),fill='#39424b')
                    if code in cmap:
                        bbox=face.getbbox(chr(code),anchor='ls')
                        dx=x+(cellw-5-(bbox[2]-bbox[0]))//2-bbox[0]
                        d.text((dx,baseline),chr(code),font=face,fill=color if altered else '#d4dce6',anchor='ls')
            im.save(args.output/f'{path.stem}-{name}.png')
        index.append(f'<section><h2>{html.escape(path.name)}</h2><p>Змінено: {html.escape(report[path.name]["changed_characters"]) or "немає"}</p><a href="{path.stem}-all.png">Усі {len(codes)} Unicode-гліфів</a><img src="{path.stem}-uk.png" alt="Символи: було та стало"></section>')
    (args.output/'changes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (args.output/'index.html').write_text('<!doctype html><html lang="uk"><meta charset="utf-8"><title>Шрифти: було і стало</title><style>body{background:#151b23;color:#e7edf5;font:18px system-ui;max-width:1440px;margin:32px auto;padding:16px}img{width:100%}a{color:#73e3b5}section{margin-bottom:48px}</style><h1>Повне порівняння гліфів</h1><p>У кожній комірці зверху — було, знизу — стало. Змінені символи позначено помаранчевим і зеленим. Порожні комірки можуть відповідати пробілам або службовим символам.</p>'+''.join(index)+'</html>',encoding='utf-8')
    im=Image.new('RGB',(1500,1120),'#151b23');d=ImageDraw.Draw(im)
    d.text((20,10),'Символи та наголос — усі дев’ять шрифтів',font=title,fill='white')
    for i,path in enumerate(sorted(OUTPUT.glob('*.ttf'))):
        f=TTFont(path)
        size=round(28*f['head'].unitsPerEm/f['glyf'][f.getBestCmap()[ord('Н')]].yMax)
        face=ImageFont.truetype(str(path),size);y=80+i*114
        d.text((20,y-8),path.name,font=label,fill='white')
        d.text((290,y+35),'«Юю» – — № ~ Ви́кувати',font=face,fill='#73e3b5',anchor='ls')
    im.save(args.output/'symbols.png')
    print(json.dumps(report,ensure_ascii=True))

if __name__=='__main__': main()
