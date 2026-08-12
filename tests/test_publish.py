"""PUBLISH：HF frontmatter（license/pipeline_tag）与源仓库 license 推断测试。"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.stages.acquire import infer_source_license  # noqa: E402
from magnetar.stages.publish import _build_hf_frontmatter, _infer_pipeline_tag  # noqa: E402


class PipelineTagTest(unittest.TestCase):
    def test_audio_tasks(self):
        for task in ("tts", "TTS", "speech", "audio-to-audio", "vocoder", "noise"):
            self.assertEqual(_infer_pipeline_tag(task), "audio-to-audio", task)

    def test_text_tasks(self):
        for task in ("llm", "text-generation", "chat", "question-answering"):
            self.assertEqual(_infer_pipeline_tag(task), "text-generation", task)

    def test_vision_tasks(self):
        self.assertEqual(_infer_pipeline_tag("detection"), "object-detection")
        self.assertEqual(_infer_pipeline_tag("image-classification"), "image-classification")

    def test_unknown_task(self):
        self.assertEqual(_infer_pipeline_tag(""), "other")
        self.assertEqual(_infer_pipeline_tag("something-weird"), "other")


class FrontmatterTest(unittest.TestCase):
    def test_flow_task_and_license(self):
        fm = _build_hf_frontmatter(
            {"task": "tts", "license": "mit"}, {"task": "image-classification"}, "demo")
        self.assertIn("license: mit", fm)
        self.assertIn("pipeline_tag: audio-to-audio", fm)
        self.assertIn("- demo", fm)

    def test_meta_fallback_and_default_mit(self):
        fm = _build_hf_frontmatter({}, {"task": "llm"}, "demo")
        self.assertIn("license: mit", fm)
        self.assertIn("pipeline_tag: text-generation", fm)

    def test_unknown_defaults(self):
        fm = _build_hf_frontmatter(None, None, "demo")
        self.assertIn("license: mit", fm)
        self.assertIn("pipeline_tag: other", fm)


class LicenseInferTest(unittest.TestCase):
    def setUp(self):
        self.origin = Path(tempfile.mkdtemp(prefix="origin_license_"))

    def _write(self, rel, text):
        p = self.origin / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_mit_text(self):
        self._write("my-model/LICENSE",
                    "MIT License\n\nPermission is hereby granted, free of charge, "
                    "to any person obtaining a copy of this software...")
        self.assertEqual(infer_source_license(self.origin), "mit")

    def test_apache_spdx(self):
        self._write("my-model/LICENSE.md",
                    "SPDX-License-Identifier: Apache-2.0\n\nLicensed under the Apache License...")
        self.assertEqual(infer_source_license(self.origin), "apache-2.0")

    def test_bsd3_vs_bsd2(self):
        self._write("repo/LICENSE", (
            "Redistribution and use in source and binary forms, with or without\n"
            "modification, are permitted provided that the following conditions are met:\n"
            "Neither the name of the copyright holder nor the names of its contributors\n"))
        self.assertEqual(infer_source_license(self.origin), "bsd-3-clause")

    def test_no_license(self):
        self.assertEqual(infer_source_license(self.origin), "")
        self.assertEqual(infer_source_license(self.origin / "nonexistent"), "")


if __name__ == "__main__":
    unittest.main()
