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


def guide_path(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "projects", "02 项目") / folder_name(config, "codex_project", "Codex") / "11 Obsidian 新手使用指南.md"


def behavior_profile_path(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "projects", "02 项目") / folder_name(config, "codex_project", "Codex") / "12 Codex 线程行为画像与帮助策略.md"


def inbox_dir(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "inbox", "00 收件箱")


def daily_dir(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "daily", "01 今日日志")


def codex_overview_path(config: dict[str, Any]) -> Path:
    return vault_path(config) / folder_name(config, "projects", "02 项目") / folder_name(config, "codex_project", "Codex") / "00 Codex 总览.md"


def build_guide(config: dict[str, Any]) -> str:
    vault = vault_path(config)
    today = now_local().strftime("%Y-%m-%d")
    return f"""# Obsidian 新手使用指南

生成日期：`{today}`

## 先记住一句话

Obsidian 不需要一开始就搭复杂体系。你只要会做三件事：先丢进收件箱，每天做一次今日记录，重要内容再归到项目页。

## 你的当前库

- Obsidian 仓库：`{vault}`
- 收件箱：`{vault}\\00 收件箱`
- 今日日志：`{vault}\\01 今日日志`
- 项目：`{vault}\\02 项目`
- 会议：`{vault}\\03 会议`
- 例行工作：`{vault}\\04 例行工作`
- 模板：`{vault}\\90 模板`
- 归档：`{vault}\\99 归档`

## 每天怎么用

1. 有零碎想法、文件、链接、任务，先写进 `00 收件箱`。
2. 当天做过什么、卡在哪里、明天继续什么，写进 `01 今日日志`。
3. 能持续超过一天的事情，放进 `02 项目`。
4. 重复发生的流程和自动化，放进 `04 例行工作`。
5. 不确定放哪，就先放收件箱，不要停下来纠结分类。

## 现在这个助手能帮你做什么

在 `D:\\codex\\file-management-assistant` 里运行：

```powershell
python .\\obsidian_assistant.py guide
```

重新生成这份指南。

```powershell
python .\\obsidian_assistant.py ask \"我今天怎么记录工作？\"
```

回答 Obsidian 常见问题。

```powershell
python .\\obsidian_assistant.py capture --title \"一个想法\" --body \"先丢进收件箱，之后再整理。\" --tags idea
```

写入收件箱。

```powershell
python .\\obsidian_assistant.py daily --done \"完成文件管理助手\" --next \"继续整理工作流\" --blocker \"暂无\"
```

写入今天的日志。

## 我建议你的最小工作流

### 早上

- 打开 `01 今日日志`。
- 写今天最多 3 件要推进的事。
- 不要写很长，能指导今天行动就够。

### 工作中

- 临时想法直接 capture 到 `00 收件箱`。
- 文件管理助手每天自动生成复盘。
- 不要边做事边整理知识库，先保证工作不断流。

### 晚上

- 看今天的日志。
- 把已完成、未完成、卡住点各写 1-3 条。
- 能复用的流程再移动或链接到 `02 项目` / `04 例行工作`。

## 如何判断放哪里

| 内容 | 放哪里 |
| --- | --- |
| 临时想法、待处理材料 | `00 收件箱` |
| 今天做了什么 | `01 今日日志` |
| Codex / OpenClaw / 求职 / 文件管理助手这类持续事项 | `02 项目` |
| 会议纪要 | `03 会议` |
| 自动化、复盘、周期性检查 | `04 例行工作` |
| 固定格式 | `90 模板` |
| 阶段性完成、只需追溯的内容 | `99 归档` |

## 常见问题

### 我不会分类怎么办？

先放 `00 收件箱`。分类不是第一步，记录才是第一步。

### 我应该用标签还是文件夹？

新手先用文件夹。标签只用于状态或类型，比如 `#todo`、`#idea`、`#review`。

### 双链怎么用？

只在确实要跳转时用，例如 `[[09 文件管理助手流程归档]]`。不要为了“高级”到处乱链。

### 文件很多会乱吗？

会，所以当前助手每天会生成文件复盘，提醒哪些该归档、哪些该回看。

## 当前推荐入口

- [[00 Codex 总览]]
- [[09 文件管理助手流程归档]]
- [[10 高难长任务 Harness 复盘]]
- [[12 Codex 线程行为画像与帮助策略]]

## 当你需要帮助时，助手应该怎么做

你不需要先学会完整分类。直接把需求说出来，助手应按你的习惯处理：

| 你说 | 助手处理 |
| --- | --- |
| “这段帮我归档” | 判断放收件箱、今日日志、项目、例行工作还是归档，并写入文件 |
| “这个任务继续跑完” | 直接推进到产物和验证，不停在建议 |
| “这个自动任务还在跑吗” | 检查任务配置、最近运行、日志和产物 |
| “这个文件怎么整理” | 先读真实文件，再给分类和下一步 |
| “复盘一下” | 写失败原因、改进规则和后续检查点 |

## 下一步

你不用先学完 Obsidian。接下来只按这个顺序：

1. 有东西就丢收件箱。
2. 每天写今日日志。
3. 每周把收件箱里的内容归到项目或例行工作。
4. 需要问怎么放、怎么写、怎么找，就用 `ask` 或直接问我。
"""


