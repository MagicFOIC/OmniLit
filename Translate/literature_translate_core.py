from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable

import fitz

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - tqdm is optional at runtime
    tqdm = None


PROMPT_VERSION = "academic-pdf-zh-v12-readable-fragment-guard"

SEGMENT_RULES = (
    "Important segment rules:\n"
    "- Translate each segment independently.\n"
    "- Do not continue a segment with text from the next segment, next column, next page, or document context.\n"
    "- If a segment ends mid-sentence, translate only the visible fragment and keep it as an incomplete fragment. Do not use context to complete the sentence, and do not end the translation with sentence-final punctuation if the source fragment is unfinished.\n"
    "- Preserve equations, variables, citation numbers, figure/table labels, URLs, DOI text, protected acronyms, and product/model names such as CATDA, CatGraph, DatasetAgent, CatAgent, LLM, LLMs, GPT, RAG, ChatGPT-o3, Gemini 2.5 Pro, Cypher.\n"
    "- In AI/LLM papers, translate Agent/Agents as 智能体 unless it is part of a product/model name; never translate LLM or LLMs into Chinese, and never translate them as 法学硕士.\n"
    "- For English academic prose, output fluent Simplified Chinese. Do not leave a complete English sentence untranslated unless it is a reference, URL, formula, code, figure-internal label, or protected name."
)

SYSTEM_PROMPT = """你是严谨的中英文学术文献翻译专家，擅长催化、化学、材料、机器学习和工程论文翻译。
目标是把英文论文翻译成符合中国大陆学术写作习惯的简体中文，表达准确、凝练、术语统一，并尽量保持原 PDF 版式可直接覆盖排版。
必须遵守：
1. 只翻译给定片段，不增删事实，不解释，不补充参考文献。
2. 保留公式、变量、化学式、数字、单位、DOI、URL、图表编号、引用编号和缩写，例如 CATDA、CatGraph、DatasetAgent、CatAgent、F1、R2、SiO2、Al2O3、LLM、LLMs、GPT、RAG、Cypher。
3. 专业术语要稳定一致；不确定的专名、数据库名、软件名、模型名和机构名保留英文；AI/LLM 语境下 Agent/Agents 译为“智能体”，不要译为“代理”；LLM/LLMs 必须保留为 LLM/LLMs，绝不能译为“法学硕士”。
4. Figure / Fig. / Table / Scheme caption 分别翻译为“图 / 图 / 表 / 方案”开头；ABSTRACT 翻译为“摘要”；KEYWORDS 翻译为“关键词”；INTRODUCTION / RESULTS / DISCUSSION / CONCLUSION 等章节标题要翻译。
5. 作者姓名：明显是中文姓名拼音时可译为中文姓名；其他人名保留原文。
6. 英文学术正文必须译为简体中文；除受保护术语、参考文献、URL/DOI、公式、代码、化学式和图内英文标签外，不要整句保留英文。
7. 输出必须是合法 JSON 对象，键名与输入 id 完全一致，值为对应中文译文。"""

USER_PROMPT_TEMPLATE = """文档上下文（用于术语统一，不要逐字翻译这部分）：
{context}

术语表（必须优先采用）：
{glossary}

请逐条翻译 segments 中的 text 字段，保持每个 id 独立，不要合并段落。
若某项 ends_mid_sentence 为 true，它是页尾/栏尾的可见截断片段；译文也必须保留为未完句，不得补全下一页或下一栏内容。
segments:
{segments_json}

只返回 JSON 对象。"""


BUILTIN_GLOSSARY_TEXT = """LLM => LLM
LLMs => LLMs
large language model => 大语言模型
large language models => 大语言模型
long-context large language model => 长上下文大语言模型
Agent => 智能体
Agents => 智能体
agent => 智能体
agents => 智能体
agentic framework => 智能体框架
multi-agent => 多智能体
knowledge graph => 知识图谱
knowledge graphs => 知识图谱
CATDA => CATDA
Corpus-aware Automated Text-to-Graph Catalyst Discovery Agent => 语料感知的自动文本到图催化剂发现智能体
CatGraph => CatGraph
CatAgent => CatAgent
DatasetAgent => DatasetAgent
ChatGPT-o3 => ChatGPT-o3
Gemini 2.5 Pro => Gemini 2.5 Pro
Cypher => Cypher
RAG => RAG
GPT => GPT
large-scale data analysis => 大规模数据分析
rational catalyst design => 理性催化剂设计
manual curation => 手动整理
data curation => 数据整理"""


DEFAULT_GLOSSARY_PACK: dict[str, dict[str, object]] = {
    "00_general_academic.csv": {
        "title": "通用学术术语表",
        "description": "论文结构、研究方法、统计评价和通用学术表达。默认启用。",
        "default": True,
        "terms": [
            ("ABSTRACT", "摘要"), ("Abstract", "摘要"), ("KEYWORDS", "关键词"), ("Keywords", "关键词"),
            ("INTRODUCTION", "引言"), ("Introduction", "引言"), ("METHODS", "方法"),
            ("MATERIALS AND METHODS", "材料与方法"), ("RESULTS", "结果"), ("DISCUSSION", "讨论"),
            ("CONCLUSION", "结论"), ("CONCLUSIONS", "结论"), ("Supporting Information", "支持信息"),
            ("Supplementary Information", "补充信息"), ("Data Availability", "数据可用性"),
            ("Code Availability", "代码可用性"), ("Acknowledgments", "致谢"),
            ("Conflict of Interest", "利益冲突"), ("References", "参考文献"), ("Research Article", "研究文章"),
            ("Review Article", "综述文章"), ("Received", "收稿"), ("Revised", "修订"),
            ("Accepted", "接收"), ("Published", "发表"), ("workflow", "工作流程"),
            ("framework", "框架"), ("paradigm", "范式"), ("benchmark", "基准"), ("baseline", "基线"),
            ("robustness", "鲁棒性"), ("scalability", "可扩展性"), ("reproducibility", "可重复性"),
            ("quantitative analysis", "定量分析"), ("qualitative analysis", "定性分析"),
            ("statistically significant", "具有统计显著性"), ("standard deviation", "标准差"),
            ("confidence interval", "置信区间"), ("dataset", "数据集"), ("data set", "数据集"), ("metadata", "元数据"),
        ],
    },
    "01_ai_ml_data_science.csv": {
        "title": "AI / 机器学习 / 数据科学",
        "description": "LLM、RAG、智能体、知识图谱、机器学习评价指标等。",
        "default": False,
        "terms": [
            ("artificial intelligence", "人工智能"), ("machine learning", "机器学习"), ("deep learning", "深度学习"),
            ("large language model", "大语言模型"), ("large language models", "大语言模型"),
            ("LLM", "LLM"), ("LLMs", "LLMs"), ("GPT", "GPT"), ("RAG", "RAG"),
            ("retrieval-augmented generation", "检索增强生成"), ("Agent", "智能体"), ("Agents", "智能体"),
            ("agent", "智能体"), ("agents", "智能体"), ("multi-agent", "多智能体"),
            ("agentic framework", "智能体框架"), ("tool-augmented LLM", "工具增强的LLM"),
            ("prompt", "提示词"), ("fine-tuning", "微调"), ("embedding", "嵌入"),
            ("knowledge graph", "知识图谱"), ("graph database", "图数据库"), ("node", "节点"), ("edge", "边"),
            ("entity extraction", "实体抽取"), ("relation extraction", "关系抽取"),
            ("classification", "分类"), ("regression", "回归"), ("prediction", "预测"),
            ("training set", "训练集"), ("test set", "测试集"), ("feature sparsity", "特征稀疏性"),
            ("ground truth", "真实值"), ("accuracy", "准确率"), ("precision", "精确率"), ("recall", "召回率"),
            ("F1 score", "F1分数"), ("long-context", "长上下文"), ("context window", "上下文窗口"),
            ("hallucination", "幻觉"), ("evidence-grounded", "基于证据的"),
        ],
    },
    "02_catalysis_chemistry_materials.csv": {
        "title": "催化 / 化学 / 材料科学",
        "description": "催化剂、合成步骤、表征方法、沸石与材料性质。",
        "default": False,
        "terms": [
            ("catalyst", "催化剂"), ("catalysis", "催化"), ("selectivity", "选择性"), ("conversion", "转化率"),
            ("yield", "收率"), ("active site", "活性位点"), ("support", "载体"), ("binder", "粘结剂"),
            ("precursor", "前驱体"), ("reagent", "试剂"), ("solvent", "溶剂"), ("feedstock", "原料"),
            ("reaction condition", "反应条件"), ("testing condition", "测试条件"),
            ("performance metric", "性能指标"), ("synthesis protocol", "合成方案"),
            ("synthesis pathway", "合成路径"), ("unit operation", "单元操作"), ("impregnation", "浸渍"),
            ("calcination", "煅烧"), ("drying", "干燥"), ("mixing", "混合"), ("ion exchange", "离子交换"),
            ("hydrothermal synthesis", "水热合成"), ("hydrogenation", "加氢"), ("dehydrogenation", "脱氢"),
            ("isomerization", "异构化"), ("xylene isomerization", "二甲苯异构化"), ("p-xylene", "对二甲苯"),
            ("ethylbenzene", "乙苯"), ("ethylbenzene conversion", "乙苯转化率"), ("xylene loss", "二甲苯损失"),
            ("disproportionation", "歧化"), ("zeolite", "沸石"), ("framework", "骨架"),
            ("pore size", "孔径"), ("surface area", "比表面积"), ("BET surface area", "BET比表面积"),
            ("pore volume", "孔容"), ("crystallinity", "结晶度"), ("morphology", "形貌"),
            ("particle size", "粒径"), ("dopant", "掺杂剂"), ("adsorption", "吸附"), ("desorption", "解吸"),
            ("XRD", "XRD"), ("XPS", "XPS"), ("SEM", "SEM"), ("TEM", "TEM"), ("FTIR", "FTIR"),
            ("SiO2", "SiO2"), ("Al2O3", "Al2O3"),
        ],
    },
    "03_biology_medicine_pharmaceuticals.csv": {
        "title": "生物 / 医学 / 药学",
        "description": "基因组、蛋白、临床试验、药代药效与安全性评价。",
        "default": False,
        "terms": [("biology", "生物学"), ("medicine", "医学"), ("pharmacology", "药理学"), ("drug discovery", "药物发现"), ("biomarker", "生物标志物"), ("gene", "基因"), ("genome", "基因组"), ("protein", "蛋白质"), ("enzyme", "酶"), ("receptor", "受体"), ("antibody", "抗体"), ("immune response", "免疫反应"), ("cell line", "细胞系"), ("clinical trial", "临床试验"), ("randomized controlled trial", "随机对照试验"), ("efficacy", "疗效"), ("safety", "安全性"), ("adverse event", "不良事件"), ("toxicity", "毒性"), ("dose", "剂量"), ("bioavailability", "生物利用度"), ("pharmacokinetics", "药代动力学"), ("pharmacodynamics", "药效学"), ("in vitro", "体外"), ("in vivo", "体内")],
    },
    "04_energy_environment_chemical_engineering.csv": {
        "title": "能源 / 环境 / 化工",
        "description": "储能、碳中和、电催化、反应器、传质传热与过程工程。",
        "default": False,
        "terms": [("energy conversion", "能量转换"), ("energy storage", "储能"), ("renewable energy", "可再生能源"), ("carbon neutrality", "碳中和"), ("carbon emission", "碳排放"), ("carbon capture", "碳捕集"), ("life cycle assessment", "生命周期评价"), ("photocatalysis", "光催化"), ("electrocatalysis", "电催化"), ("hydrogen evolution reaction", "析氢反应"), ("oxygen evolution reaction", "析氧反应"), ("CO2 reduction reaction", "CO2还原反应"), ("fuel cell", "燃料电池"), ("battery", "电池"), ("electrode", "电极"), ("electrolyte", "电解质"), ("overpotential", "过电位"), ("current density", "电流密度"), ("Faradaic efficiency", "法拉第效率"), ("chemical engineering", "化学工程"), ("reactor", "反应器"), ("fixed-bed reactor", "固定床反应器"), ("mass transfer", "传质"), ("heat transfer", "传热"), ("WHSV", "WHSV")],
    },
    "05_physics_electronics_mechanical_engineering.csv": {
        "title": "物理 / 电子 / 机械工程",
        "description": "半导体、光电、力学、有限元、流体和热工程。",
        "default": False,
        "terms": [("physics", "物理学"), ("mechanics", "力学"), ("quantum mechanics", "量子力学"), ("thermodynamics", "热力学"), ("semiconductor", "半导体"), ("band gap", "带隙"), ("conduction band", "导带"), ("valence band", "价带"), ("charge carrier", "载流子"), ("mobility", "迁移率"), ("conductivity", "电导率"), ("dielectric constant", "介电常数"), ("photoluminescence", "光致发光"), ("transistor", "晶体管"), ("sensor", "传感器"), ("mechanical engineering", "机械工程"), ("stress", "应力"), ("strain", "应变"), ("elastic modulus", "弹性模量"), ("tensile strength", "拉伸强度"), ("fracture toughness", "断裂韧性"), ("finite element analysis", "有限元分析"), ("computational fluid dynamics", "计算流体力学"), ("laminar flow", "层流"), ("turbulent flow", "湍流")],
    },
    "06_computer_science_software.csv": {
        "title": "计算机 / 软件工程",
        "description": "算法、数据库、工程化、部署、测试、网络与安全。",
        "default": False,
        "terms": [("computer science", "计算机科学"), ("software engineering", "软件工程"), ("algorithm", "算法"), ("data structure", "数据结构"), ("database", "数据库"), ("query", "查询"), ("API", "API"), ("frontend", "前端"), ("backend", "后端"), ("microservice", "微服务"), ("container", "容器"), ("deployment", "部署"), ("continuous integration", "持续集成"), ("version control", "版本控制"), ("repository", "代码仓库"), ("unit test", "单元测试"), ("debugging", "调试"), ("logging", "日志记录"), ("monitoring", "监控"), ("latency", "延迟"), ("throughput", "吞吐量"), ("cache", "缓存"), ("authentication", "身份认证"), ("authorization", "授权"), ("encryption", "加密")],
    },
    "07_economics_management_finance.csv": {
        "title": "经济 / 管理 / 金融",
        "description": "宏微观经济、管理、供应链、风险、估值与金融市场。",
        "default": False,
        "terms": [("economics", "经济学"), ("microeconomics", "微观经济学"), ("macroeconomics", "宏观经济学"), ("supply", "供给"), ("demand", "需求"), ("market equilibrium", "市场均衡"), ("inflation", "通货膨胀"), ("interest rate", "利率"), ("management", "管理"), ("strategy", "战略"), ("business model", "商业模式"), ("value chain", "价值链"), ("stakeholder", "利益相关者"), ("governance", "治理"), ("supply chain", "供应链"), ("risk management", "风险管理"), ("finance", "金融"), ("financial market", "金融市场"), ("asset", "资产"), ("liability", "负债"), ("equity", "权益"), ("return", "回报"), ("portfolio", "投资组合"), ("net present value", "净现值"), ("cash flow", "现金流")],
    },
    "08_social_science_education_psychology.csv": {
        "title": "社会科学 / 教育 / 心理学",
        "description": "问卷、访谈、教育评价、心理变量与社会科学研究方法。",
        "default": False,
        "terms": [("social science", "社会科学"), ("sociology", "社会学"), ("education", "教育学"), ("psychology", "心理学"), ("cognition", "认知"), ("behavior", "行为"), ("motivation", "动机"), ("emotion", "情绪"), ("attitude", "态度"), ("learning outcome", "学习成效"), ("curriculum", "课程"), ("pedagogy", "教学法"), ("assessment", "评价"), ("intervention", "干预"), ("treatment group", "处理组"), ("control group", "对照组"), ("survey", "调查"), ("questionnaire", "问卷"), ("interview", "访谈"), ("participant", "参与者"), ("sample", "样本"), ("variable", "变量"), ("independent variable", "自变量"), ("dependent variable", "因变量"), ("validity", "效度"), ("reliability", "信度")],
    },
}

