import unittest
import os
import shutil
import tempfile
import json
import zipfile
from PySide6.QtCore import QThread
from modules.database import DataManager, initialize_database
import modules.database as database_module
from modules.backup import BackupWorker

class TestBackupLogic(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_db.db")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir)
        
        # Patch the DB_FILE in the database module
        self.original_db_file = database_module.DB_FILE
        database_module.DB_FILE = self.db_path
        
        # Initialize database schema
        initialize_database()
        
        # Initialize DataManager and populate with data
        self.data_manager = DataManager()
        self._populate_data()
        
    def _populate_data(self):
        # Add a book
        book_id = self.data_manager.add_book(title="Backup Test Book", description="Desc")
        # Add chapters
        self.data_manager.add_chapter(book_id, "Vol 1", "Chapter 1")
        # Add materials
        self.data_manager.add_material(name="Mat1", type="Text", description="Desc")

    def tearDown(self):
        self.data_manager.close_local_connection()
        database_module.DB_FILE = self.original_db_file
        shutil.rmtree(self.test_dir)

    def test_create_zip_backup(self):
        # We instantiate BackupWorker directly.
        # Since we are not calling start(), run() is not executed in a thread.
        # We will directly call _create_zip.
        
        worker = BackupWorker('stage', self.backup_dir)
        
        # We need to pass the data_manager instance to _create_zip
        # In the actual code, _run_full_backup creates a new DataManager.
        # We can pass our self.data_manager which is connected to the test DB.
        
        zip_path = worker._create_zip(self.data_manager, "test_backup_")
        
        self.assertIsNotNone(zip_path)
        self.assertTrue(os.path.exists(zip_path))
        self.assertTrue(zip_path.endswith('.zip'))
        
        # Verify zip content
        with zipfile.ZipFile(zip_path, 'r') as zf:
            file_list = zf.namelist()
            
            # Check for bookList.json
            self.assertIn('book/bookList.json', file_list)
            
            # Check for materials.json
            self.assertIn('materials.json', file_list)
            
            # Read bookList.json and verify content
            with zf.open('book/bookList.json') as f:
                book_list = json.load(f)
                self.assertEqual(len(book_list), 1)
                self.assertEqual(book_list[0]['name'], "Backup Test Book")
            
            # Read materials.json
            with zf.open('materials.json') as f:
                materials = json.load(f)
                self.assertEqual(len(materials), 1)
                self.assertEqual(materials[0]['name'], "Mat1")

if __name__ == '__main__':
    unittest.main()
