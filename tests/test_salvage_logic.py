import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import convert_and_analyze as ca


class SalvageLogicTests(unittest.TestCase):
    def test_high_value_framework_can_stay_a(self):
        obj = {
            "topic": "建立跨專案決策框架",
            "valuable_residuals": ["三層決策框架", "反例檢查原則"],
            "drift_point": "無明顯帶偏",
            "next_steps": ["將框架寫入團隊決策模板"],
            "route_recommendation": "A",
            "verdict": "可直接保存為長期決策模型",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "A")
        ok, _ = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok)

    def test_project_decision_is_b(self):
        obj = {
            "topic": "API 版本切換",
            "valuable_residuals": ["決定改用 v2 並保留回滾條件"],
            "drift_point": "無明顯帶偏",
            "next_steps": ["本週內更新 migration checklist"],
            "route_recommendation": "B",
            "verdict": "有明確專案決策與執行路徑",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "B")
        ok, _ = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok)

    def test_partial_salvage_forces_c(self):
        obj = {
            "topic": "討論寫作方向",
            "valuable_residuals": ["一句可用命名：反脆弱迭代"],
            "drift_point": "後段多為普通鼓勵",
            "next_steps": ["暫不行動"],
            "route_recommendation": "B",
            "verdict": "只有局部可留，其餘多為普通內容",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "C")
        ok, _ = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok)

    def test_not_worth_forces_d(self):
        obj = {
            "topic": "一般翻譯",
            "valuable_residuals": [],
            "drift_point": "無明顯帶偏",
            "next_steps": ["暫不行動"],
            "route_recommendation": "A",
            "verdict": "整體不值得保存，資訊密度不高",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "D")
        ok, _ = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok)

    def test_default_schema_unchanged(self):
        obj = {
            "summary": "A concise summary",
            "tags": ["x"],
            "language": "en-US",
            "quality_score": 72,
        }
        ok, reason = ca.validate_analysis(obj, "default")
        self.assertTrue(ok, reason)

    def test_cli_sample_resume_force_skip_analysis(self):
        data = [
            {
                "id": "c1",
                "title": "t1",
                "messages": [{"role": "user", "content": "hi", "timestamp": "2024-01-01"}],
            },
            {
                "id": "c2",
                "title": "t2",
                "messages": [{"role": "user", "content": "hello", "timestamp": "2024-01-01"}],
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "input.json"
            out_path = Path(td) / "out"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            cmd = [
                "python",
                "convert_and_analyze.py",
                "--input",
                str(input_path),
                "--format",
                "chatgpt",
                "--output-root",
                str(out_path),
                "--skip-analysis",
                "--sample",
                "1",
                "--resume",
                "--force",
            ]
            cp = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertTrue((out_path / "index.csv").exists())


if __name__ == "__main__":
    unittest.main()
