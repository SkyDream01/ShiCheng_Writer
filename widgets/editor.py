# ShiCheng_Writer/widgets/editor.py
"""
编辑器模块 - 自定义文本编辑器，支持素材高亮、缩进等功能
"""
import logging
from typing import List, Optional, Tuple

from PySide6.QtWidgets import QTextEdit, QApplication, QWidget
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QTextBlockFormat, QTextCursor, QTextDocument, QKeyEvent
)
from PySide6.QtCore import QRegularExpression, Qt

logger = logging.getLogger(__name__)

# 类型别名
HighlightingRule = Tuple[QRegularExpression, QTextCharFormat]


class MaterialHighlighter(QSyntaxHighlighter):
    """
    素材高亮器 - 性能优化版

    功能：
    - 根据素材列表高亮文本中的关键词
    - 支持 ASCII 和非 ASCII 关键词的智能匹配
    - 使用缓存机制避免重复计算
    """

    def __init__(self, parent: Optional[QTextDocument] = None) -> None:
        """
        初始化高亮器

        Args:
            parent: 父对象（通常是 QTextDocument）
        """
        super().__init__(parent)
        self.highlighting_rules: List[HighlightingRule] = []
        self.highlight_format = QTextCharFormat()

        # Store normalized input rather than a hash: this avoids rebuilding a
        # large document's syntax highlighting when the effective material
        # list and theme have not changed.
        self._materials_key: Tuple[str, ...] = ()
        self._is_dark_theme: Optional[bool] = None
        self.update_highlight_color()

    def update_highlight_color(self) -> None:
        """根据当前主题更新高亮颜色"""
        application = QApplication.instance()
        if application is None:
            return

        palette = application.palette()
        # 简单的暗色主题检测
        is_dark_theme = palette.window().color().lightness() < 128
        if self._is_dark_theme == is_dark_theme:
            return

        self._is_dark_theme = is_dark_theme

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

    def set_materials_list(self, materials_list: Optional[List[str]]) -> None:
        """
        设置需要高亮的素材列表

        Args:
            materials_list: 素材名称列表
        """
        normalized_materials = tuple(
            sorted(
                {
                    material
                    for material in (materials_list or [])
                    if material and material.strip()
                },
                key=lambda material: (-len(material), material),
            )
        )
        if normalized_materials == self._materials_key:
            return

        self._materials_key = normalized_materials
        self.highlighting_rules = []

        # 快速路径：如果列表为空，直接清除高亮。
        if not normalized_materials:
            self.rehighlight()
            return

        # 按长度降序排序，防止短词覆盖长词；ASCII 关键词需要单词边界。
        ascii_keywords: List[str] = []
        non_ascii_keywords: List[str] = []

        for m in normalized_materials:
            # 使用 str.isascii() 方法（Python 3.7+）更高效
            if m.isascii():
                ascii_keywords.append(QRegularExpression.escape(m))
            else:
                non_ascii_keywords.append(QRegularExpression.escape(m))

        patterns_parts: List[str] = []
        if ascii_keywords:
            patterns_parts.append(f"\\b({'|'.join(ascii_keywords)})\\b")
        if non_ascii_keywords:
            patterns_parts.append(f"({'|'.join(non_ascii_keywords)})")

        if not patterns_parts:
            self.rehighlight()
            return

        pattern_str = "|".join(patterns_parts)

        # QRegularExpression 会在首次匹配时自行优化。PySide6 并未暴露
        # setOptimizationHints/OptimizeOnFirstUsageOption，调用它们会在存在
        # 任意素材关键词时抛出 AttributeError。
        pattern = QRegularExpression(pattern_str)
        self.highlighting_rules.append((pattern, self.highlight_format))

        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        """
        高亮文本块

        Args:
            text: 要高亮的文本
        """
        for pattern, format in self.highlighting_rules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)


