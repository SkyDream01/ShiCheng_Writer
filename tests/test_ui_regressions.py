import os
import gc
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMessageBox

import modules.database as database_module
from main_window import MainWindow
from modules.backup import BackupManager
from modules.database import DataManager, initialize_database
from modules.inspiration import InspirationKitPanel
from widgets.editor import Editor


class InspirationDataManagerStub:
    def __init__(self):
        self.fragment = {
            'id': 1,
            'type': 'text',
            'content': 'old content',
            'source': 'test',
        }
        self.update_arguments = None

    def get_inspiration_fragments(self):
        return [dict(self.fragment)]

    def update_inspiration_fragment(
        self,
        fragment_id,
        type=None,
        content=None,
        source=None,
    ):
        self.update_arguments = {
            'fragment_id': fragment_id,
            'type': type,
            'content': content,
            'source': source,
        }
        if content is not None:
            self.fragment['content'] = content
        return True


class TestUIRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_nonempty_material_highlighter_does_not_raise(self):
        editor = Editor()
        editor.update_highlighter(['角色甲'])
        self.assertEqual(len(editor.highlighter.highlighting_rules), 1)

    def test_inspiration_edit_updates_content_not_type(self):
        data_manager = InspirationDataManagerStub()
        panel = InspirationKitPanel(data_manager)
        item = panel.list_widget.item(0)

        with patch(
            'modules.inspiration.QInputDialog.getMultiLineText',
            return_value=('new content', True),
        ):
            panel.edit_fragment(item)

        self.assertEqual(data_manager.update_arguments['fragment_id'], 1)
        self.assertIsNone(data_manager.update_arguments['type'])
        self.assertEqual(data_manager.update_arguments['content'], 'new content')


class TestMainWindowRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_db_file = database_module.DB_FILE
        database_module.DB_FILE = os.path.join(self.test_dir, 'ui.db')
        initialize_database()
        self.data_manager = DataManager()
        self.backup_manager = BackupManager(
            self.data_manager,
            os.path.join(self.test_dir, 'backups'),
        )
        with patch('main_window.QTimer.singleShot'):
            self.window = MainWindow(
                self.data_manager,
                self.backup_manager,
                'light',
            )
        self.window.snapshot_timer.stop()
        self.window.stage_point_timer.stop()
        self.window.autosave_timer.stop()
        self.window.typing_timer.stop()

    def tearDown(self):
        for worker in list(self.window._load_workers):
            worker.wait()
        if (
            self.window.save_chapter_worker
            and self.window.save_chapter_worker.isRunning()
        ):
            self.window.save_chapter_worker.wait()
        self.app.processEvents()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.data_manager.close_local_connection()
        database_module.DB_FILE = self.original_db_file
        gc.collect()
        for attempt in range(3):
            try:
                shutil.rmtree(self.test_dir)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.05)

    def test_clear_editor_does_not_create_dirty_state(self):
        self.window.current_chapter_id = None
        self.window.editor.setPlainText('unsaved')
        self.assertTrue(self.window.is_text_changed)

        self.window._clear_editor_content()

        self.assertFalse(self.window.is_text_changed)
        self.assertEqual(self.window.editor.toPlainText(), '')

    def test_recent_chapter_from_another_book_loads_target(self):
        first_book = self.data_manager.add_book('First')
        self.data_manager.add_chapter(first_book, 'V', 'First chapter')
        second_book = self.data_manager.add_book('Second')
        target_chapter = self.data_manager.add_chapter(
            second_book,
            'V',
            'Target chapter',
        )
        self.data_manager.update_chapter_content(target_chapter, 'TARGET')
        self.window.load_books()

        self.window.open_recent_chapter(target_chapter)
        for worker in list(self.window._load_workers):
            worker.wait()
        self.app.processEvents()

        self.assertEqual(self.window.current_book_id, second_book)
        self.assertEqual(self.window.current_chapter_id, target_chapter)
        self.assertEqual(self.window.editor.toPlainText(), 'TARGET')

    def test_queued_save_keeps_original_chapter_identity(self):
        first_book = self.data_manager.add_book('First')
        first_chapter = self.data_manager.add_chapter(
            first_book,
            'V',
            'First chapter',
        )
        second_book = self.data_manager.add_book('Second')
        second_chapter = self.data_manager.add_chapter(
            second_book,
            'V',
            'Second chapter',
        )

        class RunningWorkerStub:
            @staticmethod
            def isRunning():
                return True

        running_worker = RunningWorkerStub()
        self.window.save_chapter_worker = running_worker
        self.window.current_chapter_id = second_chapter
        self.window._trigger_async_save(
            'FIRST LATEST',
            chapter_id=first_chapter,
        )

        self.window._on_save_worker_thread_finished(running_worker)
        real_worker = self.window.save_chapter_worker
        real_worker.wait()
        self.app.processEvents()

        self.assertEqual(
            self.data_manager.get_chapter_content(first_chapter)[0],
            'FIRST LATEST',
        )
        self.assertNotEqual(
            self.data_manager.get_chapter_content(second_chapter)[0],
            'FIRST LATEST',
        )

    def test_close_is_cancelled_when_save_fails(self):
        book_id = self.data_manager.add_book('Book')
        chapter_id = self.data_manager.add_chapter(book_id, 'V', 'Chapter')
        self.window.current_book_id = book_id
        self.window.current_chapter_id = chapter_id
        self.window.editor.setPlainText('unsaved changes')

        class CloseEventStub:
            def __init__(self):
                self.accepted = False
                self.ignored = False

            def accept(self):
                self.accepted = True

            def ignore(self):
                self.ignored = True

        event = CloseEventStub()
        with patch(
            'main_window.QMessageBox.question',
            return_value=QMessageBox.Save,
        ), patch(
            'main_window.QMessageBox.critical',
        ), patch.object(
            self.data_manager,
            'update_chapter_content',
            return_value=False,
        ):
            self.window.closeEvent(event)

        self.assertTrue(event.ignored)
        self.assertFalse(event.accepted)


if __name__ == '__main__':
    unittest.main()
