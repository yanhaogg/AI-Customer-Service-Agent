"""Finalize readable Chinese summaries and preserve conservative field semantics."""
from pathlib import Path
import json
import collect
ROOT=Path(__file__).resolve().parents[1]
rows=json.loads((ROOT/'products.json').read_text(encoding='utf8'))
for row in rows:
 parts=[]
 for fact in row['extracted_attributes']:
  key,value=fact['attribute'],fact['value_original']
  if key=='screen_size':
   fact['attribute']='size_inch_mention'
   piece='尺寸 '+value.replace('inches','英寸').replace('inch','英寸').replace('"',' 英寸').replace('”',' 英寸')
  elif key=='storage_or_memory':piece='容量 '+value
  elif key=='resolution':piece='分辨率 '+value
  elif key=='battery_capacity':piece='电池容量 '+value
  elif key=='camera_resolution':piece='成像规格 '+value
  elif key=='connectivity':piece='接口或连接方式 '+value
  else:continue
  if piece not in parts:parts.append(piece)
 brand=row['brand'] or '该品牌'
 intro=f"{brand} 的{row['category_name_zh']}商品。"
 if parts:intro+='来源介绍提及：'+'；'.join(parts[:3])+'。具体对应的部件或兼容设备，请结合英文原文确认。'
 else:intro+='具体功能、适用设备和配件说明见保留的英文原文。'
 intro+='该记录来自历史商品目录，实际参数与当前售价需重新核对。'
 old=row['introduction_zh'];row['introduction_zh']=intro
 folder=ROOT/'categories'/row['category_id']/row['id']
 (folder/'product.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
 (folder/'introduction.txt').write_text(intro+'\n',encoding='utf8')
 md=folder/'introduction.md';md.write_text(md.read_text(encoding='utf8').replace(old,intro),encoding='utf8')
(ROOT/'products.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
(ROOT/'products.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf8')
print('Finalized',len(rows),'Chinese summaries')
