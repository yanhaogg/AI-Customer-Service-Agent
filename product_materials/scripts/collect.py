"""Collect 400 historical consumer-electronics records with verified local images.
Run from project root. Python 3 + Pillow (image validation) required.
"""
from pathlib import Path
import json, re, html, hashlib, urllib.request, urllib.parse, time, io
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'sources'
SOURCE_URL = 'https://github.com/BestBuy/api-playground'
MIRROR_URL = 'https://github.com/algolia/datasets/tree/master/ecommerce'
COLLECTED = datetime.now(timezone.utc).isoformat()
GROUPS = [
 ('01_phones','手机',35),('02_computers','笔记本与台式电脑',45),
 ('03_tablets','平板电脑',30),('04_monitors','显示器',20),
 ('05_audio','耳机与音箱',75),('06_wearables','智能穿戴',30),
 ('07_smart_home','智能家居',25),('08_cameras','相机与摄像机',30),
 ('09_networking','路由器与网络设备',20),('10_storage','存储设备',25),
 ('11_power','充电与电源配件',25),('12_peripherals','键鼠与电脑外设',40),
]
LABELS = {key:name for key,name,_ in GROUPS}

def clean(value):
 if value is None:return ''
 return re.sub(r'\s+',' ',html.unescape(str(value))).strip()

def classify(row):
 cats = row.get('categories',[]); leaf = cats[-1] if cats else ''; top = cats[0] if cats else ''
 name = clean(row['name']).lower()
 if re.search(r'\b(refurbished|pre-owned|replacement screen)\b',name):return None
 if leaf in ['All Unlocked Cell Phones','All Cell Phones with Plans','All No-Contract Phones','iPhone']:return '01_phones'
 if leaf in ['PC Laptops','MacBooks','All Desktops','All-in-One Computers','Gaming Laptops','Chromebooks','Ultrabooks']:return '02_computers'
 if leaf in ['All Tablets','iPad','Kids\' Tablets','Microsoft Surface Tablets']:return '03_tablets'
 if leaf in ['All Monitors','LED Monitors','LCD Monitors','Gaming Monitors']:return '04_monitors'
 if top=='Audio' and (re.search(r'headphone|earbud|speaker|bluetooth.*audio',name) or leaf in ['Wireless & Multiroom Audio','MP3 Players','iPod touch']):
  if not re.search(r'\b(cable|wire|stand|case|replacement|adapter|mount|ear tip|ear cushion|cover)\b',name):return '05_audio'
 if leaf in ['Smartwatches','Apple Watch','Apple Watch Sport','Fitness & GPS Watches','Activity Trackers'] or ('Activity Trackers' in cats and 'Bands' not in leaf):return '06_wearables'
 if top=='Connected Home' and leaf in ['Security Cameras','Smart Light Bulbs','Smart Door Locks','Smart Lighting Kits','Smart Light Strips','Remote Monitoring Kits','Motion Sensors','Appliance & Outlet Control','Smoke Detectors','Baby Monitors']:return '07_smart_home'
 if top=='Cameras & Camcorders' and leaf in ['All Point & Shoot Cameras','DSLR Body & Lens','All Mirrorless Cameras','DSLR Body Only','All Action Camcorders','All Traditional Camcorders','360 & Panoramic Cameras']:return '08_cameras'
 if leaf in ['Wireless Routers','PC Range Extenders','Network Adapters','Wireless USB Adapters','Network Switches','Cable Modems','Modem & Router Combos']:return '09_networking'
 if leaf in ['USB Flash Drives','External Hard Drives','Internal Hard Drives','Solid State Drives','All Memory Cards','Portable Hard Drives']:return '10_storage'
 if leaf in ['Portable Chargers/Power Packs','Cell Phone Chargers','Wall Chargers','Car Chargers','Laptop Chargers & Adapters','Surge Protectors','Battery Backup (UPS)','iPhone Chargers','Charging Stations']:
  if re.search(r'charger|power|charging|surge|battery backup',name):return '11_power'
 if leaf in ['Wireless & Bluetooth Mice','Wired Mice','Gaming Mice','Keyboards','Computer Keyboards','Gaming Keyboards','Webcams','USB Cables & Hubs','Keyboard & Mouse Combos']:
  if not re.search(r'\b(cable|cover|case|replacement)\b',name):return '12_peripherals'
 return None

