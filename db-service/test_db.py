"""
test_db.py - Unit tests for db-service
Uses mongomock to avoid needing a real MongoDB instance.
"""
import unittest
import json
import sys
import os

# Patch pymongo before importing db_service so mongomock is used
import mongomock
import unittest.mock as mock

# Patch MongoClient globally before the module loads
patcher = mock.patch("pymongo.MongoClient", mongomock.MongoClient)
patcher.start()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_service import app, get_db, _ensure_indexes

# Re-run indexes on the mock db
with app.app_context():
    try:
        db = get_db()
    except Exception:
        pass


class TestDBServiceHealth(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    def test_health_returns_up(self):
        """Health endpoint should return status 'up'."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "up")
        self.assertEqual(data["service"], "db-service")

    def test_version_endpoint(self):
        """Version endpoint should return a version string."""
        resp = self.client.get("/version")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("version", data)

    def test_metrics_endpoint_is_plaintext(self):
        """Metrics endpoint should return Prometheus-style plaintext."""
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"db_requests_total", resp.data)


class TestUserCRUD(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True
        # Clean DB between tests
        db = get_db()
        db.users.drop()
        _ensure_indexes(db)

    def test_create_and_fetch_user(self):
        """Creating a user and retrieving it should work end-to-end."""
        payload = {
            "username": "alice",
            "password": "secret123",
            "role": "user",
            "has_llm_access": False,
            "access_requested": False,
        }
        resp = self.client.post("/users",
                                data=json.dumps(payload),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 201)

        resp = self.client.get("/users/alice")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["username"], "alice")
        self.assertEqual(data["role"], "user")
        self.assertNotIn("password_hash", data)  # Should not expose hash

    def test_duplicate_user_returns_400(self):
        """Creating same username twice should return 400."""
        payload = {"username": "bob", "password": "pass", "role": "user"}
        self.client.post("/users", data=json.dumps(payload), content_type="application/json")
        resp = self.client.post("/users", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_get_nonexistent_user_returns_404(self):
        """Fetching a user that doesn't exist should return 404."""
        resp = self.client.get("/users/nobody")
        self.assertEqual(resp.status_code, 404)

    def test_update_llm_access(self):
        """Updating has_llm_access via PUT should persist."""
        self.client.post("/users",
                         data=json.dumps({"username": "carol", "password": "x", "role": "user"}),
                         content_type="application/json")
        resp = self.client.put("/users/carol",
                               data=json.dumps({"has_llm_access": True}),
                               content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/users/carol")
        data = json.loads(resp.data)
        self.assertTrue(data["has_llm_access"])

    def test_delete_user(self):
        """Deleting a user should remove them from the DB."""
        self.client.post("/users",
                         data=json.dumps({"username": "dave", "password": "x", "role": "user"}),
                         content_type="application/json")
        resp = self.client.delete("/users/dave")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/users/dave")
        self.assertEqual(resp.status_code, 404)

    def test_verify_password_correct(self):
        """Password verification should succeed for correct password."""
        self.client.post("/users",
                         data=json.dumps({"username": "eve", "password": "mypassword", "role": "user"}),
                         content_type="application/json")
        resp = self.client.post("/users/eve/verify",
                                data=json.dumps({"password": "mypassword"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["valid"])

    def test_verify_password_wrong(self):
        """Password verification should fail for wrong password."""
        self.client.post("/users",
                         data=json.dumps({"username": "frank", "password": "right", "role": "user"}),
                         content_type="application/json")
        resp = self.client.post("/users/frank/verify",
                                data=json.dumps({"password": "wrong"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)
        data = json.loads(resp.data)
        self.assertFalse(data["valid"])

    def test_list_pending_users(self):
        """Should return only users who requested access but don't have it yet."""
        self.client.post("/users",
                         data=json.dumps({"username": "grace", "password": "x", "role": "user",
                                          "access_requested": True, "has_llm_access": False}),
                         content_type="application/json")
        self.client.post("/users",
                         data=json.dumps({"username": "heidi", "password": "x", "role": "user",
                                          "access_requested": False, "has_llm_access": True}),
                         content_type="application/json")
        resp = self.client.get("/users/pending")
        data = json.loads(resp.data)
        self.assertIn("grace", data["users"])
        self.assertNotIn("heidi", data["users"])


class TestInferenceLog(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True
        db = get_db()
        db.inference_logs.drop()

    def _log(self, user_id, model="T2M"):
        return self.client.post("/inference-log",
                                data=json.dumps({"user_id": user_id, "model_name": model, "lat": 13.0, "lon": 77.5}),
                                content_type="application/json")

    def test_log_and_retrieve(self):
        """Logging a prediction and fetching it should work."""
        self._log("user1", "T2M")
        resp = self.client.get("/inference-log/user1")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data["history"]), 1)
        self.assertEqual(data["history"][0]["model_name"], "T2M")

    def test_bounded_history_enforced(self):
        """After MAX_HISTORY+2 logs, only MAX_HISTORY should be stored."""
        for i in range(12):  # MAX_HISTORY is 10 by default
            self._log("user2", f"T2M")
        resp = self.client.get("/inference-log/user2")
        data = json.loads(resp.data)
        self.assertLessEqual(len(data["history"]), 10)

    def test_missing_user_id_returns_400(self):
        """Omitting user_id should return 400."""
        resp = self.client.post("/inference-log",
                                data=json.dumps({"model_name": "T2M"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_empty_history_returns_empty_list(self):
        """Getting history for an unknown user returns empty list."""
        resp = self.client.get("/inference-log/unknown_user")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["history"], [])


if __name__ == "__main__":
    unittest.main()
