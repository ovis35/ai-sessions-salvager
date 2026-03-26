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

    def test_thin_partial_salvage_without_action_is_c(self):
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

    def test_partial_salvage_with_strong_assets_can_be_b(self):
        obj = {
            "topic": "成長流程整理",
            "valuable_residuals": [
                "付費廣告啟動門檻：PMF 後、LTV/CAC 約 3、3 個月回本",
                "網紅合作原則：按轉化計價並分期綁定成效",
            ],
            "drift_point": "多數內容仍是常見整理",
            "next_steps": ["把門檻改寫為本產品 KPI 與歸因口徑"],
            "route_recommendation": "C",
            "verdict": "其餘多為普通內容，但上述門檻與原則可直接落地",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "B")
        ok, reason = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok, reason)

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

    def test_case_one_promoted_to_b(self):
        obj = {
            "topic": "依《宣傳的藝術》七手法出題並延伸成宣傳設計框架",
            "valuable_residuals": [
                "PERSUADE：Purpose/Emotion/Reasoning/Social Proof/Unity/Authenticity/Dissemination/Evaluation，將七手法嵌入流程",
                "七手法映射：Emotion(辱罵/粉飾)、Reasoning(洗牌)、Social Proof(佐證/花車)、Authenticity(平民)、Dissemination(挪移)",
            ],
            "drift_point": "從對答案跳到框架，但邊界與倫理限制不足",
            "next_steps": ["補上適用情境、禁用紅線、風險與反制檢核表"],
            "route_recommendation": "C",
            "verdict": "其餘多為一般內容，但框架與映射可直接入方法筆記",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "B")
        ok, reason = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok, reason)

    def test_case_two_promoted_to_b(self):
        obj = {
            "topic": "整理 0 到 5M ARR 增長指南並再概括",
            "valuable_residuals": [
                "付費廣告啟動門檻：PMF、LTV/CAC≈3、3 個月內回本",
                "網紅合作談判原則：避免按粉絲數計價，改以轉化/效果，分期且綁成效",
                "短視頻原則：以播放/互動為主，找到可複製系列並多平台日更再發布",
            ],
            "drift_point": "新增見解不多，偏排版整理",
            "next_steps": ["把三條原則轉成產品情境量化指標與測量方式"],
            "route_recommendation": "C",
            "verdict": "其餘多為普通內容，但門檻與談判原則足以進入決策紀錄",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "B")
        ok, reason = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok, reason)

    def test_default_schema_unchanged(self):
        obj = {
            "summary": "A concise summary",
            "tags": ["x"],
            "language": "en-US",
            "quality_score": 72,
        }
        ok, reason = ca.validate_analysis(obj, "default")
        self.assertTrue(ok, reason)

    def test_infer_format_dict_chatgpt(self):
        data = {
            "conversations": [
                {
                    "conversation_id": "c1",
                    "mapping": {},
                }
            ]
        }
        self.assertEqual(ca.infer_format(data), "chatgpt")

    def test_infer_format_dict_claude(self):
        data = {
            "conversations": [
                {
                    "uuid": "u1",
                    "chat_messages": [],
                }
            ]
        }
        self.assertEqual(ca.infer_format(data), "claude")

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
