"""待办功能移除后，不再暴露业务接口或向客服助手注入待办。"""

import unittest
from fastapi.testclient import TestClient
from app.main import server


class RemovedSupportTaskTests(unittest.TestCase):
    def test_task_endpoints_are_removed(self):
        self.assertFalse(any("support-tasks" in p for p in server.openapi()["paths"]))
        with TestClient(server) as client:
            self.assertEqual(client.get("/api/admin/support-tasks").status_code, 404)
            self.assertEqual(
                client.post(
                    "/api/admin/support-tasks/preview", json={"order_id": 1}
                ).status_code,
                404,
            )


if __name__ == "__main__":
    unittest.main()
