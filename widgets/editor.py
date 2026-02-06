# ShiCheng_Writer/widgets/editor.py
import logging
from PySide6.QtWidgets import QTextEdit, QApplication
from PySide6.QtGui import (QSyntaxHighlighter, QTextCharFormat, QColor, QFont, 
                           QTextBlockFormat, QTextCursor, QTextDocument) 
from PySide6.QtCore import QRegularExpression, Qt

logger = logging.getLogger(__name__)

class MaterialHighlighter(QSyntaxHighlighter):
    """素材高亮器 - 性能优化版"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        
        self.highlight_format = QTextCharFormat()
        self.update_highlight_color()
        
        # 缓存优化
        self._current_materials_hash = None
        self._cached_pattern = None
        self._cached_materials_list = None

    def update_highlight_color(self):
        palette = QApplication.instance().palette()
        # 简单的暗色主题检测
        is_dark_theme = palette.window().color().lightness() < 128
        
        if is_dark_theme:
            # 暗色模式：深蓝背景，亮灰字，柔和护眼
            self.highlight_format.setBackground(QColor("#1e3a5f"))
            self.highlight_format.setForeground(QColor("#dcdcdc"))
        else: 
            # 亮色模式：极淡蓝背景，深色字
            self.highlight_format.setBackground(QColor("#e3f2fd"))
            self.highlight_format.setForeground(QColor("#2c3e50"))

        self.highlight_format.setFontWeight(QFont.Bold)
        self.highlight_format.setToolTip("这是一个素材")
        self.rehighlight()

    def set_materials_list(self, materials_list):
        """设置需要高亮的素材列表
        
        Args:
            materials_list: 素材名称列表
        """
        # 检查材料列表是否实际发生变化
        if materials_list is None:
            materials_list = []
        
        # 快速路径：如果列表为空，直接清除高亮
        if not materials_list:
            if self._current_materials_hash is not None:
                self.highlighting_rules = []
                self._current_materials_hash = None
                self._cached_pattern = None
                self._cached_materials_list = None
                self.rehighlight()
            return
        
        # 计算当前列表的哈希（使用frozenset提高性能）
        materials_set = frozenset(materials_list)
        new_hash = hash(materials_set)
        
        # 如果哈希相同，跳过更新
        if self._current_materials_hash == new_hash:
            return
        
        self.highlighting_rules = []
        
        # 1. 按长度降序排序，防止短词覆盖长词
        sorted_by_length = sorted(materials_list, key=len, reverse=True)

        # 2. [核心优化] 分离 ASCII (需要 \b) 和 非ASCII (不需要 \b) 关键词
        ascii_keywords = []
        non_ascii_keywords = []
        
        for m in sorted_by_length:
            if not m or not m.strip():
                continue
            # 使用str.isascii()方法（Python 3.7+）更高效
            if m.isascii():
                ascii_keywords.append(QRegularExpression.escape(m))
            else:
                non_ascii_keywords.append(QRegularExpression.escape(m))

        patterns_parts = []
        if ascii_keywords:
            patterns_parts.append(f"\\b({'|'.join(ascii_keywords)})\\b")
        if non_ascii_keywords:
            patterns_parts.append(f"({'|'.join(non_ascii_keywords)})")
        
        if not patterns_parts:
            self.rehighlight()
            return

        pattern_str = "|".join(patterns_parts)
        
        # 使用优化选项创建正则表达式
        pattern = QRegularExpression(pattern_str)
        pattern.setOptimizationHints(QRegularExpression.OptimizeOnFirstUsageOption)
        self.highlighting_rules.append((pattern, self.highlight_format))
        
        # 更新缓存
        self._current_materials_hash = new_hash
        self._cached_pattern = pattern
        self._cached_materials_list = sorted(materials_list)
        
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

class Editor(QTextEdit):
    """自定义文本编辑器 - 视觉优化版"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighter = MaterialHighlighter(self.document())
        
        # 设置文档边距，营造“纸张”感
        self.setViewportMargins(40, 20, 40, 20)
        
        # 加宽光标
        self.setCursorWidth(2)
        
        self.set_font_size("16px") 
        
    def set_font_size(self, size_str):
        font = self.font()
        try:
            size = int(size_str.replace('px', ''))
            font.setPointSize(size)
            # 使用字体族列表，兼容多平台
            font.setFamilies(["Microsoft YaHei", "PingFang SC", "Heiti SC", "SimHei", "Sans-Serif"])
            self.setFont(font)
            
            # 设置Tab宽度为4个空格
            self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
            
            # 初始化行间距 (150% 行高)
            self.set_line_height(150)
            
        except ValueError:
            logger.warning(f"无效的字体大小: {size_str}")

    def set_line_height(self, percentage):
        """设置行高百分比"""
        block_fmt = QTextBlockFormat()
        # 1 = ProportionalHeight (按比例设置行高)
        block_fmt.setLineHeight(percentage, 1) 
        
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.mergeBlockFormat(block_fmt)
        cursor.clearSelection()
        self.setTextCursor(cursor)
        
    def auto_indent_document(self):
        """
        [优化] 全文缩进：使用 Cursor 操作，保留撤销栈历史，不重置视图
        """
        cursor = self.textCursor()
        cursor.beginEditBlock() # 开始编辑块，确保可一次性撤销
        
        doc = self.document()
        # 遍历所有段落
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            text = block.text()
            
            # 仅对非空、非缩进、非标题行进行缩进
            if text.strip() and not text.startswith(("　　", "    ", "#")):
                cursor.setPosition(block.position())
                cursor.insertText("　　")
        
        cursor.endEditBlock() # 结束编辑块

    def auto_unindent_document(self):
        """
        [优化] 取消缩进：使用 Cursor 操作，保留撤销栈历史
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()
        
        doc = self.document()
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            text = block.text()
            
            cursor.setPosition(block.position())
            
            if text.startswith("　　"):
                # 选中前两个字符并删除
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 2)
                cursor.removeSelectedText()
            elif text.startswith("    "):
                # 选中前四个字符并删除
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 4)
                cursor.removeSelectedText()
                
        cursor.endEditBlock()

    def update_highlighter(self, materials_list):
        """外部调用此方法来更新需要高亮的素材词汇"""
        self.highlighter.set_materials_list(materials_list)
        self.highlighter.update_highlight_color()

    def find_text(self, text, backward=False, case_sensitive=False, whole_words=False):
        """查找文本"""
        if not text:
            return False
            
        flags = QTextDocument.FindFlags()
        if backward:
            flags |= QTextDocument.FindBackward
        if case_sensitive:
            flags |= QTextDocument.FindCaseSensitively
        if whole_words:
            flags |= QTextDocument.FindWholeWords
            
        found = self.find(text, flags)
        return found

    def replace_current(self, text):
        """替换当前选中的文本"""
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.insertText(text)
            return True
        return False

    def replace_all(self, target, replacement, case_sensitive=False, whole_words=False):
        """全部替换"""
        if not target:
            return 0
            
        # 保存当前光标位置
        original_cursor = self.textCursor()
        
        # 移动到文档开头开始查找
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.setTextCursor(cursor)
        
        count = 0
        cursor.beginEditBlock() # 批量替换作为一次撤销
        while self.find_text(target, False, case_sensitive, whole_words):
            self.replace_current(replacement)
            count += 1
        cursor.endEditBlock()
        
        # 恢复大致位置（可选）
        if count == 0:
             self.setTextCursor(original_cursor)
            
        return count

    def keyPressEvent(self, event):
        cursor = self.textCursor()
        
        if event.key() in [Qt.Key_Return, Qt.Key_Enter]:
            block_text = cursor.block().text()
            # 处理列表项 (- 或 * 开头)
            if block_text.strip().startswith(("- ", "* ")):
                super().keyPressEvent(event)
                self.insertPlainText(block_text.split()[0] + " ")
                return
            
            super().keyPressEvent(event)
            
            # 确保新起的段落保持行高格式
            current_fmt = cursor.blockFormat()
            if current_fmt.lineHeight() != 150:
                fmt = QTextBlockFormat()
                fmt.setLineHeight(150, 1)
                cursor.mergeBlockFormat(fmt)
                
            # 处理中文首行缩进
            prev_block = cursor.block().previous() 
            if prev_block.isValid() and prev_block.text().strip():
                 self.insertPlainText("　　")
            return

        elif event.key() == Qt.Key_Tab:
            cursor.insertText("    ")
            return
            
        elif event.key() == Qt.Key_Backtab:
            if not cursor.hasSelection():
                line_text = cursor.block().text()
                if line_text.startswith("　　"):
                    cursor.movePosition(cursor.StartOfBlock)
                    cursor.movePosition(cursor.Right, cursor.KeepAnchor, 2)
                    cursor.removeSelectedText()
                elif line_text.startswith("    "):
                    cursor.movePosition(cursor.StartOfBlock)
                    cursor.movePosition(cursor.Right, cursor.KeepAnchor, 4)
                    cursor.removeSelectedText()
            return
            
        super().keyPressEvent(event)