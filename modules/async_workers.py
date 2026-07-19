from PySide6.QtCore import QThread, Signal
import logging

logger = logging.getLogger(__name__)

class LoadChapterWorker(QThread):
    """加载章节内容的异步工作线程"""
    completed = Signal(object, object)  # content (str), word_count (int)
    error = Signal(str)

    def __init__(self, data_manager, chapter_id):
        super().__init__()
        self.data_manager = data_manager
        self.chapter_id = chapter_id

    def run(self):
        content = ""
        word_count = 0
        error_message = None
        try:
            # 在 data_manager 内部按需创建新连接（由 thread-local 处理）
            content, word_count = self.data_manager.get_chapter_content(self.chapter_id)
        except Exception as e:
            logger.error(f"Error loading chapter {self.chapter_id}: {e}", exc_info=True)
            error_message = str(e)
        finally:
            self.data_manager.close_local_connection()
        if error_message is not None:
            self.error.emit(error_message)
        else:
            self.completed.emit(content, word_count)

class SaveChapterWorker(QThread):
    """保存章节内容的异步工作线程"""
    completed = Signal(bool)  # 成功
    error = Signal(str)

    def __init__(self, data_manager, chapter_id, content):
        super().__init__()
        self.data_manager = data_manager
        self.chapter_id = chapter_id
        self.content = content

    def run(self):
        success = False
        error_message = None
        try:
            success = self.data_manager.update_chapter_content(
                self.chapter_id,
                self.content,
            )
            if not success:
                error_message = f"章节 {self.chapter_id} 不存在"
        except Exception as e:
            logger.error(f"Error saving chapter {self.chapter_id}: {e}", exc_info=True)
            error_message = str(e)
        finally:
            self.data_manager.close_local_connection()
        if error_message is not None:
            self.error.emit(error_message)
        self.completed.emit(success)
