# ShiCheng_Writer/widgets/editor.py
from PySide6.QtWidgets import QTextEdit, QApplication
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtCore import QRegularExpression, Qt

class SettingsHighlighter(QSyntaxHighlighter):
    """设定高亮器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        
        self.highlight_format = QTextCharFormat()
        self.update_highlight_color()

    def update_highlight_color(self):
        """根据当前应用的主题更新高亮颜色"""
        palette = QApplication.instance().palette()
        base_lightness = palette.base().color().lightness()
        text_lightness = palette.windowText().color().lightness()

        if base_lightness < text_lightness: # 暗色主题
            self.highlight_format.setBackground(QColor("#015a9e"))
            self.highlight_format.setForeground(QColor("#e0e0e0"))
        else: # 亮色主题
            self.highlight_format.setBackground(QColor("#d9e9f7"))
            self.highlight_format.setForeground(QColor("#000000"))

        self.highlight_format.setFontWeight(QFont.Bold)
        self.highlight_format.setToolTip("这是一个设定")
        self.rehighlight()

    def set_settings_list(self, settings_list):
        self.highlighting_rules = []
        if not settings_list:
            self.rehighlight()
            return
        
        # 对列表进行排序，优先匹配更长的单词
        sorted_list = sorted(settings_list, key=len, reverse=True)

        for setting in sorted_list:
            # 使用 \b 保证是全词匹配, Qt的正则引擎
            pattern = QRegularExpression(f"\\b{QRegularExpression.escape(setting)}\\b")
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
        self.highlighter = SettingsHighlighter(self.document())
        self.set_font_size("16px") # 设置默认字体大小
        
    def set_font_size(self, size_str):
        """设置编辑器字体大小"""
        font = self.font()
        try:
            size = int(size_str.replace('px', ''))
            font.setPointSize(size)
            self.setFont(font)
            self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        except ValueError:
            print(f"无效的字体大小: {size_str}")


    def auto_indent_document(self):
        """为全文非空行且尚未缩进的行添加首行缩进。"""
        self.setUpdatesEnabled(False)
        cursor = self.textCursor()
        cursor.beginEditBlock()

        scrollbar = self.verticalScrollBar()
        old_value = scrollbar.value()

        new_content = []
        for i in range(self.document().blockCount()):
            block = self.document().findBlockByNumber(i)
            line = block.text()
            if line.strip() and not line.startswith("　　") and not line.startswith("    ") and not line.startswith("#"):
                 new_content.append("　　" + line)
            else:
                 new_content.append(line)
        
        self.setPlainText("\n".join(new_content))

        scrollbar.setValue(old_value)

        cursor.endEditBlock()
        self.setUpdatesEnabled(True)

    def auto_unindent_document(self):
        """移除全文所有行的首行缩进（两个全角空格或四个半角空格）。"""
        self.setUpdatesEnabled(False)
        cursor = self.textCursor()
        cursor.beginEditBlock()

        scrollbar = self.verticalScrollBar()
        old_value = scrollbar.value()

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

        scrollbar.setValue(old_value)

        cursor.endEditBlock()
        self.setUpdatesEnabled(True)

    def update_highlighter(self, settings_list):
        """外部调用此方法来更新需要高亮的设定词汇"""
        self.highlighter.set_settings_list(settings_list)
        self.highlighter.update_highlight_color()

    def keyPressEvent(self, event):
        """重写按键事件以实现中文首行缩进和Tab功能"""
        cursor = self.textCursor()
        
        if event.key() in [Qt.Key_Return, Qt.Key_Enter]:
            
            # 如果当前行是列表项 (e.g.,以'- ', '* '开头)，则自动创建新列表项
            block_text = cursor.block().text()
            if block_text.strip().startswith(("- ", "* ")):
                super().keyPressEvent(event)
                self.insertPlainText(block_text.split()[0] + " ")
                return

            # 默认回车行为
            super().keyPressEvent(event)

            # 获取上一段(即当前光标所在新行的前一行)
            prev_block = cursor.block().previous() 
            if prev_block.text().strip(): # 如果上一行不是空行
                 self.insertPlainText("　　") # 新段落首行缩进
            return

        # 处理Tab键
        elif event.key() == Qt.Key_Tab:
            cursor.insertText("    ")
            return
            
        # 处理Shift+Tab（反向缩进）
        elif event.key() == Qt.Key_Backtab:
            if not cursor.hasSelection():
                line_text = cursor.block().text()
                start_pos = cursor.positionInBlock()

                if line_text.startswith("　　"):
                    cursor.movePosition(cursor.StartOfBlock)
                    cursor.movePosition(cursor.Right, cursor.KeepAnchor, 2)
                    cursor.removeSelectedText()
                elif line_text.startswith("    "):
                    cursor.movePosition(cursor.StartOfBlock)
                    cursor.movePosition(cursor.Right, cursor.KeepAnchor, 4)
                    cursor.removeSelectedText()
            # (可以扩展多行反缩进的逻辑)
            return
            
        super().keyPressEvent(event)