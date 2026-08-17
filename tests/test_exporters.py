import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import modules.database as database_module
from modules.database import DataManager, initialize_database
from modules.exporters import HTMLExporter, export_book


class TestHTMLExporter(unittest.TestCase):
    def test_escapes_book_metadata_and_chapter_content(self):
        book_data = {
            'title': '<script>book</script>',
            'author': 'A & B',
            'summary': '<summary>',
            'children': [
                {
                    'name': '<Volume>',
                    'children': [
                        {
                            'name': '<Chapter>',
                            'content': '<img src=x onerror=alert(1)>',
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'book.html')

            self.assertTrue(HTMLExporter().export(book_data, output_path))

            with open(output_path, encoding='utf-8') as output_file:
                rendered_html = output_file.read()

        self.assertIn('&lt;script&gt;book&lt;/script&gt;', rendered_html)
        self.assertIn('A &amp; B', rendered_html)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', rendered_html)
        self.assertNotIn('<script>book</script>', rendered_html)
        self.assertNotIn('<img src=x onerror=alert(1)>', rendered_html)


class TestExportBook(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_db_file = database_module.DB_FILE
        database_module.DB_FILE = os.path.join(self.test_dir, 'export.db')
        initialize_database()
        self.data_manager = DataManager()

    def tearDown(self):
        self.data_manager.close_local_connection()
        database_module.DB_FILE = self.original_db_file
        shutil.rmtree(self.test_dir)

    def test_export_fetches_chapter_content_in_bulk(self):
        book_id = self.data_manager.add_book('Export Test')
        first_chapter = self.data_manager.add_chapter(book_id, 'Vol 1', 'First')
        second_chapter = self.data_manager.add_chapter(book_id, 'Vol 1', 'Second')
        self.data_manager.update_chapter_content(first_chapter, 'FIRST')
        self.data_manager.update_chapter_content(second_chapter, 'SECOND')
        output_path = os.path.join(self.test_dir, 'book.txt')

        with patch.object(
            self.data_manager,
            'get_chapter_content',
            wraps=self.data_manager.get_chapter_content,
        ) as get_chapter_content:
            result = export_book(
                self.data_manager,
                book_id,
                'txt',
                output_path,
            )

        self.assertTrue(result)
        get_chapter_content.assert_not_called()
        with open(output_path, encoding='utf-8') as output_file:
            self.assertIn('FIRST', output_file.read())

