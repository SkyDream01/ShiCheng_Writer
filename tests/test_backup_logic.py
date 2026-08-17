import unittest
import os
import shutil
import tempfile
import json
import zipfile
from datetime import datetime, timedelta
from unittest.mock import patch
from modules.database import DataManager, initialize_database
import modules.database as database_module
from modules.backup import BackupManager, BackupWorker

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
        book_id = self.data_manager.add_book(
            title="Backup Test Book",
            description="Desc",
            cover_path="cover.png",
        )
        self.book_id = book_id
        # Add chapters
        self.chapter_id = self.data_manager.add_chapter(book_id, "Vol 1", "Chapter 1")
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

    def test_full_backup_fetches_chapter_text_in_bulk(self):
        self.data_manager.add_chapter(self.book_id, "Vol 1", "Chapter 2")

        with patch.object(
            self.data_manager,
            'get_chapter_content',
            wraps=self.data_manager.get_chapter_content,
        ) as get_chapter_content:
            zip_path = BackupWorker('stage', self.backup_dir)._create_zip(
                self.data_manager,
                "bulk_content_",
            )

        self.assertIsNotNone(zip_path)
        get_chapter_content.assert_not_called()

    def test_backup_filenames_do_not_overwrite_same_second_backups(self):
        worker = BackupWorker('stage', self.backup_dir)
        fixed_time = datetime(2026, 1, 1, 12, 0, 0)

        with patch('modules.backup.datetime') as backup_datetime:
            backup_datetime.now.return_value = fixed_time
            first_path = worker._create_zip(self.data_manager, "same_second_")
            second_path = worker._create_zip(self.data_manager, "same_second_")

        self.assertIsNotNone(first_path)
        self.assertIsNotNone(second_path)
        self.assertNotEqual(first_path, second_path)
        self.assertTrue(os.path.exists(first_path))
        self.assertTrue(os.path.exists(second_path))

    def test_stale_worker_result_does_not_change_active_backup_state(self):
        manager = BackupManager(self.data_manager, self.backup_dir)
        stale_worker = BackupWorker('snapshot', self.backup_dir)
        active_worker = BackupWorker('stage', self.backup_dir)
        manager._current_worker = active_worker
        manager._pending_snapshot_check_time = datetime(2026, 1, 1, 12, 0, 0)
        previous_check_time = manager.last_snapshot_check_time

        manager._on_worker_finished(
            True,
            'stale complete',
            worker=stale_worker,
        )

        self.assertEqual(manager.last_snapshot_check_time, previous_check_time)
        self.assertIsNotNone(manager._pending_snapshot_check_time)

    def test_chapter_content_files_use_stable_ids(self):
        second_chapter_id = self.data_manager.add_chapter(
            self.book_id,
            "Vol 1",
            "Chapter 2",
        )
        self.data_manager.update_chapter_content(self.chapter_id, "FIRST")
        self.data_manager.update_chapter_content(second_chapter_id, "SECOND")
        with self.data_manager.conn:
            self.data_manager.conn.execute(
                "UPDATE chapters SET createTime = NULL WHERE id IN (?, ?)",
                (self.chapter_id, second_chapter_id),
            )

        zip_path = BackupWorker('stage', self.backup_dir)._create_zip(
            self.data_manager,
            "stable_ids_",
        )

        with zipfile.ZipFile(zip_path, 'r') as archive:
            content_files = sorted(
                name for name in archive.namelist() if '/content/' in name
            )
            self.assertEqual(
                content_files,
                [
                    f'book/{self.book_id}/content/chapter_{self.chapter_id}.json',
                    f'book/{self.book_id}/content/chapter_{second_chapter_id}.json',
                ],
            )
            book_data = json.loads(
                archive.read(f'book/{self.book_id}/book.json')
            )
            chapter_metadata = book_data['children'][0]['children']
            self.assertEqual(
                {chapter['id'] for chapter in chapter_metadata},
                {self.chapter_id, second_chapter_id},
            )

    def test_incomplete_zip_is_rejected_without_clearing_data(self):
        backup_path = os.path.join(
            self.backup_dir,
            'backup_stage_incomplete.zip',
        )
        with zipfile.ZipFile(backup_path, 'w') as archive:
            archive.writestr('README.txt', 'missing manifest')

        manager = BackupManager(self.data_manager, self.backup_dir)
        result = manager.restore_from_backup({
            'file': os.path.basename(backup_path),
            'dir': self.backup_dir,
            'type': 'Stage',
        })

        self.assertFalse(result)
        self.assertIsNotNone(self.data_manager.get_book_details(self.book_id))
        self.assertIsNotNone(self.data_manager.get_chapter_details(self.chapter_id))

    def test_restore_failure_rolls_back_current_connection(self):
        valid_path = BackupWorker('stage', self.backup_dir)._create_zip(
            self.data_manager,
            "rollback_source_",
        )
        broken_path = os.path.join(
            self.backup_dir,
            'backup_stage_broken_material.zip',
        )
        with zipfile.ZipFile(valid_path, 'r') as source, zipfile.ZipFile(
            broken_path,
            'w',
            zipfile.ZIP_DEFLATED,
        ) as destination:
            for name in source.namelist():
                if name == 'materials.json':
                    destination.writestr(name, json.dumps([{}]))
                else:
                    destination.writestr(name, source.read(name))

        manager = BackupManager(self.data_manager, self.backup_dir)
        result = manager.restore_from_backup({
            'file': os.path.basename(broken_path),
            'dir': self.backup_dir,
            'type': 'Stage',
        })

        self.assertFalse(result)
        self.assertEqual(
            self.data_manager.get_book_details(self.book_id)['title'],
            'Backup Test Book',
        )
        self.data_manager.add_book('After rollback')
        self.data_manager.close_local_connection()
        self.data_manager = DataManager()
        self.assertEqual(
            {book['title'] for book in self.data_manager.get_all_books()},
            {'Backup Test Book', 'After rollback'},
        )

    def test_full_restore_preserves_chapter_ids_and_cover(self):
        original_content = "content captured by backup"
        self.data_manager.update_chapter_content(self.chapter_id, original_content)
        zip_path = BackupWorker('stage', self.backup_dir)._create_zip(
            self.data_manager,
            "roundtrip_",
        )

        self.data_manager.update_chapter_content(self.chapter_id, "newer content")
        extra_book_id = self.data_manager.add_book("Extra")

        manager = BackupManager(self.data_manager, self.backup_dir)
        result = manager.restore_from_backup({
            'file': os.path.basename(zip_path),
            'dir': self.backup_dir,
            'type': 'Stage',
        })

        self.assertTrue(result)
        self.assertIsNone(self.data_manager.get_book_details(extra_book_id))
        self.assertEqual(
            self.data_manager.get_chapter_content(self.chapter_id)[0],
            original_content,
        )
        self.assertEqual(
            self.data_manager.get_book_details(self.book_id)['cover_path'],
            'cover.png',
        )

    def test_busy_snapshot_does_not_advance_cursor(self):
        class BusyWorker:
            @staticmethod
            def isRunning():
                return True

        manager = BackupManager(self.data_manager, self.backup_dir)
        manager.last_snapshot_check_time = datetime.now() - timedelta(days=1)
        previous_check_time = manager.last_snapshot_check_time
        manager._current_worker = BusyWorker()

        self.assertFalse(manager.create_snapshot_backup())
        self.assertEqual(manager.last_snapshot_check_time, previous_check_time)

if __name__ == '__main__':
    unittest.main()
