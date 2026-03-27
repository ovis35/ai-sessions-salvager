#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _progress(idx: int, total: int, label: str, title: str) -> None:
    width = len(str(total))
    short_title = title[:60] + "…" if len(title) > 60 else title
    print(f"[{idx:{width}d}/{total}] {label:<10} {short_title}", flush=True)


@dataclass
class NormalizedMessage:
    role: str
    content: str
    timestamp: Optional[str] = None


@dataclass
class NormalizedConversation:
    id: str
    source: str
    title: str
    created_at: Optional[str]
    updated_at: Optional[str]
    messages: List[NormalizedMessage]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", value)[:80]


def infer_format(data: Any) -> str:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        if "mapping" in data[0] or "conversation_id" in data[0]:
            return "chatgpt"
        if "chat_messages" in data[0] or "uuid" in data[0]:
            return "claude"

    if isinstance(data, dict) and isinstance(data.get("conversations"), list):
        conversations = data.get("conversations", [])
        if conversations and isinstance(conversations[0], dict):
            first = conversations[0]
            if "mapping" in first or "conversation_id" in first:
                return "chatgpt"
            if "chat_messages" in first or "uuid" in first:
                return "claude"
        return "unknown"

    return "unknown"


def parse_chatgpt(data: Any) -> List[NormalizedConversation]:
    conversations = data if isinstance(data, list) else data.get("conversations", [])
    out: List[NormalizedConversation] = []
    for c in conversations:
        mapping = c.get("mapping", {})
        messages: List[NormalizedMessage] = []
        if isinstance(mapping, dict) and mapping:
            nodes = list(mapping.values())
            nodes.sort(key=lambda n: (n.get("message", {}).get("create_time") or 0))
            for node in nodes:
                msg = node.get("message") or {}
                author = (msg.get("author") or {}).get("role", "unknown")
                content = msg.get("content") or {}
                parts = content.get("parts", []) if isinstance(content, dict) else []
                text = "\n".join([p for p in parts if isinstance(p, str)]).strip()
                if not text:
                    continue
                ct = msg.get("create_time")
                ts = (
                    datetime.fromtimestamp(ct, tz=timezone.utc).isoformat()
                    if isinstance(ct, (int, float))
                    else None
                )
                messages.append(
                    NormalizedMessage(role=author, content=text, timestamp=ts)
                )
        elif "messages" in c:
            for m in c.get("messages", []):
                text = m.get("content", "")
                if text:
                    messages.append(
                        NormalizedMessage(
                            role=m.get("role", "unknown"),
                            content=text,
                            timestamp=m.get("timestamp"),
                        )
                    )

        cid = (
            c.get("id")
            or c.get("conversation_id")
            or hashlib.sha1(
                (c.get("title", "") + str(c.get("create_time", ""))).encode()
            ).hexdigest()[:12]
        )
        out.append(
            NormalizedConversation(
                id=str(cid),
                source="chatgpt",
                title=c.get("title") or "Untitled",
                created_at=(
                    datetime.fromtimestamp(
                        c.get("create_time"), tz=timezone.utc
                    ).isoformat()
                    if isinstance(c.get("create_time"), (int, float))
                    else None
                ),
                updated_at=(
                    datetime.fromtimestamp(
                        c.get("update_time"), tz=timezone.utc
                    ).isoformat()
                    if isinstance(c.get("update_time"), (int, float))
                    else None
                ),
                messages=messages,
            )
        )
    return out


def parse_claude(data: Any) -> List[NormalizedConversation]:
    conversations = data if isinstance(data, list) else data.get("conversations", [])
    out: List[NormalizedConversation] = []
    for c in conversations:
        msgs = c.get("chat_messages", c.get("messages", []))
        messages: List[NormalizedMessage] = []
        for m in msgs:
            text = m.get("text") or m.get("content") or ""
            if isinstance(text, list):
                text = "\n".join(
                    [t.get("text", "") if isinstance(t, dict) else str(t) for t in text]
                )
            if not str(text).strip():
                continue
            role = m.get("sender") or m.get("role") or "unknown"
            ts = m.get("created_at") or m.get("timestamp")
            messages.append(
                NormalizedMessage(role=role, content=str(text).strip(), timestamp=ts)
            )

        cid = (
            c.get("uuid")
            or c.get("id")
            or hashlib.sha1(
                (c.get("name", "") + str(c.get("created_at", ""))).encode()
            ).hexdigest()[:12]
        )
        out.append(
            NormalizedConversation(
                id=str(cid),
                source="claude",
                title=c.get("name") or c.get("title") or "Untitled",
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
                messages=messages,
            )
        )
    return out


