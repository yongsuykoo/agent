import json
import unittest
from unittest.mock import patch, Mock
from app_agent.voice import transcribe


class VoiceTests(unittest.TestCase):
    def test_audio_sent_as_wav_and_transcript_returned(self):
        response = Mock()
        response.read.return_value = json.dumps({"text": "Calculate two plus two"}).encode()
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.dict("os.environ", {"AGENT_API_KEY": "test"}), patch("app_agent.voice.build_opener", return_value=opener):
            self.assertEqual(transcribe(b"RIFFtestaudio"), "Calculate two plus two")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/audio/transcriptions")
        self.assertIn(b"RIFFtestaudio", request.data)
        self.assertIn(b"whisper-1", request.data)

    def test_missing_credentials_fail_before_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("app_agent.voice.build_opener") as opener:
            with self.assertRaises(RuntimeError):
                transcribe(b"audio")
            opener.assert_not_called()
