from pathlib import Path
import pyttsx3


class TTSEngine:

    def __init__(
        self,
        rate=170,
        volume=1.0,
        voice_id=None
    ):
        self.rate = rate
        self.volume = volume
        self.voice_id = voice_id

    def _create_engine(self):
        engine = pyttsx3.init(driverName="sapi5")
        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", self.volume)
        if self.voice_id:
            engine.setProperty("voice", self.voice_id)
        return engine

    def synthesize_to_file(
        self,
        text,
        output_path
    ):
        engine = self._create_engine()
        engine.save_to_file(text, str(output_path))
        engine.runAndWait()
        engine.stop()
        return output_path