class Editor(QTextEdit):
    """
    自定义文本编辑器 - 视觉优化版

    功能：
    - 素材关键词高亮
    - 中文首行缩进
    - 自定义字体大小和行高
    - 查找与替换
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore
        """
        初始化编辑器

        Args:
            parent: 父组件
        """
        super().__init__(parent)
        self.highlighter = MaterialHighlighter(self.document())

        # 设置文档边距，营造"纸张"感
        self.setViewportMargins(40, 20, 40, 20)

        # 加宽光标
        self.setCursorWidth(2)

        self.set_font_size("16px")

    def set_font_size(self, size_str: str) -> None:
        """
        设置字体大小

        Args:
            size_str: 字体大小字符串（如 "16px"）
        """
        font = self.font()
        try:
            size = int(size_str.replace('px', ''))
            font.setPointSize(size)
            # 使用字体族列表，兼容多平台
            font.setFamilies(["Microsoft YaHei", "PingFang SC", "Heiti SC", "SimHei", "Sans-Serif"])
            self.setFont(font)

            # 设置 Tab 宽度为 4 个空格
            self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

            # 初始化行间距 (150% 行高)
            self.set_line_height(150)

        except ValueError:
            logger.warning(f"无效的字体大小：{size_str}")

    def set_line_height(self, percentage: int) -> None:
        """
        设置行高百分比

        Args:
            percentage: 行高百分比（如 150 表示 150%）
        """
        block_fmt = QTextBlockFormat()
        # 1 = ProportionalHeight (按比例设置行高)
        block_fmt.setLineHeight(percentage, 1)

        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.mergeBlockFormat(block_fmt)
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def auto_indent_document(self) -> None:
        """
        全文缩进：使用 Cursor 操作，保留撤销栈历史，不重置视图
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()  # 开始编辑块，确保可一次性撤销

        doc = self.document()
        # 遍历所有段落
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            text = block.text()

            # 仅对非空、非缩进、非标题行进行缩进
            if text.strip() and not text.startswith(("  ", "    ", "#")):
                cursor.setPosition(block.position())
                cursor.insertText("  ")

        cursor.endEditBlock()  # 结束编辑块

    def auto_unindent_document(self) -> None:
        """
        取消缩进：使用 Cursor 操作，保留撤销栈历史
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()

        doc = self.document()
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            text = block.text()

            cursor.setPosition(block.position())

            if text.startswith("    "):
                # 选中前四个字符并删除
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 4)
                cursor.removeSelectedText()
            elif text.startswith("  "):
                # 选中前两个字符并删除
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 2)
                cursor.removeSelectedText()

        cursor.endEditBlock()

    def update_highlighter(self, materials_list: List[str]) -> None:
        """
        外部调用此方法来更新需要高亮的素材词汇

        Args:
            materials_list: 素材名称列表
        """
        self.highlighter.set_materials_list(materials_list)
        self.highlighter.update_highlight_color()

    def find_text(self, text: str, backward: bool = False,
                  case_sensitive: bool = False, whole_words: bool = False) -> bool:
        """
        查找文本

        Args:
            text: 要查找的文本
            backward: 是否向后查找
            case_sensitive: 是否区分大小写
            whole_words: 是否全词匹配

        Returns:
            是否找到
        """
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

    def replace_current(self, text: str) -> bool:
        """
        替换当前选中的文本

        Args:
            text: 替换后的文本

        Returns:
            是否成功替换
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.insertText(text)
            return True
        return False

    def replace_all(self, target: str, replacement: str,
                    case_sensitive: bool = False, whole_words: bool = False) -> int:
        """
        全部替换

        Args:
            target: 要查找的文本
            replacement: 替换后的文本
            case_sensitive: 是否区分大小写
            whole_words: 是否全词匹配

        Returns:
            替换的数量
        """
        if not target:
            return 0

        # 保存当前光标位置
        original_cursor = self.textCursor()

        # 移动到文档开头开始查找
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.setTextCursor(cursor)

        count = 0
        cursor.beginEditBlock()  # 批量替换作为一次撤销
        while self.find_text(target, False, case_sensitive, whole_words):
            self.replace_current(replacement)
            count += 1
        cursor.endEditBlock()

        # 恢复大致位置（可选）
        if count == 0:
            self.setTextCursor(original_cursor)

        return count

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        处理键盘按键事件

        Args:
            event: 键盘事件
        """
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
                self.insertPlainText("  ")
            return

        elif event.key() == Qt.Key_Tab:
            cursor.insertText("    ")
            return

        elif event.key() == Qt.Key_Backtab:
            if not cursor.hasSelection():
                line_text = cursor.block().text()
                if line_text.startswith("  "):
                    cursor.movePosition(cursor.StartOfBlock)
                    cursor.movePosition(cursor.Right, cursor.KeepAnchor, 2)
                    cursor.removeSelectedText()
                elif line_text.startswith("    "):
                    cursor.movePosition(cursor.StartOfBlock)
                    cursor.movePosition(cursor.Right, cursor.KeepAnchor, 4)
                    cursor.removeSelectedText()
            return

        super().keyPressEvent(event)
