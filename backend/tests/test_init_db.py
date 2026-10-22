"""验证统一入口覆盖所有模型，并能按外键依赖生成 PostgreSQL 建表语句。"""

import ast
from pathlib import Path
import sys
import unittest
from typing import get_args, get_type_hints

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_mock_engine
from sqlalchemy.orm import DeclarativeBase, Mapped
from typing import get_origin
from app.database.init_db import Base


class DatabaseInitializationTests(unittest.TestCase):
    def test_models_use_typed_declarative_mapping(self):
        self.assertTrue(issubclass(Base, DeclarativeBase))
        for mapper in Base.registry.mappers:
            hints = get_type_hints(mapper.class_)
            for attribute in mapper.column_attrs:
                hint = hints[attribute.key]
                self.assertIs(get_origin(hint), Mapped)
                value_type = get_args(hint)[0]
                self.assertEqual(
                    type(None) in get_args(value_type),
                    attribute.columns[0].nullable,
                    f"{mapper.class_.__name__}.{attribute.key}",
                )

    def test_every_declared_table_is_registered(self):
        expected = set()
        folder = Path(__file__).resolve().parents[1] / "app" / "database"
        for path in folder.glob("*models.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Assign):
                    if any(
                        isinstance(target, ast.Name) and target.id == "__tablename__"
                        for target in node.targets
                    ):
                        expected.add(ast.literal_eval(node.value))
        self.assertTrue(expected)
        self.assertEqual(expected, set(Base.metadata.tables))

    def test_postgres_ddl_covers_registered_tables(self):
        created = []

        def execute(statement, *args, **kwargs):
            # 实际编译可发现未注册的外键目标或 PostgreSQL 类型不兼容等问题。
            str(statement.compile(dialect=engine.dialect))
            if statement.__visit_name__ == "create_table":
                created.append(statement.element.name)

        engine = create_mock_engine("postgresql://", execute)
        Base.metadata.create_all(engine, checkfirst=False)
        self.assertEqual(set(created), set(Base.metadata.tables))


if __name__ == "__main__":
    unittest.main()