def feature_extract(text):
 patterns = [
  ('screen_size',r'\b\d+(?:\.\d+)?[ -]?(?:inch|inches|"|”)(?:\s+(?:display|screen))?'),
  ('storage_or_memory',r'\b\d+(?:\.\d+)?\s?(?:GB|TB|MB)\b'),
  ('resolution',r'\b(?:\d{3,4}\s?[x×]\s?\d{3,4}|4K|1080p|720p|Full HD|Ultra HD)\b'),
  ('battery_capacity',r'\b\d{3,5}\s?mAh\b'),
  ('camera_resolution',r'\b\d+(?:\.\d+)?[ -]?(?:megapixel|MP)\b'),
  ('connectivity',r'\b(?:Bluetooth(?:\s+\d(?:\.\d)?)?|Wi-Fi|USB(?:[ -](?:C|3\.0|2\.0))?|HDMI|NFC)\b'),
 ]
 out=[]
 for key,pattern in patterns:
  seen=set()
  for match in re.finditer(pattern,text,re.I):
   value=match.group(0).strip()
   if value.lower() not in seen:out.append({'attribute':key,'value_original':value,'evidence_original':text[max(0,match.start()-40):min(len(text),match.end()+70)]});seen.add(value.lower())
 return out

def chinese_intro(row,group,facts):
 brand=clean(row.get('brand')) or '该品牌'
 clauses=[]
 for fact in facts:
  key,value=fact['attribute'],fact['value_original']
  if key=='screen_size':clause='介绍中提及 '+re.sub(r'inches|inch|["”]',' 英寸',value,flags=re.I)+' 显示规格'
  elif key=='storage_or_memory':clause='提及 '+value+' 容量规格（内存或存储用途见原文）'
  elif key=='resolution':clause='提及 '+value+' 分辨率规格'
  elif key=='battery_capacity':clause='提及 '+value+' 电池容量'
  elif key=='camera_resolution':clause='提及 '+value+' 成像规格'
  elif key=='connectivity':clause='提及 '+value+' 接口或连接方式'
  else:continue
  if clause not in clauses:clauses.append(clause)
  if len(clauses)>=3:break
 base=f'{brand} 品牌的{LABELS[group]}商品。'
 if clauses:base+='来源介绍'+ '；'.join(clauses)+'。'
 else:base+='具体产品功能、适用设备与配件说明见保留的英文介绍。'
 return base+'该记录来自历史商品目录，适合商品展示与数据库练习；实际参数和当前售价需重新核对。'

def image_candidates(row,official):
 originals=[]
 if official and official.get('image'):originals.append(official['image'])
 if row.get('image'):originals.append(row['image'])
 urls=[]
 for source in originals:
  if 'img.bbystatic.com/' in source:
   path=urllib.parse.urlsplit(source).path
   urls += ['https://pisces.bbystatic.com/image2'+path,source.replace('http://','https://',1)]
  elif 'cdn-demo.algolia.com/bestbuy/' in source:
   filename=source.rsplit('/',1)[-1];sku=filename.split('_')[0]
   urls += [f'https://pisces.bbystatic.com/image2/BestBuy_US/images/products/{sku[:4]}/{filename}',f'https://img.bbystatic.com/BestBuy_US/images/products/{sku[:4]}/{filename}',source]
  else:urls.append(source.replace('http://','https://',1))
 return list(dict.fromkeys(urls))

