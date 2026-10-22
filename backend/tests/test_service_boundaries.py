"""约束全项目的 API、请求模型、服务与 Agent 依赖边界。"""

import ast
from pathlib import Path
import unittest


class ServiceBoundaryTests(unittest.TestCase):
    def test_services_do_not_import_api(self):
        folder = Path(__file__).resolve().parents[1] / "app" / "services"
        for path in folder.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(
                        (node.module or "").startswith("app.api"), str(path)
                    )
                elif isinstance(node, ast.Import):
                    self.assertFalse(
                        any(alias.name.startswith("app.api") for alias in node.names),
                        str(path),
                    )

    def test_all_routes_leave_database_operations_to_services(self):
        folder = Path(__file__).resolve().parents[1] / "app/api"
        for path in folder.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        self.assertNotEqual(node.func.value.id, "db", str(path))
                if isinstance(node, ast.ClassDef):
                    self.fail(f"请求模型应放在 schemas：{path}:{node.name}")

    def test_agents_do_not_depend_on_http_routes(self):
        folder = Path(__file__).resolve().parents[1] / "app/agent"
        for path in folder.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(
                        (node.module or "").startswith("app.api"), str(path)
                    )


if __name__ == "__main__":
    unittest.main()
