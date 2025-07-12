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
        self.update_highlight_color() # 初始化颜色

    def update_highlight_color(self):
        """根据当前应用的主题更新高亮颜色"""
        # 通过检查QApplication的调色板来判断是亮色还是暗色主题
        # 暗色主题的基色会比窗口文字颜色更亮
        if QApplication.instance().palette().base().color().lightness() < QApplication.instance().palette().windowText().color().lightness():
            # 暗色主题
            self.highlight_format.setBackground(QColor("#005f87")) # 深蓝色背景
            self.highlight_format.setForeground(QColor("#e0e0e0")) # 亮灰色文字
        else:
            # 亮色主题
            self.highlight_format.setBackground(QColor("#d4edff")) # 淡蓝色背景
            self.highlight_format.setForeground(QColor("#000000")) # 黑色文字

        self.highlight_format.setFontWeight(QFont.Bold)
        self.highlight_format.setToolTip("这是一个设定")
        # 重新高亮整个文档以应用新颜色
        self.rehighlight()

    def set_settings_list(self, settings_list):
        self.highlighting_rules = []
        if not settings_list:
            self.rehighlight()
            return
        
        for setting in settings_list:
            # 使用 \b 保证是全词匹配
            pattern = QRegularExpression(f"\\b{setting}\\b")
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
        # 设置Tab键的宽度为4个空格
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

    def auto_indent_document(self):
        """为全文非空行且尚未缩进的行添加首行缩进。"""
        self.setUpdatesEnabled(False)
        cursor = self.textCursor()
        cursor.beginEditBlock()

        # 保存当前视口位置
        scrollbar = self.verticalScrollBar()
        old_value = scrollbar.value()

        # 处理文本
        new_content = []
        for i in range(self.document().blockCount()):
            block = self.document().findBlockByNumber(i)
            line = block.text()
            if line.strip() and not line.startswith("　　") and not line.startswith("    "):
                 new_content.append("　　" + line)
            else:
                 new_content.append(line)
        
        self.setPlainText("\n".join(new_content))

        # 恢复视口位置
        scrollbar.setValue(old_value)

        cursor.endEditBlock()
        self.setUpdatesEnabled(True)

    def auto_unindent_document(self):
        """移除全文所有行的首行缩进（两个全角空格或四个半角空格）。"""
        self.setUpdatesEnabled(False)
        cursor = self.textCursor()
        cursor.beginEditBlock()

        # 保存当前视口位置
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

        # 恢复视口位置
        scrollbar.setValue(old_value)

        cursor.endEditBlock()
        self.setUpdatesEnabled(True)

    def update_highlighter(self, settings_list):
        """外部调用此方法来更新需要高亮的设定词汇"""
        self.highlighter.set_settings_list(settings_list)
        # 当高亮列表更新时，也检查并更新颜色
        self.highlighter.update_highlight_color()

    def keyPressEvent(self, event):
        """重写按键事件以实现中文首行缩进和Tab功能"""
        # 处理回车键
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            super().keyPressEvent(event) # 首先执行默认的回车操作

            # 实现中文首行缩进
            cursor = self.textCursor()
            block = cursor.block().previous() # 获取上一段

            # 如果是文档开头，或者上一行是空行，则认为是新段落的开始
            if not block.isValid() or len(block.text().strip()) == 0:
                self.insertPlainText("　　") # 插入两个全角空格
            # 否则，意味着在段落中间换行，不添加额外缩进
            else:
                # 继承上一行的缩进（用于代码或手动对齐的场景）
                indentation = ""
                for char in block.text():
                    if char.isspace():
                        indentation += char
                    else:
                        break
                self.insertPlainText(indentation)

        # 处理Tab键
        elif event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            cursor.insertText("    ") # 插入四个空格
            
        # 处理Shift+Tab（反向缩进）
        elif event.key() == Qt.Key_Backtab:
            cursor = self.textCursor()
            if not cursor.hasSelection():
                # 移动到行首
                start_pos = cursor.positionInBlock()
                cursor.movePosition(cursor.StartOfBlock, cursor.MoveAnchor)
                # 检查前四个字符是否是空格
                cursor.movePosition(cursor.Right, cursor.KeepAnchor, 4)
                if cursor.selectedText() == "    ":
                    cursor.removeSelectedText()
                else:
                    # 如果不是四个空格，则移动回原来的位置
                    cursor.setPosition(cursor.anchor())
                    cursor.setPosition(start_pos, cursor.MoveAnchor)
        else:
            super().keyPressEvent(event)