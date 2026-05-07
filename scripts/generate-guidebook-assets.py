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
    "panel": "#ffffff",
    "ink": "#121826",
    "muted": "#667085",
    "blue": "#2f6ecb",
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
    image, draw = make_canvas()
    y = title_block(
        draw,
        "GUI FLOW",
        "可视化上下文入口",
        "GUI 不替代 Codex。它把本地文件、Obsidian、历史报告和 AI 对话归档整理成 Codex 接手包。",
    )
    top = max(330, y + 20)
    cards = [
        ("本地文件", "扫描目录，输出报告、候选和路径。", COLORS["blue"]),
        ("Obsidian", "读取 vault、知识卡、项目记录。", COLORS["green"]),
        ("历史报告", "复用文件雷达、体检和复盘报告。", COLORS["violet"]),
        ("AI 对话归档", "保存对话来源、背景、结论和待办。", COLORS["amber"]),
    ]
    for index, (title, body, color) in enumerate(cards):
        row = index // 2
        col = index % 2
        draw_card(draw, (70 + col * 390, top + row * 205, 430 + col * 390, top + 178 + row * 205), title, body, color, str(index + 1))

    rounded(draw, (860, top + 72, 1145, top + 330), "#ffffff", "#c9d9f3", 36)
    draw.text((900, top + 110), "Codex", font=FONTS["h2"], fill=COLORS["blue"])
    draw.text((900, top + 156), "接手包", font=FONTS["title"], fill=COLORS["ink"])
    multiline(draw, (896, top + 256), "来源路径 + 相关原因 + 压缩摘要 + 安全边界 + 下一步请求", FONTS["small"], COLORS["muted"], 220, 8)
    draw.line((835, top + 200, 860, top + 200), fill="#93add4", width=5)
    draw.polygon([(860, top + 200), (835, top + 186), (835, top + 214)], fill="#93add4")
    draw.line((1145, top + 200, 1180, top + 200), fill="#93add4", width=5)
    draw.polygon([(1180, top + 200), (1154, top + 186), (1154, top + 214)], fill="#93add4")
    draw_card(draw, (1190, top + 72, 1530, top + 330), "Codex 继续", "复制接手包，基于真实上下文继续处理。", COLORS["green"])
    save(image, GUI_DIR / "interaction-map.png")


def generate_interaction_states() -> None:
    image, draw = make_canvas()
    title_block(
        draw,
        "STATES",
        "点击后状态变化",
        "页面只负责组织上下文和生成接手包。高级 JSON 只用于调试，不是默认体验。",
    )
    states = [
        ("打开页面", "看到本地上下文概览和四类来源。"),
        ("写当前任务", "输入目标和边界"),
        ("生成接手包", "展示匹配来源、压缩摘要和边界。"),
        ("复制给 Codex", "新对话少问路径，基于真实文件继续"),
    ]
    start_x = 86
    for index, (title, body) in enumerate(states):
        x = start_x + index * 374
        draw_card(draw, (x, 360, x + 320, 620), title, body, [COLORS["blue"], COLORS["green"], COLORS["violet"], COLORS["amber"]][index], str(index + 1))
        if index < len(states) - 1:
            draw.line((x + 324, 490, x + 360, 490), fill="#93add4", width=5)
            draw.polygon([(x + 360, 490), (x + 340, 478), (x + 340, 502)], fill="#93add4")
    rounded(draw, (110, 690, 1490, 800), COLORS["green_soft"], "#d7eadc", 30)
    multiline(draw, (148, 718), "安全边界：默认只读，不删除、不移动、不重命名、不重写源文件。记录类入口只写新的 Obsidian 笔记。", FONTS["body"], "#174a34", 1280, 8)
    save(image, GUI_DIR / "interaction-states.png")


def bullet_section(draw: ImageDraw.ImageDraw, x: int, y: int, title: str, bullets: Iterable[str], width: int) -> int:
    draw.text((x, y), title, font=FONTS["h2"], fill=COLORS["ink"])
    y += 62
    for item in bullets:
        draw.ellipse((x, y + 10, x + 16, y + 26), fill=COLORS["blue"])
        y = multiline(draw, (x + 34, y), item, FONTS["body"], COLORS["muted"], width - 34, 9) + 8
    return y


def generate_slide(index: int, title: str, subtitle: str, sections: list[tuple[str, list[str]]]) -> Path:
    image, draw = make_canvas()
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
    draw.text((70, 816), "Obsidian AI 整理工作台 | 可视化上下文入口 | 默认只读", font=FONTS["tiny"], fill=COLORS["muted"])
    draw.text((1456, 816), f"{index}/7", font=FONTS["tiny"], fill=COLORS["muted"])
    path = SLIDES_DIR / f"page-{index:02d}.png"
    save(image, path)
    return path


def generate_guidebook() -> list[Path]:
    slides = [
        (
            "它不是替代 Codex",
            "GUI 的意义是把本地上下文整理成入口，让 Codex 接手时少读上下文、少问路径。",
            [
                ("新定位", ["可视化上下文入口", "本地文件、Obsidian、历史报告集中展示", "核心产物是 Codex 接手包"]),
                ("不做什么", ["不假装替代 Codex 推理", "不把网页做成伪控制台", "不自动删除、移动或改名源文件"]),
            ],
        ),
        (
            "四类上下文来源",
            "接手包不是凭空生成，而是从已经整理过的材料里提取来源和摘要。",
            [
                ("来源", ["本地文件：文件雷达和路径", "Obsidian：知识卡、项目记录、复盘", "历史报告：文件雷达、体检、自评报告"]),
                ("AI 对话", ["归档已有对话", "保留背景、结论、产出路径", "为后续 Codex 取用做准备"]),
            ],
        ),
        (
            "怎么生成 Codex 接手包",
            "把你准备交给 Codex 的任务写进输入框，再点击生成。",
            [
                ("三步", ["写当前任务", "点击生成 Codex 接手包", "复制 prompt 给 Codex"]),
                ("输出", ["匹配来源路径", "为什么相关", "压缩后的上下文", "建议给 Codex 的下一步请求"]),
            ],
        ),
        (
            "接手包里应该有什么",
            "好的接手包让 Codex 能直接进入工作，不需要重新从零问你。",
            [
                ("必须包含", ["真实路径", "来源摘要", "当前目标", "验收标准"]),
                ("必须说明", ["安全边界", "哪些信息不确定", "需要先读哪些文件", "不要编造当前状态"]),
            ],
        ),
        (
            "记录与沉淀",
            "GUI 也保留记录入口，但它们服务于后续上下文取用。",
            [
                ("ACT", ["Action：一任务一笔记", "Card：可复用知识", "Time：轻量复盘"]),
                ("AI 对话归档", ["只保存已有对话", "不等于新对话上下文取用", "需要继续问 Codex 时再生成接手包"]),
            ],
        ),
        (
            "安全边界",
            "默认先看、先建议、先生成上下文，不碰源文件。",
            [
                ("默认只读", ["文件雷达只生成报告", "Obsidian 体检只生成报告", "接手包只读取已整理上下文"]),
                ("允许写入", ["只写新的 Obsidian 笔记", "追加到明确位置", "保留来源和路径"]),
            ],
        ),
        (
            "一周使用节奏",
            "每天不要整理太重。把日常使用压成入口，复杂工作交给 Codex。",
            [
                ("每天", ["先看本地上下文概览", "只处理 1-3 个重点", "需要继续时生成接手包"]),
                ("每周", ["处理归档 backlog", "复盘 Action 和 Card", "优化 Obsidian 结构"]),
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
