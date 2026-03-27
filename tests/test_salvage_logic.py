import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_b_blocker_semantics_forces_c(self):
        obj = {
            "topic": "定義上線審核門檻",
            "valuable_residuals": ["上線風險檢核門檻：錯誤率 < 1% 且核心路徑通過"],
            "drift_point": "無明顯帶偏",
            "next_steps": ["把門檻寫入 release checklist 並指定 owner"],
            "route_recommendation": "B",
            "verdict": "有可留要點，但尚不足直接進入工作系統",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "C")
        ok, reason = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok, reason)

    def test_partial_but_not_work_system_ready_is_c(self):
        obj = {
            "topic": "內容企劃整理",
            "valuable_residuals": ["受眾切分原則：先看付費意圖再看互動深度"],
            "drift_point": "後段偏靈感拋點",
            "next_steps": ["先摘錄可用原則，暫不進規格"],
            "route_recommendation": "B",
            "verdict": "僅局部可摘用，未達可直接採用",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "C")
        ok, reason = ca.validate_analysis(normalized, "salvage")
        self.assertTrue(ok, reason)

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

    def test_true_work_system_ready_case_remains_b(self):
        obj = {
            "topic": "客訴升級處理規格",
            "valuable_residuals": [
                "升級門檻：連續 2 次 SLA 逾時或單筆損失超過 5 萬即轉主管",
                "談判原則：先鎖定補償上限，再以回購折扣換取撤訴",
            ],
            "drift_point": "無明顯帶偏",
            "next_steps": ["把門檻與談判原則寫入客服 runbook"],
            "route_recommendation": "C",
            "verdict": "可直接進入決策紀錄與 runbook，具可執行性",
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

    def test_needs_second_pass_explicit_d_is_false(self):
        obj = {
            "topic": "一般問答",
            "valuable_residuals": [],
            "drift_point": "無明顯帶偏",
            "next_steps": ["暫不行動"],
            "route_recommendation": "D",
            "verdict": "整體不值得保存，資訊密度太低",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "D")
        self.assertFalse(ca.needs_second_pass(normalized))
        final_obj = ca.finalize_salvage_result(normalized)
        self.assertFalse(final_obj["calibration_applied"])

    def test_needs_second_pass_explicit_a_is_false(self):
        obj = {
            "topic": "建立完整評估框架",
            "valuable_residuals": ["三層評估框架", "量化門檻", "風險檢核清單"],
            "drift_point": "無明顯帶偏",
            "next_steps": ["寫入團隊 SOP 並指定 owner"],
            "route_recommendation": "A",
            "verdict": "可直接保存為長期知識框架",
        }
        normalized = ca.normalize_salvage_analysis(obj)
        self.assertEqual(normalized["route_recommendation"], "A")
        self.assertFalse(ca.needs_second_pass(normalized))

    def test_analyze_salvage_second_pass_can_downgrade_b_to_c(self):
        conv = ca.NormalizedConversation(
            id="c1",
            source="chatgpt",
            title="混合案例",
            created_at=None,
            updated_at=None,
            messages=[ca.NormalizedMessage(role="user", content="test")],
        )
        first_pass = {
            "topic": "流程整理",
            "valuable_residuals": ["一條可留原則：先定義輸入再定義輸出"],
            "drift_point": "中段偏發散",
            "next_steps": ["整理可留句，尚不進入規格"],
            "route_recommendation": "B",
            "verdict": "有局部可留且可用，但整體仍有限",
        }
        second_pass = {
            "final_route": "C",
            "reason": "僅局部可摘錄，尚不足進入工作系統",
            "confidence": "medium",
        }
        with patch.object(ca, "call_openai_chat", side_effect=[first_pass]), patch.object(
            ca, "second_pass_judge", return_value=second_pass
        ):
            result = ca.analyze_conversation(
                conv=conv,
                model="gpt-test",
                provider="openai",
                api_key="k",
                retries=0,
                analysis_schema="salvage",
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["initial_route_recommendation"], "B")
        self.assertEqual(result["final_route_recommendation"], "C")
        self.assertEqual(result["route_recommendation"], "C")
        self.assertTrue(result["calibration_applied"])

    def test_analyze_salvage_second_pass_keeps_true_b(self):
        conv = ca.NormalizedConversation(
            id="c2",
            source="chatgpt",
            title="true b",
            created_at=None,
            updated_at=None,
            messages=[ca.NormalizedMessage(role="user", content="test")],
        )
        first_pass = {
            "topic": "決策紀錄整理",
            "valuable_residuals": ["門檻：LTV/CAC>=3 且 90 天回本"],
            "drift_point": "後段有雜訊",
            "next_steps": ["寫入方法筆記並附測量口徑"],
            "route_recommendation": "B",
            "verdict": "雖然整段不值得完整保存，但殘留已足以進入方法筆記",
        }
        second_pass = {
            "final_route": "B",
            "reason": "殘留可直接進入決策紀錄",
            "confidence": "high",
        }
        with patch.object(ca, "call_openai_chat", side_effect=[first_pass]), patch.object(
            ca, "second_pass_judge", return_value=second_pass
        ):
            result = ca.analyze_conversation(
                conv=conv,
                model="gpt-test",
                provider="openai",
                api_key="k",
                retries=0,
                analysis_schema="salvage",
            )
        self.assertEqual(result["initial_route_recommendation"], "B")
        self.assertEqual(result["route_recommendation"], "B")
        self.assertTrue(result["calibration_applied"])

    def test_analyze_salvage_second_pass_failure_fallback(self):
        conv = ca.NormalizedConversation(
            id="c3",
            source="chatgpt",
            title="failure fallback",
            created_at=None,
            updated_at=None,
            messages=[ca.NormalizedMessage(role="user", content="test")],
        )
        first_pass = {
            "topic": "流程整理",
            "valuable_residuals": ["一條可留原則：先定義輸入再定義輸出"],
            "drift_point": "中段偏發散",
            "next_steps": ["整理可留句，尚不進入規格"],
            "route_recommendation": "B",
            "verdict": "有局部可留且可用，但整體仍有限",
        }
        with patch.object(ca, "call_openai_chat", side_effect=[first_pass]), patch.object(
            ca, "second_pass_judge", side_effect=RuntimeError("boom")
        ):
            result = ca.analyze_conversation(
                conv=conv,
                model="gpt-test",
                provider="openai",
                api_key="k",
                retries=0,
                analysis_schema="salvage",
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["route_recommendation"], "B")
        self.assertEqual(result["initial_route_recommendation"], "B")
        self.assertFalse(result["calibration_applied"])
        self.assertEqual(result["calibration_reason"], "second_pass_failed")

    def test_second_pass_direction_guard_blocks_c_to_b_without_strong_evidence(self):
        conv = ca.NormalizedConversation(
            id="c4",
            source="chatgpt",
            title="direction guard",
            created_at=None,
            updated_at=None,
            messages=[ca.NormalizedMessage(role="user", content="test")],
        )
        first_pass = {
            "topic": "一般整理",
            "valuable_residuals": ["一條泛用提醒"],
            "drift_point": "後段發散",
            "next_steps": ["先摘錄，暫不落地"],
            "route_recommendation": "C",
            "verdict": "僅局部可摘錄，尚不足進入工作系統",
        }
        with patch.object(
            ca, "call_openai_chat", return_value={"final_route": "B", "reason": "可留", "confidence": "high"}
        ):
            result = ca.second_pass_judge(
                conv=conv,
                first_pass=first_pass,
                model="gpt-test",
                provider="openai",
                api_key="k",
            )
        self.assertEqual(result["final_route"], "C")
        self.assertIn("direction_guard_fallback", result["reason"])
        self.assertEqual(result["confidence"], "high")

    def test_second_pass_hard_rule_blocker_downgrades_b_to_c(self):
        conv = ca.NormalizedConversation(
            id="c5",
            source="chatgpt",
            title="hard rule blocker",
            created_at=None,
            updated_at=None,
            messages=[ca.NormalizedMessage(role="user", content="test")],
        )
        first_pass = {
            "topic": "流程整理",
            "valuable_residuals": ["上線檢核規則：核心路徑需通過"],
            "drift_point": "中段偏發散",
            "next_steps": ["先做摘錄，暫不納入規格"],
            "route_recommendation": "B",
            "verdict": "僅局部可摘用，尚不足直接進入工作系統",
        }
        with patch.object(
            ca, "call_openai_chat", return_value={"final_route": "B", "reason": "可直接採用", "confidence": "high"}
        ):
            result = ca.second_pass_judge(
                conv=conv,
                first_pass=first_pass,
                model="gpt-test",
                provider="openai",
                api_key="k",
            )
        self.assertEqual(result["final_route"], "C")
        self.assertIn("hard_rule_b_blocker", result["reason"])
        self.assertEqual(result["confidence"], "high")

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


    def test_format_run_stats(self):
        stats = {
            "total": 3,
            "converted": 1,
            "skipped": 1,
            "analysis_ok": 1,
            "analysis_failed": 0,
        }
        route_counts = {"A": 0, "B": 1, "C": 0, "D": 0}
        out = ca.format_run_stats(stats, route_counts)
        self.assertIn("Run stats:", out)
        self.assertIn("total=3", out)
        self.assertIn("converted=1", out)
        self.assertIn("skipped=1", out)
        self.assertIn("analysis_ok=1", out)
        self.assertIn("routes[A=0, B=1, C=0, D=0]", out)

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
            self.assertIn("Run stats:", cp.stdout)
            self.assertIn("converted=1", cp.stdout)
            self.assertIn("analysis_ok=0", cp.stdout)


class CallLLMProviderTests(unittest.TestCase):
    def test_call_llm_unsupported_provider_raises(self):
        with self.assertRaises(ValueError) as ctx:
            ca.call_llm(
                provider="unknown_provider",
                model="some-model",
                api_key="key",
                system_prompt="system",
                user_prompt="user",
            )
        self.assertIn("Unsupported provider", str(ctx.exception))

    def test_call_llm_openai_dispatches(self):
        with patch.object(ca, "call_openai_chat", return_value={"result": "ok"}) as m:
            result = ca.call_llm(
                provider="openai",
                model="gpt-4o",
                api_key="key",
                system_prompt="system",
                user_prompt="user",
            )
            m.assert_called_once_with(
                model="gpt-4o",
                api_key="key",
                system_prompt="system",
                user_prompt="user",
            )
            self.assertEqual(result, {"result": "ok"})

    def test_call_llm_anthropic_dispatches(self):
        with patch.object(ca, "call_claude_chat", return_value={"result": "claude"}) as m:
            result = ca.call_llm(
                provider="anthropic",
                model="claude-sonnet-4-6",
                api_key="key",
                system_prompt="system",
                user_prompt="user",
            )
            m.assert_called_once_with(
                model="claude-sonnet-4-6",
                api_key="key",
                system_prompt="system",
                user_prompt="user",
            )
            self.assertEqual(result, {"result": "claude"})

    def test_call_claude_strips_markdown_fences(self):
        import urllib.request

        mock_body = json.dumps({
            "content": [{"text": '```json\n{"key": "value"}\n```'}]
        }).encode("utf-8")

        class FakeResp:
            def read(self):
                return mock_body
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch.object(urllib.request, "urlopen", return_value=FakeResp()):
            result = ca.call_claude_chat(
                model="claude-haiku-4-5-20251001",
                api_key="test-key",
                system_prompt="system",
                user_prompt="user",
            )
        self.assertEqual(result, {"key": "value"})

    def test_call_claude_plain_json(self):
        import urllib.request

        mock_body = json.dumps({
            "content": [{"text": '{"answer": 42}'}]
        }).encode("utf-8")

        class FakeResp:
            def read(self):
                return mock_body
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch.object(urllib.request, "urlopen", return_value=FakeResp()):
            result = ca.call_claude_chat(
                model="claude-sonnet-4-6",
                api_key="test-key",
                system_prompt="system",
                user_prompt="user",
            )
        self.assertEqual(result, {"answer": 42})

    def test_externalized_markers_support_english_criterion(self):
        marker_set = ca.build_marker_set("en")
        score = ca.residual_asset_strength(
            "Launch criterion: KPI threshold at CAC < 30", marker_set=marker_set
        )
        self.assertGreaterEqual(score, 2)

    def test_auto_language_detection_uses_multi_marker_set(self):
        conv = ca.NormalizedConversation(
            id="lang1",
            source="chatgpt",
            title="English conversation",
            created_at=None,
            updated_at=None,
            messages=[ca.NormalizedMessage(role="user", content="Define a launch framework")],
        )
        self.assertEqual(ca.resolve_analysis_language("auto", conv=conv), "multi")


if __name__ == "__main__":
    unittest.main()
