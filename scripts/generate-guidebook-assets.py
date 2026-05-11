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
    multiline(draw, (74, 244), "先浏览最近整理的内容；需要处理时，只选择添加资料、搜索回顾或生成 AI 上下文包。", FONTS["subtitle"], "#dbeafe", 980, 14)
    cards = [
        ("先看最近内容", "查看已整理笔记、AI 对话和报告。", COLORS["blue"]),
        ("整理新资料", "把文本、文件路径或 AI 对话写入 Obsidian。", COLORS["cyan"]),
        ("回顾旧内容", "按关键词找到答案和来源路径。", COLORS["violet"]),
        ("提取给 AI", "把相关内容打包成可复制的上下文。", COLORS["green"]),
    ]
    top = 390
    for index, (title, body, color) in enumerate(cards):
        x = 70 + index * 382
        rounded(draw, (x, top, x + 330, top + 270), "#ffffff", "#dfe7f2", 32)
        draw.rounded_rectangle((x + 28, top + 30, x + 76, top + 78), radius=15, fill=color)
        draw.text((x + 42, top + 36), str(index + 1), font=FONTS["small"], fill="white")
        draw.text((x + 30, top + 104), title, font=FONTS["h2"], fill=COLORS["ink"])
        multiline(draw, (x + 30, top + 164), body, FONTS["body"], COLORS["muted"], 270, 10)
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
        ("打开首页", "先看用途、四入口和知识流。"),
        ("点击卡片", "只展开详情和来源，不写入。"),
        ("使用入口", "添加资料、搜索回顾、生成 AI 上下文包。"),
        ("查看结果", "结果卡展示来源、保存位置和下一步建议。"),
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
                ("第一眼", ["这是添加资料、搜索回顾和生成 AI 上下文包的本地知识站", "只生成建议和新记录，不改动源文件", "两个按钮：向下看知识流 / 添加资料"]),
                ("核心价值", ["把资料变成可归档记录", "把旧知识找回来", "把上下文反向打包给 AI", "每天只保留最多 3 条行动建议"]),
            ],
        ),
        (
            "首页怎么走",
            "三张主卡是导航，不是后台按钮。点击后跳到同页锚点区。",
            [
                ("三个锚点", ["#organize 添加资料", "#review 搜索回顾", "#extract 生成 AI 上下文包"]),
                ("工具维护页", ["文件雷达", "知识库体检", "旧资料索引", "只放独立子页面"]),
            ],
        ),
        (
            "知识流怎么用",
            "下滑看到的卡片来自已整理内容，会随着 Obsidian 笔记和报告持续更新。",
            [
                ("卡片内容", ["标题", "描述", "类型", "来源路径", "更新时间"]),
                ("点击行为", ["展开详情", "查看来源路径", "复制路径", "不自动写入、不自动提取"]),
            ],
        ),
        (
            "添加资料",
            "把文本、本地路径或 AI 对话放进整理区，先留下可追溯记录。",
            [
                ("输入", ["资料正文", "本地路径", "拖放/选择文件作为来源提示"]),
                ("输出", ["Obsidian 新笔记", "来源", "生活 / 学习 / 工作判断", "下一步"]),
            ],
        ),
        (
            "回顾与提取",
            "先回顾，后提取。不要让 AI 从零猜上下文。",
            [
                ("搜索回顾", ["输入关键词或问题", "返回答案 + 来源", "适合找旧教程、项目记录和历史报告"]),
                ("生成 AI 上下文包", ["输入当前任务", "生成 AI 上下文包", "包含来源路径、摘要、安全边界和下一步请求"]),
            ],
        ),
        (
            "安全边界与高级工具",
            "首页不再放今日行动按钮；计划任务仍可在后台生成轻量行动建议。",
            [
                ("每天", ["需要提醒时使用计划任务", "不要处理全部归档候选", "需要继续问 AI 时先生成上下文包"]),
                ("每周", ["处理收件箱 backlog", "复盘 Action 和 Card", "再优化 Obsidian 结构"]),
            ],
        ),
        (
            "安全边界",
            "这不是源文件搬迁工具，默认先看、先建议、先生成上下文。",
            [
                ("不会做", ["不删除", "不移动", "不重命名", "不重写源文件"]),
                ("允许做", ["写新的 Obsidian 笔记", "生成本地报告", "生成 AI 上下文包", "保留来源和路径"]),
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
