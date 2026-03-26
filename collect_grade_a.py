"""
collect_grade_a.py — 從輸出目錄批次蒐集等級 A 的對話，合併 analysis.json 與 .md 輸出。

用法：
    python collect_grade_a.py --input-root ./output --output-dir ./grade_a

每個符合條件的對話會產生一個合併的 Markdown 檔案，包含：
  - 分析摘要區塊（來自 analysis.json）
  - 完整對話內容（來自 conv_<id>.md）
"""

import argparse
import json
import sys
from pathlib import Path


def _render_list(items: list) -> str:
    if not items:
        return "（無）"
    return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))


def merge_to_markdown(analysis: dict, md_content: str, md_filename: str) -> str:
    route = analysis.get("route_recommendation", "A")
    initial = analysis.get("initial_route_recommendation", "")
    final = analysis.get("final_route_recommendation", "")
    topic = analysis.get("topic", "")
    verdict = analysis.get("verdict", "")
    drift_point = analysis.get("drift_point", "")
    residuals = analysis.get("valuable_residuals", [])
    next_steps = analysis.get("next_steps", [])
    calibration_applied = analysis.get("calibration_applied", False)
    calibration_confidence = analysis.get("calibration_confidence", "")
    calibration_reason = analysis.get("calibration_reason", "")

    lines = []

    # 分析摘要區塊
    lines.append("## 分析摘要\n")

    lines.append(f"| 欄位 | 內容 |")
    lines.append(f"|------|------|")
    lines.append(f"| 路由等級 | **{route}** |")
    if initial and initial != route:
        lines.append(f"| 初始等級 | {initial} |")
    if final and final != route:
        lines.append(f"| 最終等級 | {final} |")
    lines.append(f"| 主題 | {topic} |")
    if calibration_applied:
        lines.append(f"| 二次校準 | 已套用（信心度：{calibration_confidence}）|")
        if calibration_reason:
            lines.append(f"| 校準原因 | {calibration_reason} |")

    lines.append("")
    lines.append(f"**判斷：** {verdict}")
    lines.append("")

    if drift_point:
        lines.append(f"**漂移點：** {drift_point}")
        lines.append("")

    lines.append("**有價值的殘值：**")
    lines.append(_render_list(residuals))
    lines.append("")

    lines.append("**後續步驟：**")
    lines.append(_render_list(next_steps))
    lines.append("")
    lines.append("---\n")

    # 原始對話內容
    lines.append(md_content.rstrip())
    lines.append("")

    return "\n".join(lines)


def collect(input_root: Path, output_dir: Path) -> int:
    analysis_files = sorted(input_root.glob("*.analysis.json"))
    if not analysis_files:
        print(f"在 {input_root} 找不到任何 *.analysis.json 檔案", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    found = 0
    skipped_no_md = 0

    for an_path in analysis_files:
        try:
            analysis = json.loads(an_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[跳過] 無法讀取 {an_path.name}: {e}", file=sys.stderr)
            continue

        route = str(analysis.get("route_recommendation", "")).strip().upper()
        if route != "A":
            continue

        # 對應的 .md 檔案名稱：conv_<id>.analysis.json -> conv_<id>.md
        md_name = an_path.name.replace(".analysis.json", ".md")
        md_path = input_root / md_name

        if not md_path.exists():
            print(f"[警告] 找不到對應的 Markdown：{md_name}，跳過", file=sys.stderr)
            skipped_no_md += 1
            continue

        md_content = md_path.read_text(encoding="utf-8")
        merged = merge_to_markdown(analysis, md_content, md_name)

        out_path = output_dir / md_name
        out_path.write_text(merged, encoding="utf-8")
        found += 1
        print(f"[A] {md_name} -> {out_path}")

    print(f"\n完成：共找到 {found} 筆等級 A，輸出至 {output_dir}")
    if skipped_no_md:
        print(f"警告：{skipped_no_md} 筆因找不到 .md 檔案而略過")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="批次蒐集等級 A 的對話，合併 analysis.json 與 .md 輸出到指定目錄。"
    )
    p.add_argument(
        "--input-root",
        required=True,
        help="包含 *.analysis.json 與 *.md 的目錄（即 convert_and_analyze.py 的 --output-root）",
    )
    p.add_argument(
        "--output-dir",
        required=True,
        help="合併結果的輸出目錄",
    )
    args = p.parse_args()

    input_root = Path(args.input_root)
    if not input_root.is_dir():
        p.error(f"--input-root 不存在或非目錄：{input_root}")

    return collect(input_root, Path(args.output_dir))


if __name__ == "__main__":
    sys.exit(main())
