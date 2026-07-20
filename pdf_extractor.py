#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 题目提取器
从 PDF 中提取单选、多选和是非题，识别红色字体的正确答案
"""

import fitz  # PyMuPDF
import json
import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Literal
from enum import Enum


class QuestionType(Enum):
    SINGLE_CHOICE = "single"  # 单选题
    MULTIPLE_CHOICE = "multiple"  # 多选题
    TRUE_FALSE = "true_false"  # 是非题


@dataclass
class Question:
    id: int
    type: str
    content: str
    options: List[str]
    answer: str
    explanation: str = ""
    
    def to_dict(self):
        return asdict(self)


def is_red_color(color):
    """
    判断颜色是否为红色（或接近红色）
    color 可以是灰度值、RGB 元组或 CMYK 元组
    """
    if isinstance(color, (int, float)):
        # 灰度图像，无法判断红色
        return False
    elif isinstance(color, (tuple, list)) and len(color) == 3:
        # RGB 颜色
        r, g, b = color[0], color[1], color[2]
        # 红色的判断：R 值高，G 和 B 值低
        return r > 0.5 and g < 0.3 and b < 0.3
    elif isinstance(color, (tuple, list)) and len(color) == 4:
        # CMYK 颜色
        c, m, y, k = color
        # CMYK 中红色通常是低 C, 高 M, 高 Y, 低 K
        return m > 0.5 and y > 0.5 and c < 0.3
    return False


def extract_text_with_color(page):
    """
    提取页面上的文本及其颜色信息
    返回：[(text, is_red), ...]
    """
    text_blocks = []
    
    # 获取详细文本块信息
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    
    for block in blocks:
        if block["type"] != 0:  # 0 表示文本块
            continue
        
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                
                color = span.get("color", 0)
                is_red = is_red_color(color)
                
                text_blocks.append((text, is_red))
    
    return text_blocks


def parse_questions_from_pdf(pdf_path: str) -> List[Question]:
    """
    从 PDF 文件中解析题目
    """
    doc = fitz.open(pdf_path)
    questions = []
    question_id = 0
    
    current_question = None
    current_options = []
    collecting_options = False
    option_labels = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text_blocks = extract_text_with_color(page)
        
        i = 0
        while i < len(text_blocks):
            text, is_red = text_blocks[i]
            
            # 检测题目开始（通常以数字开头，如 "1.", "一、", "1、" 等）
            question_start_match = re.match(r'^(\d+)[\.、\s]', text)
            
            if question_start_match and not collecting_options:
                # 保存上一题
                if current_question is not None:
                    question_id += 1
                    questions.append(Question(
                        id=question_id,
                        **current_question
                    ))
                
                # 开始新题目
                question_num = question_start_match.group(1)
                content = text[question_start_match.end():].strip()
                
                # 判断题型
                if re.search(r'[是否对错][√×XO]|正确 | 错误', content):
                    q_type = QuestionType.TRUE_FALSE.value
                else:
                    q_type = QuestionType.SINGLE_CHOICE.value  # 默认单选，后面可能更新为多选
                
                current_question = {
                    "type": q_type,
                    "content": content,
                    "options": [],
                    "answer": "",
                    "explanation": ""
                }
                current_options = []
                collecting_options = True
                i += 1
                continue
            
            # 检测选项（A. B. C. D. 等）
            option_match = re.match(r'^([A-H])[\.、\s]\s*(.*)', text)
            if option_match and collecting_options and current_question:
                option_label = option_match.group(1)
                option_text = option_match.group(2).strip()
                
                if is_red:
                    # 红色选项是正确答案
                    current_question["answer"] += option_label
                    if current_question["type"] == QuestionType.SINGLE_CHOICE.value and len(current_question["answer"]) > 1:
                        current_question["type"] = QuestionType.MULTIPLE_CHOICE.value
                else:
                    current_options.append(f"{option_label}. {option_text}")
                
                i += 1
                continue
            
            # 检测是非题的答案（红字的"正确"、"错误"、"√"、"×"等）
            if current_question and current_question["type"] == QuestionType.TRUE_FALSE.value:
                if is_red:
                    if any(kw in text for kw in ["正确", "对", "√", "T"]):
                        current_question["answer"] = "正确"
                    elif any(kw in text for kw in ["错误", "错", "×", "X", "F"]):
                        current_question["answer"] = "错误"
                i += 1
                continue
            
            # 收集额外内容（可能是题干延续或解释）
            if current_question and collecting_options and not option_match:
                if text and not is_red:
                    # 可能是题干的延续
                    if not current_question["options"]:
                        current_question["content"] += " " + text
                i += 1
                continue
            
            i += 1
    
    # 保存最后一题
    if current_question is not None:
        question_id += 1
        current_question["options"] = current_options
        questions.append(Question(
            id=question_id,
            **current_question
        ))
    
    doc.close()
    return questions


def save_questions_to_json(questions: List[Question], output_path: str):
    """将题目保存到 JSON 文件"""
    data = [q.to_dict() for q in questions]
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已保存 {len(questions)} 道题目到 {output_path}")


def load_questions_from_json(json_path: str) -> List[Question]:
    """从 JSON 文件加载题目"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    questions = []
    for item in data:
        questions.append(Question(**item))
    return questions


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法：python pdf_extractor.py <pdf 文件路径> [输出 json 路径]")
        print("示例：python pdf_extractor.py questions.pdf questions.json")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "questions.json"
    
    print(f"正在解析 PDF: {pdf_path}")
    questions = parse_questions_from_pdf(pdf_path)
    print(f"成功提取 {len(questions)} 道题目")
    
    save_questions_to_json(questions, output_path)
    
    # 显示前几道题预览
    print("\n题目预览:")
    for q in questions[:3]:
        print(f"\n第{q.id}题 [{q.type}]:")
        print(f"题干：{q.content[:100]}...")
        print(f"选项：{q.options}")
        print(f"答案：{q.answer}")
