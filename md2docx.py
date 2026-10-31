# -*- coding: utf-8 -*-
"""
Markdown -> Word 转换器（支持标题/表格/列表/分隔线/代码块）
用法：python md2docx.py
"""
import os
import re
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def set_run_font(run, name="微软雅黑", size=11, bold=False, italic=False, color=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if color:
        run.font.color.rgb = RGBColor(*color)

def add_heading(doc, text, level):
    heading = doc.add_heading(text, level=level)
    for run in heading.runs:
        set_run_font(run, size={1: 22, 2: 18, 3: 15, 4: 13}.get(level, 12), bold=True)
    return heading

def add_paragraph(doc, text, bold=False, italic=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, bold=bold)
    run.italic = italic
    return p

def add_rich_paragraph(doc, text):
    """支持简单的 **bold** 和 `code` 内联"""
    p = doc.add_paragraph()
    # 先按 ** 和 ` 切分
    parts = re.split(r'(\*\*[^*]+\*\*|`[^`]+`)', text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = p.add_run(part[2:-2])
            set_run_font(run, bold=True)
        elif part.startswith("`") and part.endswith("`"):
            run = p.add_run(part[1:-1])
            set_run_font(run, name="Consolas", size=10)
        else:
            # 处理普通文本里的 [链接文字](url)
            link_match = re.match(r'^\[([^\]]+)\]\(([^)]+)\)$', part.strip())
            if link_match:
                run = p.add_run(link_match.group(1))
                set_run_font(run, color=(0, 102, 204))
            else:
                run = p.add_run(part)
                set_run_font(run)
    return p

def set_cell_shading(cell, color_hex):
    """设置单元格背景色"""
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color_hex)
    shading.set(qn("w:val"), "clear")
    cell._tc.get_or_add_tcPr().append(shading)

def add_table(doc, header, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # 表头
    for i, h in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(h.strip())
        set_run_font(run, bold=True, size=10)
        set_cell_shading(cell, "D9E2F3")
    # 数据行
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(val.strip())
            set_run_font(run, size=10)
    doc.add_paragraph()
    return table

def is_table_line(line):
    """判断是否是 Markdown 表格分隔线如 |---|---|"""
    return re.match(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$', line)

def parse_table_block(lines):
    """把 | a | b | 格式的表格解析出来，返回 header, rows"""
    raw = [l.strip() for l in lines if l.strip().startswith("|")]
    raw = [l for l in raw if not is_table_line(l)]
    if not raw:
        return None, None
    def split_row(l):
        cells = l.strip().strip("|").split("|")
        return [c.strip() for c in cells]
    header = split_row(raw[0])
    rows = [split_row(l) for l in raw[1:]]
    # 对齐列数
    n = len(header)
    rows = [r + [""] * (n - len(r)) if len(r) < n else r[:n] for r in rows]
    return header, rows

def md_to_docx(md_path, docx_path):
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    doc = Document()
    # 页边距
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")

        # 表格块
        if line.strip().startswith("|") and i + 1 < len(lines) and is_table_line(lines[i + 1]):
            # 收集整个表格块
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            header, rows = parse_table_block(block)
            if header:
                add_table(doc, header, rows)
            continue

        # 分隔线
        if re.match(r'^\s*---+\s*$', line):
            doc.add_paragraph("─" * 60)
            i += 1
            continue

        # 标题
        h = re.match(r'^(#{1,6})\s+(.+)$', line)
        if h:
            add_heading(doc, h.group(2).strip(), len(h.group(1)))
            i += 1
            continue

        # 引用
        if line.strip().startswith(">"):
            text = line.strip().lstrip(">").strip()
            p = doc.add_paragraph()
            run = p.add_run(text)
            set_run_font(run, italic=True, color=(100, 100, 100))
            # 左边框
            pPr = p._p.get_or_add_pPr()
            pBdr = OxmlElement("w:pBdr")
            left = OxmlElement("w:left")
            left.set(qn("w:val"), "single")
            left.set(qn("w:sz"), "12")
            left.set(qn("w:color"), "AAAAAA")
            pBdr.append(left)
            pPr.append(pBdr)
            i += 1
            continue

        # 无序列表
        if re.match(r'^\s*[-*+]\s+', line):
            text = re.sub(r'^\s*[-*+]\s+', '', line)
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(text)
            set_run_font(run)
            i += 1
            continue

        # 有序列表
        if re.match(r'^\s*\d+\.\s+', line):
            text = re.sub(r'^\s*\d+\.\s+', '', line)
            p = doc.add_paragraph(style="List Number")
            run = p.add_run(text)
            set_run_font(run)
            i += 1
            continue

        # 代码块
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i].rstrip("\n"))
                i += 1
            i += 1  # 跳过结束的 ```
            # 代码块段落
            for cl in code_lines:
                p = doc.add_paragraph()
                run = p.add_run(cl if cl else " ")
                set_run_font(run, name="Consolas", size=9)
            doc.add_paragraph()
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 普通段落
        add_rich_paragraph(doc, line)
        i += 1

    doc.save(docx_path)
    print(f"✓ 已生成：{docx_path}")

def main():
    files = [
        (
            os.path.join(BASE_DIR, "docs", "项目立项书.md"),
            os.path.join(BASE_DIR, "docs", "项目立项书.docx"),
        ),
        (
            os.path.join(BASE_DIR, "docs", "详细设计.md"),
            os.path.join(BASE_DIR, "docs", "详细设计.docx"),
        ),
    ]
    for md, docx in files:
        if os.path.exists(md):
            md_to_docx(md, docx)
        else:
            print(f"× 文件不存在：{md}")

if __name__ == "__main__":
    main()