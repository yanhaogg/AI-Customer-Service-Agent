"""Read-only API checks against the imported PostgreSQL collection."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.catalog import router

class CatalogApiTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  app=FastAPI();app.include_router(router);cls.client=TestClient(app)
 def test_pagination_search_categories_and_prices(self):
  data=self.client.get('/api/catalog/products').json()
  self.assertEqual(data['total'],400);self.assertEqual(len(data['items']),24)
  page2=self.client.get('/api/catalog/products?page=2').json()
  self.assertFalse({p['id'] for p in data['items']} & {p['id'] for p in page2['items']})
  cats=self.client.get('/api/catalog/categories').json()['items']
  self.assertEqual(len(cats),12);self.assertEqual(sum(c['count'] for c in cats),400)
  audio=self.client.get('/api/catalog/products?category=05_audio&page_size=60').json()
  self.assertEqual(audio['total'],75)
  searched=self.client.get('/api/catalog/products',params={'q':'Bose'}).json()
  self.assertGreater(searched['total'],0)
  low=self.client.get('/api/catalog/products?sort=price_asc&page_size=60').json()
  prices=[float(p['price']['amount']) for p in low['items']]
  self.assertEqual(prices,sorted(prices))
  self.assertTrue(all(p['price']['currency']=='USD' and p['price']['is_historical'] for p in data['items']))
  self.assertEqual(self.client.get('/api/catalog/products',params={'q':'not-a-product-12345'}).json()['total'],0)
  self.assertEqual(self.client.get('/api/catalog/products',params={'q':'%'}).json()['total'],0)
  self.assertEqual(self.client.get('/api/catalog/products?page_size=999').status_code,422)
 def test_home_detail_and_local_image(self):
  home=self.client.get('/api/catalog/home').json()
  self.assertEqual(home['total'],400);self.assertIsNotNone(home['hero']['image'])
  self.assertEqual(len(home['spotlights']),2);self.assertEqual(len(home['featured']),8)
  detail=self.client.get(f"/api/catalog/products/{home['hero']['id']}")
  self.assertEqual(detail.status_code,200);self.assertTrue(detail.json()['description_original'])
  image=self.client.get(home['hero']['image']['url'])
  self.assertEqual(image.status_code,200);self.assertIn('image/',image.headers['content-type']);self.assertGreater(len(image.content),1000)
  self.assertEqual(self.client.get('/api/catalog/products/999999999').status_code,404)
  self.assertEqual(self.client.get('/api/catalog/media/999999999').status_code,404)
if __name__=='__main__':unittest.main()