GLOSSARY_FILE_EXTENSIONS = {".csv", ".tsv", ".txt", ".json", ".md"}
DEFAULT_GLOSSARY_FILENAMES = tuple(
    filename for filename, spec in DEFAULT_GLOSSARY_PACK.items() if bool(spec.get("default"))
)


def localized_log(language: str, message: str) -> str:
    """翻译核心进度日志。参数：语言和中文消息。返回值：任务启动语言对应的文本。"""
    if language != "en":
        return message
    replacements = (
        ("准备处理 ", "Preparing "),
        ("读取 PDF 并提取文本段", "Reading PDF and extracting text segments"),
        ("已提取 ", "Extracted "),
        (" 段，需要翻译 ", " segments; translation required for "),
        ("构建上下文，准备翻译 ", "Building context; preparing to translate "),
        ("待翻译 ", "Pending translation: "),
        (" 段，分为 ", " segments in "),
        (" 个批次", " batches"),
        ("全部段落命中缓存，无需调用模型", "All segments were loaded from cache; no model call is needed"),
        ("正在翻译批次 ", "Translating batch "),
        ("已完成翻译批次 ", "Completed translation batch "),
        ("生成文献核心要点概况", "Generating document summary"),
        ("文献核心要点概况已生成", "Document summary generated"),
        ("加载字体并生成输出 PDF", "Loading fonts and generating output PDF"),
        ("准备渲染 ", "Preparing to render "),
        ("已渲染页面 ", "Rendered page "),
        ("追加文献概况页", "Appending document summary page"),
        ("已保存 ", "Saved "),
    )
    text = message
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def glossary_title_for(path: Path | str) -> str:
    """功能：生成术语表展示标题。参数：path。返回值：str。"""
    file_path = Path(path)
    meta = DEFAULT_GLOSSARY_PACK.get(file_path.name, {})
    return str(meta.get("title") or file_path.stem)


def glossary_description_for(path: Path | str) -> str:
    """功能：生成术语表展示说明。参数：path。返回值：str。"""
    file_path = Path(path)
    meta = DEFAULT_GLOSSARY_PACK.get(file_path.name, {})
    return str(meta.get("description") or "自定义术语表")


def ensure_default_glossaries(glossary_dir: Path, overwrite: bool = False) -> list[Path]:
    """功能：将缺失的内置术语表补齐到可写目录。参数：glossary_dir、overwrite。返回值：list[Path]。"""
    glossary_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, spec in DEFAULT_GLOSSARY_PACK.items():
        target = glossary_dir / filename
        if target.exists() and not overwrite:
            written.append(target)
            continue
        with target.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["source", "target"])
            for source, target_text in (spec.get("terms") or []):
                writer.writerow([source, target_text])
        written.append(target)
    readme = glossary_dir / "README_术语表使用说明.txt"
    if overwrite or not readme.exists():
        readme.write_text(
            "术语表格式：CSV 两列 source,target，或 TXT 中每行写成 英文 => 中文。\n"
            "GUI 中点击‘术语表’后的‘选择’按钮，可在弹窗内勾选多个术语表。\n"
            "默认启用 00_general_academic.csv；正式翻译建议使用‘通用学术 + 当前学科’组合，避免跨学科误译。\n"
            "AI/LLM 论文中，LLM/LLMs 保留英文；Agent/Agents 在智能体语境下译为‘智能体’。\n",
            encoding="utf-8",
        )
    return written


def discover_glossary_files(glossary_dir: Path) -> list[Path]:
    """功能：扫描可用术语表文件。参数：glossary_dir。返回值：list[Path]。"""
    if not glossary_dir.exists():
        return []
    result = [
        path for path in glossary_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in GLOSSARY_FILE_EXTENSIONS
        and not path.name.startswith("~")
        and not path.name.startswith("_")
        and "README" not in path.name.upper()
    ]
    return sorted(result, key=lambda item: (0 if item.name in DEFAULT_GLOSSARY_PACK else 1, item.name.lower()))


def normalize_glossary_paths(paths: Path | str | Iterable[Path | str] | None) -> list[Path]:
    """功能：规范化术语表路径参数。参数：paths。返回值：list[Path]。"""
    if paths is None:
        return []
    if isinstance(paths, Path):
        return [paths]
    if isinstance(paths, str):
        raw = paths.strip()
        if not raw:
            return []
        if os.pathsep in raw:
            return [Path(part) for part in raw.split(os.pathsep) if part.strip()]
        return [Path(raw)]
    result: list[Path] = []
    for item in paths:
        if item is None:
            continue
        item_text = str(item).strip()
        if item_text:
            result.append(Path(item_text))
    return result


# Product/model/database names that should stay in English when present in the
# source text.  These are protected both in the model prompt and in
# post-processing so cached or provider-specific outputs cannot degrade into
# mistranslations such as “分类器” for CatAgent.
PROTECTED_SOURCE_TERMS = (
    "CATDA",
    "CatGraph",
    "CatAgent",
    "DatasetAgent",
    "ChatGPT-o3",
    "Gemini 2.5 Pro",
    "Cypher",
    "ChemDataExtractor",
    "DigiMOF",
    "ChatExtract",
    "L2M3 Database",
    "Catalysis-Hub",
    "Derwent Innovations Index",
)

TERM_VARIANT_REPAIRS = {
    "CATDA": ("CatDA", "catda"),
    "CatGraph": ("catgraph", "Cat Graph", "Cat-Graph"),
    "CatAgent": ("catagent", "Cat Agent", "Cat-Agent", "分类器"),
    "DatasetAgent": ("datasetagent", "Dataset Agent", "Dataset-Agent", "数据集智能体"),
    "ChatGPT-o3": ("ChatGPT O3", "ChatGPT-03", "ChatGPT-3"),
    "Gemini 2.5 Pro": ("Gemini2.5 Pro", "Gemini 2.5Pro"),
    "Cypher": ("cypher",),
}

PROTECTED_SHORT_TOKENS = {
    "AI", "ML", "LLM", "LLMs", "GPT", "RAG", "CATDA", "F1", "R2", "PET",
}


def merge_builtin_glossary(glossary_text: str | None) -> str:
    """功能：合并内置术语表与用户术语表文本。参数：glossary_text。返回值：str。"""
    user_text = (glossary_text or "").strip()
    if not user_text or user_text == "无":
        return BUILTIN_GLOSSARY_TEXT
    return f"{BUILTIN_GLOSSARY_TEXT}\n{user_text}"


SUMMARY_PROMPT_TEMPLATE = """请基于下面提供的论文内容，生成一页中文“文献核心要点概况”。

硬性要求：
1. 只能依据给定内容总结，不能凭空杜撰、不能补充文中没有的信息。
2. 表述要科学严谨，避免夸大结论。
3. 如果某项信息在材料中不明确，写“文中未明确说明”，不要猜测。
4. 优先覆盖：研究问题、方法/框架、数据来源与评估方式、主要结果/发现、应用价值、局限或注意事项。
5. 输出应适合放在 PDF 最后一页，控制在 700-1100 个中文字符。
6. 只返回合法 JSON 对象，键名固定为 "summary"。

论文内容：
{material}
"""


@dataclass
class LineSlot:
    """功能：保存 PDF 中单行文字的位置和样式。参数：无。返回值：无。"""
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float
    color: tuple[float, float, float]
    bold: bool

    @property
    def width(self) -> float:
        """功能：返回文本行宽度。参数：无。返回值：float。"""
        return max(0.0, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        """功能：返回文本行高度。参数：无。返回值：float。"""
        return max(0.0, self.bbox[3] - self.bbox[1])


@dataclass
class Segment:
    """功能：保存可独立翻译和渲染的文本片段。参数：无。返回值：无。"""
    sid: str
    page_index: int
    kind: str
    text: str
    lines: list[LineSlot]
    translate: bool

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """功能：返回片段边界框。参数：无。返回值：tuple[float, float, float, float]。"""
        x0 = min(line.bbox[0] for line in self.lines)
        y0 = min(line.bbox[1] for line in self.lines)
        x1 = max(line.bbox[2] for line in self.lines)
        y1 = max(line.bbox[3] for line in self.lines)
        return (x0, y0, x1, y1)

    @property
    def font_size(self) -> float:
        """功能：返回片段主要字号。参数：无。返回值：float。"""
        sizes = [line.font_size for line in self.lines if line.font_size > 0]
        return sum(sizes) / len(sizes) if sizes else 9.5

    @property
    def color(self) -> tuple[float, float, float]:
        """功能：返回片段主要颜色。参数：无。返回值：tuple[float, float, float]。"""
        counts = Counter(line.color for line in self.lines)
        return counts.most_common(1)[0][0] if counts else (0, 0, 0)

    @property
    def bold(self) -> bool:
        # Keep translated body text visually consistent.  The source PDF may
        # contain mixed bold spans inside one paragraph; applying that span
        # information to the whole translated segment made adjacent body
        # paragraphs randomly switch between thick and thin weights.
        """功能：返回片段是否使用粗体。参数：无。返回值：bool。"""
        return self.kind in {"title", "heading"}


class TranslationCache:
    """功能：持久化翻译结果缓存。参数：无。返回值：无。"""
    def __init__(self, cache_path: Path, enabled: bool = True) -> None:
        """功能：初始化对象状态。参数：cache_path、enabled。返回值：无。"""
        self.cache_path = cache_path
        self.enabled = enabled
        self.data: dict[str, str] = {}
        if enabled and cache_path.exists():
            try:
                loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                self.data = loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                broken_path = cache_path.with_suffix(cache_path.suffix + ".broken")
                try:
                    cache_path.replace(broken_path)
                except OSError:
                    pass
                self.data = {}

    def key(self, provider: str, model: str, target_lang: str, text: str, glossary: str) -> str:
        """功能：生成翻译缓存键。参数：provider、model、target_lang、text、glossary。返回值：str。"""
        raw = "\n".join([PROMPT_VERSION, provider, model, target_lang, glossary, text])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        """功能：读取缓存值。参数：key。返回值：str | None。"""
        return self.data.get(key) if self.enabled else None

    def set(self, key: str, value: str) -> None:
        """功能：写入缓存值。参数：key、value。返回值：None。"""
        if self.enabled:
            self.data[key] = value

    def save(self) -> None:
        """功能：持久化缓存内容。参数：无。返回值：None。"""
        if not self.enabled:
            return
        write_json_atomic(self.cache_path, self.data)


def write_json_atomic(path: Path, data: object) -> None:
    """Write JSON through a temporary file so interrupted runs do not corrupt reports."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


class BaseTranslator:
    """功能：定义翻译器统一接口。参数：无。返回值：无。"""
    provider = "base"
    model = ""

    def translate_many(self, segments: list[Segment], context: str) -> dict[str, str]:
        """功能：批量翻译文本片段。参数：segments、context。返回值：dict[str, str]。"""
        raise NotImplementedError

    def summarize_document(self, material: str) -> str:
        """功能：生成文档摘要。参数：material。返回值：str。"""
        return fallback_document_summary(material)


ProgressCallback = Callable[..., None]
PreviewCallback = Callable[[dict[str, str]], None]


class CopyTranslator(BaseTranslator):
    """功能：提供不调用网络的原文复制翻译器。参数：无。返回值：无。"""
    provider = "copy"
    model = "copy"

    def translate_many(self, segments: list[Segment], context: str) -> dict[str, str]:
        """功能：批量翻译文本片段。参数：segments、context。返回值：dict[str, str]。"""
        return {segment.sid: segment.text for segment in segments}

    def summarize_document(self, material: str) -> str:
        """功能：生成文档摘要。参数：material。返回值：str。"""
        return fallback_document_summary(material)


class OpenAITranslator(BaseTranslator):
    """功能：通过 OpenAI 兼容接口执行批量翻译。参数：无。返回值：无。"""
    provider = "openai-compatible"

    def __init__(
        self,
        model: str,
        target_lang: str,
        glossary_text: str,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.15,
        max_retries: int = 4,
        json_mode: bool = True,
    ) -> None:
        """功能：初始化对象状态。参数：model、target_lang、glossary_text、api_key、base_url、temperature、max_retries、json_mode。返回值：无。"""
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai is not installed. Install dependencies from environment.yml.") from exc

        self.model = model
        self.target_lang = target_lang
        self.glossary_text = merge_builtin_glossary(glossary_text)
        self.temperature = temperature
        self.max_retries = max_retries
        self.json_mode = json_mode
        api_key = (
            api_key
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("MOONSHOT_API_KEY")
            or os.getenv("GEMINI_API_KEY")
        )
        base_url = base_url or os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com"
        if not api_key:
            raise RuntimeError(
                "API key is not set. Pass --api-key, or set the API key for the selected provider."
            )
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def translate_many(self, segments: list[Segment], context: str) -> dict[str, str]:
        """功能：批量翻译文本片段。参数：segments、context。返回值：dict[str, str]。"""
        if not segments:
            return {}

        payload = [
            {
                "id": segment.sid,
                "kind": segment.kind,
                "ends_mid_sentence": not sentence_ended(segment.text),
                "text": segment.text,
            }
            for segment in segments
        ]
        user_prompt = USER_PROMPT_TEMPLATE.format(
            context=f"{SEGMENT_RULES}\n\n{context or 'None'}",
            glossary=self.glossary_text,
            segments_json=json.dumps(payload, ensure_ascii=False, indent=2),
        )
        expected_ids = [segment.sid for segment in segments]
        content = self._chat(user_prompt)
        try:
            parsed = parse_json_object(content, expected_ids=expected_ids)
        except ValueError as exc:
            print(f"批量响应不是可用 JSON：{exc}；改为逐段重试 {len(segments)} 段。")
            parsed = {}

        missing = [segment.sid for segment in segments if segment.sid not in parsed]
        if missing:
            # Retry missing items individually. This keeps long batch failures localized.
            for segment in segments:
                if segment.sid in parsed:
                    continue
                single_payload = [{
                    "id": segment.sid,
                    "kind": segment.kind,
                    "ends_mid_sentence": not sentence_ended(segment.text),
                    "text": segment.text,
                }]
                single_prompt = USER_PROMPT_TEMPLATE.format(
                    context=f"{SEGMENT_RULES}\n\n{context or 'None'}",
                    glossary=self.glossary_text,
                    segments_json=json.dumps(single_payload, ensure_ascii=False, indent=2),
                )
                parsed.update(parse_json_object(self._chat(single_prompt), expected_ids=[segment.sid]))
        return {segment.sid: str(parsed.get(segment.sid, segment.text)).strip() for segment in segments}

    def summarize_document(self, material: str) -> str:
        """功能：生成文档摘要。参数：material。返回值：str。"""
        prompt = SUMMARY_PROMPT_TEMPLATE.format(material=material)
        content = self._chat(prompt)
        parsed = parse_json_object(content, expected_ids=["summary"])
        return str(parsed.get("summary", "")).strip()

    def _chat(self, user_prompt: str) -> str:
        """功能：调用模型聊天接口并执行重试。参数：user_prompt。返回值：str。"""
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self.temperature,
                }
                if self.json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content or "{}"
            except Exception as exc:  # noqa: BLE001 - SDK/provider errors vary
                last_error = exc
                if self.json_mode:
                    self.json_mode = False
                time.sleep(min(30, 2**attempt))
        raise RuntimeError(f"Translation request failed after retries: {last_error}") from last_error


def _json_preview(content: str, limit: int = 240) -> str:
    """功能：截取便于日志展示的 JSON 文本。参数：content、limit。返回值：str。"""
    preview = re.sub(r"\s+", " ", content).strip()
    return preview[:limit] + ("..." if len(preview) > limit else "")


def _load_json_payload(content: str):
    """功能：解析模型返回的 JSON 载荷。参数：content。返回值：处理结果。"""
    raw = content.strip()
    candidates = [raw]
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    spans = []
    object_start, object_end = raw.find("{"), raw.rfind("}")
    if object_start >= 0 and object_end > object_start:
        spans.append(raw[object_start : object_end + 1])
    array_start, array_end = raw.find("["), raw.rfind("]")
    if array_start >= 0 and array_end > array_start:
        spans.append(raw[array_start : array_end + 1])
    for span in spans:
        try:
            return json.loads(span)
        except json.JSONDecodeError:
            continue

    raise ValueError(f"Translator did not return valid JSON. Response preview: {_json_preview(content)}")


def _scalar_translation(value) -> str | None:
    """功能：将标量模型结果规范化为译文。参数：value。返回值：str | None。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("translation", "translated_text", "target", "zh", "text", "content", "value"):
            if key in value:
                return _scalar_translation(value[key])
    return None


def _normalize_translation_payload(obj, expected_ids: list[str] | None = None) -> dict[str, str] | None:
    """功能：规范化模型批量翻译结果结构。参数：obj、expected_ids。返回值：dict[str, str] | None。"""
    expected_ids = expected_ids or []
    if isinstance(obj, dict):
        if "id" in obj:
            value = _scalar_translation(obj)
            if value is not None:
                return {str(obj["id"]): value}

        for key in ("translations", "segments", "results", "items", "data"):
            if key in obj:
                nested = _normalize_translation_payload(obj[key], expected_ids)
                if nested:
                    return nested

        result: dict[str, str] = {}
        for key, value in obj.items():
            scalar = _scalar_translation(value)
            if scalar is not None:
                result[str(key)] = scalar
        return result or None

    if isinstance(obj, list):
        result: dict[str, str] = {}
        for index, item in enumerate(obj):
            if isinstance(item, dict) and "id" in item:
                value = _scalar_translation(item)
                if value is not None:
                    result[str(item["id"])] = value
            elif expected_ids and index < len(expected_ids):
                value = _scalar_translation(item)
                if value is not None:
                    result[expected_ids[index]] = value
        return result or None

    if isinstance(obj, str) and len(expected_ids) == 1:
        return {expected_ids[0]: obj.strip()}

    return None


def parse_json_object(content: str, expected_ids: list[str] | None = None) -> dict[str, str]:
    """功能：解析并校验模型返回的 JSON 对象。参数：content、expected_ids。返回值：dict[str, str]。"""
    expected_ids = expected_ids or []
    try:
        obj = _load_json_payload(content)
    except ValueError:
        if len(expected_ids) == 1 and content.strip():
            return {expected_ids[0]: content.strip().strip("`").strip()}
        raise
    parsed = _normalize_translation_payload(obj, expected_ids)
    if parsed is None:
        raise ValueError(f"Translator did not return a JSON object. Response preview: {_json_preview(content)}")

    if len(expected_ids) == 1 and expected_ids[0] not in parsed and len(parsed) == 1:
        return {expected_ids[0]: next(iter(parsed.values())).strip()}
    return {str(key): str(value).strip() for key, value in parsed.items()}


def int_color_to_rgb(color: int) -> tuple[float, float, float]:
    """功能：将整数颜色转换为 RGB 浮点元组。参数：color。返回值：tuple[float, float, float]。"""
    return (
        ((color >> 16) & 255) / 255,
        ((color >> 8) & 255) / 255,
        (color & 255) / 255,
    )


def weighted_font_size(spans: Iterable[dict]) -> float:
    """功能：计算文字跨度的加权字号。参数：spans。返回值：float。"""
    total_chars = 0
    total_size = 0.0
    for span in spans:
        text = span.get("text", "")
        weight = max(1, len(text))
        total_chars += weight
        total_size += float(span.get("size", 9.5)) * weight
    return total_size / total_chars if total_chars else 9.5


def is_bold_font(font_name: str) -> bool:
    """功能：判断字体名称是否表示粗体。参数：font_name。返回值：bool。"""
    lowered = font_name.lower()
    return any(marker in lowered for marker in ("bold", "smbd", "semibold", "black", "heavy"))


def clean_line_text(text: str) -> str:
    """功能：清理 PDF 抽取出的单行文本。参数：text。返回值：str。"""
    text = text.replace("\u00ad", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def join_extracted_lines(lines: list[LineSlot]) -> str:
    """功能：按阅读顺序拼接抽取文本行。参数：lines。返回值：str。"""
    pieces: list[str] = []
    for line in lines:
        text = clean_line_text(line.text)
        if not text:
            continue
        if pieces and pieces[-1].endswith("-") and re.match(r"^[a-z]", text):
            pieces[-1] = pieces[-1][:-1] + text
        elif pieces and pieces[-1].endswith("‐") and re.match(r"^[a-z]", text):
            pieces[-1] = pieces[-1][:-1] + text
        else:
            pieces.append(text)
    joined = " ".join(pieces)
    joined = re.sub(r"\s+([,.;:!?%)\]\}])", r"\1", joined)
    joined = re.sub(r"([\(\[\{])\s+", r"\1", joined)
    return joined.strip()


def sentence_ended(text: str) -> bool:
    """功能：判断文本是否以句末标点结束。参数：text。返回值：bool。"""
    return bool(re.search(r"[.?!;:。！？；：\)]\s*$", text.strip()))


def is_heading_text(text: str) -> bool:
    """功能：判断文本是否像标题。参数：text。返回值：bool。"""
    stripped = text.strip()
    upper = stripped.upper()
    if stripped.startswith("■"):
        return True
    if upper.startswith(("ABSTRACT", "KEYWORDS", "REFERENCES", "ACKNOWLEDG", "AUTHOR INFORMATION")):
        return True
    if 3 <= len(stripped) <= 80 and upper == stripped and re.search(r"[A-Z]", stripped):
        return not re.search(r"[.,;:]{2,}", stripped)
    return False


def is_caption_text(text: str) -> bool:
    """功能：判断文本是否像图表说明。参数：text。返回值：bool。"""
    return bool(re.match(r"^(Figure|Fig\.|Table|Scheme)\s+\d+", text.strip(), re.IGNORECASE))


REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\s*)?(?:references?|bibliography|literature\s+cited|works\s+cited|references\s+and\s+notes|参考文献)\b",
    re.IGNORECASE,
)

