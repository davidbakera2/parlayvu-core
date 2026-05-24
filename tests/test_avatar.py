import unittest
from unittest.mock import patch

from app.avatar import get_tavus_config, tavus_status
from app.avatar.tavus import replica_for_agent


class AvatarTavusTests(unittest.TestCase):
    def test_status_reports_unconfigured_when_env_empty(self):
        with patch.dict("os.environ", {}, clear=True):
            status = tavus_status()
        self.assertEqual(status["provider"], "tavus")
        self.assertFalse(status["configured"])
        self.assertFalse(status["persona_id_configured"])
        self.assertFalse(status["agent_replicas"]["nathan"]["configured"])

    def test_status_reports_configured_when_required_env_present(self):
        with patch.dict(
            "os.environ",
            {"TAVUS_API_KEY": "k", "TAVUS_PERSONA_ID": "p", "TAVUS_REPLICA_ID": "r"},
            clear=True,
        ):
            status = tavus_status()
        self.assertTrue(status["configured"])
        self.assertTrue(status["persona_id_configured"])
        self.assertTrue(status["default_replica_id_configured"])

    def test_replica_for_agent_uses_per_agent_override_when_set(self):
        with patch.dict(
            "os.environ",
            {
                "TAVUS_API_KEY": "k",
                "TAVUS_PERSONA_ID": "p",
                "TAVUS_REPLICA_ID": "shared",
                "TAVUS_REPLICA_ID_NATHAN": "nathan-specific",
            },
            clear=True,
        ):
            self.assertEqual(replica_for_agent("nathan"), "nathan-specific")
            # Unknown agent falls back to the default shared replica
            self.assertEqual(replica_for_agent("alex"), "shared")

    def test_replica_for_agent_falls_back_to_default(self):
        with patch.dict(
            "os.environ",
            {"TAVUS_API_KEY": "k", "TAVUS_PERSONA_ID": "p", "TAVUS_REPLICA_ID": "shared"},
            clear=True,
        ):
            self.assertEqual(replica_for_agent("nathan"), "shared")

    def test_get_tavus_config_returns_dataclass(self):
        with patch.dict(
            "os.environ",
            {"TAVUS_API_KEY": "k", "TAVUS_PERSONA_ID": "p"},
            clear=True,
        ):
            cfg = get_tavus_config()
        self.assertEqual(cfg.api_key, "k")
        self.assertEqual(cfg.persona_id, "p")
        self.assertTrue(cfg.configured)


if __name__ == "__main__":
    unittest.main()
