# ShiCheng_Writer/modules/exporters.py
"""
导出器模块 - 支持多种格式的书籍导出
"""
import html
import re
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .database import DataManager

logger = logging.getLogger(__name__)


class Exporter(ABC):
    """导出器基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """导出器名称"""
        pass

    @property
    @abstractmethod
    def extension(self) -> str:
        """文件扩展名（不含点）"""
        pass

    @abstractmethod
    def export(self, book_data: Dict[str, Any], output_path: str) -> bool:
        """
        导出书籍

        Args:
            book_data: 书籍数据（包含书籍信息和章节列表）
            output_path: 输出文件路径

        Returns:
            导出是否成功
        """
        pass


class TextExporter(Exporter):
    """纯文本导出器"""

    @property
    def name(self) -> str:
        return "纯文本 (.txt)"

    @property
    def extension(self) -> str:
        return "txt"

    def export(self, book_data: Dict[str, Any], output_path: str) -> bool:
        """导出为 UTF-8 编码的纯文本文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # 写入书籍信息
                f.write(f"《{book_data['title']}》\n")
                f.write(f"作者：{book_data.get('author', '未知')}\n")
                f.write(f"简介：{book_data.get('summary', '无')}\n")
                f.write("=" * 50 + "\n\n")

                # 写入章节内容
                volumes = book_data.get('children', [])
                for volume in volumes:
                    vol_name = volume.get('name', '')
                    if vol_name and vol_name != '未分卷':
                        f.write(f"\n{'=' * 20} {vol_name} {'=' * 20}\n\n")

                    for chapter in volume.get('children', []):
                        chapter_title = chapter.get('name', '无标题')
                        chapter_content = chapter.get('content', '')

                        f.write(f"\n{chapter_title}\n\n")
                        f.write(f"{chapter_content}\n")

            logger.info(f"成功导出 TXT: {output_path}")
            return True
        except Exception as e:
            logger.error(f"导出 TXT 失败：{e}", exc_info=True)
            return False


