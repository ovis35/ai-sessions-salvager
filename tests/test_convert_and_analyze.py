import json
import subprocess
import sys
from pathlib import Path

from convert_and_analyze import infer_format, normalize, render_markdown


def test_infer_chatgpt_and_normalize():
    data = [{
        "id": "abc123",
        "title": "Test Chat",
        "mapping": {
            "1": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["hello"]},
                    "create_time": 1700000000,
                }
            },
            "2": {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"parts": ["world"]},
                    "create_time": 1700000001,
                }
            }
        }
    }]
    assert infer_format(data) == "chatgpt"
    convs = normalize(data, "auto")
    assert len(convs) == 1
    assert convs[0].id == "abc123"
    assert len(convs[0].messages) == 2
    md = render_markdown(convs[0])
    assert "# Test Chat" in md
    assert "## Message 1" in md


def test_cli_skip_analysis(tmp_path: Path):
    export = tmp_path / "export.json"
    payload = [{
        "uuid": "claude-1",
        "name": "Claude test",
        "chat_messages": [
            {"sender": "human", "text": "hi"},
            {"sender": "assistant", "text": "hello"},
        ],
    }]
    export.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "convert_and_analyze.py",
            "--input",
            str(export),
            "--format",
            "auto",
            "--provider",
            "openai",
            "--model",
            "gpt-4.1-mini",
            "--output-root",
            str(tmp_path),
            "--skip-analysis",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    md = tmp_path / "conv_claude-1.md"
    analysis = tmp_path / "conv_claude-1.analysis.json"
    index = tmp_path / "index.csv"
    assert md.exists()
    assert analysis.exists()
    assert index.exists()
    parsed = json.loads(analysis.read_text(encoding="utf-8"))
    assert parsed["status"] == "skipped_analysis"
