import unittest
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class TestMLOpsComponents(unittest.TestCase):
    def test_imports(self):
        try:
            import model
            import data_pipeline
        except ImportError as e:
            self.fail(f"Failed to import modules: {e}")

if __name__ == '__main__':
    unittest.main()