REFERENCE_ENTRY_RE = re.compile(
    r"^\s*(?:\[\s*\d{1,3}\s*\]|\d{1,3}\s*[.)]\s+|\d{1,3}\s+(?=[A-Z][A-Za-z'’.-]+(?:,|\s)))",
    re.IGNORECASE,
)

REFERENCE_CLUE_RE = re.compile(
    r"\b(?:doi|https?://|arxiv|pubmed|crossref|proceedings|journal|vol\.|pp\.|pages?|\d{4}[a-z]?)\b",
    re.IGNORECASE,
)

PAGE_HEADER_RE = re.compile(
    r"(?:^|\b)(?:\d{1,4}\s+)?Page\s+\d+\s+of\s+\d+(?:\b|$)|"
    r"(?:^|\b)\d{1,4}\s+Page\s+\d+\s+of\s+\d+(?:\b|$)",
    re.IGNORECASE,
)


def is_running_page_header_text(text: str) -> bool:
    """功能：判断文本是否像页眉页脚。参数：text。返回值：bool。"""
    stripped = clean_line_text(text)
    if not stripped or len(stripped) > 180:
        return False
    if PAGE_HEADER_RE.search(stripped):
        return True
    # Some journal running headers do not contain an explicit "Page x of y"
    # phrase after extraction, but they still combine the journal name, year and
    # article/page number.  Treat only short top-band strings as such headers.
    if re.search(r"Nano[- ]Micro\s+Lett\.", stripped, re.I) and re.search(r"\(20\d{2}\)", stripped):
        return True
    return False


def is_reference_heading_text(text: str, lines: list[LineSlot] | None = None) -> bool:
    """Detect the start of the bibliography section more robustly.

    Some PDFs extract the heading together with the first bibliography item,
    so checking only `"REFERENCES" in text and len(text) < 80` misses those
    pages and causes references to be translated even when the UI switch is off.
    Prefer the first extracted line when available, then fall back to the joined
    segment text.
    """
    candidates: list[str] = []
    if lines:
        candidates.extend(clean_line_text(line.text) for line in lines[:3])
    candidates.append(clean_line_text(text))
    for candidate in candidates:
        if not candidate:
            continue
        compact = re.sub(r"\s+", " ", candidate)
        compact_no_marker = re.sub(r"^[\s■●•▪◆◇]+", "", compact)
        spaced = re.sub(r"\s+", "", compact_no_marker).lower()
        if REFERENCE_HEADING_RE.search(compact_no_marker) or spaced.startswith("references"):
            return True
    return False


def looks_like_equation_text(text: str) -> bool:
    """Detect equation-like text using only the text string.

    This is intentionally separate from :func:`is_equation_text`, which also
    receives layout lines.  It prevents formulas such as
    ``2 Precision Recall × × F1 = Precision Recall + (3)`` from being mistaken
    for numbered bibliography entries.  That bug caused every following block
    on the page to be treated as references and therefore left untranslated.
    """
    stripped = clean_line_text(text)
    if not stripped or len(stripped) > 220:
        return False
    compact = re.sub(r"\s+", "", stripped)
    if not compact:
        return False
    equation_marks = sum(1 for char in compact if char in "=+-*/×÷∑∏√≤≥<>≈≠±^_()[]{}|")
    equation_number = bool(re.search(r"\(\s*\d+[a-z]?\s*\)\s*$", stripped, re.IGNORECASE))
    alpha_words = re.findall(r"[A-Za-z]{2,}", stripped)
    prose_words = [word for word in alpha_words if word.lower() not in MATH_WORDS]
    symbol_ratio = equation_marks / max(1, len(compact))

    if equation_number and equation_marks >= 2 and len(prose_words) <= 3:
        return True
    if symbol_ratio >= 0.22 and len(prose_words) <= 2:
        return True
    return False


def is_reference_entry_text(text: str) -> bool:
    """功能：判断文本是否像参考文献条目。参数：text。返回值：bool。"""
    stripped = clean_line_text(text)
    if not stripped:
        return False
    if REFERENCE_HEADING_RE.search(stripped):
        return True
    # Formula lines can start with a leading glyph/number after PDF extraction
    # (for example the F1 formula may become "2 Precision Recall × × F1...").
    # They must not switch the rest of the page into reference mode.
    if looks_like_equation_text(stripped):
        return False
    if not REFERENCE_ENTRY_RE.match(stripped):
        return False
    # Avoid treating ordinary numbered section headings, formulas, or short
    # ordered lists as references.  Real reference entries usually contain
    # bibliographic clues such as a year, journal name, DOI, pages, or URL.
    if not REFERENCE_CLUE_RE.search(stripped):
        return False
    return True


def page_reading_order_key(page_rect: fitz.Rect, bbox: tuple[float, float, float, float]) -> tuple[int, float, float]:
    """功能：生成适合页面阅读顺序排序的键。参数：page_rect、bbox。返回值：tuple[int, float, float]。"""
    x0, y0, x1, _y1 = bbox
    width = max(1.0, x1 - x0)
    page_width = max(1.0, page_rect.width)
    # Full-width headings stay in natural vertical order; narrow text follows left column then right column.
    column = 0 if width > page_width * 0.62 else (0 if (x0 + x1) / 2 < page_rect.x0 + page_width * 0.52 else 1)
    return (column, y0, x0)


MATH_WORDS = {
    "accuracy",
    "auc",
    "cos",
    "exp",
    "f1",
    "fn",
    "fp",
    "log",
    "ln",
    "mae",
    "precision",
    "recall",
    "rmse",
    "sin",
    "tan",
    "tn",
    "tp",
}


def is_equation_text(text: str, lines: list[LineSlot]) -> bool:
    """功能：判断片段是否主要是公式。参数：text、lines。返回值：bool。"""
    stripped = clean_line_text(text)
    if not stripped or len(stripped) > 180:
        return False
    compact = re.sub(r"\s+", "", stripped)
    if not compact:
        return False

    equation_marks = sum(1 for char in compact if char in "=+-*/×÷∑∏√≤≥<>≈≠±^_()[]{}|")
    equation_number = bool(re.search(r"\(\s*\d+[a-z]?\s*\)\s*$", stripped, re.IGNORECASE))
    alpha_words = re.findall(r"[A-Za-z]{2,}", stripped)
    prose_words = [word for word in alpha_words if word.lower() not in MATH_WORDS]
    symbol_ratio = equation_marks / max(1, len(compact))

    if equation_number and equation_marks >= 2 and len(prose_words) <= 3:
        return True
    if len(lines) >= 4 and equation_marks >= 2 and len(prose_words) <= 3:
        return True
    if symbol_ratio >= 0.22 and len(prose_words) <= 2:
        return True
    return False


def union_bbox(lines: list[LineSlot]) -> tuple[float, float, float, float]:
    """功能：合并多行文本的边界框。参数：lines。返回值：tuple[float, float, float, float]。"""
    return (
        min(line.bbox[0] for line in lines),
        min(line.bbox[1] for line in lines),
        max(line.bbox[2] for line in lines),
        max(line.bbox[3] for line in lines),
    )


def should_start_new_segment(current: list[LineSlot], line: LineSlot) -> bool:
    """功能：判断当前文字行是否需要开启新片段。参数：current、line。返回值：bool。"""
    if not current:
        return False
    previous = current[-1]
    current_min_x = min(item.bbox[0] for item in current)
    gap = line.bbox[1] - previous.bbox[3]
    line_height = max(previous.height, 1.0)
    text = clean_line_text(line.text)
    prev_text = clean_line_text(previous.text)
    if is_heading_text(text) or is_heading_text(prev_text):
        return True
    if is_caption_text(text):
        return True
    if text.upper().startswith("KEYWORDS"):
        return True
    if gap > line_height * 0.75:
        return True
    if sentence_ended(prev_text) and line.bbox[0] - current_min_x > 6:
        return True
    return False


def extract_line_slots(block: dict) -> list[LineSlot]:
    """功能：从 PDF 文本块抽取带样式的文字行。参数：block。返回值：list[LineSlot]。"""
    slots: list[LineSlot] = []
    for line in block.get("lines", []):
        spans = line.get("spans", [])
        text = "".join(span.get("text", "") for span in spans)
        text = clean_line_text(text)
        if not text:
            continue
        bbox = tuple(float(value) for value in line.get("bbox", (0, 0, 0, 0)))
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width < 18 and height > 80:
            continue
        font_size = weighted_font_size(spans)
        colors = [int_color_to_rgb(int(span.get("color", 0))) for span in spans]
        color = Counter(colors).most_common(1)[0][0] if colors else (0, 0, 0)
        bold = any(is_bold_font(span.get("font", "")) for span in spans)
        slots.append(LineSlot(text=text, bbox=bbox, font_size=font_size, color=color, bold=bold))
    return slots


def classify_segment(
    text: str,
    lines: list[LineSlot],
    page_index: int,
    page_rect: fitz.Rect,
    in_references: bool,
    translate_references: bool,
    translate_header_footer: bool,
) -> tuple[str, bool, bool]:
    """功能：分类片段并决定是否参与翻译。参数：text、lines、page_index、page_rect、in_references、translate_references、translate_header_footer。返回值：tuple[str, bool, bool]。"""
    x0, y0, x1, y1 = union_bbox(lines)
    stripped = text.strip()
    upper = stripped.upper()
    is_reference_heading = is_reference_heading_text(stripped, lines)
    reference_like_entry = is_reference_entry_text(stripped)
    next_in_references = in_references or is_reference_heading

    max_font = max(line.font_size for line in lines)
    # Header/footer detection must be conservative.  Some journals start a
    # continued body paragraph just below the header (around y=49 pt); the
    # previous broad `y0 < 55` rule marked those paragraphs as metadata and
    # left them untranslated.  Treat only the real header/footer bands or
    # explicit DOI/URL-only metadata as metadata.
    is_top_header = y1 < 42 or (
        y0 < 48
        and y1 < 55
        and len(lines) <= 4
        and re.search(r"(article|https?://|doi:|nature communications)", stripped, re.I)
    )
    # Running headers such as "184 Page 2 of 22 Nano-Micro Lett. (2026)"
    # sit lower than many publisher logos and can otherwise be misclassified as
    # bibliography entries because they start with a number and contain a year.
    # Once that happens, the old global reference flag leaves the whole document
    # untranslated.
    is_top_header = is_top_header or (y0 < 92 and is_running_page_header_text(stripped))
    is_bottom_footer = y0 > page_rect.height - 45
    if is_top_header or is_bottom_footer or re.match(r"^(https?://|DOI:)", stripped, re.I):
        return "metadata", translate_header_footer, next_in_references
    if re.search(r"(orcid\.org|E-?mail\s*:)", stripped, re.I):
        return "metadata", False, next_in_references
    if page_index == 0 and y0 < 235 and max_font <= 9.5:
        return "metadata", translate_header_footer, next_in_references
    # Equation detection must happen before reference-entry detection.
    # Otherwise extracted formulas that begin with a number can be misread as
    # bibliography entries, which makes all following body text untranslated.
    if is_equation_text(stripped, lines):
        return "equation", False, next_in_references
    if (next_in_references or reference_like_entry) and not translate_references:
        # A single reference-looking line must not switch the rest of the paper
        # into reference mode.  Page headers often look like references after
        # extraction (leading number + journal + year), so only an actual
        # References heading keeps the state enabled for following segments.
        return "reference", False, next_in_references
    if is_caption_text(stripped):
        return "caption", True, next_in_references
    if page_index == 0 and max_font >= 14:
        return "title", True, next_in_references
    if is_heading_text(stripped):
        return "heading", True, next_in_references
    if page_index == 0 and y0 < 180 and max_font >= 10.5:
        return "authors", True, next_in_references
    return "body", True, next_in_references


