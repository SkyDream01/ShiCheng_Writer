# ShiCheng_Writer/widgets/editor.py
from PySide6.QtWidgets import QTextEdit, QApplication
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtCore import QRegularExpression, Qt

# vvvvvvvvvv [修改] 重命名为 MaterialHighlighter vvvvvvvvvv
class MaterialHighlighter(QSyntaxHighlighter):
    """素材高亮器"""
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        
        self.highlight_format = QTextCharFormat()
        self.update_highlight_color()

    def update_highlight_color(self):
        palette = QApplication.instance().palette()
        # A simple check for dark theme
        is_dark_theme = palette.window().color().lightness() < 128
        
        if is_dark_theme:
            self.highlight_format.setBackground(QColor("#015a9e"))
            self.highlight_format.setForeground(QColor("#e0e0e0"))
        else: 
            self.highlight_format.setBackground(QColor("#d9e9f7"))
            self.highlight_format.setForeground(QColor("#000000"))

        self.highlight_format.setFontWeight(QFont.Bold)
        # vvvvvvvvvv [修改] 更新提示文本 vvvvvvvvvv
        self.highlight_format.setToolTip("这是一个素材")
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        self.rehighlight()

    # vvvvvvvvvv [修改] 重命名函数 vvvvvvvvvv
    def set_materials_list(self, materials_list):
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        self.highlighting_rules = []
        if not materials_list:
            self.rehighlight()
            return
        
        sorted_list = sorted(materials_list, key=len, reverse=True)

        for material in sorted_list:
            pattern = QRegularExpression(f"\\b{QRegularExpression.escape(material)}\\b")
            self.highlighting_rules.append((pattern, self.highlight_format))
        
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

class Editor(QTextEdit):
    """自定义文本编辑器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # vvvvvvvvvv [修改] 使用新的高亮器 vvvvvvvvvv
        self.highlighter = MaterialHighlighter(self.document())
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        self.set_font_size("16px") 
        
    def set_font_size(self, size_str):
        font = self.font()
        try:
            size = int(size_str.replace('px', ''))
            font.setPointSize(size)
            self.setFont(font)
            self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        except ValueError:
            print(f"无效的字体大小: {size_str}")


    def auto_indent_document(self):
        self.setUpdatesEnabled(False)
        cursor = self.textCursor()
        cursor.beginEditBlock()
        scrollbar_pos = self.verticalScrollBar().value()
        new_content = []
        for i in range(self.document().blockCount()):
            block = self.document().findBlockByNumber(i)
            line = block.text()
            if line.strip() and not line.startswith(("　　", "    ", "#")):
                 new_content.append("　　" + line)
            else:
                 new_content.append(line)
        self.setPlainText("\n".join(new_content))
        self.verticalScrollBar().setValue(scrollbar_pos)
        cursor.endEditBlock()
        self.setUpdatesEnabled(True)

    def auto_unindent_document(self):
        self.setUpdatesEnabled(False)
        cursor = self.textCursor()
        cursor.beginEditBlock()
        scrollbar_pos = self.verticalScrollBar().value()
        new_content = []
        for i in range(self.document().blockCount()):
            block = self.document().findBlockByNumber(i)
            line = block.text()
            if line.startswith("　　"):
                new_content.append(line[2:])
            elif line.startswith("    "):
                new_content.append(line[4:])
            else:
                new_content.append(line)
        self.setPlainText("\n".join(new_content))
        self.verticalScrollBar().setValue(scrollbar_pos)
        cursor.endEditBlock()
        self.setUpdatesEnabled(True)

    # vvvvvvvvvv [修改] 更新高亮器函数 vvvvvvvvvv
    def update_highlighter(self, materials_list):
        """外部调用此方法来更新需要高亮的素材词汇"""
        self.highlighter.set_materials_list(materials_list)
        self.highlighter.update_highlight_color()
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    def keyPressEvent(self, event):
        cursor = self.textCursor()
        
        if event.key() in [Qt.Key_Return, Qt.Key_Enter]:
            block_text = cursor.block().text()
            if block_text.strip().startswith(("- ", "* ")):
                super().keyPressEvent(event)
                self.insertPlainText(block_text.split()[0] + " ")
                return
            super().keyPressEvent(event)
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