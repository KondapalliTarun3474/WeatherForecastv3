import unittest
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from param_service import app

class TestInferenceService(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_health_check(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'up')

    def test_version_check(self):
        response = self.app.get('/version')
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
