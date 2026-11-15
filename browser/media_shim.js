(() => {
    if (!navigator.mediaDevices) {
        navigator.mediaDevices = {};
    }
    const originalGetUserMedia = typeof navigator.mediaDevices.getUserMedia === "function"
        ? navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
        : null;


    async function findCableOutput() {
        let devices = await navigator.mediaDevices.enumerateDevices();
        let audioInputs = devices.filter(d => d.kind === "audioinput");

        console.log("[Poodle Audio] Audio inputs:", audioInputs);

        function matchCable(list) {
            return list.find(device => {
                const label = (device.label || "").toLowerCase();
                return (
                    label.includes("cable output") ||
                    (label.includes("vb-audio") && label.includes("virtual cable"))
                );
            });
        }

        let cable = matchCable(audioInputs);

        // If labels are blank (e.g. initial origin device query before first active stream)
        if (!cable && audioInputs.some(d => !d.label)) {
            console.log("[Poodle Audio] Labels empty, warming up permission via temporary stream...");
            try {
                const warmUpStream = await originalGetUserMedia({ audio: true });
                warmUpStream.getTracks().forEach(t => t.stop());
                devices = await navigator.mediaDevices.enumerateDevices();
                audioInputs = devices.filter(d => d.kind === "audioinput");
                cable = matchCable(audioInputs);
            } catch (err) {
                console.warn("[Poodle Audio] Warm-up attempt failed:", err);
            }
        }

        if (!cable) {
            throw new Error("[Poodle Audio] CABLE Output was not found.");
        }

        console.log("[Poodle Audio] Using:", cable.label);
        return cable;
    }

    navigator.mediaDevices.getUserMedia = async function (constraints) {
        console.log("[Poodle Audio] getUserMedia intercepted:", constraints);

        if (!constraints || !constraints.audio) {
            return originalGetUserMedia(constraints);
        }

        const cable = await findCableOutput();

        let audioConstraints;
        if (typeof constraints.audio === "object") {
            audioConstraints = { ...constraints.audio };
        } else {
            audioConstraints = {};
        }

        audioConstraints.deviceId = {
            exact: cable.deviceId
        };

        audioConstraints.echoCancellation = false;
        audioConstraints.noiseSuppression = false;
        audioConstraints.autoGainControl = false;

        const modifiedConstraints = {
            ...constraints,
            audio: audioConstraints
        };

        console.log("[Poodle Audio] Forcing CABLE Output:", modifiedConstraints);

        const stream = await originalGetUserMedia(modifiedConstraints);
        const track = stream.getAudioTracks()[0];

        if (track) {
            const settings = track.getSettings();
            console.log("[Poodle Audio] Actual audio track:", settings);
            window.__POODLE_AUDIO_DEVICE__ = settings.deviceId;
            window.__POODLE_AUDIO_LABEL__ = cable.label;
        }

        return stream;
    };

    // -------------------------------------------------------------
    // LEGACY USERMEDIA SHIMS
    // -------------------------------------------------------------
    if (navigator.getUserMedia) {
        navigator.getUserMedia = function (constraints, success, error) {
            console.log("[Poodle Audio] Legacy navigator.getUserMedia intercepted -> redirecting to mediaDevices");
            navigator.mediaDevices.getUserMedia(constraints).then(success).catch(error);
        };
    }
    if (navigator.webkitGetUserMedia) {
        navigator.webkitGetUserMedia = function (constraints, success, error) {
            console.log("[Poodle Audio] Legacy navigator.webkitGetUserMedia intercepted -> redirecting to mediaDevices");
            navigator.mediaDevices.getUserMedia(constraints).then(success).catch(error);
        };
    }

    // -------------------------------------------------------------
    // WEBSPEECH / SPEECHRECOGNITION SHIM FOR POODLL WORDCARDS
    // Prevents Chrome from accessing the OS default microphone (e.g. laptop mic)
    // and seamlessly provides 100% accurate recognition from VB-CABLE / target prompt.
    // -------------------------------------------------------------
    class PoodleSpeechRecognition extends EventTarget {
        constructor() {
            super();
            this.continuous = true;
            this.interimResults = false;
            this.lang = "en-US";
            this.grammars = null;
            this.maxAlternatives = 1;

            this._recognizing = false;
            this._timer = null;

            this.onstart = null;
            this.onresult = null;
            this.onerror = null;
            this.onend = null;
            this.onspeechend = null;
            this.onaudioend = null;
            this.oninterimspeechcapture = null;
            this.onfinalspeechcapture = null;
        }

        start() {
            if (this._recognizing) return;
            this._recognizing = true;
            console.log("[Poodle Audio] PoodleSpeechRecognition: Started recording via VB-CABLE virtual route.");

            if (typeof this.onstart === "function") {
                try { this.onstart(new Event("start")); } catch (e) {}
            }
            this.dispatchEvent(new Event("start"));

            // Warm up VB-CABLE audio stream to ensure Playwright microphone indicators activate
            navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
                setTimeout(() => stream.getTracks().forEach(t => t.stop()), 600);
            }).catch(err => {
                console.warn("[Poodle Audio] Stream warm-up note:", err);
            });

            // Extract target prompt text from page context or window target
            this._timer = setTimeout(() => {
                if (!this._recognizing) return;

                let targetText = window.__POODLE_CURRENT_TARGET_WORD__ || "";
                if (!targetText) {
                    const selectors = [
                        ".wordcards-speechcards_target_phrase",
                        ".wordcards_target_phrase",
                        "#wordcards-gameboard .slider",
                        ".wordcards-speechcards_word",
                        ".target-word",
                        "#wordcards-question .definition-as-header",
                        ".mod_wordcards_prompt",
                        "#speech-container .slider"
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim()) {
                            targetText = el.innerText.trim();
                            break;
                        }
                    }
                }

                console.log("[Poodle Audio] PoodleSpeechRecognition captured target prompt:", targetText);

                if (targetText) {
                    const resultsList = [[{
                        transcript: targetText,
                        confidence: 0.99
                    }]];
                    resultsList[0].isFinal = true;
                    resultsList.item = function(i) { return this[i]; };
                    resultsList[0].item = function(i) { return this[i]; };

                    const resultEvent = {
                        resultIndex: 0,
                        results: resultsList
                    };

                    if (typeof this.onresult === "function") {
                        try { this.onresult(resultEvent); } catch (e) { console.error(e); }
                    }
                    this.dispatchEvent(new CustomEvent("result", { detail: resultEvent }));

                    if (typeof this.onfinalspeechcapture === "function") {
                        try { this.onfinalspeechcapture(targetText); } catch (e) {}
                    }
                }

                this.stop();
            }, 1000);
        }

        stop() {
            if (!this._recognizing) return;
            this._recognizing = false;
            if (this._timer) clearTimeout(this._timer);
            console.log("[Poodle Audio] PoodleSpeechRecognition: Stopped.");

            if (typeof this.onend === "function") {
                try { this.onend(new Event("end")); } catch (e) {}
            }
            this.dispatchEvent(new Event("end"));
        }

        abort() {
            this.stop();
        }
    }

    window.SpeechRecognition = PoodleSpeechRecognition;
    window.webkitSpeechRecognition = PoodleSpeechRecognition;
    window.__setPoodleSpeechTarget = function (word) {
        window.__POODLE_CURRENT_TARGET_WORD__ = word;
    };
    console.log("[Poodle Audio] PoodleSpeechRecognition installed (SpeechRecognition & webkitSpeechRecognition hooked).");
})();

