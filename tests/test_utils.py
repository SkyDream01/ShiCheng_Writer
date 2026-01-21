import unittest
import os
from modules.utils import get_app_root, resource_path

class TestUtils(unittest.TestCase):
    def test_get_app_root(self):
        root = get_app_root()
        self.assertTrue(os.path.exists(root))
        self.assertTrue(os.path.isdir(root))

    def test_resource_path(self):
        # Assuming there is a resources directory or we can check relative path joining
        path = resource_path("test.txt")
        root = get_app_root()
        expected = os.path.join(root, "test.txt")
        self.assertEqual(path, expected)

if __name__ == '__main__':
    unittest.main()