def ensure_overview_link(config: dict[str, Any]) -> None:
    overview = codex_overview_path(config)
    if not overview.exists():
        return
    text = overview.read_text(encoding="utf-8")
    links = [
        "- [[11 Obsidian 新手使用指南]]",
        "- [[12 Codex 线程行为画像与帮助策略]]",
    ]
    marker = "- [[10 高难长任务 Harness 复盘]]"
    for link in links:
        if link in text:
            marker = link
            continue
        if marker in text:
            text = text.replace(marker, f"{marker}\n{link}")
            marker = link
        else:
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
        return "你可以问：怎么开始、怎么记录工作、怎么归档、怎么找东西、怎么写每日复盘。"

    if any(word in q for word in ["开始", "新手", "怎么用", "入门", "打开"]):
        return (
            f"先打开 Obsidian 仓库 `{vault}`。新手只做三步："
            "1. 零碎内容放 `00 收件箱`；2. 当天进展放 `01 今日日志`；"
            "3. 持续项目放 `02 项目`。不要一开始折腾复杂插件。"
        )
    if any(word in q for word in ["记录工作", "今日", "日报", "日志", "daily"]):
        return (
            "记录工作用 `daily`：写今天完成了什么、下一步是什么、卡点是什么。"
            "推荐命令：`python .\\obsidian_assistant.py daily --done \"完成事项\" --next \"下一步\" --blocker \"卡点\"`。"
        )
    if any(word in q for word in ["收件箱", "capture", "临时", "想法"]):
        return (
            "不确定放哪里时直接放 `00 收件箱`。"
            "推荐命令：`python .\\obsidian_assistant.py capture --title \"标题\" --body \"内容\" --tags idea`。"
        )
    if any(word in q for word in ["归档", "整理", "分类", "放哪"]):
        return (
            "归档规则：临时材料进 `00 收件箱`；今天过程进 `01 今日日志`；"
            "持续项目进 `02 项目`；会议进 `03 会议`；重复流程进 `04 例行工作`；"
            "阶段完成但需要追溯的内容进 `99 归档`。"
        )
    if any(word in q for word in ["习惯", "行为", "画像", "怎么帮我", "帮助我"]):
        return (
            "按本地行为画像处理：先查真实文件和真实状态，低风险任务直接推进，"
            "跨系统任务读回证据，最后把产物落盘并补入口。画像入口是 "
            f"`{behavior_profile_path(config)}`。"
        )
    if any(word in q for word in ["找", "搜索", "查", "链接", "双链"]):
        return (
            "找东西优先用 Obsidian 全局搜索；确定是持续项目时看 `02 项目`。"
            "双链只链接真正会复用的页面，例如 `[[09 文件管理助手流程归档]]`。"
        )
    if any(word in q for word in ["模板", "格式"]):
        return (
            "模板放 `90 模板`。新手先别追求复杂模板，先固定三段："
            "`完成了什么`、`下一步`、`卡点`。"
        )
    if any(word in q for word in ["助手", "自动", "文件管理"]):
        return (
            "文件管理助手负责每天扫描文件、生成 HTML/Markdown/JSON 报告、写 Obsidian 复盘并发飞书。"
            "Obsidian 使用助手负责生成指南、写收件箱、写今日日志、读取本地行为画像并回答常见用法问题。"
        )

    return (
        "这个问题我会按最小 Obsidian 工作流处理：先判断是临时输入、当天记录、持续项目、会议还是例行流程。"
        "如果你不确定，先放 `00 收件箱`，晚点再整理。"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Obsidian helper for the file management assistant")
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
    else:
        raise ValueError(args.command)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
