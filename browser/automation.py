from typing import Dict, Any, List, Optional
from playwright.sync_api import BrowserContext, Page


class BrowserController:

    def __init__(self, context: BrowserContext):
        self.context = context
        self.page: Optional[Page] = None

    def navigate(self, url: str) -> Page:
        self.page = self.context.new_page()
        self.page.goto(url, wait_until="domcontentloaded")
        return self.page

    def inspect_audio_devices(self) -> List[Dict[str, Any]]:
        if not self.page:
            raise RuntimeError("No active page. Call navigate() first.")

        result = self.page.evaluate(
            """
            async () => {
                const devices = await navigator.mediaDevices.enumerateDevices();
                return devices
                    .filter(d => d.kind === "audioinput")
                    .map(d => ({
                        deviceId: d.deviceId,
                        label: d.label,
                        kind: d.kind
                    }));
            }
            """
        )
        return result

    def verify_cable_stream(self) -> Dict[str, Any]:
        if not self.page:
            raise RuntimeError("No active page. Call navigate() first.")

        result = self.page.evaluate(
            """
            async () => {
                const stream = await navigator.mediaDevices.getUserMedia({
                    audio: true
                });

                const track = stream.getAudioTracks()[0];
                const settings = track.getSettings();

                const result = {
                    deviceId: settings.deviceId,
                    label: window.__POODLE_AUDIO_LABEL__ || track.label,
                    sampleRate: settings.sampleRate,
                    channelCount: settings.channelCount,
                    echoCancellation: settings.echoCancellation,
                    noiseSuppression: settings.noiseSuppression,
                    autoGainControl: settings.autoGainControl
                };

                track.stop();
                return result;
            }
            """
        )
        return result
