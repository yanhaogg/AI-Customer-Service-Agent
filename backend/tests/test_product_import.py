"""Importer validation tests and transactional PostgreSQL integration checks.
No catalog rows are committed: integration tables live in a rollback-only schema.
"""
from pathlib import Path
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
import uuid

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location('product_importer', BACKEND / 'scripts/import_products.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)
ROOT = BACKEND.parent / 'product_materials'


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materials = importer.load_materials(ROOT / 'products.jsonl', ROOT)

    def check_rows(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'products.jsonl'
            path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows), encoding='utf8')
            return importer.load_materials(path, ROOT)

    def test_entire_collection_and_deduplicated_images(self):
        self.assertEqual(len(self.materials), 400)
        hashes = {im['sha256'] for m in self.materials for im in m['row']['images']}
        self.assertEqual(len(hashes), 395)

    def test_duplicate_source_rejected(self):
        row = self.materials[0]['row']
        with self.assertRaises(importer.MaterialError):
            self.check_rows([row, row])

    def test_path_escape_rejected(self):
        row = copy.deepcopy(self.materials[0]['row'])
        row['images'][0]['local_path'] = '../backend/.env'
        with self.assertRaises(importer.MaterialError):
            self.check_rows([row])

    def test_bad_image_hash_rejected(self):
        row = copy.deepcopy(self.materials[0]['row'])
        row['images'][0]['sha256'] = '0' * 64
        with self.assertRaises(importer.MaterialError):
            self.check_rows([row])

    def test_historical_price_and_missing_observation_time(self):
        self.assertIsNone(self.materials[0]['observed_at'])
        row = copy.deepcopy(self.materials[0]['row'])
        row['price']['amount'] = 0.001
        with self.assertRaises(importer.MaterialError):
            self.check_rows([row])
        row['price']['amount'] = 29.99
        row['price']['current_price_verified'] = True
        with self.assertRaises(importer.MaterialError):
            self.check_rows([row])


@unittest.skipUnless(os.getenv('CATALOG_PG_TEST') == '1', 'Set CATALOG_PG_TEST=1 for rollback-only PostgreSQL tests')
class PostgreSQLTests(unittest.TestCase):
    def test_import_repeat_reviewed_fields_and_atomic_rollback(self):
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, select, func, update, text
        load_dotenv(BACKEND / '.env')
        from app.database.database import Base, DATABASE_URL
        from app.database.catalog_models import (
            CATALOG_TABLES, CatalogCategory, Product, MediaAsset,
            ProductSource, ProductImage, ProductPriceRecord,
        )
        engine = create_engine(os.getenv('DATABASE_URL') or DATABASE_URL, connect_args={'connect_timeout': 5})
        schema = 'catalog_test_' + uuid.uuid4().hex
        connection = engine.connect()
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection = connection.execution_options(schema_translate_map={None: schema})
            Base.metadata.create_all(connection, tables=CATALOG_TABLES)
            materials = importer.load_materials(ROOT / 'products.jsonl', ROOT)
            importer.import_materials(connection, materials)
            models = (CatalogCategory, Product, MediaAsset, ProductSource, ProductImage, ProductPriceRecord)

            def counts():
                return [connection.scalar(select(func.count()).select_from(model)) for model in models]

            self.assertEqual(counts(), [12, 400, 395, 400, 400, 400])
            product_id = connection.scalar(select(Product.id).where(Product.import_key == materials[0]['row']['id']))
            connection.execute(update(Product).where(Product.id == product_id).values(
                name_zh='人工翻译的名称', status='reviewed', specs={'verified': {'reviewed_example': True}},
            ))
            importer.import_materials(connection, materials)
            self.assertEqual(counts(), [12, 400, 395, 400, 400, 400])
            reviewed = connection.execute(select(Product.__table__).where(Product.id == product_id)).mappings().one()
            self.assertEqual(reviewed['name_zh'], '人工翻译的名称')
            self.assertEqual(reviewed['status'], 'reviewed')
            self.assertTrue(reviewed['specs']['verified']['reviewed_example'])
            self.assertEqual(reviewed['specs']['source_original'], materials[0]['row']['specifications_original'])
            self.assertEqual(connection.scalar(select(func.count()).select_from(ProductImage).where(ProductImage.is_primary.is_(True))), 400)
            self.assertEqual(connection.scalar(select(func.count()).select_from(ProductPriceRecord).where(ProductPriceRecord.observed_at.is_(None))), 400)
            saved = counts()
            savepoint = connection.begin_nested()
            changed = copy.deepcopy(materials[:2])
            changed[0]['row']['introduction_zh'] = '此更新应回滚'
            changed[1]['row']['source']['publisher'] = None  # Fail after the first product is written.
            try:
                with self.assertRaises(Exception):
                    importer.import_materials(connection, changed)
            finally:
                savepoint.rollback()
            self.assertEqual(counts(), saved)
            self.assertEqual(connection.scalar(select(Product.introduction_zh).where(Product.id == product_id)), materials[0]['row']['introduction_zh'])
        finally:
            transaction.rollback()
            connection.close()
        # The schema and all test rows must disappear with the transaction.
        with engine.connect() as verify:
            exists = verify.scalar(text('SELECT count(*) FROM pg_namespace WHERE nspname = :name'), {'name': schema})
            self.assertEqual(exists, 0)
        engine.dispose()


if __name__ == '__main__':
    unittest.main()