def validate_real_image(path_or_bytes):
 with Image.open(io.BytesIO(path_or_bytes) if isinstance(path_or_bytes,bytes) else path_or_bytes) as im:
  im.load()  # Full decode catches truncated JPEGs that verify() alone misses.
  sample=im.convert('RGB').resize((32,32))
  with Image.open(SOURCES/'unavailable_image_reference.jpg') as reference:
   reference.load()
   distance=sum(ImageStat.Stat(ImageChops.difference(sample,reference.convert('RGB').resize((32,32)))).mean)/3
  if distance<5:raise ValueError('Image Unavailable placeholder, not a product photo')

def collect_one(row,group,official):
 sku=str(row['objectID']);pid='bb-'+sku
 folder=ROOT/'categories'/group/pid;folder.mkdir(parents=True,exist_ok=True)
 path=folder/'main.jpg'
 title=clean(row['name']);attempts=[];image_meta=None
 cache=folder/'image_metadata.json'
 if path.exists() and cache.exists():
  try:
   validate_real_image(path)
   image_meta=json.loads(cache.read_text(encoding='utf8'))
  except Exception: image_meta=None
 if not image_meta:
  for url in image_candidates(row,official):
   try:
    req=urllib.request.Request(url,headers={'User-Agent':'ServAI-Learning-Material-Collector/1.0'})
    with urllib.request.urlopen(req,timeout=16) as response:
     final_url=response.geturl();b=response.read(12*1024*1024+1)
     content_type=response.headers.get('Content-Type','')
    if len(b)>12*1024*1024:raise ValueError('Image exceeds 12MB')
    validate_real_image(b)
    with Image.open(io.BytesIO(b)) as im:
     im.verify()
    with Image.open(io.BytesIO(b)) as im:
     width,height=im.size;fmt=im.format
     if min(width,height)<100:raise ValueError('Image too small')
     if fmt!='JPEG':
      im.convert('RGB').save(path,quality=94)
     else:path.write_bytes(b)
    image_meta={'source_url':url,'resolved_url':final_url,'width':width,'height':height,'content_type':content_type,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'original_format':fmt,'status':'verified','downloaded_at':COLLECTED,'rights_status':'third_party_product_image_not_separately_verified'}
    cache.write_text(json.dumps(image_meta,ensure_ascii=False,indent=2),encoding='utf8');break
   except Exception as error:attempts.append({'url':url,'error':str(error)})
 if not image_meta:return None,{'sku':sku,'category':group,'attempts':attempts}
 description=clean(row.get('description'));official_desc=clean(official.get('description')) if official else ''
 text=' '.join([title,description,official_desc]);facts=feature_extract(text)
 details={k:official.get(k) for k in ['manufacturer','model','upc','type'] if official and official.get(k)}
 product_url=urllib.parse.urlsplit(row.get('url',''));source_url=urllib.parse.urlunsplit(('https',product_url.netloc,product_url.path,'',''))
 record={
  'id':pid,'source_sku':sku,'category_id':group,'category_name_zh':LABELS[group],
  'name_original':title,'brand':clean(row.get('brand')) or None,'model':details.get('model'),
  'description_original':description,'description_official_dataset':official_desc or None,
  'introduction_zh':chinese_intro(row,group,facts),'introduction_method':'rule_based_summary_of_category_and_source_evidence_not_full_translation',
  'price':{'amount':row.get('price'),'currency':'USD','kind':'historical_dataset_price','observed_at':None,'current_price_verified':False},
  'source_categories':row.get('categories',[]),'specifications_original':details,
  'extracted_attributes':facts,'attribute_extraction_method':'regex_matches_with_evidence_not_independently_verified',
  'images':[{'local_path':path.relative_to(ROOT).as_posix(),'alt':title,**image_meta}],
  'source':{'publisher':'Best Buy','official_dataset_url':SOURCE_URL,'metadata_mirror_url':MIRROR_URL,'product_url':source_url,'collected_at':COLLECTED,'catalog_date':'historical (official dataset copyright 2016; mirror exact snapshot date unknown)','metadata_license':'CC-BY-NC-4.0 applies to official BestBuy dataset; mirror-derived descriptions need separate rights verification'},
  'quality':{'raw_original_preserved':True,'image_decoded':True,'description_present':bool(description),'official_dataset_match':bool(official),'missing_fields':[k for k,v in [('model',details.get('model')),('upc',details.get('upc'))] if not v]},
 }
 (folder/'product.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
 (folder/'source_original.json').write_text(json.dumps({'algolia':row,'bestbuy':official},ensure_ascii=False,indent=2),encoding='utf8')
 (folder/'introduction.txt').write_text(record['introduction_zh']+'\n',encoding='utf8')
 lines=[f'# {title}',f'\n分类：{LABELS[group]}\n',f'品牌：{record["brand"]}\n',f'历史价格：USD {row.get("price")}（非当前报价）\n','## 中文简要介绍\n',record['introduction_zh'],'\n## 英文介绍\n',description,'\n## 原始参数\n',json.dumps(details,ensure_ascii=False,indent=2),'\n## 来源\n',source_url,'\n历史目录素材；中文简介为整理摘要，不是品牌官方中文文案。']
 (folder/'introduction.md').write_text('\n'.join(lines),encoding='utf8')
 return record,None

def main():
 import sqlite3
 rows=json.loads((SOURCES/'algolia_records.json').read_text(encoding='utf8'))
 db=SOURCES/'bestbuy_complete.sqlite'
 conn=sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True);conn.row_factory=sqlite3.Row
 official={str(row['id']):dict(row) for row in conn.execute('SELECT * FROM products')}
 buckets=defaultdict(list)
 seen=set()
 for row in rows:
  group=classify(row)
  if not group or len(clean(row.get('description')))<60:continue
  key=re.sub(r'[^a-z0-9]','',clean(row['name']).lower())
  if key in seen:continue
  seen.add(key);buckets[group].append(row)
 for group in buckets:
  by_brand=defaultdict(deque)
  for row in buckets[group]:by_brand[clean(row.get('brand'))].append(row)
  ordered=[]
  while any(by_brand.values()):
   for brand in sorted(by_brand):
    if by_brand[brand]:ordered.append(by_brand[brand].popleft())
  buckets[group]=ordered
 print('Candidate counts:',{k:len(v) for k,v in buckets.items()},flush=True)
 records=[];failures=[];candidates=[]
 with ThreadPoolExecutor(max_workers=8) as pool:
  for group,label,target in GROUPS:
   got=[];index=0
   while len(got)<target and index<len(buckets[group]):
    batch=buckets[group][index:index+min(16,target-len(got))];index+=len(batch)
    futures={pool.submit(collect_one,row,group,official.get(str(row['objectID']))):row for row in batch}
    for future in as_completed(futures):
     record,error=future.result()
     if record:got.append(record)
     else:failures.append(error)
    print(label,len(got),'/',target,flush=True)
   records.extend(sorted(got,key=lambda x:x['source_sku']))
 records.sort(key=lambda x:(x['category_id'],x['source_sku']))
 (ROOT/'products.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
 (ROOT/'products.jsonl').write_text(''.join(json.dumps(record,ensure_ascii=False)+'\n' for record in records),encoding='utf8')
 report={'count':len(records),'target':400,'collected_at':COLLECTED,'categories':dict(Counter(r['category_name_zh'] for r in records)),'verified_images':len(records),'official_dataset_matches':sum(r['quality']['official_dataset_match'] for r in records),'with_extracted_attributes':sum(bool(r['extracted_attributes']) for r in records),'with_model':sum(bool(r['model']) for r in records),'with_price':sum(r['price']['amount'] is not None for r in records),'unique_skus':len({r['source_sku'] for r in records}),'unique_image_hashes':len({r['images'][0]['sha256'] for r in records}),'total_image_bytes':sum(r['images'][0]['bytes'] for r in records),'image_failures':failures,'source_file_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [db,SOURCES/'algolia_records.json']}}
 (ROOT/'collection_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print('FINISHED',json.dumps({k:v for k,v in report.items() if k not in ['image_failures','source_file_sha256']},ensure_ascii=False),flush=True)
 if len(records)!=400:raise SystemExit('Collection incomplete: see report')
if __name__=='__main__':main()
