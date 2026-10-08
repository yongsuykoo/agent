import json
import unittest
import tempfile
import types
import wave
from pathlib import Path
from unittest.mock import patch, Mock
from app_agent.voice import transcribe, synthetic_test_audio


class VoiceTests(unittest.TestCase):
    def test_synthetic_speech_writes_valid_audio_without_opening_a_microphone(self):
        voice, stream = Mock(), Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.wav"
            def speak(phrase):
                with wave.open(str(path), "wb") as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
                    wav.writeframes(b'\x00\x00' * 22050)
            voice.Speak.side_effect = speak
            package = types.ModuleType("win32com.client")
            package.Dispatch = Mock(side_effect=[voice, stream])
            with patch("sys.platform", "win32"), \
                 patch.dict("sys.modules", {"win32com": types.ModuleType("win32com"), "win32com.client": package}):
                audio = synthetic_test_audio(path, "Known test utterance")
            self.assertTrue(audio.startswith(b"RIFF"))
            stream.Open.assert_called_once_with(str(path), 3, False)
            stream.Close.assert_called_once()
            self.assertIsNone(voice.AudioOutputStream)

    def test_speech_fixture_closes_stream_on_generation_failure(self):
        voice, stream = Mock(), Mock()
        voice.Speak.side_effect = RuntimeError("SAPI unavailable")
        package = types.ModuleType("win32com.client")
        package.Dispatch = Mock(side_effect=[voice, stream])
        with patch("sys.platform", "win32"), patch.dict("sys.modules", {"win32com": types.ModuleType("win32com"), "win32com.client": package}):
            with self.assertRaisesRegex(RuntimeError, "SAPI unavailable"):
                synthetic_test_audio("unused.wav", "Known utterance")
        stream.Close.assert_called_once()
        self.assertIsNone(voice.AudioOutputStream)
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
