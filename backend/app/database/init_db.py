from app.database.database import engine
from app.database.models import Base
from app.database.admin_migration import migrate_admin
from app.database import shop_models
from app.database import activity_models
from app.database.activity_migration import migrate_activity
from app.database.aftersales_migration import migrate_aftersales


def init_database():

    with engine.begin() as connection:
        Base.metadata.create_all(bind=connection)
        migrate_admin(connection)
        migrate_activity(connection)
        migrate_aftersales(connection)


if __name__ == "__main__":

    init_database()

    print("Database initialized")