class MarkdownExporter(Exporter):
    """Markdown 格式导出器"""

    @property
    def name(self) -> str:
        return "Markdown (.md)"

    @property
    def extension(self) -> str:
        return "md"

    def export(self, book_data: Dict[str, Any], output_path: str) -> bool:
        """导出为 Markdown 格式"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # 写入书籍信息
                f.write(f"# 《{book_data['title']}》\n\n")
                f.write(f"**作者**: {book_data.get('author', '未知')}\n\n")

                if book_data.get('summary'):
                    f.write("## 简介\n\n")
                    f.write(f"{book_data['summary']}\n\n")

                f.write("---\n\n")
                f.write("## 目录\n\n")

                # 生成目录
                toc = []
                volumes = book_data.get('children', [])
                chapter_index = 1

                for volume in volumes:
                    vol_name = volume.get('name', '')
                    if vol_name and vol_name != '未分卷':
                        toc.append(f"### {vol_name}\n")

                    for chapter in volume.get('children', []):
                        chapter_title = chapter.get('name', '无标题')
                        anchor = f"chapter-{chapter_index}"
                        if vol_name and vol_name != '未分卷':
                            toc.append(f"- [{vol_name} - {chapter_title}](#{anchor})\n")
                        else:
                            toc.append(f"- [{chapter_title}](#{anchor})\n")
                        chapter_index += 1

                f.write("".join(toc))
                f.write("\n---\n\n")

                # 写入章节内容
                chapter_index = 1
                for volume in volumes:
                    vol_name = volume.get('name', '')

                    if vol_name and vol_name != '未分卷':
                        f.write(f"## {vol_name}\n\n")

                    for chapter in volume.get('children', []):
                        chapter_title = chapter.get('name', '无标题')
                        chapter_content = chapter.get('content', '')

                        # 写入章节锚点
                        f.write(f"<a id=\"chapter-{chapter_index}\"></a>\n\n")
                        f.write(f"### {chapter_title}\n\n")

                        # 处理内容：转换缩进为空行
                        content_lines = chapter_content.split('\n')
                        processed_lines = []
                        for line in content_lines:
                            # 移除 Markdown 标题标记（如果存在）
                            if line.startswith('# '):
                                line = line[2:]
                            # 转换中文缩进
                            if line.startswith('  '):
                                line = '    ' + line[2:]
                            processed_lines.append(line)

                        f.write('\n'.join(processed_lines))
                        f.write("\n\n")
                        chapter_index += 1

            logger.info(f"成功导出 MD: {output_path}")
            return True
        except Exception as e:
            logger.error(f"导出 MD 失败：{e}", exc_info=True)
            return False


class HTMLExporter(Exporter):
    """HTML 格式导出器"""

    @property
    def name(self) -> str:
        return "HTML (.html)"

    @property
    def extension(self) -> str:
        return "html"

    def export(self, book_data: Dict[str, Any], output_path: str) -> bool:
        """导出为 HTML 格式"""
        try:
            title = html.escape(str(book_data.get('title') or '无标题'))
            author = html.escape(str(book_data.get('author') or '未知'))
            summary = html.escape(str(book_data.get('summary') or '无'))
            # 生成目录 HTML
            toc_html = self._generate_toc(book_data)
            # 生成章节 HTML
            chapters_html = self._generate_chapters(book_data)

            html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
            line-height: 1.8;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            text-align: center;
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 15px;
        }}
        .book-info {{
            background: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .toc {{
            background: #fafafa;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .toc ul {{
            list-style: none;
            padding-left: 20px;
        }}
        .toc a {{
            color: #3498db;
            text-decoration: none;
        }}
        .toc a:hover {{
            text-decoration: underline;
        }}
        .volume-title {{
            color: #e74c3c;
            margin-top: 30px;
            border-left: 4px solid #e74c3c;
            padding-left: 10px;
        }}
        .chapter {{
            margin: 40px 0;
            padding: 20px;
            background: #fff;
            border-top: 1px solid #eee;
        }}
        .chapter h3 {{
            color: #2c3e50;
        }}
        .chapter-content {{
            text-indent: 2em;
            color: #333;
        }}
        .chapter-content p {{
            margin: 1em 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>《{title}》</h1>

        <div class="book-info">
            <p><strong>作者:</strong> {author}</p>
            <p><strong>简介:</strong> {summary}</p>
        </div>

        <div class="toc">
            <h2>目录</h2>
            {toc_html}
        </div>

        <hr>

        {chapters_html}
    </div>
</body>
</html>"""

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"成功导出 HTML: {output_path}")
            return True
        except Exception as e:
            logger.error(f"导出 HTML 失败：{e}", exc_info=True)
            return False

    def _generate_toc(self, book_data: Dict[str, Any]) -> str:
        """生成目录 HTML"""
        toc_parts = ['<ul>']
        chapter_index = 1
        volumes = book_data.get('children', [])

        for volume in volumes:
            vol_name = volume.get('name', '')
            if vol_name and vol_name != '未分卷':
                safe_volume_name = html.escape(str(vol_name))
                toc_parts.append(f'<li><strong>{safe_volume_name}</strong><ul>')

            for chapter in volume.get('children', []):
                chapter_title = chapter.get('name', '无标题')
                safe_chapter_title = html.escape(str(chapter_title))
                if vol_name and vol_name != '未分卷':
                    toc_parts.append(
                        f'<li><a href="#chapter-{chapter_index}">'
                        f'{safe_volume_name} - {safe_chapter_title}</a></li>'
                    )
                else:
                    toc_parts.append(
                        f'<li><a href="#chapter-{chapter_index}">'
                        f'{safe_chapter_title}</a></li>'
                    )
                chapter_index += 1

            if vol_name and vol_name != '未分卷':
                toc_parts.append('</ul></li>')

        toc_parts.append('</ul>')
        return ''.join(toc_parts)

    def _generate_chapters(self, book_data: Dict[str, Any]) -> str:
        """生成章节 HTML"""
        chapter_index = 1
        chapters_parts = []
        volumes = book_data.get('children', [])

        for volume in volumes:
            vol_name = volume.get('name', '')
            if vol_name and vol_name != '未分卷':
                safe_volume_name = html.escape(str(vol_name))
                chapters_parts.append(
                    f'<h2 class="volume-title">{safe_volume_name}</h2>'
                )

            for chapter in volume.get('children', []):
                chapter_title = chapter.get('name', '无标题')
                chapter_content = chapter.get('content', '')
                safe_chapter_title = html.escape(str(chapter_title))

                # 处理内容
                content_html = self._process_content(str(chapter_content))

                chapters_parts.append(f"""
                <div class="chapter" id="chapter-{chapter_index}">
                    <h3>{safe_chapter_title}</h3>
                    <div class="chapter-content">
                        {content_html}
                    </div>
                </div>
                """)
                chapter_index += 1

        return ''.join(chapters_parts)

    def _process_content(self, content: str) -> str:
        """处理章节内容为 HTML 格式"""
        # 移除 Markdown 标题
        content = re.sub(r'^# ', '', content, flags=re.MULTILINE)
        # 转换段落
        paragraphs = content.split('\n\n')
        html_paragraphs = []
        for p in paragraphs:
            p = p.strip()
            if p:
                # 处理中文缩进
                if p.startswith('  '):
                    p = p[2:]
                escaped_paragraph = html.escape(p).replace('\n', '<br>')
                html_paragraphs.append(f'<p>{escaped_paragraph}</p>')
        return '\n'.join(html_paragraphs)


