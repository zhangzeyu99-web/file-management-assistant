from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
GUI_DIR = ROOT / "docs" / "assets" / "gui"
GUIDEBOOK_DIR = ROOT / "docs" / "guidebook"
SLIDES_DIR = GUIDEBOOK_DIR / "slides"
PDF_PATH = GUIDEBOOK_DIR / "knowledge-action-assistant-tutorial.pdf"
WIDTH = 1600
HEIGHT = 900


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONTS = {
    "kicker": font(28, True),
    "title": font(68, True),
    "subtitle": font(30),
    "h2": font(38, True),
    "body": font(28),
    "small": font(23),
    "tiny": font(19),
}


COLORS = {
    "bg": "#f5f7fb",
    "hero": "#071426",
    "hero_2": "#0d2d3d",
    "panel": "#ffffff",
    "ink": "#121826",
    "muted": "#667085",
    "blue": "#2f6ecb",
    "cyan": "#26c3d8",
    "blue_soft": "#eaf2ff",
    "green": "#26875a",
    "green_soft": "#eef7f1",
    "violet": "#6b5cf6",
    "amber": "#f5a524",
    "line": "#dfe7f2",
}


def text_width(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=text_font)
    return box[2] - box[0]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            candidate = current + char
            if text_width(draw, candidate, text_font) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines or [""]


def multiline(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    text_font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 10,
) -> int:
    x, y = xy
    for line in wrap_text(draw, text, text_font, max_width):
        draw.text((x, y), line, font=text_font, fill=fill)
        box = draw.textbbox((x, y), line or " ", font=text_font)
        y += box[3] - box[1] + line_gap
    return y


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str = COLORS["line"], radius: int = 28) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def make_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    draw.ellipse((-200, -260, 620, 420), fill="#edf1ff")
    draw.ellipse((1180, -190, 1780, 420), fill="#eaf8fb")
    return image, draw


def make_dark_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["hero"])
    draw = ImageDraw.Draw(image)
    for offset in range(0, WIDTH, 44):
        draw.line((offset, 0, offset, HEIGHT), fill="#0e2237", width=1)
    for offset in range(0, HEIGHT, 44):
        draw.line((0, offset, WIDTH, offset), fill="#0e2237", width=1)
    draw.ellipse((-260, -240, 620, 520), fill="#0b2850")
    draw.ellipse((1060, -200, 1840, 520), fill="#0b3b4a")
    return image, draw


def title_block(draw: ImageDraw.ImageDraw, kicker: str, title: str, subtitle: str) -> int:
    draw.rounded_rectangle((70, 54, 380, 102), radius=24, fill=COLORS["blue_soft"], outline="#d8e6fb")
    draw.text((96, 64), kicker, font=FONTS["kicker"], fill=COLORS["blue"])
    draw.text((70, 132), title, font=FONTS["title"], fill=COLORS["ink"])
    return multiline(draw, (74, 232), subtitle, FONTS["subtitle"], "#344054", 1020, 13)


def draw_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    body: str,
    accent: str = COLORS["blue"],
    number: str | None = None,
) -> None:
    rounded(draw, box, COLORS["panel"])
    x1, y1, x2, _ = box
    draw.rounded_rectangle((x1 + 26, y1 + 28, x1 + 72, y1 + 74), radius=14, fill=accent)
    if number:
        draw.text((x1 + 40, y1 + 34), number, font=FONTS["small"], fill="white")
    draw.text((x1 + 92, y1 + 28), title, font=FONTS["h2"], fill=COLORS["ink"])
    multiline(draw, (x1 + 32, y1 + 98), body, FONTS["body"], COLORS["muted"], x2 - x1 - 64, 10)


def save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)


