import urllib.request,concurrent.futures,time,pathlib
URL='https://raw.githubusercontent.com/BestBuy/api-playground/master/dataset.sqlite'
SIZE=60936192
root=pathlib.Path('product_materials/sources/bestbuy_chunks');root.mkdir(exist_ok=True)
def get(i):
 start=i*4*1024*1024;end=min(SIZE,start+4*1024*1024)-1;p=root/f'{i:02}.part'
 if p.exists() and p.stat().st_size==end-start+1:return p
 for attempt in range(3):
  try:
   req=urllib.request.Request(URL+f'?chunk={i}',headers={'Range':f'bytes={start}-{end}'})
   with urllib.request.urlopen(req,timeout=45) as r:
    if r.status!=206:raise ValueError(f'Expected range response, got {r.status}')
    b=r.read()
   if len(b)!=end-start+1:raise ValueError('Incomplete range')
   p.write_bytes(b);print('Chunk',i,'ready',flush=True);return p
  except Exception as e:
   if attempt==2:raise
   time.sleep(1+attempt)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 paths=list(pool.map(get,range((SIZE+4*1024*1024-1)//(4*1024*1024))))
p=pathlib.Path('product_materials/sources/bestbuy_complete.sqlite')
with p.open('wb') as f:
 for part in paths:f.write(part.read_bytes())
print('COMPLETE',p.stat().st_size,flush=True)