def normalize(data: Any, fmt: str) -> List[NormalizedConversation]:
    if fmt == "auto":
        fmt = infer_format(data)
        if fmt == "unknown":
            raise ValueError(
                "Could not infer format from input. Please specify --format chatgpt or --format claude."
            )
    if fmt == "chatgpt":
        return parse_chatgpt(data)
    if fmt == "claude":
        return parse_claude(data)
    raise ValueError(
        "Unsupported format. Use --format chatgpt|claude or provide supported export."
    )


def render_markdown(conv: NormalizedConversation) -> str:
    lines = [
        f"# {conv.title}",
        "",
        f"- id: {conv.id}",
        f"- source: {conv.source}",
        f"- created_at: {conv.created_at or ''}",
        f"- updated_at: {conv.updated_at or ''}",
        f"- message_count: {len(conv.messages)}",
        "",
        "---",
        "",
    ]
    for idx, m in enumerate(conv.messages, start=1):
        lines.extend(
            [
                f"## Message {idx}",
                f"**role:** {m.role}",
                f"**time:** {m.timestamp or ''}",
                "",
                m.content,
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def truncate_messages(messages: List[NormalizedMessage], max_chars: int = 18000) -> str:
    joined = []
    for m in messages:
        joined.append(f"[{m.role}] {m.content}")
    text = "\n\n".join(joined)
    return text[:max_chars]


def call_openai_chat(
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 120,
) -> Dict[str, Any]:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def call_claude_chat(
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 120,
) -> Dict[str, Any]:
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["content"][0]["text"]
    # Strip markdown code fences if present
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Remove opening fence (```json or ```)
        lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return json.loads(stripped)


def call_llm(
    provider: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> Dict[str, Any]:
    if provider == "openai":
        return call_openai_chat(
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    if provider == "anthropic":
        return call_claude_chat(
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    raise ValueError(f"Unsupported provider: {provider!r}. Supported: openai, anthropic")


def normalize_text_list(value: Any, max_items: int) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            cleaned.append(text)
    return cleaned[:max_items]


def is_no_action_step(step: str) -> bool:
    text = step.strip().lower()
    if text in {"暫不行動", "no action", "none", "n/a"}:
        return True
    return "暫不行動" in text or "不需行動" in text


def has_actionable_next_steps(next_steps: List[str]) -> bool:
    if not next_steps:
        return False
    return any(not is_no_action_step(step) for step in next_steps)


def residual_asset_strength(residual: str) -> int:
    text = residual.strip().lower()
    if not text:
        return 0
    strong_markers = [
        "框架",
        "流程",
        "映射",
        "門檻",
        "判準",
        "條件",
        "原則",
        "規則",
        "檢核",
        "指標",
        "kpi",
        "決策",
        "清單",
        "模型",
        "framework",
        "mapping",
        "threshold",
        "criteria",
        "principle",
        "checklist",
        "metric",
        "rule",
    ]
    score = sum(1 for marker in strong_markers if marker in text)
    if re.search(r"(?:ltv|cac|arr|pmf|\d)", text):
        score += 1
    if "：" in residual or ":" in residual:
        score += 1
    return score


def residual_is_work_system_worthy(residual: str) -> bool:
    return residual_asset_strength(residual) >= 2


def build_work_system_signals(residuals: List[str]) -> Dict[str, Any]:
    strengths = [residual_asset_strength(item) for item in residuals]
    work_system_count = sum(1 for score in strengths if score >= 2)
    strong_asset_count = sum(1 for score in strengths if score >= 3)
    return {
        "work_system_count": work_system_count,
        "has_work_system_residual": work_system_count > 0,
        "strong_asset_count": strong_asset_count,
        "has_strong_residual_asset": strong_asset_count > 0,
    }


def can_promote_to_b(signals: Dict[str, Any]) -> bool:
    if signals.get("has_b_blocker_semantics"):
        return False
    if not signals["has_actionable_steps"]:
        return False
    if signals["residual_count"] >= 2 and signals["has_work_system_residual"]:
        return True
    if signals["residual_count"] == 1 and signals["has_work_system_residual"]:
        return True
    return False


def can_stay_b(signals: Dict[str, Any]) -> bool:
    return can_promote_to_b(signals) and not signals.get("has_b_blocker_semantics", False)


def can_keep_a(signals: Dict[str, Any]) -> bool:
    return (
        signals["residual_count"] >= 2
        and signals["has_actionable_steps"]
        and signals["has_work_system_residual"]
        and not signals["partial_salvage"]
    )


def detect_verdict_semantics(verdict: str) -> Dict[str, bool]:
    text = verdict.strip().lower()
    not_worth_markers = [
        "不值得保存",
        "不值得留",
        "不必保存",
        "整體不值得",
        "資訊密度太低",
        "資訊密度不高",
        "普通問答",
        "流水帳",
        "not worth",
        "low information",
    ]
    partial_markers = [
        "只有局部",
        "局部可留",
        "其餘多為普通",
        "需重寫才值得留",
        "部分可留",
        "僅留一點",
        "partial salvage",
        "thin residual",
        "needs rewrite",
    ]
    explicit_not_worth = any(marker in text for marker in not_worth_markers)
    partial_salvage = any(marker in text for marker in partial_markers)
    insufficient_readiness_markers = [
        "尚不足直接進入工作系統",
        "未達可直接進入工作系統",
        "難直接進入工作系統",
        "尚不足直接採用",
        "未達可直接採用",
        "未達可直接落地",
        "not yet ready for direct use",
        "not ready for work system",
        "not ready for direct adoption",
    ]
    partial_only_markers = [
        "僅局部可摘用",
        "僅部分可留",
        "勉強可留",
        "勉強可摘錄",
        "只適合摘錄",
        "只能局部保留",
        "only partially salvageable",
        "only suitable for excerpting",
    ]
    concept_or_draft_markers = [
        "仍停在概念層",
        "只是草案",
        "只是一般整理",
        "只是初步整理",
        "still too conceptual",
        "draft only",
    ]
    has_insufficient_readiness = any(marker in text for marker in insufficient_readiness_markers)
    has_partial_only = any(marker in text for marker in partial_only_markers)
    has_concept_or_draft = any(marker in text for marker in concept_or_draft_markers)
    indicates_partial = (
        "局部" in text
        or "部分" in text
        or "partial" in text
        or "摘錄" in text
        or "excerpt" in text
    )
    mentions_work_system_gate = (
        "工作系統" in text
        or "直接採用" in text
        or "直接落地" in text
        or "direct use" in text
        or "work system" in text
        or "direct adoption" in text
    )
    has_b_blocker_semantics = (
        has_insufficient_readiness
        or has_partial_only
        or (has_concept_or_draft and (indicates_partial or mentions_work_system_gate))
    )
    return {
        "explicit_not_worth": explicit_not_worth,
        "partial_salvage": partial_salvage,
        "has_b_blocker_semantics": has_b_blocker_semantics,
    }


def _has_any_marker(text: str, markers: List[str]) -> bool:
    return any(marker in text for marker in markers)


def verdict_has_mixed_signals(verdict: str) -> bool:
    text = verdict.strip().lower()
    if not text:
        return False
    positive_markers = [
        "可留",
        "可用",
        "可直接",
        "可落地",
        "可採用",
        "值得保留",
        "可進入",
        "足以進入",
        "usable",
        "ready",
        "actionable",
    ]
    negative_markers = [
        "不足",
        "不宜",
        "有限",
        "不值得整段保存",
        "尚不足",
        "難直接",
        "僅局部",
        "only partial",
        "not ready",
        "not enough",
    ]
    return _has_any_marker(text, positive_markers) and _has_any_marker(
        text, negative_markers
    )


def build_salvage_signals(obj: Dict[str, Any]) -> Dict[str, Any]:
    residuals = normalize_text_list(obj.get("valuable_residuals"), max_items=3)
    next_steps = normalize_text_list(obj.get("next_steps"), max_items=2)
    verdict = str(obj.get("verdict", "")).strip()
    semantics = detect_verdict_semantics(verdict)
    residual_count = len(residuals)
    actionable = has_actionable_next_steps(next_steps)
    thin_residual = residual_count <= 1
    work_system_signals = build_work_system_signals(residuals)
    return {
        "residuals": residuals,
        "next_steps": next_steps,
        "verdict": verdict,
        "residual_count": residual_count,
        "has_actionable_steps": actionable,
        "thin_residual": thin_residual,
        **work_system_signals,
        **semantics,
    }


def needs_second_pass(result: Dict[str, Any]) -> bool:
    route = str(result.get("route_recommendation", "")).strip().upper()
    if route not in {"B", "C"}:
        return False
    signals = build_salvage_signals(result)
    mixed_verdict = verdict_has_mixed_signals(signals["verdict"])
    low_residual_but_actionable = (
        signals["residual_count"] <= 1 and signals["has_actionable_steps"]
    )
    richer_residual_with_blocker = (
        signals["residual_count"] >= 2 and signals["has_b_blocker_semantics"]
    )
    uncertain_boundary = (
        signals["partial_salvage"]
        and signals["has_actionable_steps"]
        and signals["residual_count"] > 0
    )
    return any(
        [
            mixed_verdict,
            low_residual_but_actionable,
            richer_residual_with_blocker,
            uncertain_boundary,
        ]
    )


def normalize_salvage_analysis(obj: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(obj)
    normalized["topic"] = str(normalized.get("topic", "")).strip()
    normalized["drift_point"] = str(normalized.get("drift_point", "")).strip()
    normalized["verdict"] = str(normalized.get("verdict", "")).strip()
    normalized["valuable_residuals"] = normalize_text_list(
        normalized.get("valuable_residuals"), max_items=3
    )
    normalized["next_steps"] = normalize_text_list(normalized.get("next_steps"), max_items=2)

    route = str(normalized.get("route_recommendation", "")).strip().upper()
    signals = build_salvage_signals(normalized)

    if signals["explicit_not_worth"] or (
        signals["residual_count"] == 0 and not signals["has_actionable_steps"]
    ):
        route = "D"
    elif route == "A":
        route = "A" if can_keep_a(signals) else ("B" if can_stay_b(signals) else "C")
    elif route == "B":
        route = "B" if can_stay_b(signals) else ("D" if signals["residual_count"] == 0 else "C")
    elif route == "C" and can_stay_b(signals):
        route = "B"
    elif route in {"A", "B", "C"} and signals["has_b_blocker_semantics"]:
        route = "C"
    elif signals["thin_residual"] and not signals["has_actionable_steps"]:
        route = "C"
    elif route not in {"C", "D"}:
        route = "C"

    normalized["route_recommendation"] = route
    return normalized


def build_calibration_prompt(
    conv: NormalizedConversation, first_pass: Dict[str, Any]
) -> Tuple[str, str]:
    initial_route = str(first_pass.get("route_recommendation", "")).strip().upper()
    system_prompt = (
        "你是 second-pass overrating adjudicator。\n"
        "你的任務不是背書 first-pass，而是檢查此案例是否被高估。\n"
        "first-pass JSON 只是待審主張，不是可信答案；conversation excerpt 才是反證來源。\n"
        "若 verdict 出現『僅局部可摘錄/僅少量可留/保存價值有限/尚不足直接進入工作系統』等語義，預設降為 C。\n"
        "只有在殘留內容足以直接寫入方法筆記、規格、決策紀錄時，才可保留 B。\n"
        "若不確定，降級，不升級。\n"
        "判準：A=高價值且較完整，可直接保存為長期知識；"
        "B=雖不完整但殘留已足以進入工作系統；"
        "C=只有局部可摘錄，尚不足進入工作系統；"
        "D=整體不值得保存。\n"
        "只輸出 JSON，且 key 必須且只能是：final_route, reason, confidence。\n"
        "final_route 只能是 A/B/C/D。confidence 只能是 low/medium/high。"
    )
    compact_first_pass = {
        "initial_route_recommendation": initial_route,
        "topic": first_pass.get("topic", ""),
        "valuable_residuals": first_pass.get("valuable_residuals", []),
        "drift_point": first_pass.get("drift_point", ""),
        "next_steps": first_pass.get("next_steps", []),
        "route_recommendation": first_pass.get("route_recommendation", ""),
        "verdict": first_pass.get("verdict", ""),
    }
    user_prompt = (
        "請只做 overrating 仲裁，不要重做摘要或 extraction。\n"
        "initial_route_recommendation 是待審對象，不是既定答案。\n\n"
        f"Title: {conv.title}\n"
        f"First-pass salvage JSON:\n{json.dumps(compact_first_pass, ensure_ascii=False)}\n\n"
        f"Conversation excerpt:\n{truncate_messages(conv.messages, max_chars=3500)}"
    )
    return system_prompt, user_prompt


def second_pass_judge(
    conv: NormalizedConversation,
    first_pass: Dict[str, Any],
    model: str,
    provider: str,
    api_key: str,
) -> Dict[str, str]:
    system_prompt, user_prompt = build_calibration_prompt(conv, first_pass)
    calibration = call_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    final_route = str(calibration.get("final_route", "")).strip().upper()
    if final_route not in {"A", "B", "C", "D"}:
        raise ValueError("invalid_second_pass_final_route")
    confidence = str(calibration.get("confidence", "")).strip().lower()
    if confidence not in {"low", "medium", "high"}:
        raise ValueError("invalid_second_pass_confidence")
    reason = str(calibration.get("reason", "")).strip()
    if not reason:
        raise ValueError("invalid_second_pass_reason")
    signals = build_salvage_signals(first_pass)
    initial_route = str(first_pass.get("route_recommendation", "")).strip().upper()

    can_strongly_upgrade_c_to_b = (
        can_stay_b(signals)
        and signals["residual_count"] >= 2
        and signals["has_strong_residual_asset"]
    )
    if initial_route == "B":
        allowed_routes = {"B", "C", "D"}
    elif initial_route == "C":
        allowed_routes = {"C", "D"}
        if can_strongly_upgrade_c_to_b:
            allowed_routes.add("B")
    else:
        allowed_routes = {"A", "B", "C", "D"}

    if final_route not in allowed_routes:
        final_route = "C" if initial_route in {"B", "C"} else initial_route
        reason = f"{reason}；direction_guard_fallback"
        confidence = "high"

    if final_route == "B" and signals["has_b_blocker_semantics"]:
        final_route = "C"
        reason = f"{reason}；hard_rule_b_blocker"
        confidence = "high"
    return {
        "final_route": final_route,
        "confidence": confidence,
        "reason": reason,
    }


def finalize_salvage_result(
    first_pass: Dict[str, Any],
    calibration: Optional[Dict[str, str]] = None,
    calibration_error: Optional[str] = None,
) -> Dict[str, Any]:
    finalized = dict(first_pass)
    initial_route = str(first_pass.get("route_recommendation", "")).strip().upper()
    finalized["initial_route_recommendation"] = initial_route
    finalized["calibration_applied"] = False
    finalized["calibration_confidence"] = ""
    finalized["calibration_reason"] = ""
    finalized["final_route_recommendation"] = initial_route
    if calibration:
        final_route = calibration["final_route"]
        finalized["route_recommendation"] = final_route
        finalized["final_route_recommendation"] = final_route
        finalized["calibration_reason"] = calibration["reason"]
        finalized["calibration_confidence"] = calibration["confidence"]
        finalized["calibration_applied"] = True
    elif calibration_error:
        finalized["calibration_reason"] = calibration_error
    return finalized


def validate_analysis(obj: Dict[str, Any], analysis_schema: str) -> Tuple[bool, str]:
    if analysis_schema == "salvage":
        required = [
            "topic",
            "valuable_residuals",
            "drift_point",
            "next_steps",
            "route_recommendation",
            "verdict",
        ]
    else:
        required = ["summary", "tags", "language", "quality_score"]

    for k in required:
        if k not in obj:
            return False, f"missing_{k}"

    if analysis_schema == "salvage":
        if not isinstance(obj["topic"], str) or not obj["topic"].strip():
            return False, "invalid_topic"

        if not isinstance(obj["valuable_residuals"], list):
            return False, "invalid_valuable_residuals"
        if len(obj["valuable_residuals"]) > 3:
            return False, "too_many_valuable_residuals"
        if any(
            not isinstance(item, str) or not item.strip()
            for item in obj["valuable_residuals"]
        ):
            return False, "invalid_valuable_residuals_item"

        if not isinstance(obj["drift_point"], str) or not obj["drift_point"].strip():
            return False, "invalid_drift_point"

        if not isinstance(obj["next_steps"], list):
            return False, "invalid_next_steps"
        if len(obj["next_steps"]) > 2:
            return False, "too_many_next_steps"
        if obj["next_steps"] == ["暫不行動"]:
            pass
        elif any(not isinstance(item, str) or not item.strip() for item in obj["next_steps"]):
            return False, "invalid_next_steps_item"

        if obj["route_recommendation"] not in {"A", "B", "C", "D"}:
            return False, "invalid_route_recommendation"

        if not isinstance(obj["verdict"], str) or not obj["verdict"].strip():
            return False, "invalid_verdict"

        signals = build_salvage_signals(obj)
        route = obj["route_recommendation"]

        if signals["residual_count"] == 0 and not signals["has_actionable_steps"] and route != "D":
            return False, "semantic_empty_must_be_d"

        if route == "A":
            if not can_keep_a(signals):
                return False, "semantic_a_requires_strong_residuals"
            if signals["partial_salvage"]:
                return False, "semantic_a_reject_partial_salvage"

        if route == "B" and not can_stay_b(signals):
            if signals["has_b_blocker_semantics"]:
                return False, "semantic_b_blocker_forces_c"
            return False, "semantic_b_requires_actionable_work_system_value"

        if (
            signals["thin_residual"]
            and not signals["has_actionable_steps"]
            and route in {"A", "B"}
        ):
            return False, "semantic_thin_residual_c_or_d_only"

        if signals["explicit_not_worth"] and route != "D":
            return False, "semantic_not_worth_must_be_d"

        if signals["partial_salvage"] and route == "A":
            return False, "semantic_partial_salvage_not_a"

        if signals["has_b_blocker_semantics"] and route in {"A", "B"}:
            return False, "semantic_blocker_not_a_or_b"
    else:
        if not isinstance(obj["summary"], str) or not obj["summary"].strip():
            return False, "invalid_summary"
        if not isinstance(obj["tags"], list) or not obj["tags"]:
            return False, "invalid_tags"
        if not isinstance(obj["language"], str) or not obj["language"].strip():
            return False, "invalid_language"
        if not isinstance(obj["quality_score"], (int, float)):
            return False, "invalid_quality_score"

    return True, "ok"


def build_analysis_prompts(
    conv: NormalizedConversation, analysis_schema: str
) -> Tuple[str, str]:
    if analysis_schema == "salvage":
        system_prompt = (
            "你是對話殘渣打撈器。目標是 residue salvage，不是一般摘要。\n"
            "評分預設請偏向 C 或 D。A/B 必須稀少，只有證據非常明確才可使用。\n"
            "若不確定，往低評，不往高評。不要因為回覆完整、漂亮、有條理而高估價值。\n"
            "請嚴格、克制、少廢話，只輸出真正值得留下的內容。不要討好，不要美化普通內容，不要重述整段聊天。\n"
            "普通問答、一般翻譯、課後對答案、資訊整理、客套鼓勵、模糊靈感、無後續影響討論，通常直接判 D。\n"
            "partial salvage 代表不是 A，但不等於一定是 C：若殘留部分已足以進入工作系統，仍可判 B。\n"
            "B 的關鍵不是完整度，而是是否可直接進入專案筆記、規格、任務、方法清單、決策紀錄。\n"
            "不要把「單一高價值可執行框架/門檻/原則 + 明確下一步」過度壓成 C。\n"
            "valuable_residuals 寧缺勿濫；next_steps 只保留有壓力且可執行的下一步。\n"
            "盡量將整體結果控制在 250 個中文字以內。\n"
            "只輸出 JSON 物件，且 key 必須且只能是："
            "topic, valuable_residuals, drift_point, next_steps, route_recommendation, verdict。\n"
            "規則：\n"
            "- topic：一句話，描述實際在處理什麼。\n"
            "- valuable_residuals：0-3 條；每條只能是 新觀點/框架、值得保留的好句或命名、有幫助的明確判斷/決策；沒價值就 []。\n"
            "- drift_point：一句話指出最明顯帶偏；沒有就必須是「無明顯帶偏」。\n"
            "- next_steps：0-2 條最值得做的具體下一步；若不值得行動就 [\"暫不行動\"]；避免空泛建議。\n"
            "- route_recommendation：只能是 A/B/C/D 其中一個。\n"
            "  A=高價值且可直接保存為長期知識、原則、模型、框架；"
            "  B=未必完整或原創，但已具明確執行價值，可直接進入專案、規格、任務、方法清單、決策紀錄；"
            "    常見是可重複流程/框架/映射、可執行門檻或量化條件、可直接採用的操作/談判原則或風險檢核；"
            "  C=只有局部殘留可救，通常只值得摘一句，尚不足以進入工作系統；"
            "  D=整體不值得保存，或資訊密度太低，或只是普通內容。\n"
            "- verdict：一句更銳利但準確的判決，必須直接說清楚是否值得保存。"
        )
        user_prompt = (
            "請依規則輸出殘渣打撈結果。記住：預設 C/D，A/B 需高門檻證據。\n\n"
            f"Title: {conv.title}\n"
            f"Conversation:\n{truncate_messages(conv.messages)}"
        )
        return system_prompt, user_prompt

    system_prompt = (
        "Return JSON only. Be strict, restrained, and concise. Do not flatter. Do not pad weak material.\n"
        "Required keys: summary, tags, language, quality_score.\n"
        "Rules: summary concise; tags is an array (1-12); language is a locale-like code; quality_score is 0-100."
    )
    user_prompt = (
        "Analyze this conversation.\n\n"
        f"Title: {conv.title}\n"
        f"Conversation:\n{truncate_messages(conv.messages)}"
    )
    return system_prompt, user_prompt


def failed_analysis_result(analysis_schema: str, error: str) -> Dict[str, Any]:
    if analysis_schema == "salvage":
        return {
            "schema": analysis_schema,
            "status": "failed",
            "topic": "",
            "valuable_residuals": [],
            "drift_point": "",
            "next_steps": [],
            "route_recommendation": "",
            "initial_route_recommendation": "",
            "final_route_recommendation": "",
            "calibration_reason": "",
            "calibration_confidence": "",
            "calibration_applied": False,
            "verdict": "",
            "error": error,
        }
    return {
        "schema": analysis_schema,
        "status": "failed",
        "summary": "",
        "tags": [],
        "language": "",
        "quality_score": 0,
        "error": error,
    }


def analyze_conversation(
    conv: NormalizedConversation,
    model: str,
    provider: str,
    api_key: str,
    retries: int,
    analysis_schema: str,
) -> Dict[str, Any]:
    system_prompt, user_prompt = build_analysis_prompts(conv, analysis_schema)
    last_error = "unknown"
    for i in range(retries + 1):
        try:
            first_pass = call_llm(
                provider=provider,
                model=model,
                api_key=api_key,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            if analysis_schema == "salvage":
                first_pass = normalize_salvage_analysis(first_pass)
            ok, reason = validate_analysis(first_pass, analysis_schema=analysis_schema)
            if ok:
                if analysis_schema != "salvage":
                    return {"schema": analysis_schema, "status": "ok", **first_pass}

                finalized = finalize_salvage_result(first_pass)
                if needs_second_pass(first_pass):
                    try:
                        calibration = second_pass_judge(
                            conv=conv,
                            first_pass=first_pass,
                            model=model,
                            provider=provider,
                            api_key=api_key,
                        )
                        finalized = finalize_salvage_result(
                            first_pass, calibration=calibration
                        )
                    except Exception:
                        finalized = finalize_salvage_result(
                            first_pass, calibration_error="second_pass_failed"
                        )

                final_route = finalized.get("route_recommendation", "")
                if final_route not in {"A", "B", "C", "D"}:
                    finalized = finalize_salvage_result(
                        first_pass, calibration_error="invalid_final_route_fallback"
                    )
                return {"schema": analysis_schema, "status": "ok", **finalized}
            last_error = reason
        except Exception as e:
            last_error = str(e)
        if i < retries:
            time.sleep(2**i)
    return failed_analysis_result(analysis_schema=analysis_schema, error=last_error)


def write_index_row(index_path: Path, row: Dict[str, Any]) -> None:
    exists = index_path.exists()
    fields = [
        "id",
        "title",
        "source",
        "md_file",
        "analysis_file",
        "route_recommendation",
        "initial_route_recommendation",
        "final_route_recommendation",
        "calibration_applied",
        "calibration_confidence",
        "verdict",
        "valuable_residual_count",
        "next_steps_count",
        "primary_text",
        "summary",
        "tags",
        "status",
        "error",
    ]
    with index_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow(
            {
                **row,
                "tags": ";".join(row.get("tags", []))
                if isinstance(row.get("tags"), list)
                else row.get("tags", ""),
            }
        )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Convert official conversation exports to markdown and batch-analyze via LLM."
    )
    p.add_argument("--input", required=True)
    p.add_argument("--format", default="auto", choices=["auto", "chatgpt", "claude"])
    p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    p.add_argument("--model")
    p.add_argument("--api-key-env", default=None)
    p.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Convert to markdown and index.csv only; skip LLM analysis.",
    )
    p.add_argument("--analysis-schema", default="default", choices=["default", "salvage"])
    p.add_argument("--output-root", default=".")
    p.add_argument("--max-concurrency", type=int, default=5)
    p.add_argument("--retry", type=int, default=3)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--sample", type=int)
    args = p.parse_args()

    if not args.skip_analysis and not args.model:
        p.error("--model is required unless --skip-analysis is used")

    api_key = ""
    if not args.skip_analysis:
        _default_env = "ANTHROPIC_API_KEY" if args.provider == "anthropic" else "OPENAI_API_KEY"
        api_key_env = args.api_key_env if args.api_key_env is not None else _default_env
        api_key = os.getenv(api_key_env, "")
        if not api_key:
            print(f"Missing API key env: {api_key_env}", file=sys.stderr)
            return 2

    input_path = Path(args.input)
    out_root = Path(args.output_root)
    out_root.mkdir(parents=True, exist_ok=True)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    try:
        conversations = normalize(data, args.format)
    except ValueError as e:
        p.error(str(e))
    if args.sample:
        conversations = conversations[: args.sample]

    index_path = out_root / "index.csv"
    total = len(conversations)
    print(f"Loaded {total} conversations → {out_root}", flush=True)

    jobs = []
    for n, conv in enumerate(conversations, start=1):
        sid = safe_id(conv.id)
        md_name = f"conv_{sid}.md"
        an_name = f"conv_{sid}.analysis.json"
        md_path = out_root / md_name
        an_path = out_root / an_name

        md_path.write_text(render_markdown(conv), encoding="utf-8")

        if args.skip_analysis:
            _progress(n, total, "converted", conv.title)
            write_index_row(
                index_path,
                {
                    "id": conv.id,
                    "title": conv.title,
                    "source": conv.source,
                    "md_file": md_name,
                    "analysis_file": "",
                    "route_recommendation": "",
                    "initial_route_recommendation": "",
                    "final_route_recommendation": "",
                    "calibration_applied": "",
                    "calibration_confidence": "",
                    "verdict": "",
                    "valuable_residual_count": "",
                    "next_steps_count": "",
                    "primary_text": "",
                    "summary": "",
                    "tags": [],
                    "status": "converted",
                    "error": "",
                },
            )
            continue

        if args.resume and an_path.exists() and not args.force:
            _progress(n, total, "skipped", conv.title)
            write_index_row(
                index_path,
                {
                    "id": conv.id,
                    "title": conv.title,
                    "source": conv.source,
                    "md_file": md_name,
                    "analysis_file": an_name,
                    "route_recommendation": "",
                    "initial_route_recommendation": "",
                    "final_route_recommendation": "",
                    "calibration_applied": "",
                    "calibration_confidence": "",
                    "verdict": "",
                    "valuable_residual_count": "",
                    "next_steps_count": "",
                    "primary_text": "",
                    "summary": "",
                    "tags": [],
                    "status": "skipped",
                    "error": "",
                },
            )
            continue

        jobs.append((conv, an_path, md_name, an_name))

    if not args.skip_analysis:
        with ThreadPoolExecutor(max_workers=max(1, args.max_concurrency)) as ex:
            fut_map = {
                ex.submit(
                    analyze_conversation,
                    conv,
                    args.model,
                    args.provider,
                    api_key,
                    args.retry,
                    args.analysis_schema,
                ): (conv, an_path, md_name, an_name)
                for conv, an_path, md_name, an_name in jobs
            }

            n_done = total - len(jobs)
            for fut in as_completed(fut_map):
                n_done += 1
                conv, an_path, md_name, an_name = fut_map[fut]
                result = fut.result()
                status = result.get("status", "unknown")
                if status == "ok":
                    route = result.get("route_recommendation", "")
                    label = f"ok route={route}" if route else "ok"
                else:
                    label = f"{status}"
                _progress(n_done, total, label, conv.title)
                an_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                primary_text = (
                    result.get("verdict", "")
                    if args.analysis_schema == "salvage"
                    else result.get("summary", "")
                )
                write_index_row(
                    index_path,
                    {
                        "route_recommendation": result.get("route_recommendation", ""),
                        "initial_route_recommendation": result.get(
                            "initial_route_recommendation", ""
                        ),
                        "final_route_recommendation": result.get(
                            "final_route_recommendation", ""
                        ),
                        "calibration_applied": result.get("calibration_applied", ""),
                        "calibration_confidence": result.get("calibration_confidence", ""),
                        "verdict": result.get("verdict", ""),
                        "valuable_residual_count": len(result.get("valuable_residuals", []))
                        if isinstance(result.get("valuable_residuals"), list)
                        else "",
                        "next_steps_count": len(result.get("next_steps", []))
                        if isinstance(result.get("next_steps"), list)
                        else "",
                        "id": conv.id,
                        "title": conv.title,
                        "source": conv.source,
                        "md_file": md_name,
                        "analysis_file": an_name,
                        "primary_text": primary_text,
                        "summary": result.get("summary", ""),
                        "tags": result.get("tags", []),
                        "status": result.get("status", "unknown"),
                        "error": result.get("error", ""),
                    },
                )

    print(
        f"Done at {iso_now()}. conversations={len(conversations)} "
        f"skip_analysis={args.skip_analysis} analysis_schema={args.analysis_schema}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