def extract_segments(
    doc: fitz.Document,
    translate_references: bool,
    translate_header_footer: bool,
    max_pages: int | None = None,
) -> list[Segment]:
    """功能：从 PDF 页面抽取可翻译片段。参数：doc、translate_references、translate_header_footer、max_pages。返回值：list[Segment]。"""
    segments: list[Segment] = []
    in_references = False
    page_count = min(len(doc), max_pages) if max_pages else len(doc)
    for page_index in range(page_count):
        page = doc[page_index]
        page_groups: list[list[LineSlot]] = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            block_lines = sorted(extract_line_slots(block), key=lambda item: (item.bbox[1], item.bbox[0]))
            if not block_lines:
                continue
            current: list[LineSlot] = []
            for line in block_lines:
                if should_start_new_segment(current, line):
                    page_groups.append(current)
                    current = []
                current.append(line)
            if current:
                page_groups.append(current)

        page_groups.sort(key=lambda group: page_reading_order_key(page.rect, union_bbox(group)))

        for group in page_groups:
            text = join_extracted_lines(group)
            if not text:
                continue
            # Respect the reading order within the page so a References heading
            # switches off every following bibliography entry, even when PyMuPDF
            # returned blocks out of visual order.
            kind, translate, next_in_references = classify_segment(
                text,
                group,
                page_index,
                page.rect,
                in_references,
                translate_references,
                translate_header_footer,
            )
            in_references = next_in_references
            sid = f"p{page_index + 1:03d}_s{len(segments) + 1:04d}"
            segments.append(Segment(sid=sid, page_index=page_index, kind=kind, text=text, lines=group, translate=translate))
    return segments

def build_document_context(segments: list[Segment], max_chars: int = 7000) -> str:
    """功能：构建供模型参考的文档上下文。参数：segments、max_chars。返回值：str。"""
    preferred = [
        segment
        for segment in segments
        if segment.kind in {"title", "heading", "caption"} or segment.text.upper().startswith("ABSTRACT")
    ]
    if not preferred:
        preferred = segments[:30]
    pieces: list[str] = []
    total = 0
    for segment in preferred:
        item = f"[{segment.kind}] {segment.text}"
        if total + len(item) > max_chars:
            break
        pieces.append(item)
        total += len(item)
    return "\n".join(pieces)


def _glossary_entry_from_text_line(line: str) -> str | None:
    """功能：解析纯文本术语表中的单行记录。参数：line。返回值：str | None。"""
    text = line.strip()
    if not text or text.startswith("#") or text.startswith("//"):
        return None
    if "=>" in text:
        source, target = text.split("=>", 1)
        source, target = source.strip(), target.strip()
        if source and target:
            return f"{source} => {target}"
    return None


def _load_single_glossary(path: Path) -> list[str]:
    """功能：读取单个术语表文件。参数：path。返回值：list[str]。"""
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[str] = []
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key, value in data.items():
                if str(key).strip() and str(value).strip():
                    rows.append(f"{str(key).strip()} => {str(value).strip()}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    source = item.get("source") or item.get("src") or item.get("en") or item.get("term")
                    target = item.get("target") or item.get("dst") or item.get("zh") or item.get("translation")
                    if source and target:
                        rows.append(f"{str(source).strip()} => {str(target).strip()}")
                    continue
                parsed = _glossary_entry_from_text_line(str(item))
                if parsed:
                    rows.append(parsed)
        return rows

    if suffix in {".txt", ".md"}:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            parsed = _glossary_entry_from_text_line(line)
            if parsed:
                rows.append(parsed)
        return rows

    delimiter = "	" if suffix == ".tsv" else ","
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file, delimiter=delimiter)
        for row in reader:
            if not row:
                continue
            if len(row) == 1:
                parsed = _glossary_entry_from_text_line(row[0])
                if parsed:
                    rows.append(parsed)
                continue
            source, target = row[0].strip(), row[1].strip()
            if not source or not target or source.lower() in {"source", "english", "en", "term"}:
                continue
            rows.append(f"{source} => {target}")
    return rows


def load_glossary(path: Path | str | Iterable[Path | str] | None) -> str:
    """功能：读取并合并多个术语表。参数：path。返回值：str。"""
    paths = normalize_glossary_paths(path)
    if not paths:
        return "无"
    rows: list[str] = []
    seen: set[str] = set()
    for glossary_path in paths:
        for item in _load_single_glossary(glossary_path):
            if item not in seen:
                rows.append(item)
                seen.add(item)
    return "\n".join(rows) if rows else "无"


def batch_segments(segments: list[Segment], batch_size: int, max_chars: int) -> Iterable[list[Segment]]:
    """功能：按数量和字符数拆分翻译批次。参数：segments、batch_size、max_chars。返回值：Iterable[list[Segment]]。"""
    batch: list[Segment] = []
    chars = 0
    for segment in segments:
        length = len(segment.text)
        if batch and (len(batch) >= batch_size or chars + length > max_chars):
            yield batch
            batch = []
            chars = 0
        batch.append(segment)
        chars += length
    if batch:
        yield batch


def compact_text_length(text: str) -> int:
    """功能：计算忽略空白后的文本长度。参数：text。返回值：int。"""
    return len(re.sub(r"\s+", "", text or ""))


def sentence_end_count(text: str) -> int:
    """功能：统计句末标点数量。参数：text。返回值：int。"""
    return len(re.findall(r"[。！？.!?;；]", text or ""))


def is_suspicious_translation(segment: Segment, translation: str) -> bool:
    """功能：判断译文是否存在明显质量异常。参数：segment、translation。返回值：bool。"""
    if segment.kind in {"metadata", "reference", "equation"}:
        return False
    source = clean_line_text(segment.text)
    target = normalize_translated_text(translation)
    source_len = compact_text_length(source)
    target_len = compact_text_length(target)
    if source_len < 20 or target_len < 20:
        return False

    ratio = target_len / max(1, source_len)
    source_ends = sentence_ended(source)
    target_sentences = sentence_end_count(target)

    if not source_ends and re.search(r"[。！？.!?；;]\s*$", target):
        # A page/column fragment that ends mid-sentence must remain incomplete.
        # If the model returned a sentence-final punctuation mark, it probably
        # completed the fragment from document context, which can create severe
        # layout pressure and tiny rendered text.
        return True
    if not source_ends and source_len <= 220 and target_len > max(source_len * 3.2, source_len + 260):
        return True
    if source_len <= 90 and target_len > source_len * 4.5 and target_sentences >= 2:
        return True
    if source_len <= 160 and ratio > 5.0 and target_sentences >= 3:
        return True
    return False


def guarded_translation(
    translator: BaseTranslator,
    segment: Segment,
    text: str,
    context: str,
) -> tuple[str, bool]:
    """功能：执行单片段翻译并处理异常译文。参数：translator、segment、text、context。返回值：tuple[str, bool]。"""
    cleaned = apply_term_guard(segment.text, normalize_translated_text(text)).strip()
    if translator.provider == "copy":
        return cleaned, True
    needs_retry = is_suspicious_translation(segment, cleaned) or is_probably_untranslated(segment, cleaned)
    if not needs_retry:
        return cleaned, True

    reason = "untranslated English" if is_probably_untranslated(segment, cleaned) else "suspiciously long translation"
    if translator.provider != "copy":
        print(f"{segment.sid}: {reason}; retrying this segment alone.")
        try:
            retry = translator.translate_many([segment], context="").get(segment.sid, segment.text).strip()
            retry = apply_term_guard(segment.text, normalize_translated_text(retry))
            if not is_suspicious_translation(segment, retry) and not is_probably_untranslated(segment, retry):
                return retry, True
        except Exception as exc:  # noqa: BLE001 - providers vary
            print(f"{segment.sid}: single-segment retry failed: {exc}")

    # Keep the model output when it contains some Chinese after term repair; that
    # is usually better than falling all the way back to the English source.  Do
    # not cache it, so a later run can repair the segment with another provider.
    if cjk_char_count(cleaned) >= 4:
        if not sentence_ended(clean_line_text(segment.text)):
            cleaned = re.sub(r"[。！？.!?；;]+\s*$", "", cleaned).rstrip()
        print(f"{segment.sid}: {reason} after retry; using repaired output without caching.")
        return cleaned, False
    print(f"{segment.sid}: {reason} rejected; keeping original text and reporting as uncached.")
    return segment.text, False


def translation_units_for_segments(segments: list[Segment]) -> list[tuple[Segment, list[Segment]]]:
    """Merge visually continuous extracted lines before sending them to the model.

    PDF extraction often returns one visual line as one segment on title pages.
    Translating those line fragments independently produces broken sentences and
    makes the renderer clip long Chinese fragments.  This function builds the
    same paragraph-like units that the renderer uses, while retaining the first
    source segment id so the rest of the pipeline and cache stay stable.
    """
    units: list[tuple[Segment, list[Segment]]] = []
    group: list[Segment] = []

    def flush() -> None:
        """功能：提交当前翻译批次。参数：无。返回值：None。"""
        nonlocal group
        if not group:
            return
        if len(group) == 1:
            units.append((group[0], list(group)))
        else:
            first = group[0]
            merged_lines = [line for segment in group for line in segment.lines]
            merged = replace(
                first,
                text=join_extracted_lines(merged_lines),
                lines=merged_lines,
            )
            units.append((merged, list(group)))
        group = []

    for segment in segments:
        if not segment.translate:
            flush()
            continue
        if group and should_merge_render_segments(group[-1], segment):
            group.append(segment)
        else:
            flush()
            group = [segment]
    flush()
    return units


def translate_segments(
    segments: list[Segment],
    translator: BaseTranslator,
    cache: TranslationCache,
    context: str,
    target_lang: str,
    glossary_text: str,
    batch_size: int,
    max_batch_chars: int,
    progress_callback: ProgressCallback | None = None,
    preview_callback: PreviewCallback | None = None,
) -> dict[str, str]:
    """功能：批量翻译片段并复用缓存结果。参数：segments、translator、cache、context、target_lang、glossary_text、batch_size、max_batch_chars、progress_callback。返回值：dict[str, str]。"""
    translations: dict[str, str] = {}
    for segment in segments:
        if not segment.translate:
            translations[segment.sid] = segment.text

    units = translation_units_for_segments(segments)
    pending: list[tuple[Segment, list[Segment]]] = []
    for unit, members in units:
        key = cache.key(translator.provider, translator.model, target_lang, unit.text, glossary_text)
        cached = cache.get(key)
        if cached is not None:
            cached = apply_term_guard(unit.text, normalize_translated_text(cached)).strip()
            if is_suspicious_translation(unit, cached) or is_probably_untranslated(unit, cached):
                print(f"{unit.sid}: cached translation is suspicious or untranslated; translating again.")
                pending.append((unit, members))
            else:
                translations[members[0].sid] = cached
                for member in members[1:]:
                    translations[member.sid] = ""
        else:
            pending.append((unit, members))

    if preview_callback:
        preview_callback(dict(translations))

    pending_units = [unit for unit, _members in pending]
    batches = list(batch_segments(pending_units, batch_size=batch_size, max_chars=max_batch_chars))
    members_by_sid = {unit.sid: members for unit, members in pending}
    if progress_callback:
        if batches:
            progress_callback("translate", f"待翻译 {len(pending_units)} 段，分为 {len(batches)} 个批次", 0, len(batches))
        else:
            progress_callback("translate", "全部段落命中缓存，无需调用模型", 1, 1)
    iterator = tqdm(batches, desc="Translating", unit="batch") if tqdm else batches
    for batch_index, batch in enumerate(iterator, start=1):
        if progress_callback:
            progress_callback("translate", f"正在翻译批次 {batch_index}/{len(batches)}", batch_index - 1, len(batches))
        result = translator.translate_many(batch, context=context)
        for unit in batch:
            members = members_by_sid[unit.sid]
            text = result.get(unit.sid, unit.text).strip()
            text, cacheable = guarded_translation(translator, unit, text, context)
            translations[members[0].sid] = text
            for member in members[1:]:
                translations[member.sid] = ""
            key = cache.key(translator.provider, translator.model, target_lang, unit.text, glossary_text)
            if cacheable:
                cache.set(key, text)
        cache.save()
        if preview_callback:
            preview_callback(dict(translations))
        if progress_callback:
            progress_callback("translate", f"已完成翻译批次 {batch_index}/{len(batches)}", batch_index, len(batches))
    return translations


def translation_preview_text(
    segments: list[Segment],
    translations: dict[str, str],
    max_chars: int = 24000,
) -> str:
    """Build a bounded, readable preview from translations completed so far."""
    pieces: list[str] = []
    total_chars = 0
    for segment in segments:
        if not segment.translate or segment.sid not in translations:
            continue
        text = translations.get(segment.sid, "").strip()
        if not text:
            continue
        piece = f"[Page {segment.page_index + 1} | {segment.kind}]\n{text}"
        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        pieces.append(piece[:remaining])
        total_chars += len(piece) + 2
    return "\n\n".join(pieces)

def collect_translation_quality_warnings(segments: list[Segment], translations: dict[str, str]) -> list[str]:
    """功能：汇总翻译质量告警。参数：segments、translations。返回值：list[str]。"""
    warnings: list[str] = []
    for segment in segments:
        if not segment.translate:
            continue
        translated = translations.get(segment.sid, segment.text)
        if not translated:
            continue
        if is_probably_untranslated(segment, translated):
            preview = clean_line_text(segment.text)[:90]
            warnings.append(f"{segment.sid}: possible untranslated English remains: {preview}")
    return warnings

SUMMARY_MATERIAL_MAX_CHARS = 45000


def fallback_document_summary(material: str) -> str:
    """功能：在摘要模型不可用时生成兜底摘要。参数：material。返回值：str。"""
    if not material.strip():
        return "文献核心要点概况\n\n用于生成总结的正文材料不足，无法在不杜撰的前提下形成可靠概况。"
    preview = normalize_translated_text(material)[:900]
    return (
        "文献核心要点概况\n\n"
        "当前为版式测试或总结模型不可用，系统未调用语言模型生成完整概况。"
        "为避免凭空杜撰，以下仅保留可核验的文献材料摘录：\n\n"
        f"{preview}"
    )


def build_summary_material(
    segments: list[Segment],
    translations: dict[str, str],
    max_chars: int = SUMMARY_MATERIAL_MAX_CHARS,
) -> str:
    """功能：构建文档摘要输入材料。参数：segments、translations、max_chars。返回值：str。"""
    usable_kinds = {"title", "authors", "heading", "caption", "body"}
    ordered = sorted(segments, key=lambda item: (item.page_index, item.bbox[1], item.bbox[0]))
    pieces: list[str] = []
    for segment in ordered:
        if segment.kind not in usable_kinds or segment.kind in {"reference", "metadata", "equation"}:
            continue
        text = translations.get(segment.sid, segment.text if segment.translate else "")
        text = normalize_translated_text(text)
        if not text or len(text) < 8:
            continue
        label = {
            "title": "标题",
            "authors": "作者",
            "heading": "章节",
            "caption": "图表",
            "body": "正文",
        }.get(segment.kind, segment.kind)
        pieces.append(f"[{label} p{segment.page_index + 1}] {text}")

    material = "\n".join(pieces)
    if len(material) <= max_chars:
        return material

    head = material[: int(max_chars * 0.58)]
    tail = material[-int(max_chars * 0.32) :]
    headings = "\n".join(piece for piece in pieces if piece.startswith(("[标题", "[章节", "[图表")))[: int(max_chars * 0.10)]
    return f"{head}\n\n[中间部分因长度限制压缩，以下保留标题/图表线索]\n{headings}\n\n[文末内容]\n{tail}"


