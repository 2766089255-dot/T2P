import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server


class APISmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api_server.app)

    def test_health_does_not_call_provider_by_default(self):
        with patch.object(
            api_server.core.ai_client,
            "generate_async",
            side_effect=AssertionError("provider should not be called"),
        ):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["api"], "healthy")

    def test_topics_are_loaded_from_seed_dataset(self):
        response = self.client.get("/topics")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["topics"]), 10)

    def test_generation_requires_topics_or_user(self):
        response = self.client.post("/generate", json={"topics": []})

        self.assertEqual(response.status_code, 422)

    def test_generation_batch_size_is_bounded(self):
        response = self.client.post(
            "/generate",
            json={"topics": ["Limits and Continuity"], "num": 11},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
