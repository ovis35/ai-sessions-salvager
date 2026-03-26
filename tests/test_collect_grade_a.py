import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import collect_grade_a as cga


class MergeToMarkdownTests(unittest.TestCase):
    def _base_analysis(self, route="A"):
        return {
            "route_recommendation": route,
            "initial_route_recommendation": route,
            "final_route_recommendation": route,
            "topic": "決策框架建立",
            "verdict": "可直接保存為長期決策模型",
            "drift_point": "無明顯帶偏",
            "valuable_residuals": ["三層決策框架", "反例檢查原則"],
            "next_steps": ["寫入團隊決策模板"],
            "calibration_applied": False,
            "calibration_confidence": "",
            "calibration_reason": "",
        }

    def test_merge_contains_analysis_section(self):
        analysis = self._base_analysis()
        md = "# 測試對話\n\n**user**: 你好\n\n**assistant**: 您好\n"
        result = cga.merge_to_markdown(analysis, md, "conv_test.md")
        self.assertIn("## 分析摘要", result)
        self.assertIn("**A**", result)
        self.assertIn("決策框架建立", result)
        self.assertIn("可直接保存為長期決策模型", result)

    def test_merge_contains_residuals(self):
        analysis = self._base_analysis()
        md = "# 對話\n"
        result = cga.merge_to_markdown(analysis, md, "conv_test.md")
        self.assertIn("三層決策框架", result)
        self.assertIn("反例檢查原則", result)

    def test_merge_contains_next_steps(self):
        analysis = self._base_analysis()
        md = "# 對話\n"
        result = cga.merge_to_markdown(analysis, md, "conv_test.md")
        self.assertIn("寫入團隊決策模板", result)

    def test_merge_contains_original_md(self):
        analysis = self._base_analysis()
        md = "# 原始對話\n\n**user**: 測試內容\n"
        result = cga.merge_to_markdown(analysis, md, "conv_test.md")
        self.assertIn("**user**: 測試內容", result)

    def test_merge_separator_between_analysis_and_md(self):
        analysis = self._base_analysis()
        md = "# 對話\n"
        result = cga.merge_to_markdown(analysis, md, "conv_test.md")
        self.assertIn("---", result)
        # 分析摘要應在對話內容之前
        idx_analysis = result.index("## 分析摘要")
        idx_sep = result.index("---")
        idx_md = result.index("# 對話")
        self.assertLess(idx_analysis, idx_sep)
        self.assertLess(idx_sep, idx_md)

    def test_merge_shows_calibration_when_applied(self):
        analysis = self._base_analysis()
        analysis["calibration_applied"] = True
        analysis["calibration_confidence"] = "high"
        analysis["calibration_reason"] = "殘值足夠強"
        md = "# 對話\n"
        result = cga.merge_to_markdown(analysis, md, "conv_test.md")
        self.assertIn("二次校準", result)
        self.assertIn("high", result)
        self.assertIn("殘值足夠強", result)

    def test_merge_hides_calibration_when_not_applied(self):
        analysis = self._base_analysis()
        analysis["calibration_applied"] = False
        md = "# 對話\n"
        result = cga.merge_to_markdown(analysis, md, "conv_test.md")
        self.assertNotIn("二次校準", result)

    def test_empty_residuals_shows_placeholder(self):
        analysis = self._base_analysis()
        analysis["valuable_residuals"] = []
        md = "# 對話\n"
        result = cga.merge_to_markdown(analysis, md, "conv_test.md")
        self.assertIn("（無）", result)


class CollectIntegrationTests(unittest.TestCase):
    def _write_analysis(self, directory: Path, conv_id: str, route: str):
        analysis = {
            "schema": "salvage",
            "status": "ok",
            "route_recommendation": route,
            "initial_route_recommendation": route,
            "final_route_recommendation": route,
            "topic": f"主題_{conv_id}",
            "verdict": "測試判斷",
            "drift_point": "無",
            "valuable_residuals": ["殘值一"],
            "next_steps": ["步驟一"],
            "calibration_applied": False,
            "calibration_confidence": "",
            "calibration_reason": "",
        }
        an_path = directory / f"conv_{conv_id}.analysis.json"
        an_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
        md_path = directory / f"conv_{conv_id}.md"
        md_path.write_text(f"# 對話 {conv_id}\n\n內容\n", encoding="utf-8")

    def test_only_grade_a_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input"
            inp.mkdir()
            out = Path(tmp) / "output"

            self._write_analysis(inp, "aaa", "A")
            self._write_analysis(inp, "bbb", "B")
            self._write_analysis(inp, "ccc", "C")
            self._write_analysis(inp, "ddd", "D")

            ret = cga.collect(inp, out)
            self.assertEqual(ret, 0)

            output_files = list(out.glob("*.md"))
            self.assertEqual(len(output_files), 1)
            self.assertEqual(output_files[0].name, "conv_aaa.md")

    def test_merged_file_contains_both_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input"
            inp.mkdir()
            out = Path(tmp) / "output"

            self._write_analysis(inp, "xyz", "A")

            cga.collect(inp, out)

            merged = (out / "conv_xyz.md").read_text(encoding="utf-8")
            self.assertIn("## 分析摘要", merged)
            self.assertIn("# 對話 xyz", merged)

    def test_missing_md_file_skips_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input"
            inp.mkdir()
            out = Path(tmp) / "output"

            # 只有 analysis.json，沒有對應的 .md
            analysis = {
                "route_recommendation": "A",
                "topic": "測試",
                "verdict": "v",
                "drift_point": "d",
                "valuable_residuals": [],
                "next_steps": [],
                "calibration_applied": False,
                "calibration_confidence": "",
                "calibration_reason": "",
            }
            (inp / "conv_orphan.analysis.json").write_text(
                json.dumps(analysis), encoding="utf-8"
            )

            ret = cga.collect(inp, out)
            self.assertEqual(ret, 0)
            self.assertEqual(list(out.glob("*.md")), [])

    def test_empty_directory_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input"
            inp.mkdir()
            out = Path(tmp) / "output"
            ret = cga.collect(inp, out)
            self.assertNotEqual(ret, 0)

    def test_multiple_grade_a_all_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input"
            inp.mkdir()
            out = Path(tmp) / "output"

            for cid in ["a1", "a2", "a3"]:
                self._write_analysis(inp, cid, "A")
            self._write_analysis(inp, "b1", "B")

            cga.collect(inp, out)

            output_files = sorted(f.name for f in out.glob("*.md"))
            self.assertEqual(output_files, ["conv_a1.md", "conv_a2.md", "conv_a3.md"])

    def test_output_dir_created_if_not_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input"
            inp.mkdir()
            out = Path(tmp) / "deep" / "nested" / "output"

            self._write_analysis(inp, "x1", "A")
            cga.collect(inp, out)

            self.assertTrue(out.is_dir())
            self.assertTrue((out / "conv_x1.md").exists())


if __name__ == "__main__":
    unittest.main()
