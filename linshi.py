import os
import re
import win32com.client  # 用于处理 .doc
from docx import Document  # 用于处理 .docx
from docx.text.paragraph import Paragraph


# --- 逻辑 1: 处理 .DOCX 文件 (使用 python-docx) ---

def modify_docx_paragraph(paragraph: Paragraph):
    """(用于.docx) 处理单个段落的序号格式 (健壮版)"""
    text = paragraph.text
    if not text.strip():
        return

    # 正则表达式(修正版):
    # (\d+\.\d+\.\d+) - 匹配 "1.1.1"
    # ([\s、]?)       - 匹配 0个或1个 "空格"或"顿号" (关键修正)

    # 必须按 3 -> 2 -> 1 的顺序检查
    level3_pattern = re.compile(r'^(\d+\.\d+\.\d+)([\s、]?)')
    level2_pattern = re.compile(r'^(\d+\.\d+)([\s、]?)')
    level1_pattern = re.compile(r'^(\d+)([\s、]?)')

    # 规则 3: 检查三级序号 (如 2.2.1) - 保持原样
    level3_match = level3_pattern.match(text)
    if level3_match:
        return  # 是三级序号，不处理

    # 规则 2: 检查二级序号 (如 1.1, 3.2)
    level2_match = level2_pattern.match(text)
    if level2_match:
        old_num = level2_match.group(1)  # e.g., "3.2"
        separator = level2_match.group(2)  # e.g., "" (空), " " 或 "、"

        # 规则：改为 ###1.1、 (保留原分隔符)
        # 如果原文是 "3.2监修", separator是"", 结果是 "###3.2监修"
        # 如果原文是 "1.1、...", separator是"、", 结果是 "###1.1、..."
        new_prefix = f"###{old_num}{separator}"

        # 计算旧前缀的长度
        old_prefix_len = len(old_num) + len(separator)

        paragraph.text = new_prefix + text[old_prefix_len:]
        return

    # 规则 1: 检查一级序号 (如 1, 2)
    level1_match = level1_pattern.match(text)
    if level1_match:
        old_num = level1_match.group(1)  # e.g., "1"
        separator = level1_match.group(2)  # e.g., "" (空), " " 或 "、"

        # 规则：改为 ###1. (统一用 ". " 替换原分隔符)
        new_prefix = f"###{old_num}. "

        # 计算旧前缀的长度
        old_prefix_len = len(old_num) + len(separator)

        paragraph.text = new_prefix + text[old_prefix_len:]
        return


def process_docx_file(file_path: str):
    """处理单个 .docx 文件"""
    try:
        doc = Document(file_path)
        for para in doc.paragraphs:
            modify_docx_paragraph(para)
        doc.save(file_path)
        print(f"已处理 (.docx): {file_path}")
    except Exception as e:
        print(f"处理 .docx 失败 {file_path}：{str(e)}")


# --- 逻辑 2: 处理 .DOC 文件 (使用 pywin32) ---

def modify_doc_paragraph(paragraph):
    """(用于.doc) 处理单个段落的序号格式 (健壮版)"""
    text = paragraph.Range.Text
    text_content = text.rstrip('\r\n')  # 获取纯文本内容
    if not text_content.strip():
        return

    # 正则表达式(修正版)
    level3_pattern = re.compile(r'^(\d+\.\d+\.\d+)([\s、]?)')
    level2_pattern = re.compile(r'^(\d+\.\d+)([\s、]?)')
    level1_pattern = re.compile(r'^(\d+)([\s、]?)')

    # 规则 3: 检查三级序号
    level3_match = level3_pattern.match(text_content)
    if level3_match:
        return

        # 规则 2: 检查二级序号
    level2_match = level2_pattern.match(text_content)
    if level2_match:
        old_num = level2_match.group(1)
        separator = level2_match.group(2)

        # 规则：保留原分隔符
        new_prefix = f"###{old_num}{separator}"
        old_prefix_len = len(old_num) + len(separator)

        new_text_content = new_prefix + text_content[old_prefix_len:]
        paragraph.Range.Text = new_text_content + "\r"  # 加回换行符
        return

    # 规则 1: 检查一级序号
    level1_match = level1_pattern.match(text_content)
    if level1_match:
        old_num = level1_match.group(1)
        separator = level1_match.group(2)

        # 规则：统一用 ". "
        new_prefix = f"###{old_num}. "
        old_prefix_len = len(old_num) + len(separator)

        new_text_content = new_prefix + text_content[old_prefix_len:]
        paragraph.Range.Text = new_text_content + "\r"  # 加回换行符
        return


def process_doc_file(file_path: str, word_app):
    """处理单个 .doc 文件"""
    try:
        doc = word_app.Documents.Open(file_path)
        for para in doc.Paragraphs:
            modify_doc_paragraph(para)

        doc.Save()
        doc.Close()
        print(f"已处理 (.doc): {file_path}")
    except Exception as e:
        print(f"处理 .doc 失败 {file_path}：{str(e)}")
        try:
            doc.Close(False)  # 处理失败时，确保关闭文档（不保存）
        except:
            pass

        # --- 主程序：遍历和分发 ---


def process_all_word_files(root_dir: str):
    """遍历根目录，根据.doc或.docx分发处理"""

    word_app = None
    try:
        # 启动 Word 应用程序（设为不可见）
        word_app = win32com.client.Dispatch("Word.Application")
        word_app.Visible = False

        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                # 排除Word临时文件（~$开头）
                if filename.startswith("~$"):
                    continue

                file_path = os.path.join(dirpath, filename)

                if filename.lower().endswith(".docx"):
                    process_docx_file(file_path)

                elif filename.lower().endswith(".doc"):
                    process_doc_file(file_path, word_app)

    except Exception as e:
        print(f"启动 Word 失败。请确保已安装 Word 且 pywin32 已正确安装。错误: {e}")
    finally:
        # 无论成功与否，最后都要关闭 Word 应用程序
        if word_app:
            word_app.Quit()
            print("Word 应用程序已关闭。")


if __name__ == "__main__":
    # 目标文件夹路径 (仍使用您上次指定的 E:\ai)
    root_directory = r"E:\ai"

    if not os.path.exists(root_directory):
        print(f"错误：路径不存在，请检查路径。 {root_directory}")
    else:
        print(f"开始处理文件夹：{root_directory} 及其子文件夹...")
        print("正在启动 Word 应用程序 (后台运行)...")
        process_all_word_files(root_directory)
        print("所有Word文件处理完成！")