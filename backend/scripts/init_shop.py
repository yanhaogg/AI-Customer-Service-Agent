"""Create shopping tables without changing legacy orders; optional explicit demo offers."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.database.database import engine
from app.database.shop_models import SHOP_TABLES, SaleOffer
from app.database.catalog_models import Product, ProductPriceRecord
from sqlalchemy.orm import Session


def migrate_shop(connection):
    for table in SHOP_TABLES:
        table.create(connection, checkfirst=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed-demo-offers', action='store_true', help='Copy historical prices into separate demo offers; initial mock stock=100')
    args = parser.parse_args()
    count = 0
    with engine.begin() as connection:
        migrate_shop(connection)
        if args.seed_demo_offers:
            with Session(bind=connection) as db:
                for product in db.scalars(select(Product).where(Product.status.in_(['draft','reviewed','published']))):
                    if db.get(SaleOffer, product.id) is not None:
                        continue
                    price = db.scalar(select(ProductPriceRecord).where(ProductPriceRecord.product_id == product.id)
                        .order_by(ProductPriceRecord.collected_at.desc(), ProductPriceRecord.id.desc()).limit(1))
                    if price and price.amount > 0 and price.currency in ('USD','CNY','EUR','GBP','JPY','HKD'):
                        db.add(SaleOffer(product_id=product.id, price=price.amount, currency=price.currency, stock=100, is_active=True))
                        count += 1
                db.flush()
    print(f'Shopping tables ready. Created {count} DEMO offers; no real payment or stock involved.')


if __name__ == '__main__':
    main()
