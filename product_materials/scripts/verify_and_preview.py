"""Validate the collection, create an offline gallery and a contact sheet."""
from pathlib import Path
import json,html,hashlib,io,collections
from PIL import Image,ImageOps,ImageDraw
from collect import validate_real_image
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
records=json.loads((ROOT/'products.json').read_text(encoding='utf8'))
errors=[];ids=set();images=[]
for r in records:
 if r['id'] in ids:errors.append('duplicate id '+r['id'])
 ids.add(r['id'])
 if not r['description_original'] or not r['introduction_zh']:errors.append('missing text '+r['id'])
 for image in r['images']:
  p=ROOT/image['local_path']
  if not p.exists():errors.append('missing image '+r['id']);continue
  if hashlib.sha256(p.read_bytes()).hexdigest()!=image['sha256']:errors.append('hash mismatch '+r['id'])
  validate_real_image(p)
 if not (ROOT/'categories'/r['category_id']/r['id']/'source_original.json').exists():errors.append('missing raw data '+r['id'])
lines=(ROOT/'products.jsonl').read_text(encoding='utf8').splitlines()
if [json.loads(line) for line in lines]!=records:errors.append('json/jsonl mismatch')
validator=Draft202012Validator(json.loads((ROOT/'product.schema.json').read_text(encoding='utf-8-sig')))
for record in records:
 errors.extend(record['id']+': '+error.message for error in validator.iter_errors(record))
assert len(records)==400 and not errors,(len(records),errors)

def esc(x):return html.escape(str(x or ''),quote=True)
# Cards contain only escaped source strings, no remote fetches or dynamic execution.
category_counts=collections.Counter(r['category_name_zh'] for r in records)
buttons=''.join(f'<button type="button" data-filter="{esc(cat)}">{esc(cat)} · {n}</button>' for cat,n in category_counts.items())
cards=[]
for r in records:
 path=(Path('categories')/r['category_id']/r['id']/'product.json').as_posix()
 cards.append(f'''<article data-category="{esc(r['category_name_zh'])}" data-search="{esc(' '.join([r['name_original'],r['brand'] or '',r['category_name_zh'],r['source_sku']])).lower()}"><a href="{esc(path)}"><img loading="lazy" src="{esc(r['images'][0]['local_path'])}" alt="{esc(r['name_original'])}" width="260" height="200"></a><div class="body"><small>{esc(r['category_name_zh'])} · {esc(r['brand'])}</small><h2>{esc(r['name_original'])}</h2><p>{esc(r['introduction_zh'])}</p><details><summary>原文与参数</summary><p>{esc(r['description_original'])}</p><pre>{esc(json.dumps(r['specifications_original'],ensure_ascii=False,indent=2))}</pre></details><footer><span>历史价格 USD {esc(r['price']['amount'])}</span><a href="{esc(path)}">商品 JSON ↗</a></footer></div></article>''')
doc='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>日常电子产品素材库 · 400 条</title><style>*{box-sizing:border-box}body{margin:0;background:#f5f6f1;color:#394333;font:14px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1400px;margin:auto;padding:35px 25px}h1{font-size:30px;margin:0}header p{color:#7e8b70}input{width:100%;padding:14px;border:1px solid #dbe3d0;border-radius:8px;font:inherit;background:white}nav{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}button{font:inherit;border:1px solid #dbe3d0;border-radius:7px;padding:8px 12px;background:white;cursor:pointer;color:#657858}button.selected{background:#df753c;color:white;border-color:#df753c}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}article{background:white;border:1px solid #e2e8da;border-radius:12px;overflow:hidden}article[hidden]{display:none}img{display:block;width:100%;height:200px;object-fit:contain;padding:15px;background:white}.body{padding:18px}small{color:#90a080;font-size:11px}h2{font-size:14px;line-height:1.6;margin:10px 0}p{font-size:12px;color:#7e8c72}details{font-size:11px;color:#788c67}pre{white-space:pre-wrap;word-break:break-word;font-size:10px}footer{display:flex;justify-content:space-between;gap:8px;margin-top:18px;font-size:10px;color:#c27443}a{color:inherit;text-decoration:none}.notice{background:#e9efdf;padding:14px 18px;border-radius:8px;font-size:12px}#count{font-size:12px;color:#859571;margin:16px 0}@media(max-width:1000px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:700px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}main{padding:25px 15px}}@media(max-width:420px){.grid{grid-template-columns:1fr}}</style><main><header><h1>日常电子产品素材库</h1><p>400 条商品 · 12 个分类 · 本地图片与原始资料 · 中文简要介绍</p></header><div class="notice">历史目录，价格以 USD 保存，不是当前报价。中文文本为基于原文证据的整理摘要；缺失参数未补造。Best Buy 官方数据许可为 CC BY-NC 4.0，镜像文案与商品图片的单独授权未核实。</div><p><label for="search">搜索商品、品牌、分类或 SKU</label></p><input id="search" placeholder="例如 Apple、Samsung、耳机…"><nav><button type="button" class="selected" data-filter="">全部商品 · 400</button>__BUTTONS__</nav><p id="count">显示 400 件商品</p><section class="grid">__CARDS__</section></main><script>let category='';const search=document.querySelector('#search'),cards=[...document.querySelectorAll('article')];function filter(){let n=0;const q=search.value.trim().toLowerCase();cards.forEach(card=>{const match=(!category||card.dataset.category===category)&&card.dataset.search.includes(q);card.hidden=!match;if(match)n++;});document.querySelector('#count').textContent='显示 '+n+' 件商品';}search.addEventListener('input',filter);document.querySelectorAll('nav button').forEach(button=>button.addEventListener('click',()=>{category=button.dataset.filter;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('selected',b===button));filter();}));</script></html>'''
(ROOT/'gallery.html').write_text(doc.replace('__BUTTONS__',buttons).replace('__CARDS__',''.join(cards)),encoding='utf8')
# One representative image per category, plus further deterministic samples.
sample=[]
for cat in category_counts:
 sample.extend([r for r in records if r['category_name_zh']==cat][:2])
canvas=Image.new('RGB',(1200,6*220),'#f5f6f1');draw=ImageDraw.Draw(canvas)
for i,r in enumerate(sample):
 x=(i%4)*300;y=(i//4)*220
 with Image.open(ROOT/r['images'][0]['local_path']) as image:
  thumb=ImageOps.contain(image.convert('RGB'),(260,170))
  canvas.paste(thumb,(x+(300-thumb.width)//2,y+10+(170-thumb.height)//2))
 draw.text((x+15,y+190),r['id']+' | '+(r['brand'] or '')[:20],fill='#394333')
canvas.save(ROOT/'preview_contact_sheet.jpg',quality=90)
validation={'records':len(records),'unique_ids':len(ids),'verified_local_images':sum(len(r['images']) for r in records),'errors':errors,'jsonl_round_trip':'passed','schema_validation':'passed','full_image_decode':'passed','placeholder_screening':'passed'}
(ROOT/'validation_report.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(validation,ensure_ascii=False))
