# ShiCheng_Writer/widgets/book_info_page.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

class BookInfoPage(QWidget):
    """
    书籍信息展示页
    用于显示书籍标题、统计信息和简介，以及空状态提示。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.setObjectName("BookInfoPage")
        
        # 整体布局：垂直方向居中
        main_layout = QVBoxLayout(self)
        # 增加左右边距，使文字在大屏幕上不会太散
        main_layout.setContentsMargins(80, 60, 80, 60) 
        
        # 信息容器 (用于控制内容宽度，但视觉上透明)
        info_container = QFrame()
        info_container.setObjectName("InfoContainer") 
        
        container_layout = QVBoxLayout(info_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(20) # 元素间距宽松

        # 书名
        self.title_label = QLabel("请选择一本书")
        self.title_label.setObjectName("InfoTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        
        # 分组与统计信息
        self.meta_label = QLabel("开始您的创作之旅")
        self.meta_label.setObjectName("InfoMeta")
        self.meta_label.setAlignment(Qt.AlignCenter)
        
        # 装饰性分割线 (极简短横线)
        line_container = QHBoxLayout()
        line_container.addStretch()
        line = QFrame()
        line.setObjectName("InfoLine")
        line.setFixedWidth(60)
        line.setFixedHeight(2)
        line_container.addWidget(line)
        line_container.addStretch()
        
        # 简介标题
        desc_title = QLabel("内容简介")
        desc_title.setObjectName("InfoDescTitle")
        desc_title.setAlignment(Qt.AlignCenter)
        
        # 简介内容
        self.desc_label = QLabel()
        self.desc_label.setObjectName("InfoDesc")
        self.desc_label.setWordWrap(True)
        self.desc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.desc_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        # 组装
        container_layout.addWidget(self.title_label)
        container_layout.addWidget(self.meta_label)
        container_layout.addSpacing(10)
        container_layout.addLayout(line_container)
        container_layout.addSpacing(30)
        container_layout.addWidget(desc_title)
        container_layout.addWidget(self.desc_label)
        container_layout.addStretch()

        # 页面垂直居中
        main_layout.addStretch(1)
        main_layout.addWidget(info_container)
        main_layout.addStretch(2) # 下方留白更多，视觉重心偏上

    def update_info(self, title, group, chapter_count, description):
        """更新页面显示的信息"""
        self.title_label.setText(title)
        self.meta_label.setText(f"分组：{group}  |  当前章节数：{chapter_count}")
        
        desc = description if description else "（暂无简介，右键点击左侧书籍标题可编辑信息）"
        self.desc_label.setText(desc)

    def reset(self):
        """重置为空状态"""
        self.title_label.setText("请选择一本书")
        self.meta_label.setText("开始您的创作之旅")
        self.desc_label.setText("")