import unittest
import sys
import os

def run_tests():
    # Ensure the current directory is in sys.path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    
    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = os.path.join(current_dir, 'tests')
    suite = loader.discover(start_dir)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    run_tests()