def generate_interaction_map() -> None:
    image, draw = make_dark_canvas()
    draw.rounded_rectangle((70, 58, 330, 106), radius=24, fill="#14293d", outline="#27405f")
    draw.text((96, 67), "使用路径", font=FONTS["kicker"], fill="#91dfff")
    draw.text((70, 142), "本地知识整理助手", font=FONTS["title"], fill="#f8fbff")
    multiline(draw, (74, 244), "只保留三步闭环：添加资料真实入库，搜索回顾找到证据，生成 AI 上下文包交给新的 AI 对话。", FONTS["subtitle"], "#dbeafe", 980, 14)
    cards = [
        ("添加资料", "粘贴文本或真实本地路径，写入 Obsidian 整理记录和文件索引。", COLORS["blue"]),
        ("搜索回顾", "按关键词找答案、命中词、证据摘录和来源路径。", COLORS["violet"]),
        ("生成上下文包", "从证据来源生成 Markdown 和可复制 prompt。", COLORS["green"]),
    ]
    top = 390
    for index, (title, body, color) in enumerate(cards):
        x = 120 + index * 500
        rounded(draw, (x, top, x + 420, top + 270), "#ffffff", "#dfe7f2", 32)
        draw.rounded_rectangle((x + 28, top + 30, x + 76, top + 78), radius=15, fill=color)
        draw.text((x + 42, top + 36), str(index + 1), font=FONTS["small"], fill="white")
        draw.text((x + 30, top + 104), title, font=FONTS["h2"], fill=COLORS["ink"])
        multiline(draw, (x + 30, top + 164), body, FONTS["body"], COLORS["muted"], 350, 10)
    save(image, GUI_DIR / "interaction-map.png")


def generate_interaction_states() -> None:
    image, draw = make_canvas()
    title_block(
        draw,
        "使用状态",
        "点击后会发生什么",
        "操作后会看到完成情况、参考来源、保存位置和下一步建议。",
    )
    states = [
        ("添加资料", "写入 Obsidian 新整理记录，并生成推荐搜索词。"),
        ("点击推荐词", "自动填入搜索回顾并执行，验证刚入库资料可找回。"),
        ("查看证据", "默认最多 4 条强证据，保留来源路径和操作。"),
        ("加入上下文包", "把证据加入候选，确认后生成可复制 prompt。"),
    ]
    start_x = 86
    for index, (title, body) in enumerate(states):
        x = start_x + index * 374
        draw_card(draw, (x, 360, x + 320, 620), title, body, [COLORS["blue"], COLORS["green"], COLORS["violet"], COLORS["amber"]][index], str(index + 1))
        if index < len(states) - 1:
            draw.line((x + 324, 490, x + 360, 490), fill="#93add4", width=5)
            draw.polygon([(x + 360, 490), (x + 340, 478), (x + 340, 502)], fill="#93add4")
    rounded(draw, (110, 690, 1490, 800), COLORS["green_soft"], "#d7eadc", 30)
    multiline(draw, (148, 718), "安全边界：只生成建议和新记录，不改动你的源文件。", FONTS["body"], "#174a34", 1280, 8)
    save(image, GUI_DIR / "interaction-states.png")


def bullet_section(draw: ImageDraw.ImageDraw, x: int, y: int, title: str, bullets: Iterable[str], width: int) -> int:
    draw.text((x, y), title, font=FONTS["h2"], fill=COLORS["ink"])
    y += 62
    for item in bullets:
        draw.ellipse((x, y + 10, x + 16, y + 26), fill=COLORS["blue"])
        y = multiline(draw, (x + 34, y), item, FONTS["body"], COLORS["muted"], width - 34, 9) + 8
    return y


def generate_slide(index: int, title: str, subtitle: str, sections: list[tuple[str, list[str]]]) -> Path:
    image, draw = make_dark_canvas() if index == 1 else make_canvas()
    if index == 1:
        draw.rounded_rectangle((70, 54, 380, 102), radius=24, fill="#14293d", outline="#27405f")
        draw.text((96, 64), f"PAGE {index:02d}", font=FONTS["kicker"], fill="#91dfff")
        draw.text((70, 132), title, font=FONTS["title"], fill="#f8fbff")
        y = multiline(draw, (74, 232), subtitle, FONTS["subtitle"], "#dbeafe", 1020, 13)
    else:
        y = title_block(draw, f"PAGE {index:02d}", title, subtitle)
    columns = len(sections)
    gap = 28
    left = 72
    top = max(350, y + 24)
    width = (WIDTH - left * 2 - gap * (columns - 1)) // columns
    for column, (section_title, bullets) in enumerate(sections):
        x = left + column * (width + gap)
        rounded(draw, (x, top, x + width, 760), COLORS["panel"])
        bullet_section(draw, x + 34, top + 34, section_title, bullets, width - 68)
    footer_color = "#cbd5e1" if index == 1 else COLORS["muted"]
    draw.text((70, 816), "本地知识整理助手 | 添加资料 / 搜索回顾 / 生成 AI 上下文包 | 不改动源文件", font=FONTS["tiny"], fill=footer_color)
    draw.text((1456, 816), f"{index}/7", font=FONTS["tiny"], fill=footer_color)
    path = SLIDES_DIR / f"page-{index:02d}.png"
    save(image, path)
    return path


