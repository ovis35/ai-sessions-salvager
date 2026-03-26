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
    if isinstance(data, dict):
        if "conversations" in data:
            return "chatgpt"
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
        "temperature": 0.2,
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
            "請嚴格、克制、少廢話，只輸出真正值得留下的內容。不要討好，不要美化普通內容，不要重述整段聊天。\n"
            "寧可少，不可濫；偏向省略，不要過度收錄。若無價值，請輸出空陣列或對應的「無／暫不行動」。\n"
            "盡量將整體結果控制在 250 個中文字以內。\n"
            "只輸出 JSON 物件，且 key 必須且只能是："
            "topic, valuable_residuals, drift_point, next_steps, route_recommendation, verdict。\n"
            "規則：\n"
            "- topic：一句話，描述實際在處理什麼。\n"
            "- valuable_residuals：0-3 條；每條只能是 新觀點/框架、值得保留的好句或命名、有幫助的明確判斷/決策；沒價值就 []。\n"
            "- drift_point：一句話指出最明顯帶偏；沒有就必須是「無明顯帶偏」。\n"
            "- next_steps：0-2 條最值得做的具體下一步；若不值得行動就 [\"暫不行動\"]；避免空泛建議。\n"
            "- route_recommendation：只能是 A/B/C/D 其中一個。\n"
            "  A=長期知識/原則/模型/人物理解/方法論；"
            "  B=專案決策/任務/規格/待辦/執行狀態；"
            "  C=靈感/句子/刺點/暫時提醒；"
            "  D=不值得保存。\n"
            "- verdict：一句更銳利但準確的判決，回答值不值得留下。"
        )
        user_prompt = (
            "請依規則輸出殘渣打撈結果。\n\n"
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
            if provider != "openai":
                raise ValueError("Only provider=openai is implemented in this version")
            result = call_openai_chat(
                model=model,
                api_key=api_key,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            ok, reason = validate_analysis(result, analysis_schema=analysis_schema)
            if ok:
                return {"schema": analysis_schema, "status": "ok", **result}
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
    p.add_argument("--provider", default="openai")
    p.add_argument("--model")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY")
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
        api_key = os.getenv(args.api_key_env, "")
        if not api_key:
            print(f"Missing API key env: {args.api_key_env}", file=sys.stderr)
            return 2

    input_path = Path(args.input)
    out_root = Path(args.output_root)
    out_root.mkdir(parents=True, exist_ok=True)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    conversations = normalize(data, args.format)
    if args.sample:
        conversations = conversations[: args.sample]

    index_path = out_root / "index.csv"

    jobs = []
    for conv in conversations:
        sid = safe_id(conv.id)
        md_name = f"conv_{sid}.md"
        an_name = f"conv_{sid}.analysis.json"
        md_path = out_root / md_name
        an_path = out_root / an_name

        md_path.write_text(render_markdown(conv), encoding="utf-8")

        if args.skip_analysis:
            write_index_row(
                index_path,
                {
                    "id": conv.id,
                    "title": conv.title,
                    "source": conv.source,
                    "md_file": md_name,
                    "analysis_file": "",
                    "primary_text": "",
                    "summary": "",
                    "tags": [],
                    "status": "converted",
                    "error": "",
                },
            )
            continue

        if args.resume and an_path.exists() and not args.force:
            write_index_row(
                index_path,
                {
                    "id": conv.id,
                    "title": conv.title,
                    "source": conv.source,
                    "md_file": md_name,
                    "analysis_file": an_name,
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

            for fut in as_completed(fut_map):
                conv, an_path, md_name, an_name = fut_map[fut]
                result = fut.result()
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