def generate_document_summary(
    translator: BaseTranslator,
    segments: list[Segment],
    translations: dict[str, str],
    cache: TranslationCache,
    target_lang: str,
    glossary_text: str,
) -> tuple[str, str | None]:
    """功能：调用翻译器生成文档摘要。参数：translator、segments、translations、cache、target_lang、glossary_text。返回值：tuple[str, str | None]。"""
    material = build_summary_material(segments, translations)
    if not material.strip():
        return "", "summary skipped: no usable document material"
    cache_key = cache.key(translator.provider, translator.model, target_lang, "DOCUMENT_SUMMARY\n" + material, glossary_text)
    cached = cache.get(cache_key)
    if cached:
        return cached.strip(), None
    try:
        summary = translator.summarize_document(material).strip()
        if not summary:
            raise ValueError("empty summary")
        cache.set(cache_key, summary)
        cache.save()
        return summary, None
    except Exception as exc:  # noqa: BLE001 - provider errors vary
        return fallback_document_summary(material), f"summary fallback: {exc}"


def discover_font(user_path: str | None, bold: bool = False) -> Path:
    """功能：查找可用于 PDF 渲染的字体。参数：user_path、bold。返回值：Path。"""
    if user_path:
        path = Path(user_path)
        if path.exists():
            return path
        raise FileNotFoundError(path)

    regular_names = [
        "Deng.ttf",
        "simhei.ttf",
        "SourceHanSerifSC-Regular.otf",
        "SourceHanSansSC-Regular.otf",
        "NotoSerifCJKsc-Regular.otf",
        "NotoSansSC-VF.ttf",
        "msyh.ttc",
        "simsun.ttc",
        "PingFang.ttc",
        "STHeiti Light.ttc",
        "NotoSansCJK-Regular.ttc",
        "NotoSansCJKsc-Regular.otf",
        "NotoSerifCJK-Regular.ttc",
        "WenQuanYi Micro Hei.ttf",
    ]
    bold_names = [
        "Dengb.ttf",
        "simhei.ttf",
        "SourceHanSerifSC-Bold.otf",
        "SourceHanSansSC-Bold.otf",
        "NotoSerifCJKsc-Bold.otf",
        "msyhbd.ttc",
        "simsunb.ttf",
        "NotoSansSC-VF.ttf",
        "simsun.ttc",
        "PingFang.ttc",
        "STHeiti Medium.ttc",
        "NotoSansCJK-Bold.ttc",
        "NotoSansCJKsc-Bold.otf",
        "NotoSerifCJK-Bold.ttc",
        "WenQuanYi Micro Hei.ttf",
    ]
    search_dirs = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local" / "share" / "fonts",
    ]
    names = bold_names if bold else regular_names
    for directory in search_dirs:
        for name in names:
            path = directory / name
            if path.exists():
                return path

    broad_patterns = [
        "*SourceHanSerifSC*Bold*" if bold else "*SourceHanSerifSC*Regular*",
        "*SourceHanSansSC*Bold*" if bold else "*SourceHanSansSC*Regular*",
        "*NotoSerifCJK*Bold*" if bold else "*NotoSerifCJK*Regular*",
        "*NotoSansCJK*Bold*" if bold else "*NotoSansCJK*Regular*",
        "*NotoSansSC*",
        "*WenQuanYi*",
    ]
    for directory in search_dirs:
        if not directory.exists():
            continue
        for pattern in broad_patterns:
            matches = sorted(directory.rglob(pattern))
            if matches:
                return matches[0]
    raise FileNotFoundError("No CJK font found. Pass --font and --bold-font explicitly.")

def quantized_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """功能：将颜色量化为稳定的缓存键。参数：rgb。返回值：tuple[int, int, int]。"""
    return tuple(min(255, round(channel / 8) * 8) for channel in rgb)


def sample_background_color(pix: fitz.Pixmap, bbox: tuple[float, float, float, float], scale: float) -> tuple[float, float, float]:
    """功能：采样片段背景颜色。参数：pix、bbox、scale。返回值：tuple[float, float, float]。"""
    n = pix.n
    if n < 3:
        return (1, 1, 1)
    x0 = max(0, min(pix.width - 1, int((bbox[0] - 1.5) * scale)))
    y0 = max(0, min(pix.height - 1, int((bbox[1] - 1.5) * scale)))
    x1 = max(x0 + 1, min(pix.width, int((bbox[2] + 1.5) * scale)))
    y1 = max(y0 + 1, min(pix.height, int((bbox[3] + 1.5) * scale)))
    step = max(1, int(min(x1 - x0, y1 - y0) / 8))
    samples = pix.samples
    counts: Counter[tuple[int, int, int]] = Counter()
    for y in range(y0, y1, step):
        row = y * pix.stride
        for x in range(x0, x1, step):
            offset = row + x * n
            r, g, b = samples[offset], samples[offset + 1], samples[offset + 2]
            brightness = (r + g + b) / 3
            # Ignore dark glyph pixels; the most frequent bright color is normally the page background.
            if brightness >= 150:
                counts[quantized_color((r, g, b))] += 1
    if not counts:
        return (1, 1, 1)
    r, g, b = counts.most_common(1)[0][0]
    return (r / 255, g / 255, b / 255)


def normalize_translated_text(text: str) -> str:
    """功能：规范化译文空白和标点。参数：text。返回值：str。"""
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    cjk = r"\u3400-\u9fff"
    text = re.sub(fr"(?<=[{cjk}])\s+(?=[{cjk}])", "", text)
    text = re.sub(fr"\s+([，。！？；：、）】》〉,.!?;:%])", r"\1", text)
    text = re.sub(fr"([（【《〈])\s+", r"\1", text)
    text = re.sub(r"(?<=\d)\s*([,，−–—-])\s*(?=\d)", r"\1", text)
    text = re.sub(r"\s+(\d{1,3}(?:[,，−–—-]\d{1,3})+)", r"\1", text)
    return text


def _contains_source_term(source_text: str, term: str) -> bool:
    """功能：判断原文是否包含指定术语。参数：source_text、term。返回值：bool。"""
    if term in {"AI", "ML", "F1", "R2"}:
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", source_text))
    return term in source_text


def _replace_term_variants(text: str, canonical: str, variants: Iterable[str]) -> str:
    """功能：将术语变体替换为标准写法。参数：text、canonical、variants。返回值：str。"""
    for variant in variants:
        if not variant:
            continue
        # ASCII aliases are replaced only at token boundaries; Chinese aliases such
        # as “分类器” are replaced literally when the corresponding source term is
        # present, which prevents over-correction elsewhere.
        if all(ord(char) < 128 for char in variant):
            text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(variant)}(?![A-Za-z0-9])", canonical, text)
        else:
            text = text.replace(variant, canonical)
    return text


def _repair_llm_term(source: str, text: str) -> str:
    """功能：修复模型对固定术语的误译。参数：source、text。返回值：str。"""
    if not re.search(r"\bLLMs?\b", source):
        return text
    preferred = "LLMs" if re.search(r"\bLLMs\b", source) else "LLM"
    # The most damaging mistranslation in Chinese scientific texts is treating
    # LLM as the academic degree “法学硕士”.  Remove common parenthetical variants
    # as well as plain over-translations.
    text = re.sub(r"(?:大型语言模型|大语言模型|大型語言模型|大語言模型|法学硕士|法學碩士)(?:（\s*LLMs?\s*）|\(\s*LLMs?\s*\))?", preferred, text)
    text = re.sub(r"LLMs?\s*[（(]\s*LLMs?\s*[）)]", preferred, text)
    text = re.sub(rf"{preferred}s", preferred, text)
    return text


