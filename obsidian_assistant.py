from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config


ILLEGAL_FILENAME_CHARS = r'<>:"/\|?*'


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def safe_filename(value: str, fallback: str = "未命名") -> str:
    cleaned = value.strip() or fallback
    for char in ILLEGAL_FILENAME_CHARS:
        cleaned = cleaned.replace(char, "-")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] or fallback


def write_text(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def append_text(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(contents)
    return path


def vault_path(config: dict[str, Any]) -> Path:
    return Path(config.get("obsidian_vault") or "D:\\Obsidian-Work")


def folder_name(config: dict[str, Any], key: str, default: str) -> str:
    return str(config.get("obsidian_folders", {}).get(key, default))


def projects_dir(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "projects", "02 项目")


def codex_dir(config: dict[str, Any]) -> Path:
    return projects_dir(config) / folder_name(config, "codex_project", "Codex")


def inbox_dir(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "inbox", "00 收件箱")


def daily_dir(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "daily", "01 今日日志")


def routine_dir(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "routine", "04 例行工作")


def knowledge_action_dir(config: dict[str, Any]) -> Path:
    return projects_dir(config) / "知识行动助手"


def guide_path(config: dict[str, Any]) -> Path:
    return codex_dir(config) / "11 Obsidian + AI 知识行动助手使用指南.md"


def behavior_profile_path(config: dict[str, Any]) -> Path:
    return codex_dir(config) / "12 Codex 线程行为画像与帮助策略.md"


def codex_overview_path(config: dict[str, Any]) -> Path:
    return codex_dir(config) / "00 Codex 总览.md"


def build_guide(config: dict[str, Any]) -> str:
    vault = vault_path(config)
    today = now_local().strftime("%Y-%m-%d")
    return f"""# Obsidian + AI 知识行动助手使用指南

生成日期：`{today}`

## 一句话定位

这个助手不是单纯帮你“清文件”，而是把本地文件、Obsidian 笔记、Codex/OpenClaw 会话和手动输入，转成可行动、可复盘、可追溯的个人知识工作流。

## 四层结构

```text
输入层：本地文件 / Obsidian 笔记 / AI 对话 / 手动输入
判断层：生活 / 学习 / 工作 + Action / Card / Time / X-AI
执行层：整理资料 / 回顾知识 / 提取上下文 / 今日提醒
输出层：本地报告 / Obsidian 笔记 / GUI 操作入口 / AI 上下文包
```

## 你每天只需要做什么

1. 有零碎内容，先丢进 `00 收件箱`。
2. 今天做过什么、卡在哪里、明天继续什么，写进 `01 今日日志`。
3. 持续超过一天的事情，用 `Action` 写成任务笔记。
4. 以后会复用的经验，用 `Card` 沉淀成知识卡。
5. 每天只做轻量复盘；归档候选放到周复盘或月复盘批处理。

## 生活 / 学习 / 工作怎么拆

| 领域 | 放什么 | 默认入口 |
| --- | --- | --- |
| 生活 | 学历认证、证件、财务、健康、账户、家庭材料 | `00 收件箱` 或生活项目 |
| 学习 | NotebookLM、Obsidian 教程、课程、思维导图、资料包 | 学习项目或 `Card` |
| 工作 | Codex 项目、本地化、更新公告、客户材料、交付物 | 工作项目或 `Action` |

## Action / Card / Time / X-AI 怎么用

| 类型 | 什么时候用 | 必填字段 |
| --- | --- | --- |
| Action | 具体任务要推进 | 领域、目标、来源、背景、过程、结果、下一步、验收标准 |
| Card | 以后会复用 | 主题、来源、适用场景、关键结论、相关链接、下一步 |
| Time | 日/周/月复盘 | 完成、卡点、下一步、归档候选、结构调整 |
| X-AI | 交给 Codex/OpenClaw 继续 | 用户偏好、工作流、工具边界、最近上下文、验收标准 |

## 今日轻量规则

- 今天只收敛 1-3 个重点。
- 不要每天处理全部归档候选。
- 收件箱只做分类和来源保留，不做大规模搬迁。
- 大文件只判断未来 7 天是否会用，不直接删除。

## 推荐命令

```powershell
python .\\obsidian_assistant.py guide
python .\\obsidian_assistant.py ask "我今天怎么记录工作？"
python .\\obsidian_assistant.py action --title "更新知识行动助手" --domain "工作" --goal "完成结构重整" --source "Codex 会话"
python .\\obsidian_assistant.py card --title "ACT 方法" --domain "学习" --source "Obsidian 课程" --conclusion "先行动，再沉淀知识。"
python .\\obsidian_assistant.py review --title "今日复盘" --period daily --done "完成结构设计" --next "跑测试验证"
```

## 当你需要帮助时

你不需要先学完整 Obsidian。直接说“这段内容放哪”“记录一个任务”“复盘今天”“交给 Codex 继续”，助手会先读真实配置和报告，再按生活 / 学习 / 工作与 ACT 结构处理。

当前 vault：`{vault}`
"""


def ensure_overview_link(config: dict[str, Any]) -> None:
    overview = codex_overview_path(config)
    if not overview.exists():
        return
    text = overview.read_text(encoding="utf-8")
    links = [
        "- [[11 Obsidian + AI 知识行动助手使用指南]]",
        "- [[12 Codex 线程行为画像与帮助策略]]",
    ]
    for link in links:
        if link not in text:
            text = text.rstrip() + f"\n{link}\n"
    overview.write_text(text, encoding="utf-8")


def command_guide(config: dict[str, Any]) -> dict[str, Any]:
    path = write_text(guide_path(config), build_guide(config))
    ensure_overview_link(config)
    return {"ok": True, "guide": str(path)}


def answer_question(question: str, config: dict[str, Any]) -> str:
    q = question.strip().lower()
    vault = vault_path(config)
    if not q:
        return "你可以问：今天先干什么、这段内容放哪、怎么记录工作、怎么复盘、怎么交给 Codex 继续。"

    if any(word in q for word in ["记录工作", "今天", "今日", "日报", "日志", "daily"]):
        return (
            "今日轻量规则：今天只收敛 1-3 个重点，不要每天处理全部归档候选。"
            "如果是具体工作，用 Action：写领域、目标、来源、任务背景、行动过程、任务成果、下一步和验收标准。"
        )
    if any(word in q for word in ["习惯", "行为", "画像", "怎么帮我", "帮助我"]):
        return (
            "按你的习惯，助手要先读真实文件、配置和报告，再执行；低风险任务直接推进到产物和验证，"
            "不要停在建议，也不要把需要落盘的任务伪装成提醒。行为画像入口是 "
            f"`{behavior_profile_path(config)}`。"
        )
    if any(word in q for word in ["开始", "新手", "怎么用", "入门", "打开"]):
        return (
            f"先打开 Obsidian vault `{vault}`。新手只做三步："
            "1. 零碎内容放 `00 收件箱`；2. 当天进展放 `01 今日日志`；"
            "3. 持续任务写 Action，复用知识写 Card。"
        )
    if any(word in q for word in ["放哪", "归档", "整理", "分类", "收件箱"]):
        return (
            "先分生活 / 学习 / 工作，再判断 inbox、daily、project、routine、archive。"
            "不确定就放 `00 收件箱`，保留来源；周复盘再提升到项目或例行工作。"
        )
    if any(word in q for word in ["复盘", "time", "周复盘", "月复盘"]):
        return (
            "复盘用 Time：日复盘只写完成、卡点、下一步；周复盘再处理收件箱和归档候选；"
            "月复盘才考虑结构调整。"
        )
    if any(word in q for word in ["codex", "openclaw", "交接", "继续"]):
        return (
            "交接用 X-AI：写清路径、目标、安全边界、用户偏好、最近上下文和验收标准。"
            "交给 Codex 前要求它先读真实文件再执行。"
        )
    return (
        "我会按最小 Obsidian 工作流处理：先判断生活 / 学习 / 工作，再落到 Action / Card / Time / X-AI。"
        "如果无法确认当前状态，会明确说明并要求先读本地文件或报告。"
    )


def command_ask(config: dict[str, Any], question: str, write_note: bool) -> dict[str, Any]:
    answer = answer_question(question, config)
    result: dict[str, Any] = {"ok": True, "question": question, "answer": answer}
    if write_note:
        stamp = now_local().strftime("%Y%m%d-%H%M%S")
        title = safe_filename(f"Obsidian 问答-{stamp}")
        path = inbox_dir(config) / f"{title}.md"
        contents = f"# Obsidian 问答\n\n问题：{question}\n\n回答：{answer}\n"
        write_text(path, contents)
        result["note"] = str(path)
    return result


def command_capture(config: dict[str, Any], title: str, body: str, tags: list[str]) -> dict[str, Any]:
    stamp = now_local().strftime("%Y%m%d-%H%M%S")
    filename = safe_filename(f"{stamp} {title}") + ".md"
    path = inbox_dir(config) / filename
    tag_line = " ".join(f"#{safe_filename(tag)}" for tag in tags if tag.strip())
    contents = "\n".join(
        [
            f"# {title}",
            "",
            f"创建时间：`{now_local().strftime('%Y-%m-%d %H:%M:%S %z')}`",
            f"标签：{tag_line or '#inbox'}",
            "",
            body.strip() or "（空）",
            "",
        ]
    )
    write_text(path, contents)
    return {"ok": True, "note": str(path)}


def command_daily(config: dict[str, Any], done: list[str], next_items: list[str], blockers: list[str]) -> dict[str, Any]:
    today = now_local().strftime("%Y-%m-%d")
    path = daily_dir(config) / f"{today}.md"
    if not path.exists():
        write_text(path, f"# {today}\n\n## 完成\n\n## 下一步\n\n## 卡点\n\n## 临时记录\n\n")

    def bullet(items: list[str]) -> str:
        return "".join(f"- {item}\n" for item in items if item.strip())

    entry = [
        f"\n## 助手追加 {now_local().strftime('%H:%M')}\n\n",
        "### 完成\n",
        bullet(done) or "- 暂无\n",
        "\n### 下一步\n",
        bullet(next_items) or "- 暂无\n",
        "\n### 卡点\n",
        bullet(blockers) or "- 暂无\n",
    ]
    append_text(path, "".join(entry))
    return {"ok": True, "daily": str(path)}


def command_action_note(config: dict[str, Any], title: str, domain: str, goal: str, source: str) -> dict[str, Any]:
    stamp = now_local().strftime("%Y%m%d-%H%M%S")
    path = knowledge_action_dir(config) / "Action" / f"{stamp} {safe_filename(title)}.md"
    contents = f"""# {title}

类型：Action
领域：{domain}
来源：{source}
创建时间：`{now_local().strftime('%Y-%m-%d %H:%M:%S %z')}`

## 目标

{goal}

## 任务背景

- 来源：{source}

## 行动过程

- 待补充。

## 任务成果

- 待验收。

## 相关资料

- {source}

## 下一步

- 明确第一步可执行动作。

## 验收标准

- 有明确产物。
- 有验证证据。
"""
    write_text(path, contents)
    return {"ok": True, "note": str(path)}


def read_source_snippet(source: str, limit: int = 700) -> str:
    if not source.strip():
        return ""
    path = Path(source).expanduser()
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return ""
    normalized = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return normalized[: limit - 1] + "…" if len(normalized) > limit else normalized


def useful_conclusion(conclusion: str, source: str) -> str:
    cleaned = conclusion.strip()
    if cleaned and cleaned not in {"待补充", "待补充。", "待补充关键结论"}:
        return cleaned
    snippet = read_source_snippet(source)
    if snippet:
        return snippet
    return "未提取到明确结论。请补充来源内容后再沉淀为知识卡。"


def command_card_note(config: dict[str, Any], title: str, domain: str, source: str, conclusion: str) -> dict[str, Any]:
    stamp = now_local().strftime("%Y%m%d-%H%M%S")
    path = knowledge_action_dir(config) / "Card" / f"{stamp} {safe_filename(title)}.md"
    final_conclusion = useful_conclusion(conclusion, source)
    if final_conclusion.startswith("未提取到明确结论"):
        return {
            "ok": False,
            "error": "没有可沉淀为知识卡的关键结论。请提供结论，或提供可读取的来源文件路径。",
        }
    source_label = source or "手动输入"
    conclusion_line = " ".join(final_conclusion.split())
    contents = f"""# {title}

类型：Card
领域：{domain}
来源：{source_label}
创建时间：`{now_local().strftime('%Y-%m-%d %H:%M:%S %z')}`

> 一句话结论：{conclusion_line}

## 主题

{title}

## 适用场景

- 需要复用这条经验、规则或资料时。
- 需要在搜索回顾或生成 AI 上下文包时快速找回这条结论时。

## 关键结论

- {conclusion_line}

## 下次怎么用

- 搜索相关关键词时优先查看这张卡。
- 生成 AI 上下文包时把这张卡作为候选来源。

## 来源

- {source_label}

## 验收标准

- 能被下一次任务直接引用。
- 保留来源，不覆盖原始资料。
"""
    write_text(path, contents)
    return {"ok": True, "note": str(path)}


def command_time_review(
    config: dict[str, Any],
    title: str,
    period: str,
    done: list[str],
    next_items: list[str],
) -> dict[str, Any]:
    stamp = now_local().strftime("%Y%m%d-%H%M%S")
    path = routine_dir(config) / "知识行动助手" / "Time" / f"{stamp} {safe_filename(title)}.md"

    def bullet(items: list[str]) -> str:
        return "".join(f"- {item}\n" for item in items if item.strip()) or "- 暂无\n"

    contents = f"""# {title}

类型：Time
周期：{period}
来源：知识行动助手
创建时间：`{now_local().strftime('%Y-%m-%d %H:%M:%S %z')}`

## 完成

{bullet(done)}
## 卡点

- 暂无

## 下一步

{bullet(next_items)}
## 归档候选

- 日复盘只记录候选，不批量处理；周复盘再集中处理。

## 结构调整

- 暂无。月复盘再评估结构是否需要调整。

## 验收标准

- 复盘没有制造额外整理负担。
- 下一步可执行。
"""
    write_text(path, contents)
    return {"ok": True, "note": str(path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Obsidian helper for the knowledge action assistant")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guide")

    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--write-note", action="store_true")

    capture = sub.add_parser("capture")
    capture.add_argument("--title", required=True)
    capture.add_argument("--body", default="")
    capture.add_argument("--tags", nargs="*", default=["inbox"])

    daily = sub.add_parser("daily")
    daily.add_argument("--done", action="append", default=[])
    daily.add_argument("--next", dest="next_items", action="append", default=[])
    daily.add_argument("--blocker", action="append", default=[])

    action = sub.add_parser("action")
    action.add_argument("--title", required=True)
    action.add_argument("--domain", default="工作")
    action.add_argument("--goal", required=True)
    action.add_argument("--source", default="手动输入")

    card = sub.add_parser("card")
    card.add_argument("--title", required=True)
    card.add_argument("--domain", default="学习")
    card.add_argument("--source", default="手动输入")
    card.add_argument("--conclusion", required=True)

    review = sub.add_parser("review")
    review.add_argument("--title", required=True)
    review.add_argument("--period", default="daily")
    review.add_argument("--done", action="append", default=[])
    review.add_argument("--next", dest="next_items", action="append", default=[])

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config))
    if args.command == "guide":
        result = command_guide(config)
    elif args.command == "ask":
        result = command_ask(config, args.question, args.write_note)
    elif args.command == "capture":
        result = command_capture(config, args.title, args.body, args.tags)
    elif args.command == "daily":
        result = command_daily(config, args.done, args.next_items, args.blocker)
    elif args.command == "action":
        result = command_action_note(config, args.title, args.domain, args.goal, args.source)
    elif args.command == "card":
        result = command_card_note(config, args.title, args.domain, args.source, args.conclusion)
    elif args.command == "review":
        result = command_time_review(config, args.title, args.period, args.done, args.next_items)
    else:
        raise ValueError(args.command)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
