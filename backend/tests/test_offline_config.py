"""The demo must stay offline even when the developer has live keys configured."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class OfflineConfigTest(unittest.TestCase):
    def test_offline_ignores_provider_keys(self):
        env = dict(os.environ, BOLO_OFFLINE="1", WA_TOKEN="fixture", WA_PHONE_NUMBER_ID="fixture",
                   SARVAM_API_KEY="fixture", GROQ_API_KEY="fixture", GEMINI_API_KEY="fixture",
                   BOLNA_API_KEY="fixture", BOLNA_AGENT_ID="fixture", TWILIO_TOKEN="fixture", TWILIO_SID="fixture")
        out = subprocess.check_output([sys.executable, "-c",
            "import config,json; print(json.dumps(config.status()))"], cwd=Path(__file__).resolve().parents[1], env=env)
        status = json.loads(out)
        self.assertEqual(status["whatsapp"], "simulator")
        self.assertEqual(status["llm"], ["offline rules"])
        self.assertEqual(status["calls"], "off")
        self.assertFalse(any(status[key] for key in ["stt_sarvam", "stt_groq", "stt_gemini"]))