def apply_term_guard(source_text: str, translated_text: str) -> str:
    """Repair high-impact terminology while preserving layout-friendly text.

    The prompt asks for these terms, but API providers and cached historical
    responses can still produce terms like “法学硕士”, “代理”, or “分类器”.  This
    guard makes the renderer deterministic and keeps the output close to the
    manually accepted standard translation.
    """
    source = source_text or ""
    text = translated_text or ""

    text = _repair_llm_term(source, text)

    if re.search(r"\b[Aa]gents?\b|\bmulti-agent\b|\bagentic\b", source):
        text = re.sub(r"代理程序|代理体|代理", "智能体", text)
        text = re.sub(r"多智能体智能体", "多智能体", text)

    # Preserve known framework/module/model names exactly when the source
    # contains them.  This also fixes provider mistakes such as CatAgent -> 分类器.
    for term in PROTECTED_SOURCE_TERMS:
        if _contains_source_term(source, term):
            variants = TERM_VARIANT_REPAIRS.get(term, ())
            text = _replace_term_variants(text, term, variants)

    # Preferred wording for this class of papers.
    replacements = {
        "知识图，": "知识图谱，",
        "知识图。": "知识图谱。",
        "知识图即": "知识图谱，即",
        "知识图（": "知识图谱（",
        "信息丰富的知识图": "信息丰富的知识图谱",
        "人工管理": "手动整理",
        "人工检索": "手动整理",
        "机器学习就绪表": "机器学习就绪表格",
        "数据集建模": "数据集用于建模",
        "对二甲苯(对二甲苯)": "对二甲苯（p-xylene）",
        "大型语言模型智能体": "大语言模型智能体",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    return normalize_translated_text(text)


def ascii_words(text: str) -> list[str]:
    """功能：提取 ASCII 单词列表。参数：text。返回值：list[str]。"""
    return re.findall(r"[A-Za-z][A-Za-z0-9_+./-]*", text or "")


def cjk_char_count(text: str) -> int:
    """功能：统计中日韩字符数量。参数：text。返回值：int。"""
    return len(re.findall(r"[\u3400-\u9fff]", text or ""))


def normalized_alnum(text: str) -> str:
    """功能：保留并规范化字母数字字符。参数：text。返回值：str。"""
    return re.sub(r"[^A-Za-z0-9]+", "", text or "").lower()


def protected_ascii_word(word: str) -> bool:
    """功能：判断英文单词是否应保留原文。参数：word。返回值：bool。"""
    if word in PROTECTED_SHORT_TOKENS:
        return True
    if re.fullmatch(r"[A-Z][A-Za-z0-9_-]*(?:Agent|Graph|Hub|GPT|RAG|LLM|LLMs)?", word):
        return True
    if re.fullmatch(r"[A-Z][a-z]?[0-9]*(?:[A-Z][a-z]?[0-9]*)*", word):
        # Chemical formula-like tokens such as SiO2, Al2O3, PET.
        return True
    return False


def is_probably_untranslated(segment: Segment, translation: str) -> bool:
    """Detect English prose that came back essentially untranslated.

    This is intentionally conservative: it only fires for body-like scientific
    prose with very little Chinese or with near-identical alphanumeric content.
    Protected names, formulas, and references are allowed to stay English.
    """
    if segment.kind in {"metadata", "reference", "equation"}:
        return False
    source_words = ascii_words(segment.text)
    if len(source_words) < 6:
        return False
    target = translation or ""
    target_cjk = cjk_char_count(target)
    target_words = [w for w in ascii_words(target) if not protected_ascii_word(w)]
    if target_cjk < 4 and len(target_words) >= 5:
        return True
    source_norm = normalized_alnum(segment.text)
    target_norm = normalized_alnum(target)
    if len(source_norm) >= 60 and source_norm == target_norm:
        return True
    if len(source_norm) >= 80 and target_cjk < 10:
        overlap = 0
        for word in set(w.lower() for w in source_words if len(w) >= 5 and not protected_ascii_word(w)):
            if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", target.lower()):
                overlap += 1
        if overlap >= max(6, len(set(source_words)) * 0.35):
            return True
    return False


BODY_FIRST_LINE_INDENT = "　　"
CITATION_RUN_PATTERN = re.compile(r"(?<!\d)\d{1,3}(?:[,，−–—-]\d{1,3})*(?!\d)")
CITATION_TOKEN_PATTERN = re.compile(r"\d{1,3}(?:[,，−–—-]\d{1,3})*")
CITATION_UNITS = set("倍年月日页段次个种项类篇点分秒%％")


def is_standalone_citation_token(token: str) -> bool:
    """功能：判断标记是否为独立引用编号。参数：token。返回值：bool。"""
    return bool(CITATION_TOKEN_PATTERN.fullmatch(token.strip()))


def _is_ascii_letter(char: str) -> bool:
    """功能：判断字符是否为 ASCII 字母。参数：char。返回值：bool。"""
    return len(char) == 1 and char.isascii() and char.isalpha()


def _is_ascii_alnum(char: str) -> bool:
    """功能：判断字符是否为 ASCII 字母或数字。参数：char。返回值：bool。"""
    return len(char) == 1 and char.isascii() and char.isalnum()


def is_likely_citation_run(text: str, start: int, end: int) -> bool:
    """功能：判断文本区间是否像连续引用编号。参数：text、start、end。返回值：bool。"""
    run = text[start:end]
    prev = text[start - 1] if start > 0 else ""
    prev_prev = text[start - 2] if start > 1 else ""
    next_char = text[end] if end < len(text) else ""
    next_next = text[end + 1] if end + 1 < len(text) else ""
    prev_nonspace = ""
    for index in range(start - 1, -1, -1):
        if not text[index].isspace():
            prev_nonspace = text[index]
            break
    next_nonspace = ""
    for index in range(end, len(text)):
        if not text[index].isspace():
            next_nonspace = text[index]
            break
    has_separator = bool(re.search(r"[,，−–—-]", run))

    if next_nonspace in CITATION_UNITS or _is_ascii_alnum(next_char):
        return False
    if next_char == "." and next_next.isdigit():
        return False
    if prev == "." and prev_prev.isdigit():
        return False
    if has_separator:
        return True
    if _is_ascii_letter(prev) and len(run) == 1:
        return False
    if prev.isspace() and len(run) >= 2:
        return bool(prev_nonspace and prev_nonspace not in "=+-/")
    if prev in ".,，。；;、)]）】" or _is_ascii_letter(prev):
        return True
    return False


def split_citation_runs(text: str) -> list[tuple[str, bool]]:
    """功能：拆分正文和连续引用编号。参数：text。返回值：list[tuple[str, bool]]。"""
    runs: list[tuple[str, bool]] = []
    cursor = 0
    for match in CITATION_RUN_PATTERN.finditer(text):
        start, end = match.span()
        if not is_likely_citation_run(text, start, end):
            continue
        if start > cursor:
            runs.append((text[cursor:start], False))
        runs.append((re.sub(r"[−–—]", "-", text[start:end]), True))
        cursor = end
    if cursor < len(text):
        runs.append((text[cursor:], False))
    return runs


ACADEMIC_INLINE_LABELS = {
    "abstract": "摘要：",
    "keywords": "关键词：",
}


def academic_inline_label_for(segment: Segment, text: str) -> str | None:
    """Return the bold-only leading label for abstract/keywords lines.

    ACS-style abstracts often extract as one segment that contains both the
    label (``ABSTRACT:``) and the first words of the paragraph.  Treating the
    whole segment as a heading made the beginning of the abstract bold and
    visually disconnected from the following paragraph.  Only the Chinese
    label should be bold; the text after the colon must use normal body weight.
    """
    source = clean_line_text(segment.text).lower()
    rendered = clean_line_text(text).lower()
    if source.startswith("abstract") or rendered.startswith(("摘要", "abstract")):
        return ACADEMIC_INLINE_LABELS["abstract"]
    if source.startswith("keywords") or rendered.startswith(("关键词", "keywords")):
        return ACADEMIC_INLINE_LABELS["keywords"]
    return None


def normalize_academic_inline_label_text(segment: Segment, text: str) -> tuple[str, str | None]:
    """功能：规范化学术段落中的行内标签。参数：segment、text。返回值：tuple[str, str | None]。"""
    label = academic_inline_label_for(segment, text)
    if not label:
        return text, None
    if label == ACADEMIC_INLINE_LABELS["abstract"]:
        text = re.sub(r"^\s*(?:摘要|ABSTRACT|Abstract)\s*[:：]?\s*", label, text, count=1)
    elif label == ACADEMIC_INLINE_LABELS["keywords"]:
        text = re.sub(r"^\s*(?:关键词|KEYWORDS|Keywords)\s*[:：]?\s*", label, text, count=1)
    # Keep the label attached to the following content; do not leave a visual gap
    # after the colon.
    text = re.sub(rf"^{re.escape(label)}\s+", label, text)
    return text, label


def draw_labelled_first_line_pymupdf(
    page: fitz.Page,
    x: float,
    baseline_y: float,
    text: str,
    label: str | None,
    regular_font_path: Path,
    bold_font_path: Path,
    regular_font: fitz.Font,
    bold_font: fitz.Font,
    font_size: float,
    color: tuple[float, float, float],
) -> None:
    """功能：用 PyMuPDF 绘制带标签的首行。参数：page、x、baseline_y、text、label、regular_font_path、bold_font_path、regular_font、bold_font、font_size、color。返回值：None。"""
    if not label or not text.startswith(label):
        draw_rich_line_pymupdf(page, x, baseline_y, text, regular_font_path, regular_font, font_size, color)
        return
    page.insert_text(
        (x, baseline_y),
        label,
        fontfile=str(bold_font_path),
        fontsize=font_size,
        color=color,
        overlay=True,
    )
    cursor = x + bold_font.text_length(label, fontsize=font_size)
    draw_rich_line_pymupdf(
        page,
        cursor,
        baseline_y,
        text[len(label):],
        regular_font_path,
        regular_font,
        font_size,
        color,
    )


def draw_labelled_first_line_reportlab(
    canvas,
    x: float,
    y: float,
    text: str,
    label: str | None,
    regular_font_name: str,
    bold_font_name: str,
    regular_meter: ReportLabTextMeter,
    bold_meter: ReportLabTextMeter,
    font_size: float,
) -> None:
    """功能：用 ReportLab 绘制带标签的首行。参数：canvas、x、y、text、label、regular_font_name、bold_font_name、regular_meter、bold_meter、font_size。返回值：None。"""
    if not label or not text.startswith(label):
        draw_rich_line_reportlab(canvas, x, y, text, regular_font_name, regular_meter, font_size)
        return
    canvas.setFont(bold_font_name, font_size)
    canvas.drawString(x, y, label)
    cursor = x + bold_meter.text_length(label, font_size)
    draw_rich_line_reportlab(
        canvas,
        cursor,
        y,
        text[len(label):],
        regular_font_name,
        regular_meter,
        font_size,
    )


def should_indent_first_line(segment: Segment, text: str) -> bool:
    """功能：判断段落首行是否需要缩进。参数：segment、text。返回值：bool。"""
    if segment.kind != "body" or not segment.translate:
        return False
    stripped = text.strip()
    if len(stripped) < 45:
        return False
    metadata_starts = ("©", "收到日期", "修订", "接收", "出版", "Received", "Revised", "Accepted", "Published")
    return not stripped.startswith(metadata_starts)


TOKEN_PATTERN = re.compile(
    r"[A-Za-z0-9Α-Ωα-ω][A-Za-z0-9Α-Ωα-ω_\-−–—/+.,:%=<>()[\]{}^]*"
    r"|\s+|[\u3400-\u9fff]|[^\s]"
)


def is_space(token: str) -> bool:
    """功能：判断标记是否为空白。参数：token。返回值：bool。"""
    return token.isspace()


def is_cjk(token: str) -> bool:
    """功能：判断标记是否为中日韩字符。参数：token。返回值：bool。"""
    return len(token) == 1 and "\u3400" <= token <= "\u9fff"


def is_closing_punct(token: str) -> bool:
    """功能：判断标记是否为闭合标点。参数：token。返回值：bool。"""
    return token in "，。！？；：、,.!?;:%)]}）】》〉"


def append_token(current: str, token: str) -> str:
    """功能：按排版规则向当前行追加标记。参数：current、token。返回值：str。"""
    if is_space(token):
        return current if not current or current.endswith(" ") else current + " "
    if not current:
        return token.strip()
    if is_closing_punct(token):
        return current.rstrip() + token
    if current.endswith(" "):
        return current + token
    if is_cjk(token) or is_cjk(current[-1]):
        return current + token
    return current + token


def split_long_token(token: str, width: float, font: fitz.Font, font_size: float) -> list[str]:
    """功能：拆分超出行宽的长标记。参数：token、width、font、font_size。返回值：list[str]。"""
    parts: list[str] = []
    current = ""
    for char in token:
        candidate = current + char
        if current and font.text_length(candidate, fontsize=font_size) > width:
            parts.append(current)
            current = char
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def wrap_text_for_widths(
    text: str,
    widths: list[float],
    font: fitz.Font,
    font_size: float,
) -> tuple[list[str], bool]:
    """功能：按每行可用宽度折行文本。参数：text、widths、font、font_size。返回值：tuple[list[str], bool]。"""
    tokens = TOKEN_PATTERN.findall(normalize_translated_text(text))
    lines: list[str] = []
    current = ""
    line_index = 0
    for token in tokens:
        if line_index >= len(widths):
            return lines, True
        candidate = append_token(current, token)
        width = widths[line_index] * 0.98
        if not candidate.strip():
            current = candidate
            continue
        if font.text_length(candidate.strip(), fontsize=font_size) <= width:
            current = candidate
            continue
        if current.strip() and is_standalone_citation_token(token.strip()):
            current = candidate
            continue
        if current.strip():
            lines.append(current.strip())
            line_index += 1
            current = "" if is_space(token) else token.strip()
            if line_index >= len(widths):
                return lines, bool(current)
            if font.text_length(current, fontsize=font_size) > widths[line_index] * 0.98:
                split_parts = split_long_token(current, widths[line_index] * 0.98, font, font_size)
                for part in split_parts[:-1]:
                    if line_index >= len(widths):
                        return lines, True
                    lines.append(part)
                    line_index += 1
                current = split_parts[-1] if split_parts else ""
        else:
            split_parts = split_long_token(token.strip(), width, font, font_size)
            for part in split_parts[:-1]:
                lines.append(part)
                line_index += 1
                if line_index >= len(widths):
                    return lines, True
            current = split_parts[-1] if split_parts else ""
    if current.strip():
        if line_index >= len(widths):
            return lines, True
        lines.append(current.strip())
    return lines, False


def target_font_size(segment: Segment) -> float:
    """功能：计算片段渲染目标字号。参数：segment。返回值：float。"""
    size = segment.font_size
    if segment.kind == "title":
        return min(18.0, max(14.0, size))
    if segment.kind == "heading":
        return min(12.5, max(9.5, size * 1.02))
    if segment.kind == "caption":
        return min(9.2, max(7.5, size * 0.95))
    if segment.kind == "metadata":
        return min(8.5, max(5.5, size * 0.9))
    return min(10.5, max(7.5, size * 0.96))


def minimum_readable_font_size(segment: Segment, base_size: float) -> float:
    """Lower bound used while fitting translated text into source line slots.

    The previous renderer allowed every segment to shrink by up to 4.2 pt.
    For normal 10 pt body text that means ~5.8 pt, which is visibly smaller
    than the surrounding paragraph.  When a model over-translates a page/column
    fragment, the renderer should truncate with a warning instead of producing
    unreadably tiny body text.
    """
    if segment.kind == "body":
        return min(base_size, max(8.2, base_size - 1.6))
    if segment.kind == "caption":
        return min(base_size, max(6.8, base_size - 1.8))
    if segment.kind == "metadata":
        return min(base_size, max(5.4, base_size - 2.0))
    return min(base_size, max(7.2, base_size - 2.2))


def paint_line_backgrounds(
    page: fitz.Page,
    segment: Segment,
    background_pix: fitz.Pixmap,
    scale: float,
    padding_x: float,
    padding_y: float,
) -> None:
    """功能：用 PyMuPDF 覆盖原文行背景。参数：page、segment、background_pix、scale、padding_x、padding_y。返回值：None。"""
    for line in segment.lines:
        color = sample_background_color(background_pix, line.bbox, scale)
        rect = fitz.Rect(line.bbox)
        rect.x0 -= padding_x
        rect.x1 += padding_x
        rect.y0 -= padding_y
        rect.y1 += padding_y
        page.draw_rect(rect, color=color, fill=color, width=0, overlay=True)


def draw_rich_line_pymupdf(
    page: fitz.Page,
    x: float,
    baseline_y: float,
    text: str,
    font_path: Path,
    meter: fitz.Font,
    font_size: float,
    color: tuple[float, float, float],
) -> None:
    """功能：用 PyMuPDF 绘制富文本行。参数：page、x、baseline_y、text、font_path、meter、font_size、color。返回值：None。"""
    cursor = x
    for run, is_citation in split_citation_runs(text):
        if not run:
            continue
        run_size = font_size * 0.68 if is_citation else font_size
        run_y = baseline_y - font_size * 0.34 if is_citation else baseline_y
        page.insert_text(
            (cursor, run_y),
            run,
            fontfile=str(font_path),
            fontsize=run_size,
            color=color,
            overlay=True,
        )
        cursor += meter.text_length(run, fontsize=run_size)


def render_segment_text(
    page: fitz.Page,
    segment: Segment,
    text: str,
    font_path: Path,
    bold_font_path: Path,
    warnings: list[str],
) -> None:
    """功能：用 PyMuPDF 渲染翻译片段。参数：page、segment、text、font_path、bold_font_path、warnings。返回值：None。"""
    render_text = normalize_translated_text(text)
    render_text, inline_label = normalize_academic_inline_label_text(segment, render_text)
    use_font_path = font_path if inline_label else (bold_font_path if segment.bold else font_path)
    font = fitz.Font(fontfile=str(use_font_path))
    bold_font = fitz.Font(fontfile=str(bold_font_path))
    base_size = target_font_size(segment)
    min_size = minimum_readable_font_size(segment, base_size)
    render_lines = list(segment.lines)
    has_section_marker = segment.text.strip().startswith("■") or render_text.startswith("■")
    if has_section_marker and render_lines:
        first = render_lines[0]
        square_size = min(base_size * 0.68, max(4.0, first.height * 0.72))
        top = first.bbox[1] + max(0.0, (first.height - square_size) / 2)
        square = fitz.Rect(first.bbox[0], top, first.bbox[0] + square_size, top + square_size)
        page.draw_rect(square, color=segment.color, fill=segment.color, width=0, overlay=True)
        shift = square_size + 3.0
        render_lines[0] = replace(
            first,
            bbox=(first.bbox[0] + shift, first.bbox[1], first.bbox[2], first.bbox[3]),
        )
        render_text = render_text.lstrip("■").strip()

    base_widths = [max(8.0, line.width + 3.0) for line in render_lines]
    indent_first_line = should_indent_first_line(segment, render_text)
    font_size = base_size
    rendered_lines: list[str] = []
    overflow = True
    while font_size >= min_size:
        widths = list(base_widths)
        if indent_first_line and widths:
            widths[0] = max(8.0, widths[0] - font.text_length(BODY_FIRST_LINE_INDENT, fontsize=font_size))
        rendered_lines, overflow = wrap_text_for_widths(render_text, widths, font, font_size)
        if not overflow and len(rendered_lines) <= len(render_lines):
            break
        font_size -= 0.35

    if overflow or len(rendered_lines) > len(render_lines):
        warnings.append(
            f"{segment.sid}: translation overflow; rendered first {len(render_lines)} lines at {font_size:.1f} pt."
        )
        rendered_lines = rendered_lines[: len(render_lines)]

    indent_width = font.text_length(BODY_FIRST_LINE_INDENT, fontsize=font_size) if indent_first_line else 0.0
    for line_index, (line_slot, line_text) in enumerate(zip(render_lines, rendered_lines)):
        if line_slot.height > font_size * 1.8:
            baseline_y = line_slot.bbox[1] + font_size * 1.05
        else:
            baseline_y = line_slot.bbox[3] - max(0.4, font_size * 0.08)
        draw_x = line_slot.bbox[0] - 0.2 + (indent_width if line_index == 0 else 0.0)
        if line_index == 0 and inline_label:
            draw_labelled_first_line_pymupdf(
                page,
                draw_x,
                baseline_y,
                line_text,
                inline_label,
                font_path,
                bold_font_path,
                font,
                bold_font,
                font_size,
                (0.0, 0.0, 0.0),
            )
        else:
            draw_rich_line_pymupdf(
                page,
                draw_x,
                baseline_y,
                line_text,
                use_font_path,
                font,
                font_size,
                segment.color,
            )


class ReportLabTextMeter:
    """功能：封装 ReportLab 字体宽度计算。参数：无。返回值：无。"""
    def __init__(self, font_name: str) -> None:
        """功能：初始化对象状态。参数：font_name。返回值：无。"""
        from reportlab.pdfbase import pdfmetrics

        self.font_name = font_name
        self.pdfmetrics = pdfmetrics

    def text_length(self, text: str, fontsize: float) -> float:
        """功能：测量指定字号下的文本宽度。参数：text、fontsize。返回值：float。"""
        return self.pdfmetrics.stringWidth(text, self.font_name, fontsize)


def register_reportlab_fonts(font_path: Path, bold_font_path: Path) -> tuple[str, str]:
    """功能：注册 ReportLab 渲染字体。参数：font_path、bold_font_path。返回值：tuple[str, str]。"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    # STSong-Light is a built-in Simplified Chinese CID font and is a safe
    # fallback when Windows .ttc collections cannot be registered by ReportLab.
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass

    def register_ttf(name: str, path: Path, fallback: str) -> str:
        """功能：注册字体文件，并在失败时使用兜底字体。参数：name、path、fallback。返回值：str。"""
        if path.suffix.lower() != ".ttf":
            return fallback
        try:
            pdfmetrics.registerFont(TTFont(name, str(path)))
            return name
        except Exception:
            return fallback

    regular_name = register_ttf("CJKRegular", font_path, "STSong-Light")
    bold_name = register_ttf("CJKBold", bold_font_path, regular_name)
    return regular_name, bold_name


def set_reportlab_color(canvas, color: tuple[float, float, float]) -> None:
    """功能：设置 ReportLab 画布颜色。参数：canvas、color。返回值：None。"""
    canvas.setFillColorRGB(
        max(0.0, min(1.0, color[0])),
        max(0.0, min(1.0, color[1])),
        max(0.0, min(1.0, color[2])),
    )


def paint_line_backgrounds_reportlab(
    canvas,
    page_height: float,
    segment: Segment,
    background_pix: fitz.Pixmap,
    scale: float,
    padding_x: float,
    padding_y: float,
) -> None:
    """功能：用 ReportLab 覆盖原文行背景。参数：canvas、page_height、segment、background_pix、scale、padding_x、padding_y。返回值：None。"""
    for line in segment.lines:
        color = sample_background_color(background_pix, line.bbox, scale)
        set_reportlab_color(canvas, color)
        x0, y0, x1, y1 = line.bbox
        x0 -= padding_x
        x1 += padding_x
        y0 -= padding_y
        y1 += padding_y
        canvas.rect(x0, page_height - y1, x1 - x0, y1 - y0, stroke=0, fill=1)


def draw_rich_line_reportlab(
    canvas,
    x: float,
    y: float,
    text: str,
    font_name: str,
    meter: ReportLabTextMeter,
    font_size: float,
) -> None:
    """功能：用 ReportLab 绘制富文本行。参数：canvas、x、y、text、font_name、meter、font_size。返回值：None。"""
    cursor = x
    for run, is_citation in split_citation_runs(text):
        if not run:
            continue
        run_size = font_size * 0.68 if is_citation else font_size
        run_y = y + font_size * 0.34 if is_citation else y
        canvas.setFont(font_name, run_size)
        canvas.drawString(cursor, run_y, run)
        cursor += meter.text_length(run, run_size)
    canvas.setFont(font_name, font_size)


def render_segment_text_reportlab(
    canvas,
    page_height: float,
    segment: Segment,
    text: str,
    regular_font_name: str,
    bold_font_name: str,
    regular_meter: ReportLabTextMeter,
    bold_meter: ReportLabTextMeter,
    warnings: list[str],
    allowed_bottom: float,
) -> None:
    """功能：用 ReportLab 渲染翻译片段。参数：canvas、page_height、segment、text、regular_font_name、bold_font_name、regular_meter、bold_meter、warnings、allowed_bottom。返回值：None。"""
    render_text = normalize_translated_text(text)
    render_text, inline_label = normalize_academic_inline_label_text(segment, render_text)
    use_font_name = regular_font_name if inline_label else (bold_font_name if segment.bold else regular_font_name)
    meter = regular_meter if inline_label else (bold_meter if segment.bold else regular_meter)
    base_size = target_font_size(segment)
    min_size = minimum_readable_font_size(segment, base_size)
    render_lines = extend_lines_to_bottom(segment, allowed_bottom)
    has_section_marker = segment.text.strip().startswith("■") or render_text.startswith("■")
    set_reportlab_color(canvas, segment.color)
    if has_section_marker and render_lines:
        first = render_lines[0]
        square_size = min(base_size * 0.68, max(4.0, first.height * 0.72))
        top = first.bbox[1] + max(0.0, (first.height - square_size) / 2)
        canvas.rect(first.bbox[0], page_height - top - square_size, square_size, square_size, stroke=0, fill=1)
        shift = square_size + 3.0
        render_lines[0] = replace(
            first,
            bbox=(first.bbox[0] + shift, first.bbox[1], first.bbox[2], first.bbox[3]),
        )
        render_text = render_text.lstrip("■").strip()

    base_widths = [max(8.0, line.width + 3.0) for line in render_lines]
    indent_first_line = should_indent_first_line(segment, render_text)
    font_size = base_size
    rendered_lines: list[str] = []
    overflow = True
    while font_size >= min_size:
        widths = list(base_widths)
        if indent_first_line and widths:
            widths[0] = max(8.0, widths[0] - meter.text_length(BODY_FIRST_LINE_INDENT, font_size))
        rendered_lines, overflow = wrap_text_for_widths(render_text, widths, meter, font_size)
        if not overflow and len(rendered_lines) <= len(render_lines):
            break
        font_size -= 0.35

    if overflow or len(rendered_lines) > len(render_lines):
        warnings.append(
            f"{segment.sid}: translation overflow; rendered first {len(render_lines)} lines at {font_size:.1f} pt."
        )
        rendered_lines = rendered_lines[: len(render_lines)]

    canvas.setFont(use_font_name, font_size)
    set_reportlab_color(canvas, segment.color)
    indent_width = meter.text_length(BODY_FIRST_LINE_INDENT, font_size) if indent_first_line else 0.0
    for line_index, (line_slot, line_text) in enumerate(zip(render_lines, rendered_lines)):
        if line_slot.height > font_size * 1.8:
            baseline_y = line_slot.bbox[1] + font_size * 1.05
        else:
            baseline_y = line_slot.bbox[3] - max(0.4, font_size * 0.08)
        draw_x = line_slot.bbox[0] - 0.2 + (indent_width if line_index == 0 else 0.0)
        draw_y = page_height - baseline_y
        if line_index == 0 and inline_label:
            set_reportlab_color(canvas, (0.0, 0.0, 0.0))
            draw_labelled_first_line_reportlab(
                canvas,
                draw_x,
                draw_y,
                line_text,
                inline_label,
                regular_font_name,
                bold_font_name,
                regular_meter,
                bold_meter,
                font_size,
            )
        else:
            draw_rich_line_reportlab(
                canvas,
                draw_x,
                draw_y,
                line_text,
                use_font_name,
                meter,
                font_size,
            )


def horizontal_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """功能：计算两个边界框的水平重叠长度。参数：a、b。返回值：float。"""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))


def starts_with_paragraph_indent(segment: Segment) -> bool:
    """功能：判断片段是否带段首缩进。参数：segment。返回值：bool。"""
    if not segment.lines:
        return False
    first_x = segment.lines[0].bbox[0]
    left_x = min(line.bbox[0] for line in segment.lines)
    return first_x - left_x >= max(5.5, segment.font_size * 0.65)


def same_text_column(previous: Segment, current: Segment) -> bool:
    """功能：判断相邻片段是否属于同一文本列。参数：previous、current。返回值：bool。"""
    overlap = horizontal_overlap(previous.bbox, current.bbox)
    min_width = max(1.0, min(previous.bbox[2] - previous.bbox[0], current.bbox[2] - current.bbox[0]))
    return overlap / min_width >= 0.45


def should_merge_render_segments(previous: Segment, current: Segment) -> bool:
    """功能：判断渲染阶段是否应合并相邻片段。参数：previous、current。返回值：bool。"""
    if previous.page_index != current.page_index:
        return False
    if not previous.translate or not current.translate:
        return False

    gap = current.bbox[1] - previous.bbox[3]
    previous_width = previous.bbox[2] - previous.bbox[0]
    close_vertical_gap = -2.0 <= gap <= max(4.0, previous.font_size * 0.8)

    # Publisher title pages often extract "ABSTRACT ..." or "KEYWORDS ..."
    # as a short heading line followed by body-line fragments.  Treat the
    # labelled heading and its following line as one translation/rendering unit
    # so the model receives a complete sentence instead of a mid-word fragment.
    if previous.kind == "heading" and current.kind == "body":
        if academic_inline_label_for(previous, previous.text) and same_text_column(previous, current) and close_vertical_gap:
            return not sentence_ended(previous.text)
        return False

    if previous.kind != "body" or current.kind != "body":
        return False

    current_indented = starts_with_paragraph_indent(current)
    previous_is_bullet = bool(re.match(r"^\s*[•●▪‣-]\s*", previous.text))
    current_is_bullet = bool(re.match(r"^\s*[•●▪‣-]\s*", current.text))
    if current_is_bullet and sentence_ended(previous.text):
        return False
    likely_wrapped_continuation = not sentence_ended(previous.text) and (current.bbox[0] - previous.bbox[0]) < max(36.0, previous_width * 0.45)
    if current_indented and not (previous_is_bullet or likely_wrapped_continuation):
        return False

    if same_text_column(previous, current):
        return close_vertical_gap and not (sentence_ended(previous.text) and current.bbox[0] <= previous.bbox[0] + 2.0)

    jumps_to_next_column = current.bbox[0] > previous.bbox[0] + previous_width * 0.72 and current.bbox[1] < previous.bbox[1]
    if jumps_to_next_column:
        return not sentence_ended(previous.text)
    return False

def grouped_render_segments(page_segments: list[Segment]) -> list[list[Segment]]:
    """功能：按渲染合并规则整理片段。参数：page_segments。返回值：list[list[Segment]]。"""
    groups: list[list[Segment]] = []
    group: list[Segment] = []
    for segment in page_segments:
        if group and should_merge_render_segments(group[-1], segment):
            group.append(segment)
        else:
            if group:
                groups.append(group)
            group = [segment]
    if group:
        groups.append(group)
    return groups


def merged_render_units(page_segments: list[Segment], translations: dict[str, str]) -> list[tuple[Segment, str]]:
    """功能：构建合并后的渲染单元。参数：page_segments、translations。返回值：list[tuple[Segment, str]]。"""
    units: list[tuple[Segment, str]] = []
    for group in grouped_render_segments(page_segments):
        first = group[0]
        if len(group) == 1:
            units.append((first, translations.get(first.sid, first.text)))
            continue
        merged_lines = [line for segment in group for line in segment.lines]
        merged = replace(
            first,
            text=join_extracted_lines(merged_lines),
            lines=merged_lines,
        )
        first_translation = translations.get(first.sid)
        continuation_values = [translations.get(segment.sid) for segment in group[1:]]
        if first_translation is not None and all(value in (None, "") for value in continuation_values):
            merged_text = first_translation
        else:
            merged_text = " ".join(
                translations.get(segment.sid, segment.text)
                for segment in group
                if translations.get(segment.sid, segment.text)
            )
        units.append((merged, merged_text))
    return units

def normalized_bbox_tuple(bbox: tuple[float, float, float, float] | fitz.Rect) -> tuple[float, float, float, float]:
    """功能：将边界框转换为标准元组。参数：bbox。返回值：tuple[float, float, float, float]。"""
    rect = fitz.Rect(bbox)
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


def image_obstacle_bboxes(page: fitz.Page) -> list[tuple[float, float, float, float]]:
    """功能：提取页面图片占用区域。参数：page。返回值：list[tuple[float, float, float, float]]。"""
    obstacles: list[tuple[float, float, float, float]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") == 0:
            continue
        bbox = block.get("bbox")
        if not bbox:
            continue
        rect = fitz.Rect(bbox)
        if rect.width < 8 or rect.height < 8:
            continue
        obstacles.append((rect.x0, rect.y0, rect.x1, rect.y1))
    return obstacles


def build_allowed_bottoms(
    segments_by_page: dict[int, list[Segment]],
    page_height: float,
    external_obstacles_by_page: dict[int, list[tuple[float, float, float, float]]] | None = None,
) -> dict[str, float]:
    """功能：计算各片段可向下延展的排版边界。参数：segments_by_page、page_height、external_obstacles_by_page。返回值：dict[str, float]。"""
    allowed: dict[str, float] = {}
    page_floor = page_height - 45
    external_obstacles_by_page = external_obstacles_by_page or {}
    for page_index, page_segments in segments_by_page.items():
        ordered = sorted(page_segments, key=lambda item: (item.bbox[1], item.bbox[0]))
        external_obstacles = [normalized_bbox_tuple(item) for item in external_obstacles_by_page.get(page_index, [])]
        for segment in ordered:
            bottom = page_floor
            bbox = segment.bbox
            obstacle_bboxes = [other.bbox for other in ordered if other.sid != segment.sid]
            obstacle_bboxes.extend(external_obstacles)
            for other_bbox in obstacle_bboxes:
                if other_bbox[1] <= bbox[3] + 1:
                    continue
                min_width = max(1.0, min(bbox[2] - bbox[0], other_bbox[2] - other_bbox[0]))
                if horizontal_overlap(bbox, other_bbox) > min_width * 0.25:
                    bottom = min(bottom, other_bbox[1] - 3)
            allowed[segment.sid] = max(bbox[3], bottom)
    return allowed

def extend_lines_to_bottom(segment: Segment, allowed_bottom: float) -> list[LineSlot]:
    """功能：按可用边界扩展片段行框。参数：segment、allowed_bottom。返回值：list[LineSlot]。"""
    lines = list(segment.lines)
    if segment.kind not in {"body", "caption"} or not lines:
        return lines
    if any(lines[index + 1].bbox[1] < lines[index].bbox[1] for index in range(len(lines) - 1)):
        return lines
    heights = [line.height for line in lines if line.height > 0]
    line_height = sum(heights) / len(heights) if heights else max(8.0, segment.font_size * 1.2)
    steps = [
        lines[index + 1].bbox[1] - lines[index].bbox[1]
        for index in range(len(lines) - 1)
        if lines[index + 1].bbox[1] > lines[index].bbox[1]
    ]
    line_step = sum(steps) / len(steps) if steps else max(line_height * 1.18, segment.font_size * 1.18)

    # Let translated Chinese use the safe blank space until the next segment,
    # instead of being forced to the exact number of English source lines.
    max_extra = 24
    while max_extra > 0:
        last = lines[-1]
        y0 = last.bbox[1] + line_step
        y1 = y0 + line_height
        if y1 > allowed_bottom:
            break
        lines.append(
            replace(
                last,
                bbox=(last.bbox[0], y0, last.bbox[2], y1),
            )
        )
        max_extra -= 1
    return lines


def render_translated_pdf_reportlab(
    input_pdf: Path,
    output_pdf: Path,
    segments: list[Segment],
    translations: dict[str, str],
    font_path: Path,
    bold_font_path: Path,
    render_scale: float,
    whiteout_padding_x: float,
    whiteout_padding_y: float,
    max_pages: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    """功能：使用 ReportLab 重建翻译版式 PDF。参数：input_pdf、output_pdf、segments、translations、font_path、bold_font_path、render_scale、whiteout_padding_x、whiteout_padding_y、max_pages、progress_callback。返回值：list[str]。"""
    from io import BytesIO

    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    source_doc = fitz.open(input_pdf)
    warnings: list[str] = []
    segments_by_page: dict[int, list[Segment]] = {}
    nontranslated_obstacles_by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for segment in segments:
        if segment.translate:
            segments_by_page.setdefault(segment.page_index, []).append(segment)
        else:
            nontranslated_obstacles_by_page.setdefault(segment.page_index, []).append(segment.bbox)

    regular_font_name, bold_font_name = register_reportlab_fonts(font_path, bold_font_path)
    regular_meter = ReportLabTextMeter(regular_font_name)
    bold_meter = ReportLabTextMeter(bold_font_name)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf_canvas = canvas.Canvas(str(output_pdf))
    page_count = min(len(source_doc), max_pages) if max_pages else len(source_doc)
    if progress_callback:
        progress_callback("render", f"准备渲染 {page_count} 页", 0, max(1, page_count))
    page_iter = range(page_count)
    iterator = tqdm(page_iter, desc="Rendering", unit="page") if tqdm else page_iter
    for page_index in iterator:
        source_page = source_doc[page_index]
        page_obstacles = list(nontranslated_obstacles_by_page.get(page_index, []))
        page_obstacles.extend(image_obstacle_bboxes(source_page))
        page_width = source_page.rect.width
        page_height = source_page.rect.height
        render_units = merged_render_units(segments_by_page.get(page_index, []), translations)
        render_segments = [segment for segment, _text in render_units]
        allowed_bottoms = build_allowed_bottoms({page_index: render_segments}, page_height, {page_index: page_obstacles})
        pdf_canvas.setPageSize((page_width, page_height))
        matrix = fitz.Matrix(render_scale, render_scale)
        pix = source_page.get_pixmap(matrix=matrix, alpha=False)
        image = ImageReader(BytesIO(pix.tobytes("png")))
        pdf_canvas.drawImage(image, 0, 0, width=page_width, height=page_height, mask=None)
        for segment, render_text in render_units:
            paint_line_backgrounds_reportlab(
                pdf_canvas,
                page_height,
                segment,
                pix,
                render_scale,
                padding_x=whiteout_padding_x,
                padding_y=whiteout_padding_y,
            )
            render_segment_text_reportlab(
                pdf_canvas,
                page_height,
                segment,
                render_text,
                regular_font_name,
                bold_font_name,
                regular_meter,
                bold_meter,
                warnings,
                allowed_bottoms.get(segment.sid, segment.bbox[3]),
            )
        pdf_canvas.showPage()
        if progress_callback:
            progress_callback("render", f"已渲染页面 {page_index + 1}/{page_count}", page_index + 1, max(1, page_count))

    pdf_canvas.save()
    source_doc.close()
    return warnings


def render_translated_pdf_pymupdf(
    input_pdf: Path,
    output_pdf: Path,
    segments: list[Segment],
    translations: dict[str, str],
    font_path: Path,
    bold_font_path: Path,
    render_scale: float,
    whiteout_padding_x: float,
    whiteout_padding_y: float,
    max_pages: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    """功能：使用 PyMuPDF 重建翻译版式 PDF。参数：input_pdf、output_pdf、segments、translations、font_path、bold_font_path、render_scale、whiteout_padding_x、whiteout_padding_y、max_pages、progress_callback。返回值：list[str]。"""
    source_doc = fitz.open(input_pdf)
    output_doc = fitz.open()
    warnings: list[str] = []
    segments_by_page: dict[int, list[Segment]] = {}
    nontranslated_obstacles_by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for segment in segments:
        if segment.translate:
            segments_by_page.setdefault(segment.page_index, []).append(segment)
        else:
            nontranslated_obstacles_by_page.setdefault(segment.page_index, []).append(segment.bbox)

    page_count = min(len(source_doc), max_pages) if max_pages else len(source_doc)
    if progress_callback:
        progress_callback("render", f"准备渲染 {page_count} 页", 0, max(1, page_count))
    page_iter = range(page_count)
    iterator = tqdm(page_iter, desc="Rendering", unit="page") if tqdm else page_iter
    for page_index in iterator:
        source_page = source_doc[page_index]
        page_obstacles = list(nontranslated_obstacles_by_page.get(page_index, []))
        page_obstacles.extend(image_obstacle_bboxes(source_page))
        page = output_doc.new_page(width=source_page.rect.width, height=source_page.rect.height)
        matrix = fitz.Matrix(render_scale, render_scale)
        pix = source_page.get_pixmap(matrix=matrix, alpha=False)
        page.insert_image(page.rect, pixmap=pix)
        render_units = merged_render_units(segments_by_page.get(page_index, []), translations)
        render_segments = [segment for segment, _text in render_units]
        allowed_bottoms = build_allowed_bottoms({page_index: render_segments}, source_page.rect.height, {page_index: page_obstacles})
        for segment, render_text in render_units:
            paint_line_backgrounds(
                page,
                segment,
                pix,
                render_scale,
                padding_x=whiteout_padding_x,
                padding_y=whiteout_padding_y,
            )
            segment_for_render = replace(segment, lines=extend_lines_to_bottom(segment, allowed_bottoms.get(segment.sid, segment.bbox[3])))
            render_segment_text(
                page,
                segment_for_render,
                render_text,
                font_path,
                bold_font_path,
                warnings,
            )
        if progress_callback:
            progress_callback("render", f"已渲染页面 {page_index + 1}/{page_count}", page_index + 1, max(1, page_count))

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_doc.save(output_pdf, garbage=4, deflate=True)
    output_doc.close()
    source_doc.close()
    return warnings


def render_translated_pdf(
    input_pdf: Path,
    output_pdf: Path,
    segments: list[Segment],
    translations: dict[str, str],
    font_path: Path,
    bold_font_path: Path,
    render_scale: float,
    whiteout_padding_x: float,
    whiteout_padding_y: float,
    max_pages: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    """功能：选择可用渲染器并生成翻译版式 PDF。参数：input_pdf、output_pdf、segments、translations、font_path、bold_font_path、render_scale、whiteout_padding_x、whiteout_padding_y、max_pages、progress_callback。返回值：list[str]。"""
    try:
        return render_translated_pdf_reportlab(
            input_pdf=input_pdf,
            output_pdf=output_pdf,
            segments=segments,
            translations=translations,
            font_path=font_path,
            bold_font_path=bold_font_path,
            render_scale=render_scale,
            whiteout_padding_x=whiteout_padding_x,
            whiteout_padding_y=whiteout_padding_y,
            max_pages=max_pages,
            progress_callback=progress_callback,
        )
    except ImportError:
        return render_translated_pdf_pymupdf(
            input_pdf=input_pdf,
            output_pdf=output_pdf,
            segments=segments,
            translations=translations,
            font_path=font_path,
            bold_font_path=bold_font_path,
            render_scale=render_scale,
            whiteout_padding_x=whiteout_padding_x,
            whiteout_padding_y=whiteout_padding_y,
            max_pages=max_pages,
            progress_callback=progress_callback,
        )


def wrap_summary_lines(text: str, meter: ReportLabTextMeter, width: float, font_size: float, max_lines: int) -> list[str]:
    """功能：按摘要页宽度和最大行数折行。参数：text、meter、width、font_size、max_lines。返回值：list[str]。"""
    paragraphs = [item.strip() for item in re.split(r"\n+", text.strip()) if item.strip()]
    lines: list[str] = []
    for paragraph in paragraphs:
        if paragraph == "文献核心要点概况":
            continue
        wrapped, overflow = wrap_text_for_widths(paragraph, [width] * max_lines, meter, font_size)
        lines.extend(wrapped)
        if overflow:
            break
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def append_summary_page(
    output_pdf: Path,
    summary_text: str,
    font_path: Path,
    bold_font_path: Path,
) -> str | None:
    """功能：在翻译 PDF 末尾追加摘要页。参数：output_pdf、summary_text、font_path、bold_font_path。返回值：str | None。"""
    if not summary_text.strip():
        return "summary page skipped: empty summary"

    from io import BytesIO

    from reportlab.pdfgen import canvas

    regular_font_name, bold_font_name = register_reportlab_fonts(font_path, bold_font_path)
    meter = ReportLabTextMeter(regular_font_name)
    output_doc = fitz.open(output_pdf)
    if output_doc.page_count:
        rect = output_doc[0].rect
        page_width, page_height = rect.width, rect.height
    else:
        page_width, page_height = 595.0, 842.0

    margin_x = 54.0
    top = 64.0
    bottom = 54.0
    title_size = 16.0
    subtitle_size = 8.5
    body_width = page_width - margin_x * 2
    available_height = page_height - top - bottom - 48.0

    warning: str | None = None
    body_size = 10.4
    while body_size >= 8.2:
        line_step = body_size * 1.55
        max_lines = max(1, int(available_height / line_step))
        body_lines = wrap_summary_lines(summary_text, meter, body_width, body_size, max_lines)
        if len(body_lines) <= max_lines:
            break
        body_size -= 0.3
    else:
        body_size = 8.2
        line_step = body_size * 1.55
        max_lines = max(1, int(available_height / line_step))
        body_lines = wrap_summary_lines(summary_text, meter, body_width, body_size, max_lines)[:max_lines]
        if body_lines:
            body_lines[-1] = body_lines[-1].rstrip("。；，,;") + "……"
        warning = "summary page truncated to fit one page"

    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    pdf_canvas.setFillColorRGB(1, 1, 1)
    pdf_canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    pdf_canvas.setFillColorRGB(0.05, 0.08, 0.12)
    pdf_canvas.setFont(bold_font_name, title_size)
    pdf_canvas.drawString(margin_x, page_height - top, "文献核心要点概况")
    pdf_canvas.setFont(regular_font_name, subtitle_size)
    pdf_canvas.setFillColorRGB(0.35, 0.42, 0.50)
    pdf_canvas.drawString(margin_x, page_height - top - 18, "本页由系统基于文献正文内容自动生成；引用与判断请以原文和正文译文为准。")

    y = page_height - top - 44
    pdf_canvas.setFont(regular_font_name, body_size)
    pdf_canvas.setFillColorRGB(0.08, 0.10, 0.14)
    line_step = body_size * 1.55
    for line in body_lines:
        if line:
            pdf_canvas.drawString(margin_x, y, line)
        y -= line_step

    pdf_canvas.showPage()
    pdf_canvas.save()
    summary_doc = fitz.open(stream=buffer.getvalue(), filetype="pdf")
    output_doc.insert_pdf(summary_doc)
    tmp_path = output_pdf.with_suffix(".summary.tmp.pdf")
    output_doc.save(tmp_path, garbage=4, deflate=True)
    summary_doc.close()
    output_doc.close()
    tmp_path.replace(output_pdf)
    return warning


def make_translator(args: argparse.Namespace, glossary_text: str) -> BaseTranslator:
    """功能：根据命令行参数创建翻译器。参数：args、glossary_text。返回值：BaseTranslator。"""
    if args.translator == "copy":
        return CopyTranslator()
    return OpenAITranslator(
        model=args.model,
        target_lang=args.target_lang,
        glossary_text=glossary_text,
        api_key=args.api_key,
        base_url=args.base_url,
        temperature=args.temperature,
        max_retries=args.max_retries,
        json_mode=not args.disable_json_mode,
    )


def output_name_for(input_pdf: Path, output_dir: Path, suffix: str) -> Path:
    """功能：生成翻译输出文件名。参数：input_pdf、output_dir、suffix。返回值：Path。"""
    return output_dir / f"{input_pdf.stem}{suffix}.pdf"


def safe_document_folder_name(filename: str) -> str:
    """Return a cross-platform-safe output folder name for a document."""
    stem = str(filename).strip()
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    if stem.upper() in {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }:
        stem += "_"
    return stem or "untitled_document"


def document_output_dir(input_pdf: Path, output_root: Path) -> Path:
    """Return the reusable per-document output directory."""
    return output_root / safe_document_folder_name(input_pdf.name)


def find_pdf_files(input_dir: Path) -> list[Path]:
    """功能：扫描输入目录中的 PDF，兼容不同平台的扩展名大小写。参数：input_dir。返回值：list[Path]。"""
    return sorted(
        (path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.name.lower(),
    )


def translate_pdf(input_pdf: Path, args: argparse.Namespace, translator: BaseTranslator, glossary_text: str) -> None:
    """功能：执行单个 PDF 的抽取、翻译、渲染和报告流程。参数：input_pdf、args、translator、glossary_text。返回值：None。"""
    progress_callback: ProgressCallback | None = getattr(args, "progress_callback", None)
    preview_callback: Callable[[str], None] | None = getattr(args, "preview_callback", None)
    language = str(getattr(args, "language", "zh") or "zh")

    def notify(stage: str, message: str, current: int | None = None, total: int | None = None) -> None:
        """功能：向调用方上报单文档翻译进度。参数：stage、message、current、total。返回值：None。"""
        if progress_callback:
            message = localized_log(language, message)
            if current is None or total is None:
                progress_callback(stage, message)
            else:
                progress_callback(stage, message, current, total)

    def localized_progress(stage: str, message: str, current: int | None = None, total: int | None = None) -> None:
        """转发下游阶段进度。参数：阶段、消息和计数。返回值：无。"""
        notify(stage, message, current, total)

    def publish_preview(partial_translations: dict[str, str]) -> None:
        """Publish the current document's completed translated segments."""
        if not preview_callback:
            return
        preview = translation_preview_text(segments, partial_translations)
        waiting = "Waiting for translated segments..." if language == "en" else "等待首批翻译结果..."
        preview_callback(f"{input_pdf.name}\n\n{preview or waiting}")

    output_dir = document_output_dir(input_pdf, Path(args.output))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = output_name_for(input_pdf, output_dir, args.suffix)
    notify("prepare", f"准备处理 {input_pdf.name}", 0, 1)
    print(f"\nProcessing: {input_pdf}")
    notify("extract", "读取 PDF 并提取文本段", 0, 1)
    doc = fitz.open(input_pdf)
    try:
        segments = extract_segments(
            doc,
            translate_references=args.translate_references,
            translate_header_footer=args.translate_header_footer,
            max_pages=args.max_pages,
        )
    finally:
        doc.close()
    translatable_segments = sum(1 for segment in segments if segment.translate)
    publish_preview({})
    print(f"提取段落：{len(segments)}；需要翻译：{translatable_segments}")
    notify("extract", f"已提取 {len(segments)} 段，需要翻译 {translatable_segments} 段", 1, 1)

    notify("translate", f"构建上下文，准备翻译 {translatable_segments} 段", 0, 1)
    context = build_document_context(segments)
    cache = TranslationCache(output_dir / "cache" / "translation_cache.json", enabled=not args.no_cache)
    translations = translate_segments(
        segments,
        translator,
        cache,
        context=context,
        target_lang=args.target_lang,
        glossary_text=glossary_text,
        batch_size=args.batch_size,
        max_batch_chars=args.max_batch_chars,
        progress_callback=localized_progress,
        preview_callback=publish_preview,
    )
    cache.save()

    summary_text = ""
    summary_warning: str | None = None
    if getattr(args, "summary_page", True):
        notify("summary", "生成文献核心要点概况", 0, 1)
        summary_text, summary_warning = generate_document_summary(
            translator=translator,
            segments=segments,
            translations=translations,
            cache=cache,
            target_lang=args.target_lang,
            glossary_text=glossary_text,
        )
        if summary_warning:
            print(summary_warning)
        notify("summary", "文献核心要点概况已生成", 1, 1)

    notify("render", "加载字体并生成输出 PDF", 0, 1)
    font_path = discover_font(args.font, bold=False)
    bold_font_path = discover_font(args.bold_font, bold=True)
    warnings = [] if translator.provider == "copy" else collect_translation_quality_warnings(segments, translations)
    for warning in warnings:
        print(warning)
    warnings.extend(render_translated_pdf(
        input_pdf=input_pdf,
        output_pdf=output_pdf,
        segments=segments,
        translations=translations,
        font_path=font_path,
        bold_font_path=bold_font_path,
        render_scale=args.render_scale,
        whiteout_padding_x=args.whiteout_padding_x,
        whiteout_padding_y=args.whiteout_padding_y,
        max_pages=args.max_pages,
        progress_callback=localized_progress,
    ))
    if summary_text:
        notify("render", "追加文献概况页", 1, 1)
        page_warning = append_summary_page(output_pdf, summary_text, font_path, bold_font_path)
        if page_warning:
            warnings.append(page_warning)

    report = {
        "input": str(input_pdf),
        "output": str(output_pdf),
        "translator": translator.provider,
        "model": translator.model,
        "segments": len(segments),
        "translated_segments": sum(1 for segment in segments if segment.translate),
        "font": str(font_path),
        "bold_font": str(bold_font_path),
        "summary_page": bool(summary_text),
        "summary_warning": summary_warning,
        "summary": summary_text,
        "warnings": warnings,
    }
    report_path = output_pdf.with_suffix(".report.json")
    write_json_atomic(report_path, report)
    print(f"Saved: {output_pdf}")
    if warnings:
        print(f"Layout warnings: {len(warnings)}. See {report_path}")
    notify("done", f"已保存 {output_pdf.name}", 1, 1)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """功能：解析翻译命令行参数。参数：argv。返回值：argparse.Namespace。"""
    parser = argparse.ArgumentParser(
        description="Translate English academic PDFs to Chinese with DeepSeek while preserving the original page layout.",
    )
    parser.add_argument("--input", default="pdf", help="Input folder containing PDF files.")
    parser.add_argument("--output", help="Parent folder for per-document translation output. Defaults to the input folder.")
    parser.add_argument("--suffix", default="_全文翻译", help="Suffix appended to translated PDF filenames.")
    parser.add_argument("--translator", choices=["deepseek", "copy"], default="deepseek", help="Use an OpenAI-compatible API for translation; copy is only for layout testing.")
    parser.add_argument("--target-lang", default="zh", help="Target language/cache label.")
    parser.add_argument(
        "--api-key",
        default=os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("MOONSHOT_API_KEY")
        or os.getenv("GEMINI_API_KEY"),
        help="API key for the selected OpenAI-compatible provider.",
    )
    parser.add_argument("--base-url", default=os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com", help="OpenAI-compatible API base URL.")
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-v4-flash")
    parser.add_argument("--temperature", type=float, default=0.15)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--disable-json-mode", action="store_true")
    parser.add_argument("--glossary", type=Path, nargs="*", help="Optional glossary file(s): CSV/TSV/TXT/JSON. CSV rows use source,target; TXT rows use source => target.")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-batch-chars", type=int, default=6500)
    parser.add_argument("--render-scale", type=float, default=2.0)
    parser.add_argument("--whiteout-padding-x", type=float, default=1.4)
    parser.add_argument("--whiteout-padding-y", type=float, default=0.9)
    parser.add_argument("--font", help="CJK regular font path.")
    parser.add_argument("--bold-font", help="CJK bold font path.")
    parser.add_argument("--translate-references", action="store_true", help="Translate bibliography entries too.")
    parser.add_argument("--translate-header-footer", action="store_true", help="Translate page headers and footers.")
    parser.add_argument("--max-pages", type=int, help="Only process the first N pages; useful for layout testing.")
    parser.add_argument("--no-summary-page", dest="summary_page", action="store_false", help="Do not append the final document-summary page.")
    parser.set_defaults(summary_page=True)
    parser.add_argument("--no-cache", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """功能：执行命令行入口流程。参数：argv。返回值：int。"""
    args = parse_args(argv or sys.argv[1:])
    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else input_dir
    args.output = str(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        glossary_text = load_glossary(args.glossary)
        translator = make_translator(args, glossary_text)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    pdfs = find_pdf_files(input_dir)
    if not pdfs:
        print(f"No PDFs found in {input_dir}", file=sys.stderr)
        return 1
    for pdf in pdfs:
        try:
            translate_pdf(pdf, args, translator, glossary_text)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(f"Error while processing {pdf}: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
