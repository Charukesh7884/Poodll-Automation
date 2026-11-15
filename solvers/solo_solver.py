import re
import time
from pathlib import Path
from playwright.sync_api import Page
from config import Config
from audio.router import AudioRouter
from solvers.gemini_generator import generate_speech_paragraph
from utils.score_parser import parse_score_value, is_passing_solo_score


class SoloSolver:
    """Solver for Poodll Solo speaking activities (/mod/solo/view.php)."""

    def __init__(self, page: Page, router: AudioRouter = None, speech_wav: Path = None):
        self.page = page
        self.router = router
        self.speech_wav = speech_wav

        # Auto-accept browser dialogs
        try:
            self.page.on("dialog", lambda d: (print(f"[Solo Dialog] Auto-accepting: {d.message}"), d.accept()))
        except Exception:
            pass

    def solve(self) -> bool:
        print("\n" + "=" * 60)
        print("SOLVING POODLL SOLO ACTIVITY")
        print("=" * 60)

        min_score = getattr(Config, "SOLO_MIN_SCORE", 70)

        url_lower = self.page.url.lower()
        main_text = self.page.locator("#region-main").inner_text() if self.page.locator("#region-main").count() > 0 else ""

        # -------------------------------------------------------------
        # 0. CHECK IF CURRENTLY ON AN ACTIVE IN-PROGRESS ATTEMPT STEP
        # -------------------------------------------------------------
        is_active_attempt = (
            "manageattempts.php" in url_lower
            or "stepno=" in url_lower
            or any(kw in main_text.lower() for kw in [
                "step 1", "step 2", "step 3", "step 4",
                "use the recorder below", "enter/check what you said", "model answer"
            ])
        )

        if is_active_attempt:
            print(f"[Solo] Active attempt in progress detected (URL: {self.page.url}). Resuming from current step...")

            # Check Step 4
            if "step 4" in main_text.lower() or "model answer" in main_text.lower():
                print("[Solo] Currently on Step 4 (Model Answer). Finishing attempt...")
                self._click_done()
                return self._check_results_and_reattempt_if_needed(attempt_count=1)

            # Check Step 3
            if "step 3" in main_text.lower() or "enter/check what you said" in main_text.lower():
                print("[Solo] Currently on Step 3 (Self-Transcribe). Processing transcript...")
                topic, mandatory_words, target_words = self._extract_step_1_info()
                speech_text = generate_speech_paragraph(topic, mandatory_words, target_words, full_context=main_text)
                self._handle_step_3_transcription(speech_text)
                self._click_done()
                return self._check_results_and_reattempt_if_needed(attempt_count=1)

            # Check Step 2
            if "step 2" in main_text.lower() or "use the recorder below" in main_text.lower():
                print("[Solo] Currently on Step 2 (Record). Recording and advancing...")
                topic, mandatory_words, target_words = self._extract_step_1_info()
                speech_text = generate_speech_paragraph(topic, mandatory_words, target_words, full_context=main_text)
                self._handle_step_2_recording(speech_text)
                self._handle_step_3_transcription(speech_text)
                self._click_done()
                return self._check_results_and_reattempt_if_needed(attempt_count=1)

            # Step 1 or start of attempt
            return self._run_attempt_flow(attempt_count=1)

        # -------------------------------------------------------------
        # 1. CHECK RESULTS / PREVIOUS ATTEMPTS (When not mid-attempt)
        from utils.score_parser import is_page_score_passing
        is_passing, score_str, marks_pct, threshold = is_page_score_passing(self.page, "solo")
        reattempt_btn = self.page.locator("a.solo_reattempt_btn, a[data-action='reattempt'], a:has-text('Try Again')")

        if is_passing and reattempt_btn.count() == 0:
            print(f"[Solo] Activity already completed with passing grade ({score_str} >= {threshold}% threshold). Moving to next activity.")
            self._check_manual_completion()
            return True
        elif marks_pct is not None and (marks_pct < threshold or reattempt_btn.count() > 0):
            print(f"[Solo] Score is {score_str} (< {threshold}% threshold). Re-attempting Solo!")
            if reattempt_btn.count() > 0 and reattempt_btn.first.is_visible():
                print("[Solo] Found 'Try Again' button. Starting Second Attempt...")
                reattempt_btn.first.click()
                self.page.wait_for_timeout(3000)
                return self._run_attempt_flow(attempt_count=2)
        elif is_passing:
            print(f"[Solo] Activity completed ({score_str}) with no reattempt available. Moving to next.")
            self._check_manual_completion()
            return True

        # Run primary attempt flow
        return self._run_attempt_flow(attempt_count=1)

    def _run_attempt_flow(self, attempt_count: int = 1) -> bool:
        """Executes the complete 4-step attempt flow: Prepare -> Record -> Transcribe -> Model Answer."""
        print(f"\n[Solo] Executing Attempt #{attempt_count}...")
        self._dismiss_modals()

        # -------------------------------------------------------------
        # STEP 1: PREPARE (Extract Topic, Targeted Words, and Word Count)
        # -------------------------------------------------------------
        print("\n[Solo] Step 1: Extracting topic, targeted words, and words goal...")
        topic, mandatory_words, target_words = self._extract_step_1_info()

        main_text = self.page.locator("#region-main").inner_text() if self.page.locator("#region-main").count() > 0 else ""

        # Generate paragraph via Gemini API
        print("\n[Solo] Generating academic speech paragraph via Gemini API...")
        speech_text = generate_speech_paragraph(topic, mandatory_words, target_words, full_context=main_text)
        print(f"  Speech Length: {len(speech_text.split())} words")
        print(f"  Generated Speech:\n  \"{speech_text}\"")

        self._dismiss_modals()

        # Click Start button to advance to Step 2 (Record)
        start_btn = self.page.locator(
            ".mod_solo_stepsubmit button:has-text('Start'), "
            "button.btn:has-text('Start'), "
            "button[id*='_button']:has-text('Start'), "
            "button:has-text('Start')"
        )
        if start_btn.count() > 0 and start_btn.first.is_visible():
            print("\n[Solo] Step 1 -> Step 2: Clicking 'Start' button...")
            try:
                start_btn.first.click(force=True)
                self.page.wait_for_timeout(3000)
            except Exception as e:
                print(f"[Solo Warning] Error clicking Start: {e}")

        # -------------------------------------------------------------
        # STEP 2: RECORDING & AUDIO PLAYBACK (STEP 2 OF 4)
        # -------------------------------------------------------------
        self._handle_step_2_recording(speech_text)

        # -------------------------------------------------------------
        # STEP 3: TRANSCRIPTION (STEP 3 OF 4)
        # -------------------------------------------------------------
        self._handle_step_3_transcription(speech_text)

        # -------------------------------------------------------------
        # STEP 4: MODEL ANSWER & FINISH ATTEMPT (STEP 4 OF 4)
        # -------------------------------------------------------------
        self._click_done()

        # -------------------------------------------------------------
        # STEP 5: EVALUATION & REATTEMPT IF SCORE < 70%
        # -------------------------------------------------------------
        return self._check_results_and_reattempt_if_needed(attempt_count=attempt_count)

    def _handle_step_2_recording(self, speech_text: str):
        """Handles Step 2: searches recorder, starts recording, plays TTS into VB-CABLE, sets filename, and clicks Next."""
        print("\n[Solo] Step 2: Searching for Microphone / Audio Recorder...")
        self._dismiss_modals()

        frame = self.page.frame_locator(
            "iframe.solo_audiorec_iframe, iframe[src*='mod_solo'], [id*='solo_audio_recorder'] iframe, .solo_audiorec_cont iframe"
        )
        rec_btn = frame.locator(
            ".poodll_mediarecorder_minimal_start_button, .poodll_start-recording_minimal, button[aria-label='Record'], .poodll_start-recording_readaloud, .poodll_record-btn"
        ).first

        recorder_started = False
        
        # Explicitly open settings and select VB-Cable for Solo
        try:
            settings_icon = frame.locator(".fa-cogs, [class*='fa-cogs']").first
            if settings_icon.count() > 0:
                print("  [Solo] Opening hidden audio settings to select VB-Cable...")
                settings_icon.click(force=True)
                time.sleep(1.0)
                
                # Attempt to find the microphone dropdown and select CABLE
                mic_select = frame.locator("select.select_settings_audio").first
                if mic_select.count() > 0:
                    options = mic_select.locator("option").all_inner_texts()
                    cable_opt = next((opt for opt in options if "CABLE Output" in opt or "VB-Audio" in opt), None)
                    if cable_opt:
                        print(f"  [Solo] Found mic dropdown, selecting: {cable_opt}")
                        mic_select.select_option(label=cable_opt, force=True)
                        time.sleep(0.5)
                    else:
                        print("  [Solo Warning] CABLE Output not found in audio settings dropdown.")
                
                # Try to close settings (clicking gear again often toggles it)
                settings_icon.click(force=True)
                time.sleep(1.0)
        except Exception as e:
            print(f"  [Solo Warning] Could not set microphone via settings: {e}")

        try:
            rec_btn.wait_for(state="visible", timeout=6000)
            print("  Found Microphone Record button! Clicking Record...")
            rec_btn.click(force=True)
            recorder_started = True
            time.sleep(1.5)
        except Exception:
            print("  [Notice] Microphone button not directly accessible (likely CDN blocking).")

        # Play synthesized speech into VB-CABLE Input
        print("  Playing synthesized speech into VB-CABLE Input...")
        try:
            if self.router and self.speech_wav:
                self.router.play_tts(speech_text, self.speech_wav, blocking=True)
                print("  Speech playback finished!")
            else:
                time.sleep(2.0)
        except Exception as e:
            print(f"  [Solo Audio Warning] Audio playback note: {e}")
        time.sleep(1.5)

        # Stop recording if active
        if recorder_started:
            try:
                stop_btn = frame.locator(
                    ".poodll_mediarecorder_minimal_stop_button, .poodll_stop-recording_minimal, button[aria-label='Stop'], .poodll_stop-recording_readaloud"
                ).first
                stop_btn.click(force=True)
                print("  Recording stopped! Waiting for audio processing...")
                time.sleep(5.0)
            except Exception as e:
                print(f"  Stop button note: {e}")

        # Ensure Moodle filename validation passes (CDN safeguard)
        self.page.evaluate(
            """() => {
                const inputs = document.querySelectorAll('input[id*="_filename"]');
                inputs.forEach(input => {
                    if (!input.value || input.value.trim() === '') {
                        input.value = 'solo_audio_recording.wav';
                    }
                });
            }"""
        )

        # Click Next button on Step 2 to advance to Step 3
        print("\n[Solo] Step 2 -> Step 3: Advancing to Step 3 (Transcription)...")
        next_btn = self.page.locator(
            ".mod_solo_stepsubmit button:has-text('Next'), "
            "button.btn:has-text('Next'), "
            "button[id*='_button']:has-text('Next'), "
            "button:has-text('Next')"
        )
        if next_btn.count() > 0 and next_btn.first.is_visible():
            next_btn.first.click(force=True)
            self.page.wait_for_timeout(4000)

    def _extract_step_1_info(self) -> tuple[str, list[str], int]:
        """Extracts speaking topic, target words, and words goal from page DOM."""
        # 1. Extract Topic
        topic_loc = self.page.locator(
            ".mod_solo_speakingtopic_readonly, .speaking_topic .mod_solo_step_card_content, [class*='speakingtopic']"
        )
        topic = ""
        if topic_loc.count() > 0 and topic_loc.first.inner_text().strip():
            topic = topic_loc.first.inner_text().strip()
        else:
            header_loc = self.page.locator("#region-main h2, #region-main h3, .page-header-headings h1")
            if header_loc.count() > 0:
                topic = header_loc.first.inner_text().strip()
            else:
                topic = self.page.title().split(":")[0].strip()

        # Clean topic text
        topic = re.sub(r"^(?:SPEAK ABOUT|Topic:)\s*", "", topic, flags=re.IGNORECASE).strip()
        print(f"  Speaking Topic: \"{topic}\"")

        # 2. Extract Targeted Words
        word_tags = self.page.locator(".mod_solo_targetwordtag, .mod_solo_step_card_tag:has-text('Target Words') ~ *").all()
        mandatory_words = []
        for w in word_tags:
            txt = w.inner_text().strip()
            clean_txt = (
                txt.replace("\ufffd", "'")
                .replace("“", '"')
                .replace("”", '"')
                .replace("‘", "'")
                .replace("’", "'")
                .strip()
            )
            if clean_txt and len(clean_txt) < 80 and clean_txt.lower() != "target words":
                mandatory_words.append(clean_txt)

        # Fallback: scan for words in target words card content
        if not mandatory_words:
            card_content = self.page.locator(".targetwords .mod_solo_step_card_content, [class*='targetwords'] .mod_solo_step_card_content")
            if card_content.count() > 0:
                raw_words = card_content.first.inner_text().strip().split()
                mandatory_words = [w for w in raw_words if len(w) > 2]

        mandatory_words = list(dict.fromkeys(mandatory_words))
        print(f"  Targeted Words ({len(mandatory_words)}): {mandatory_words}")

        # 3. Extract Word Count Goal
        goal_loc = self.page.locator(".words-goal .mod_solo_step_card_content, .words-goal, .time-words-goals, .time-goal")
        target_words = 100
        if goal_loc.count() > 0:
            for g in goal_loc.all():
                match = re.search(r"(\d+)\s*Words", g.inner_text(), re.IGNORECASE)
                if match:
                    target_words = int(match.group(1))
                    break
        print(f"  Target Word Count: ~{target_words} words")

        return topic, mandatory_words, target_words

    def _handle_step_3_transcription(self, speech_text: str):
        """
        Handles Step 3:
        1. Unhides the checkbox holder
        2. Checks 'I do not want to wait for the transcript'
        3. Enables and pastes the speech paragraph into textarea
        4. Clicks Submit to advance to Step 4 via AJAX
        """
        print("\n[Solo] Step 3: Handling Self-Transcribe page...")
        self.page.wait_for_timeout(1500)

        # 1. Reveal checkbox container (it has style="display: none;" by default)
        self.page.evaluate(
            """() => {
                const holder = document.querySelector('[id*="checkboxholder"]');
                if (holder) {
                    holder.style.display = 'block';
                    holder.style.visibility = 'visible';
                }
            }"""
        )
        self.page.wait_for_timeout(300)

        # 2. Check the "Do not wait for transcript" checkbox
        cb = self.page.locator("input[id*='dontwaitfortranscript']").first
        if cb.count() > 0:
            print("  Checking 'I do not want to wait for the transcript' checkbox...")
            try:
                if cb.is_visible():
                    cb.click()
                else:
                    cb.check(force=True)
            except Exception:
                try:
                    cb.check(force=True)
                except Exception:
                    pass

            # Dispatch change event via JS to trigger Moodle jQuery handler
            self.page.evaluate(
                """() => {
                    const el = document.querySelector('input[id*="dontwaitfortranscript"]');
                    if (el) {
                        el.checked = true;
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }"""
            )
            self.page.wait_for_timeout(500)

        # 3. Enable and fill the transcript textarea
        area = self.page.locator("textarea[id*='selftranscript'], textarea[name='selftranscript']").first
        if area.count() > 0:
            print(f"  Pasting generated paragraph into textarea ({len(speech_text.split())} words)...")
            self.page.evaluate(
                """() => {
                    const a = document.querySelector('textarea[id*="selftranscript"]');
                    if (a) {
                        a.removeAttribute('disabled');
                        a.disabled = false;
                    }
                }"""
            )

            try:
                area.fill(speech_text)
            except Exception:
                pass

            self.page.evaluate(
                """(val) => {
                    const a = document.querySelector('textarea[id*="selftranscript"]');
                    if (a) {
                        a.removeAttribute('disabled');
                        a.disabled = false;
                        a.value = val;
                        a.dispatchEvent(new Event('input', { bubbles: true }));
                        a.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""",
                speech_text
            )
            self.page.wait_for_timeout(500)

        # 4. Click Submit button on Step 3
        submit_btn = self.page.locator(
            ".mod_solo_stepsubmit button, "
            "button[id*='_button']:has-text('Submit'), "
            "button.btn:has-text('Submit'), "
            "button:has-text('Submit')"
        ).first
        if submit_btn.count() > 0 and submit_btn.is_visible():
            print("  Clicking Submit button on Step 3...")
            try:
                submit_btn.click()
                self.page.wait_for_timeout(5000)
            except Exception as e:
                print(f"  [Solo Warning] Error clicking Submit: {e}")

    def _click_done(self):
        """Clicks Done on Step 4 to complete the attempt."""
        print("\n[Solo] Step 4: Finishing attempt (Clicking 'Done')...")
        self.page.wait_for_timeout(1000)

        done_btn = self.page.locator(
            ".mod_solo_stepsubmit button, "
            "button[id*='_button']:has-text('Done'), "
            "#region-main button:not([data-action='toggle-manual-completion']):has-text('Done')"
        ).first
        if done_btn.count() > 0 and done_btn.is_visible():
            try:
                print(f"  Clicking Step 4 Done button (ID: {done_btn.get_attribute('id')})...")
                done_btn.click()
                self.page.wait_for_timeout(5000)
                print("  Successfully submitted Step 4.")
            except Exception as e:
                print(f"  [Solo Warning] Error clicking Done: {e}")

    def _check_results_and_reattempt_if_needed(self, attempt_count: int = 1) -> bool:
        """
        Inspects results and grade on the completion page.
        If grade < 70% and attempt_count < 2, clicks 'Try Again' for Second Attempt.
        """
        min_score = getattr(Config, "SOLO_MIN_SCORE", 70)
        self.page.wait_for_timeout(2000)

        score_str = self._extract_score_from_page()
        val = parse_score_value(score_str)

        print(f"\n[Solo] Attempt #{attempt_count} Result: {score_str} (Numeric: {val if val is not None else 'N/A'}%)")

        # Second Attempt Check (Only if grade < 70%)
        if attempt_count < 2 and (val is None or val < min_score):
            reattempt_btn = self.page.locator("a.solo_reattempt_btn, a[data-action='reattempt'], a:has-text('Try Again')")
            if reattempt_btn.count() > 0 and reattempt_btn.first.is_visible():
                print(f"\n[Solo] Score is {val if val is not None else 'unverified'}% (< {min_score}% threshold). Executing Second Attempt via 'Try Again' button...")
                reattempt_btn.first.click()
                self.page.wait_for_timeout(3000)
                return self._run_attempt_flow(attempt_count=2)

        self._check_manual_completion()
        print(f"[Solo] Finished attempt flow. Final Score: {score_str}")
        return True

    def _extract_score_from_page(self) -> str:
        """Extracts score / clarity percentage from the results screen or attempt summary table."""
        try:
            main_loc = self.page.locator("#region-main")
            main_text = main_loc.inner_text() if main_loc.count() > 0 else ""

            # Check general table
            table = self.page.locator("table.generaltable, .attempts-table").first
            if table.count() > 0 and table.is_visible():
                rows = table.locator("tbody tr").all()
                if rows:
                    last_row_text = rows[-1].inner_text().strip()
                    pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%", last_row_text)
                    if pct_m:
                        return f"Grade: {pct_m.group(1)}%"
                    match = re.search(r"(?:grade|score|marks?)[:\s]+(\d+(?:\.\d+)?)", last_row_text, re.IGNORECASE)
                    if match:
                        return f"Grade: {match.group(1)}"

            # Check speech details block
            if "your speech details" in main_text.lower() or "results of your speech below" in main_text.lower() or "automatic evaluation" in main_text.lower():
                ratio_match = re.search(r"(\d+\s*/\s*\d+)", main_text)
                pct_matches = re.findall(r"(\d+(?:\.\d+)?%)", main_text)
                parts = []
                if ratio_match:
                    parts.append(f"Words: {ratio_match.group(1)}")
                if pct_matches:
                    parts.append(f"Score: {pct_matches[0]}")
                if parts:
                    return " | ".join(parts)

            # Check for general percentage in region-main
            pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", main_text)
            if pct_match:
                return f"Score: {pct_match.group(1)}%"

        except Exception as e:
            print(f"[Solo Warning] Error extracting score: {e}")

        return "Completed"

    def _dismiss_modals(self):
        """Dismisses any unexpected popups or backdrops."""
        try:
            modal_btn = self.page.locator(
                ".modal.show button:has-text('OK'), "
                ".modal.show [data-action='save'], "
                ".modal.show .close, "
                ".modal.show button.btn-primary, "
                ".moodle-dialogue-focused button:has-text('OK')"
            )
            if modal_btn.count() > 0 and modal_btn.first.is_visible():
                modal_btn.first.click()
                self.page.wait_for_timeout(500)
        except Exception:
            pass

    def _check_manual_completion(self):
        """Clicks 'Mark as done' ONLY after an attempt has actually completed."""
        try:
            manual_btn = self.page.locator("button[data-action='toggle-manual-completion']:has-text('Mark as done')")
            if manual_btn.count() > 0 and manual_btn.first.is_visible():
                btn_txt = manual_btn.first.inner_text().strip().lower()
                if "mark as done" in btn_txt:
                    print("[Solo] Clicking 'Mark as done' completion requirement toggle...")
                    manual_btn.first.click()
                    self.page.wait_for_timeout(1000)
        except Exception:
            pass
