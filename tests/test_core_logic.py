import tempfile
import unittest
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from src.generator import ProblemGenerator
from src.data_loader import GoldenDataLoader
from src.ocr import OCRService
from src.postprocessor import PostProcessor
from src.services.grading import GradingService
from src.stores import JSONFileStore


class FakeDataLoader:
    pass


class FakeAIClient:
    pass


class FakePostProcessor:
    def __init__(self):
        self.deduplicate_calls = 0

    def deduplicate(self, problems, existing=None):
        self.deduplicate_calls += 1
        return problems[:1]


class StoreTests(unittest.TestCase):
    def test_user_id_cannot_escape_storage_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JSONFileStore(temp_dir)
            path = store._path("../../outside")

            self.assertEqual(path.parent, Path(temp_dir).resolve())
            self.assertNotIn("outside", path.name)

    def test_progress_round_trip_supports_unicode_user_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JSONFileStore(temp_dir)
            expected = {"metadata": {"user_id": "学习者一号"}}

            store.save("学习者一号", expected)

            self.assertEqual(store.load("学习者一号"), expected)

    def test_empty_user_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JSONFileStore(temp_dir)
            with self.assertRaises(ValueError):
                store.load("   ")


class GenerationTests(unittest.TestCase):
    def test_batch_generation_uses_injected_postprocessor(self):
        postprocessor = FakePostProcessor()
        generator = ProblemGenerator(
            data_loader=FakeDataLoader(),
            ai_client=FakeAIClient(),
            evaluator=object(),
            postprocessor=postprocessor,
        )
        generator.generate_one = lambda **kwargs: {
            "problem_statement": f"Question {kwargs['temperature']}"
        }

        with patch("src.generator.time.sleep"):
            result = generator.generate_batch(topics=["Limits"], num=2)

        self.assertEqual(len(result), 1)
        self.assertEqual(postprocessor.deduplicate_calls, 1)


class GradingTests(unittest.TestCase):
    def setUp(self):
        self.service = GradingService.__new__(GradingService)

    def test_score_is_clamped_to_valid_range(self):
        self.assertEqual(self.service._calibrate_score(False, 140, False), 100)
        self.assertEqual(self.service._calibrate_score(False, -5, False), 0)

    def test_mcq_score_is_deterministic(self):
        self.assertEqual(self.service._calibrate_score(True, 20, True), 100)
        self.assertEqual(self.service._calibrate_score(False, 80, True), 30)


class DataLoaderTests(unittest.TestCase):
    @staticmethod
    def _write_dataset(directory, problems):
        path = Path(directory) / "dataset.json"
        path.write_text(
            json.dumps({"problems": problems}),
            encoding="utf-8",
        )
        return path

    def test_legacy_answer_fields_are_normalized_in_memory(self):
        problems = [
            {
                "problem_id": "MCQ_1",
                "topic": "Limits",
                "question_type": "mcq",
                "correct_answer": "B",
            },
            {
                "problem_id": "FILL_1",
                "topic": "Limits",
                "question_type": "fill_in",
                "correct_answer": ["4"],
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            loader = GoldenDataLoader(str(self._write_dataset(temp_dir, problems)))

        self.assertEqual(loader.find_problem_by_id("MCQ_1")["answer"], "B")
        self.assertEqual(loader.find_problem_by_id("FILL_1")["correct_values"], ["4"])
        self.assertEqual(loader.find_problem_by_id("MCQ_1")["correct_answer"], "B")

    def test_duplicate_problem_ids_are_rejected(self):
        problems = [
            {"problem_id": "DUP", "topic": "Limits"},
            {"problem_id": "DUP", "topic": "Derivatives"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_dataset(temp_dir, problems)
            with self.assertRaisesRegex(ValueError, "Duplicate problem identifier"):
                GoldenDataLoader(str(path))


class PostProcessorTests(unittest.TestCase):
    def test_trailing_comma_json_is_repaired(self):
        processor = PostProcessor()
        parsed = processor.parse_json('{"problem_statement": "x",}')
        self.assertEqual(parsed, {"problem_statement": "x"})

    def test_basic_deduplication_keeps_first_occurrence(self):
        processor = PostProcessor()
        problems = [
            {"problem_statement": "Find the limit"},
            {"problem_statement": "Find  the limit"},
        ]
        self.assertEqual(len(processor._basic_deduplicate(problems)), 1)


class OCRServiceTests(unittest.TestCase):
    @staticmethod
    def _png_bytes() -> bytes:
        image = Image.new("RGB", (320, 120), "white")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    @patch("httpx.Client")
    def test_cloud_ocr_uses_configured_key_without_environment_proxy(self, client_class):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "IsErroredOnProcessing": False,
            "ParsedResults": [
                {"FileParseExitCode": 1, "ParsedText": "x = 42"}
            ],
        }
        client_class.return_value.__enter__.return_value.post.return_value = response
        service = OCRService(api_key="personal-free-key", trust_env=False)

        result = service._ocr_space(self._png_bytes())

        self.assertEqual(result, "x = 42")
        self.assertFalse(client_class.call_args.kwargs["trust_env"])
        post_kwargs = client_class.return_value.__enter__.return_value.post.call_args.kwargs
        self.assertEqual(post_kwargs["headers"]["apikey"], "personal-free-key")
        self.assertTrue(post_kwargs["data"]["base64Image"].startswith("data:image/png;base64,"))

    def test_large_image_is_reencoded_below_free_limit(self):
        image = Image.new("RGB", (2200, 2200), "white")
        source = io.BytesIO()
        image.save(source, format="BMP")
        service = OCRService(api_key="test")

        prepared, mime_type = service._prepare_cloud_image(source.getvalue())

        self.assertEqual(mime_type, "image/jpeg")
        self.assertLessEqual(len(prepared), service.MAX_FREE_IMAGE_BYTES)

    def test_local_ocr_is_used_when_cloud_returns_no_text(self):
        service = OCRService(api_key="test")
        with patch.object(service, "_ocr_space", return_value=None), patch.object(
            service, "_easyocr_extract", return_value="fallback result"
        ):
            self.assertEqual(service.extract(b"image"), "fallback result")


if __name__ == "__main__":
    unittest.main()
