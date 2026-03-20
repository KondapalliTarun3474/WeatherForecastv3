import unittest
import json
import os

class TestFrontendConfig(unittest.TestCase):
    def test_package_json_validity(self):
        file_path = os.path.join(os.path.dirname(__file__), 'package.json')
        self.assertTrue(os.path.exists(file_path), "package.json not found")
        with open(file_path, 'r') as f:
            data = json.load(f)
            self.assertIn('name', data)
            self.assertIn('version', data)

if __name__ == '__main__':
    unittest.main()
