import unittest
import os
import shutil
import tempfile
from modules.database import DataManager, initialize_database
import modules.database as database_module

class TestDataManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_db.db")
        
        # Patch the DB_FILE in the database module
        self.original_db_file = database_module.DB_FILE
        database_module.DB_FILE = self.db_path
        
        # Initialize database schema
        initialize_database()
        
        # Initialize DataManager
        self.data_manager = DataManager()

    def tearDown(self):
        # Close connection
        self.data_manager.close_local_connection()
        # Restore DB_FILE
        database_module.DB_FILE = self.original_db_file
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def test_add_and_get_book(self):
        book_id = self.data_manager.add_book(
            title="Test Book", 
            description="A test description", 
            group="Test Group"
        )
        self.assertIsNotNone(book_id)
        
        book = self.data_manager.get_book_details(book_id)
        self.assertEqual(book['title'], "Test Book")
        self.assertEqual(book['description'], "A test description")
        self.assertEqual(book['group'], "Test Group")

    def test_add_chapter(self):
        book_id = self.data_manager.add_book(title="Test Book")
        chapter_id = self.data_manager.add_chapter(
            book_id=book_id,
            volume="Volume 1",
            title="Chapter 1"
        )
        
        chapter = self.data_manager.get_chapter_details(chapter_id)
        self.assertEqual(chapter['title'], "Chapter 1")
        self.assertEqual(chapter['volume'], "Volume 1")
        self.assertEqual(chapter['book_id'], book_id)

    def test_update_chapter_content(self):
        book_id = self.data_manager.add_book(title="Test Book")
        chapter_id = self.data_manager.add_chapter(book_id=book_id, volume="Vol 1", title="Chap 1")
        
        new_content = "This is new content."
        self.data_manager.update_chapter_content(chapter_id, new_content)
        
        content, word_count = self.data_manager.get_chapter_content(chapter_id)
        self.assertEqual(content, new_content)
        self.assertEqual(word_count, len(new_content))

    def test_recycle_bin(self):
        book_id = self.data_manager.add_book(title="Test Book")
        self.data_manager.delete_book(book_id)
        
        book = self.data_manager.get_book_details(book_id)
        self.assertIsNone(book)
        
        items = self.data_manager.get_recycle_bin_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['item_type'], 'book')
        
        self.data_manager.restore_recycle_item(items[0]['id'])
        book = self.data_manager.get_book_details(book_id)
        self.assertIsNotNone(book)
        self.assertEqual(book['title'], "Test Book")

    def test_inspiration_fragments(self):
        # Test add
        frag_id = self.data_manager.add_inspiration_fragment(type="text", content="An idea", source="Shower")
        self.assertIsNotNone(frag_id)
        
        # Test get
        frags = self.data_manager.get_inspiration_fragments()
        self.assertEqual(len(frags), 1)
        self.assertEqual(frags[0]['content'], "An idea")
        
        # Test update
        self.data_manager.update_inspiration_fragment(frag_id, content="Updated idea")
        frags = self.data_manager.get_inspiration_fragments()
        self.assertEqual(frags[0]['content'], "Updated idea")
        
        # Test delete
        self.data_manager.delete_inspiration_fragment(frag_id)
        frags = self.data_manager.get_inspiration_fragments()
        self.assertEqual(len(frags), 0)

    def test_inspiration_items(self):
        # Test add
        item_id = self.data_manager.add_inspiration_item(title="Hero", content="Strong", tags="char")
        self.assertIsNotNone(item_id)
        
        # Test get
        items = self.data_manager.get_inspiration_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], "Hero")
        
        # Test update
        self.data_manager.update_inspiration_item(item_id, title="Superhero")
        items = self.data_manager.get_inspiration_items()
        self.assertEqual(items[0]['title'], "Superhero")
        
        # Test delete
        self.data_manager.delete_inspiration_item(item_id)
        items = self.data_manager.get_inspiration_items()
        self.assertEqual(len(items), 0)

    def test_materials(self):
        # Basic add
        material_id = self.data_manager.add_material(
            name="Excalibur",
            type="Weapon",
            description="King Arthur's sword"
        )
        self.assertIsNotNone(material_id)
        
        # Test complex content (JSON)
        complex_content = {
            "attributes": [
                {"name": "Power", "value": "9000", "type": "Number"},
                {"name": "Owner", "value": "Arthur", "type": "String"}
            ]
        }
        self.data_manager.update_material(material_id, name="Excalibur", type="Weapon", description="...", content=complex_content)
        
        material = self.data_manager.get_material_details(material_id)
        # The content should be retrieved as a dict
        self.assertIsInstance(material['content'], dict)
        # Note: Depending on implementation, it might be wrapped or direct. 
        # get_material_details implementation:
        # if material_data['content']:
        #     try: material_data['content'] = json.loads(...)
        
        # Let's verify the content structure matches what we expect from get_material_details
        # If content was saved as {"attributes": ...}, it should come back as such.
        self.assertEqual(material['content']['attributes'][0]['name'], "Power")

    def test_timeline_full_crud(self):
        book_id = self.data_manager.add_book(title="Epic Story")
        timeline_id = self.data_manager.add_timeline(book_id, "Main Timeline")
        
        # Test manual update of events (simulating save_and_close in UI)
        events_data = [
            {
                "id": 101,
                "timeline_id": timeline_id,
                "title": "Event 1",
                "event_time": "2023",
                "order_index": 0,
                "referenced_materials": []
            },
            {
                "id": 102,
                "timeline_id": timeline_id,
                "title": "Event 2",
                "event_time": "2024",
                "order_index": 1,
                "referenced_materials": [{"id": 1, "name": "Mat1"}]
            }
        ]
        
        self.data_manager.update_timeline_events(timeline_id, events_data)
        
        events = self.data_manager.get_timeline_events(timeline_id)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]['title'], "Event 1")
        # Verify JSON serialization/deserialization of referenced_materials might be needed if the DB stores it as string
        # database.py: update_timeline_events: referenced_materials_json = json.dumps(...)
        # But get_timeline_events does NOT json.loads it automatically in the current implementation? 
        # Let's check modules/database.py get_timeline_events...
        # It just does: return [dict(row) for row in cursor.fetchall()]
        # So referenced_materials will be a string.
        self.assertIsInstance(events[1]['referenced_materials'], str)
        import json
        refs = json.loads(events[1]['referenced_materials'])
        self.assertEqual(refs[0]['name'], "Mat1")

if __name__ == '__main__':
    unittest.main()