def generate_guidebook() -> list[Path]:
    slides = [
        (
            "本地知识整理助手",
            "把资料、Obsidian 笔记和 AI 对话沉淀成可回顾、可复用的知识系统。",
            [
                ("第一眼", ["这是添加资料、搜索回顾和生成 AI 上下文包的本地知识站", "只生成建议和新记录，不改动源文件", "首页只围绕三步闭环，不展示旧工具入口"]),
                ("核心价值", ["把资料变成可归档记录", "把旧知识找回来", "把上下文反向打包给 AI", "让下一次 AI 对话带着证据开始"]),
            ],
        ),
        (
            "三步闭环怎么走",
            "先入库，再回顾，最后提取。不要让 AI 从零猜上下文。",
            [
                ("三个锚点", ["#organize 添加资料", "#review 搜索回顾", "#extract 生成 AI 上下文包"]),
                ("结果标准", ["添加资料必须写 Obsidian 记录", "搜索回顾必须返回证据来源", "上下文包必须基于确认来源生成"]),
            ],
        ),
        (
            "添加资料",
            "把文本、本地路径或 AI 对话放进整理区，先留下可追溯记录。",
            [
                ("输入", ["资料正文", "完整本地路径", "AI 对话摘要", "拖放/选择文件只作为来源提示"]),
                ("输出", ["Obsidian 新笔记", "每文件独立索引", "manifest", "推荐搜索词"]),
            ],
        ),
        (
            "搜索回顾",
            "搜索不是闲聊回答，而是证据检索。没有证据时必须显示未找到。",
            [
                ("结果结构", ["一句话答案", "命中词", "证据摘录", "来源路径", "推荐阅读顺序"]),
                ("展示规则", ["默认最多 4 条强证据", "复制路径", "打开来源", "加入上下文包"]),
            ],
        ),
        (
            "生成 AI 上下文包",
            "先预览候选来源，确认后再生成 Markdown 和可复制 prompt。",
            [
                ("预览阶段", ["列出候选来源", "说明为什么相关", "先核对路径和摘要", "不写入文件"]),
                ("生成阶段", ["写入 Obsidian 上下文包", "生成 runtime Markdown", "输出 prompt", "包含安全边界和下一步请求"]),
            ],
        ),
        (
            "在 Obsidian 里怎么找",
            "每次操作都应该告诉你产物在哪，避免写入后找不到。",
            [
                ("添加资料后", ["整理记录", "整理目录", "文件索引目录", "点击推荐搜索词直接回顾"]),
                ("生成上下文包后", ["上下文包笔记", "上下文包目录", "runtime Markdown", "可复制 prompt"]),
            ],
        ),
        (
            "安全边界与 QA 节奏",
            "这不是源文件搬迁工具。每轮迭代都要用测试证明三步闭环没有退化。",
            [
                ("不会做", ["不删除", "不移动", "不重命名", "不重写源文件"]),
                ("必须验证", ["真实入库", "证据能搜回", "上下文包能复制", "GUI 不展示 JSON 控制台"]),
            ],
        ),
    ]
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    return [generate_slide(index, title, subtitle, sections) for index, (title, subtitle, sections) in enumerate(slides, 1)]


def generate_pdf(slides: list[Path]) -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(PDF_PATH), pagesize=(WIDTH, HEIGHT))
    for slide in slides:
        c.drawImage(ImageReader(str(slide)), 0, 0, width=WIDTH, height=HEIGHT)
        c.showPage()
    c.save()


def main() -> None:
    generate_interaction_map()
    generate_interaction_states()
    slides = generate_guidebook()
    generate_pdf(slides)
    print(f"generated {len(slides)} slides")
    print(PDF_PATH)


if __name__ == "__main__":
    main()
