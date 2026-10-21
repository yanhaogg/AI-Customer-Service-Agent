"""Import local product materials into PostgreSQL. No network downloads.

From the project root:
  backend/venv/Scripts/python.exe backend/scripts/import_products.py --check-only
  backend/venv/Scripts/python.exe backend/scripts/import_products.py
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))


class MaterialError(ValueError):
    """Actionable validation failure before any database writes."""


def required_text(value, field):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise MaterialError(f'{field}: 需要非空文本，且不能包含 NUL 字符')
    return value


def parse_timestamp(value, field, optional=False):
    if value is None and optional:
        return None
    try:
        parsed = datetime.fromisoformat(required_text(value, field).replace('Z', '+00:00'))
    except ValueError as error:
        raise MaterialError(f'{field}: 时间必须为带时区的 ISO 8601 格式') from error
    if parsed.tzinfo is None:
        raise MaterialError(f'{field}: 时间缺少时区')
    return parsed.astimezone(timezone.utc)


def material_path(root, relative):
    required_text(relative, 'local_path')
    portable = PurePosixPath(relative)
    if '\\' in relative or ':' in relative or portable.is_absolute() or '..' in portable.parts:
        raise MaterialError(f'素材路径必须是素材库内部的相对路径: {relative}')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise MaterialError(f'素材路径越出素材库: {relative}')
    return path


def price_amount(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise MaterialError('price.amount: 金额不能为布尔值')
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number >= Decimal('10000000000'):
            raise MaterialError('price.amount: 金额超出 NUMERIC(12,2) 范围')
        if number != number.quantize(Decimal('.01')):
            raise MaterialError('price.amount: 金额最多保留两位小数')
        return number.quantize(Decimal('.01'))
    except InvalidOperation as error:
        raise MaterialError('price.amount: 金额格式无效') from error


def load_materials(input_path, material_root):
    """Read and validate the entire batch including local image hashes and raw sources."""
    root = material_root.resolve()
    products = []
    ids, sources, category_names = set(), set(), {}
    with input_path.open(encoding='utf-8-sig') as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise MaterialError('商品记录必须为对象')
                for field in ['id', 'source_sku', 'category_id', 'category_name_zh',
                              'name_original', 'description_original', 'introduction_zh']:
                    required_text(row.get(field), field)
                for field in ['id', 'category_id']:
                    if not re.fullmatch(r'[A-Za-z0-9_-]+', row[field]):
                        raise MaterialError(f'{field}: 仅支持字母、数字、下划线和连字符')
                source = row.get('source')
                if not isinstance(source, dict):
                    raise MaterialError('source: 必须为对象')
                required_text(source.get('publisher'), 'source.publisher')
                required_text(source.get('metadata_license'), 'source.metadata_license')
                collected_at = parse_timestamp(source.get('collected_at'), 'source.collected_at')
                identity = (source['publisher'], row['source_sku'])
                if row['id'] in ids or identity in sources:
                    raise MaterialError(f'批次中存在重复商品或来源 SKU: {row["id"]}')
                ids.add(row['id']); sources.add(identity)
                category = row['category_id']
                if category in category_names and category_names[category] != row['category_name_zh']:
                    raise MaterialError(f'同一分类代码对应不同名称: {category}')
                category_names[category] = row['category_name_zh']
                for field in ['specifications_original', 'quality']:
                    if not isinstance(row.get(field, {}), dict):
                        raise MaterialError(f'{field}: 必须为对象')
                if not isinstance(row.get('extracted_attributes', []), list):
                    raise MaterialError('extracted_attributes: 必须为数组')
                for field in ['brand', 'model']:
                    if row.get(field) is not None:
                        required_text(row[field], field)
                price = row.get('price')
                if not isinstance(price, dict):
                    raise MaterialError('price: 必须为对象')
                amount = price_amount(price.get('amount'))
                if not re.fullmatch(r'[A-Z]{3}', str(price.get('currency', ''))):
                    raise MaterialError('price.currency: 必须为三位大写币种代码')
                if price.get('kind') != 'historical_dataset_price' or price.get('current_price_verified') is not False:
                    raise MaterialError('只支持未验证当前售价的历史目录价格')
                observed_at = parse_timestamp(price.get('observed_at'), 'price.observed_at', optional=True)
                images = row.get('images')
                if not isinstance(images, list) or not images:
                    raise MaterialError('商品至少需要一张本地图')
                seen_images = set()
                for image in images:
                    if not isinstance(image, dict):
                        raise MaterialError('图片记录必须为对象')
                    path = material_path(root, image.get('local_path'))
                    if not path.is_file():
                        raise MaterialError(f'图片不存在: {image["local_path"]}')
                    digest = image.get('sha256', '')
                    if not re.fullmatch(r'[0-9a-f]{64}', str(digest)):
                        raise MaterialError('图片 SHA-256 格式无效')
                    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                        raise MaterialError(f'图片 SHA-256 不匹配: {image["local_path"]}')
                    if digest in seen_images:
                        raise MaterialError(f'同一商品包含重复图片: {row["id"]}')
                    seen_images.add(digest)
                    for field in ['width', 'height', 'bytes']:
                        if type(image.get(field)) is not int or image[field] <= 0:
                            raise MaterialError(f'图片 {field}: 必须为正整数')
                    if image['bytes'] != path.stat().st_size or image.get('status') != 'verified':
                        raise MaterialError(f'图片大小或校验状态无效: {image["local_path"]}')
                    required_text(image.get('source_url'), 'image.source_url')
                    required_text(image.get('rights_status'), 'image.rights_status')
                    parse_timestamp(image.get('downloaded_at'), 'image.downloaded_at', optional=True)
                raw_path = material_path(root, f'categories/{category}/{row["id"]}/source_original.json')
                if not raw_path.is_file():
                    raise MaterialError(f'缺少原始来源文件: {raw_path.relative_to(root)}')
                raw = json.loads(raw_path.read_text(encoding='utf-8-sig'))
                if not isinstance(raw, dict):
                    raise MaterialError('原始来源记录必须为对象')
                # Reject NaN/Infinity anywhere, which PostgreSQL JSONB cannot store.
                json.dumps({'row': row, 'raw': raw}, allow_nan=False)
                products.append({'row': row, 'raw': raw, 'collected_at': collected_at,
                                 'amount': amount, 'observed_at': observed_at})
            except (ValueError, TypeError, KeyError, OSError) as error:
                raise MaterialError(f'第 {line_number} 行: {error}') from error
    if not products:
        raise MaterialError('素材文件没有有效商品记录')
    return products


def import_materials(connection, materials):
    """Caller controls transaction. Upsert only catalog data owned by these sources."""
    from sqlalchemy import select, update
    from sqlalchemy.dialects.postgresql import insert
    from app.database.catalog_models import (
        CatalogCategory, Product, MediaAsset, ProductSource, ProductImage, ProductPriceRecord,
    )

    def upsert(model, values, keys, update_fields=None):
        table = model.__table__
        statement = insert(table).values(**values)
        fields = update_fields if update_fields is not None else [k for k in values if k not in keys and k != 'id']
        assignments = {field: getattr(statement.excluded, field) for field in fields}
        statement = statement.on_conflict_do_update(index_elements=keys, set_=assignments)
        return connection.execute(statement.returning(table.c.id)).scalar_one()

    category_ids, asset_ids = {}, {}
    counts = Counter(products=0, sources=0, images=0, price_records=0)
    for material in materials:
        row, source = material['row'], material['row']['source']
        code = row['category_id']
        if code not in category_ids:
            category_ids[code] = upsert(CatalogCategory, {'code': code, 'name': row['category_name_zh']}, ['code'])
        source_identity = [ProductSource.source_name == source['publisher'], ProductSource.source_sku == row['source_sku']]
        existing_source = connection.execute(select(ProductSource.product_id).where(*source_identity)).scalar_one_or_none()
        product_values = {
            'import_key': row['id'], 'category_id': category_ids[code],
            'name_original': row['name_original'], 'brand': row.get('brand'), 'model': row.get('model'),
            'description_original': row['description_original'], 'introduction_zh': row['introduction_zh'],
            'specs': {'verified': {}, 'source_original': row.get('specifications_original', {}),
                      'extracted': row.get('extracted_attributes', []),
                      'extraction_method': row.get('attribute_extraction_method'),
                      'introduction_method': row.get('introduction_method')},
            'quality': row.get('quality', {}), 'updated_at': datetime.now(timezone.utc),
        }
        previous = connection.execute(select(Product.__table__).where(
            Product.id == existing_source if existing_source is not None else Product.import_key == row['id']
        )).mappings().one_or_none()
        if previous:
            # Keep manually reviewed specs, translated title, status and internal identity.
            product_values['import_key'] = previous['import_key']
            product_values['specs']['verified'] = (previous['specs'] or {}).get('verified', {})
            connection.execute(update(Product).where(Product.id == previous['id']).values(**product_values))
            product_id = previous['id']
        else:
            product_id = upsert(Product, product_values, ['import_key'])
        source_id = upsert(ProductSource, {
            'product_id': product_id, 'source_name': source['publisher'], 'source_sku': row['source_sku'],
            'product_url': source.get('product_url'), 'official_dataset_url': source.get('official_dataset_url'),
            'metadata_mirror_url': source.get('metadata_mirror_url'), 'catalog_date': source.get('catalog_date'),
            'metadata_license': source['metadata_license'], 'collected_at': material['collected_at'],
            'raw_data': {'standardized': row, 'original': material['raw']},
        }, ['source_name', 'source_sku'])
        # Replace this source's image associations, preserving other sources' associations.
        connection.execute(ProductImage.__table__.delete().where(ProductImage.source_id == source_id))
        has_primary = connection.execute(select(ProductImage.id).where(
            ProductImage.product_id == product_id, ProductImage.is_primary.is_(True)
        )).first() is not None
        for position, image in enumerate(row['images']):
            digest = image['sha256']
            if digest not in asset_ids:
                asset_ids[digest] = upsert(MediaAsset, {
                    'storage_key': image['local_path'], 'sha256': digest, 'width': image['width'],
                    'height': image['height'], 'byte_size': image['bytes'],
                    'content_type': 'image/jpeg' if image['local_path'].lower().endswith(('.jpg', '.jpeg')) else image.get('content_type', 'application/octet-stream'),
                }, ['sha256'])
            connection.execute(insert(ProductImage).values(
                product_id=product_id, source_id=source_id, asset_id=asset_ids[digest], sort_order=position,
                is_primary=position == 0 and not has_primary, alt=image.get('alt', row['name_original']),
                source_url=image['source_url'], resolved_url=image.get('resolved_url'),
                rights_status=image['rights_status'],
                downloaded_at=parse_timestamp(image.get('downloaded_at'), 'image.downloaded_at', optional=True),
                original_metadata=image,
            ))
            counts['images'] += 1
        if material['amount'] is not None:
            price = row['price']
            fingerprint = {'amount': str(material['amount']), 'currency': price['currency'],
                           'kind': price['kind'], 'observed_at': material['observed_at'].isoformat() if material['observed_at'] else None}
            record_key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
            statement = insert(ProductPriceRecord).values(
                product_id=product_id, source_id=source_id, record_key=record_key, amount=material['amount'],
                currency=price['currency'], price_kind=price['kind'], observed_at=material['observed_at'],
                collected_at=material['collected_at'], current_price_verified=False,
            ).on_conflict_do_nothing(index_elements=['source_id', 'record_key'])
            connection.execute(statement)
            counts['price_records'] += 1
        counts['products'] += 1; counts['sources'] += 1
    return {**counts, 'categories': len(category_ids), 'unique_assets': len(asset_ids)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='导入本地商品素材到 PostgreSQL（可重复执行，整批事务）')
    parser.add_argument('--input', type=Path, default=PROJECT / 'product_materials/products.jsonl')
    parser.add_argument('--materials-root', type=Path, default=PROJECT / 'product_materials')
    parser.add_argument('--check-only', action='store_true', help='仅检查文件、数据和图片哈希，不连接数据库')
    args = parser.parse_args(argv)
    try:
        materials = load_materials(args.input, args.materials_root)
        summary = {'products': len(materials), 'categories': len({m['row']['category_id'] for m in materials}),
                   'image_links': sum(len(m['row']['images']) for m in materials),
                   'unique_assets': len({im['sha256'] for m in materials for im in m['row']['images']})}
        print('素材校验通过: ' + json.dumps(summary, ensure_ascii=False))
        if args.check_only:
            print('仅校验模式：没有连接或写入数据库。')
            return 0
        from dotenv import load_dotenv
        load_dotenv(BACKEND / '.env')
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from sqlalchemy.exc import SQLAlchemyError
        from app.database.catalog_models import CATALOG_TABLES
        from app.database.database import Base, DATABASE_URL
        url = make_url(os.getenv('DATABASE_URL') or DATABASE_URL)
        if url.get_backend_name() != 'postgresql':
            raise MaterialError('本脚本仅支持 PostgreSQL DATABASE_URL')
        engine = create_engine(url, connect_args={'connect_timeout': 10})
        try:
            with engine.begin() as connection:
                # Serialize catalog imports without blocking ordinary product reads.
                connection.execute(text("SET LOCAL lock_timeout = '15s'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(734120401)"))
                Base.metadata.create_all(connection, tables=CATALOG_TABLES)
                result = import_materials(connection, materials)
            print('导入成功（整批已提交，数量为本次处理记录）: ' + json.dumps(result, ensure_ascii=False))
        except SQLAlchemyError as error:
            code = getattr(getattr(error, 'orig', None), 'pgcode', None) or getattr(getattr(error, 'orig', None), 'sqlstate', None)
            print(f'数据库操作失败，整批事务已回滚。SQLSTATE: {code or "unknown"}。请检查数据库连接、权限及已有表结构。', file=sys.stderr)
            return 1
        finally:
            engine.dispose()
        return 0
    except (MaterialError, OSError, json.JSONDecodeError) as error:
        print(f'导入未完成: {error}', file=sys.stderr)
        return 1
    except ImportError:
        print('缺少依赖，请使用 backend 虚拟环境并安装 backend/requirements.txt。', file=sys.stderr)
        return 1
    except ValueError:
        print('数据库连接配置或数据格式无效，请检查 DATABASE_URL；密码及连接串不会输出。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())

