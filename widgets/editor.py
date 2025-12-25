# ShiCheng_Writer/widgets/editor.py
from PySide6.QtWidgets import QTextEdit, QApplication
from PySide6.QtGui import (QSyntaxHighlighter, QTextCharFormat, QColor, QFont, 
                           QTextBlockFormat, QTextCursor)
from PySide6.QtCore import QRegularExpression, Qt

class MaterialHighlighter(QSyntaxHighlighter):
    """素材高亮器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        
        self.highlight_format = QTextCharFormat()
        self.update_highlight_color()

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
        self.highlighting_rules = []
        if not materials_list:
            self.rehighlight()
            return
        
        # 按长度降序排序，优先匹配长词
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
    """自定义文本编辑器 - 视觉优化版"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighter = MaterialHighlighter(self.document())
        
        # [优化] 设置文档边距，营造“纸张”感，防止文字紧贴窗口边缘
        # 参数顺序: 左, 上, 右, 下
        self.setViewportMargins(40, 20, 40, 20)
        
        # [优化] 加宽光标，在高分屏下更清晰
        self.setCursorWidth(2)
        
        self.set_font_size("16px") 
        
    def set_font_size(self, size_str):
        font = self.font()
        try:
            size = int(size_str.replace('px', ''))
            font.setPointSize(size)
            # [优化] 强制使用适合中文显示的字体
            font.setFamily("Microsoft YaHei") 
            self.setFont(font)
            
            # [优化] 设置Tab宽度为4个空格
            self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
            
            # [优化] 初始化行间距 (150% 行高)
            self.set_line_height(150)
            
        except ValueError:
            print(f"无效的字体大小: {size_str}")

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
        # [修复] 重置全文后需重新应用行高
        self.set_line_height(150)

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
        # [修复] 重置全文后需重新应用行高
        self.set_line_height(150)

    def update_highlighter(self, materials_list):
        """外部调用此方法来更新需要高亮的素材词汇"""
        self.highlighter.set_materials_list(materials_list)
        self.highlighter.update_highlight_color()

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
            
            # [优化] 确保新起的段落保持行高格式
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