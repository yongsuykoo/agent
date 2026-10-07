"""Push-to-talk recording and cloud transcription; no always-on microphone."""
import io
import json
import os
import uuid
import wave
from urllib.request import Request, build_opener
from .research import NoRedirects, validate_api_key


class Recorder:
    def __init__(self):
        self.stream = None
        self.chunks = []

    def start(self):
        import sounddevice as sd
        self.chunks = []
        self.samplerate = int(sd.query_devices(kind="input")["default_samplerate"])
        self.stream = sd.InputStream(samplerate=self.samplerate, channels=1, dtype="int16",
                                    callback=lambda data, frames, time, status: self.chunks.append(data.copy()))
        self.stream.start()

    def stop(self):
        import numpy as np
        if self.stream is None:
            raise RuntimeError("Microphone is not recording.")
        self.stream.stop()
        self.stream.close()
        self.stream = None
        if not self.chunks:
            raise RuntimeError("No audio was recorded.")
        data = np.concatenate(self.chunks)
        self.chunks = []
        if len(data) > self.samplerate * 60:
            raise ValueError("Voice commands must be shorter than one minute.")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.samplerate)
            wav.writeframes(data.tobytes())
        return buffer.getvalue()


def transcribe(audio):
    key = os.getenv("AGENT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Voice transcription requires AGENT_API_KEY.")
    validate_api_key(key)
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="command.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode()
    body += audio + f"\r\n--{boundary}--\r\n".encode()
    request = Request("https://api.openai.com/v1/audio/transcriptions", data=body,
                      headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with build_opener(NoRedirects()).open(request, timeout=60) as response:
            return json.loads(response.read(100_000))["text"]
    except Exception as error:
        raise RuntimeError("Voice transcription failed; check credentials, network, and quota.") from error