class ExporterFactory:
    """导出器工厂类"""

    _exporters: Dict[str, Exporter] = {
        'txt': TextExporter(),
        'md': MarkdownExporter(),
        'html': HTMLExporter(),
    }

    @classmethod
    def get_exporter(cls, format_type: str) -> Optional[Exporter]:
        """获取指定格式的导出器"""
        return cls._exporters.get(format_type.lower())

    @classmethod
    def get_available_formats(cls) -> List[Dict[str, str]]:
        """获取所有可用的导出格式"""
        return [
            {'format': key, 'name': exporter.name, 'extension': exporter.extension}
            for key, exporter in cls._exporters.items()
        ]


def export_book(data_manager: DataManager, book_id: int, format_type: str, output_path: str) -> bool:
    """
    导出书籍的便捷函数

    Args:
        data_manager: 数据管理器实例
        book_id: 书籍 ID
        format_type: 导出格式 ('txt', 'md', 'html')
        output_path: 输出文件路径

    Returns:
        导出是否成功
    """
    exporter = ExporterFactory.get_exporter(format_type)
    if not exporter:
        logger.error(f"不支持的导出格式：{format_type}")
        return False

    # 获取书籍数据
    book_details = data_manager.get_book_details(book_id)
    if not book_details:
        logger.error(f"书籍不存在：{book_id}")
        return False

    # 构建导出数据结构
    chapters = data_manager.get_chapters_for_book(book_id, include_content=True)
    volumes_structure: Dict[str, Dict[str, Any]] = {}

    for chapter in chapters:
        content_text = chapter.get('content') or ''
        vol_name = chapter['volume'] or "未分卷"

        if vol_name not in volumes_structure:
            volumes_structure[vol_name] = {"name": vol_name, "children": []}

        volumes_structure[vol_name]['children'].append({
            "name": chapter['title'],
            "content": content_text
        })

    export_data = {
        'id': book_id,
        'title': book_details['title'],
        'author': '',  # 可以后续添加作者字段
        'summary': book_details.get('description', ''),
        'children': list(volumes_structure.values())
    }

    return exporter.export(export_data, output_path)
