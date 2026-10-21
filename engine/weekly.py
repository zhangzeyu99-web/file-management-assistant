"""Freeze weekly archive coverage; advance it only after delivery acceptance.

Source checkpoints remain authoritative for pending work, including evidence
older than the reporting window. Opening a window never changes those
checkpoints or claims that a first-run baseline was successfully processed.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .incremental import atomic_json, writer_lock


STATE_FILENAME = "weekly-archive.json"
TIMEZONE = "Asia/Shanghai"


class WeeklyArchiveError(ValueError):
    pass


def _time(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise WeeklyArchiveError("周归档时间格式无效。") from None
    else:
        raise WeeklyArchiveError("周归档时间必须是带时区的 ISO 时间。")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WeeklyArchiveError("周归档时间必须包含时区。")
    return parsed.astimezone(timezone.utc)


def _receipt_passed(receipt):
    return (isinstance(receipt, dict) and receipt.get("job_status") == "completed"
            and all(receipt.get(key) is True for key in
                    ("quality_checked", "local_readback", "online_synced")))


def _load(data_root):
    path = Path(data_root) / STATE_FILENAME
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise WeeklyArchiveError("周归档验收记录不可读；请修复后继续，不能重置水位。") from None
    if not isinstance(state, dict) or state.get("version") != 1:
        raise WeeklyArchiveError("周归档验收记录版本无效，不能重置水位。")
    accepted = _time(state.get("accepted_until"))
    success = state.get("last_success")
    if (not isinstance(success, dict) or not isinstance(success.get("job_id"), str)
            or not success["job_id"].strip() or not _receipt_passed(success.get("receipt"))):
        raise WeeklyArchiveError("周归档水位缺少成功验收依据，不能假定已完成。")
    _, until = _window(success.get("window"))
    if until != accepted or _time(success.get("accepted_at")) < until:
        raise WeeklyArchiveError("周归档水位与验收依据不一致。")
    return state


def _window(value):
    if not isinstance(value, dict) or value.get("version") != 1 or value.get("timezone") != TIMEZONE:
        raise WeeklyArchiveError("周归档窗口格式无效。")
    since, until = _time(value.get("since")), _time(value.get("until"))
    if until <= since:
        raise WeeklyArchiveError("周归档窗口终点必须晚于起点。")
    if not isinstance(value.get("first_run"), bool):
        raise WeeklyArchiveError("周归档窗口缺少首次基线标记。")
    if value.get("checkpoint_debt") != "retain":
        raise WeeklyArchiveError("周归档窗口必须保留既有检查点欠账。")
    if value.get("catch_up") is not (until - since > timedelta(days=7)):
        raise WeeklyArchiveError("周归档窗口补齐标记与范围不符。")
    return since, until


def open_window(data_root, baseline_at, now, previous_window=None):
    """Return one frozen interval without registering successful coverage.

    Use the last accepted endpoint even after missed weeks. For a first run,
    use the later of the existing baseline and seven days ago only as the
    reporting start: pending source checkpoints must never be date-filtered
    away. A journal's previous_window is returned unchanged on job retry.
    """
    until = _time(now)
    state = _load(data_root)
    accepted = _time(state["accepted_until"]) if state else None
    if previous_window is not None:
        since, frozen_until = _window(previous_window)
        if frozen_until > until:
            raise WeeklyArchiveError("重试时间早于已冻结窗口终点。")
        # Reopening an already accepted job is useful for idempotent finalize.
        if accepted and accepted != since and accepted != frozen_until:
            raise WeeklyArchiveError("已冻结窗口与当前验收水位冲突，不能重建范围。")
        return copy.deepcopy(previous_window)
    if accepted:
        since = accepted
    else:
        since = max(_time(baseline_at), until - timedelta(days=7))
    if until <= since:
        raise WeeklyArchiveError("当前没有可开启的后续窗口，验收水位不能倒退。")
    return {
        "version": 1,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "timezone": TIMEZONE,
        "first_run": state is None,
        "catch_up": until - since > timedelta(days=7),
        "checkpoint_debt": "retain",
    }


def advance_window(data_root, window, job_id, *, verified, receipt, accepted_at):
    """Commit coverage after the caller verifies actual job and delivery data.

    This is deliberately separate from source processing: completed model
    output or local checkpoint writes alone cannot advance weekly coverage.
    The caller must read back the real job status and quality/local/cloud
    delivery evidence before supplying this receipt.
    """
    since, until = _window(window)
    if not isinstance(job_id, str) or not job_id.strip():
        raise WeeklyArchiveError("周归档验收必须关联真实任务。")
    if verified is not True or not _receipt_passed(receipt):
        raise WeeklyArchiveError("任务、质量检查、本机读回与线上同步均通过后才能推进周归档水位。")
    accepted_time = _time(accepted_at)
    if accepted_time < until:
        raise WeeklyArchiveError("验收时间不能早于归档窗口终点。")
    root = Path(data_root)
    with writer_lock(root / "weekly-archive.lock"):
        state = _load(root)
        if state:
            accepted = _time(state["accepted_until"])
            previous = state.get("last_success", {})
            if (accepted == until and previous.get("job_id") == job_id
                    and previous.get("window") == window):
                return copy.deepcopy(state)
            if until <= accepted:
                raise WeeklyArchiveError("该窗口已过期，不能覆盖或回退周归档验收水位。")
            if since != accepted:
                raise WeeklyArchiveError("归档窗口必须从上次验收终点连续接续，不能跳过或重叠范围。")
            if window["first_run"]:
                raise WeeklyArchiveError("已有验收记录，不能再按首次基线推进。")
        elif not window["first_run"]:
            raise WeeklyArchiveError("缺少既有周归档验收记录，不能假定历史范围已完成。")
        result = {
            "version": 1,
            "accepted_until": until.isoformat(),
            "last_success": {
                "job_id": job_id,
                "window": copy.deepcopy(window),
                "accepted_at": accepted_time.isoformat(),
                "receipt": copy.deepcopy(receipt),
            },
        }
        target = root / STATE_FILENAME
        atomic_json(target, result)
        if _load(root) != result:
            raise WeeklyArchiveError("周归档验收记录读回不一致。")
        return result
