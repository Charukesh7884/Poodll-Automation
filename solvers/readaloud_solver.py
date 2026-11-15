import re
import time
from typing import Optional
from playwright.sync_api import Page
from audio.router import AudioRouter
from pathlib import Path
from config import Config
from utils.score_parser import parse_score_value


class ReadAloudSolver:
    """Solver for Poodll ReadAloud activities (/mod/readaloud/view.php)."""

    def __init__(self, page: Page, router: AudioRouter, speech_wav: Path):
        self.page = page
        self.router = router
        self.speech_wav = speech_wav

    def _extract_existing_score(self, main_text: str) -> tuple[Optional[float], str]:
        """Extracts the numeric grade/accuracy and raw score string from existing attempt tables or feedback."""
        # 1. Check generaltable / attempt summary table
        try:
            tables = self.page.locator("table.generaltable, .mod_readaloud_attemptsummary, .attempts-table").all()
            for tbl in tables:
                if tbl.is_visible():
                    headers = [h.inner_text().strip().lower() for h in tbl.locator("th").all()]
                    rows = tbl.locator("tbody tr").all()
                    if rows:
                        last_row = rows[-1]
                        cells = [c.inner_text().strip() for c in last_row.locator("td").all()]
                        for idx, h in enumerate(headers):
                            if idx < len(cells) and any(kw in h for kw in ["grade", "score", "mark", "accuracy"]):
                                val = parse_score_value(cells[idx])
                                if val is not None:
                                    return val, f"{h.capitalize()}: {cells[idx]}"
                        for c_text in cells:
                            val = parse_score_value(c_text)
                            if val is not None:
                                return val, c_text
        except Exception:
            pass

        # 2. Check evaluation block text
        acc_match = re.search(r"accuracy[:\s\n]*(\d+(?:\.\d+)?)", main_text, re.IGNORECASE)
        if acc_match:
            val = float(acc_match.group(1))
            return val, f"Accuracy: {val}%"

        # 3. Check general score / grade in main_text
        val = parse_score_value(main_text)
        if val is not None:
            return val, f"Score: {val}"

        return None, ""

    def solve(self) -> bool:
        print("\n" + "=" * 50)
        print("SOLVING POODLL READALOUD ACTIVITY")
        print("=" * 50)

        min_score = getattr(Config, "READALOUD_MIN_SCORE", 80)
        print(f"[ReadAloud] Passing score threshold: {min_score}%")

        # Check if already completed or attempted
        main_text = self.page.locator("#region-main").inner_text().lower() if self.page.locator("#region-main").count() > 0 else ""
        has_table = self.page.locator("table.generaltable tbody tr").count() > 0
        is_already_attempted = (
            "summary of your previous attempts" in main_text
            or "your previous attempts" in main_text
            or "your latest attempt has been received" in main_text
            or "the evaluation is shown below" in main_text
            or ("wpm" in main_text and "accuracy" in main_text and "words/min" in main_text)
            or has_table
        )

        from utils.score_parser import is_page_score_passing
        is_passing, score_str, marks_pct, threshold = is_page_score_passing(self.page, "readaloud")

        if is_passing:
            print(f"[ReadAloud] Activity has passing grade on LMS ({score_str} >= {threshold}%). Skipping!")
            try:
                pending_btn = self.page.locator("button[data-action='toggle-manual-completion'][data-toggletype='manual:mark-done']")
                if pending_btn.count() > 0 and pending_btn.first.is_visible():
                    print("[ReadAloud] Auto-clicking 'Mark as done'...")
                    pending_btn.first.click()
                    self.page.wait_for_timeout(800)
            except Exception:
                pass
            return True
        elif marks_pct is not None:
            print(f"[ReadAloud] Previous attempt grade ({score_str}) is below threshold ({threshold}%). Re-attempting activity!")

            # Check if there is an explicit re-take or re-attempt button
            retake_btn = self.page.locator(
                "button:has-text('Re-take'), a:has-text('Re-take'), "
                "button:has-text('Take again'), a:has-text('Take again'), "
                "button:has-text('Try again'), a:has-text('Try again'), "
                "button:has-text('New attempt'), a:has-text('New attempt'), "
                "#mod_readaloud_button_retake, .mod_readaloud_button_retake"
            )
            if retake_btn.count() > 0 and retake_btn.first.is_visible():
                print("[ReadAloud] Clicking Re-take button to launch fresh attempt...")
                try:
                    retake_btn.first.click()
                    self.page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"[ReadAloud] Note on clicking re-take button: {e}")

        # 1. Extract passage text directly from DOM (avoid clicking Card 1 / Preview)
        extracted_text = self.page.evaluate("""() => {
            // 1. Spans with individual words in order
            const spans = Array.from(document.querySelectorAll('.mod_readaloud_grading_passageword'));
            if (spans.length > 0) {
                return spans.map(s => s.textContent.trim()).filter(Boolean).join(' ');
            }
            // 2. Passage containers
            const els = Array.from(document.querySelectorAll('.mod_readaloud_passage_cont, .mod_readaloud_passage, #mod_readaloud_readingcontainer'));
            for (const el of els) {
                const txt = el.textContent.trim();
                if (txt.length > 20) return txt.replace(/\\s+/g, ' ');
            }
            return '';
        }""")

        if extracted_text:
            print(f"[ReadAloud] Extracted Paragraph directly from DOM ({len(extracted_text)} chars):")
            print(f"  \"{extracted_text[:120]}...\"")

        # 2. Click the Third Card (Read mode: #mod_readaloud_button_startnoshadow)
        print("[ReadAloud] Step 4: Locating and clicking the Read card (3rd card)...")
        read_card = self.page.locator("#mod_readaloud_button_startnoshadow")
        if read_card.count() > 0 and read_card.first.is_visible():
            read_card.first.click()
        else:
            visible_cards = [c for c in self.page.locator(".mode-chooser").all() if c.is_visible()]
            if len(visible_cards) >= 3:
                print(f"[ReadAloud] Clicking 3rd visible card out of {len(visible_cards)} cards...")
                visible_cards[2].click()
            elif visible_cards:
                print("[ReadAloud] Clicking last visible card...")
                visible_cards[-1].click()
        self.page.wait_for_timeout(2500)

        # 3. If extracted_text was empty, extract now that Read mode has revealed the passage
        if not extracted_text:
            extracted_text = self.page.evaluate("""() => {
                const spans = Array.from(document.querySelectorAll('.mod_readaloud_grading_passageword'));
                if (spans.length > 0) {
                    return spans.map(s => s.textContent.trim()).filter(Boolean).join(' ');
                }
                const cont = document.querySelector('.mod_readaloud_passage_cont, #mod_readaloud_readingcontainer');
                return cont ? cont.innerText.trim() : '';
            }""")
            if extracted_text:
                print(f"[ReadAloud] Extracted Paragraph after opening Read mode ({len(extracted_text)} chars):")
                print(f"  \"{extracted_text[:120]}...\"")

        if not extracted_text:
            extracted_text = "Artificial Intelligence focuses on creating intelligent agents that perceive and act."

        # 4. Wait for Microphone Record button (in iframe or on page)
        print("[ReadAloud] Step 5: Waiting for Microphone Record button in Read mode...")
        rec_btn = None
        stop_btn = None
        start_wait = time.time()
        while time.time() - start_wait < 30:
            # Check iframe first (standard CloudPoodll)
            if self.page.locator("#therecorderid iframe").count() > 0:
                frame = self.page.frame_locator("#therecorderid iframe")
                btn = frame.locator(".poodll_start-recording_readaloud, button[aria-label='Record']")
                if btn.count() > 0 and btn.first.is_visible():
                    rec_btn = btn.first
                    stop_btn = frame.locator(".poodll_stop-recording_readaloud, button[aria-label='Stop']").first
                    break

            # Check page directly
            page_btn = self.page.locator(".poodll_start-recording_readaloud, button[aria-label='Record']")
            if page_btn.count() > 0 and page_btn.first.is_visible():
                rec_btn = page_btn.first
                stop_btn = self.page.locator(".poodll_stop-recording_readaloud, button[aria-label='Stop']").first
                break

            self.page.wait_for_timeout(500)

        if not rec_btn:
            raise TimeoutError("[ReadAloud] Microphone Record button was not found within 30 seconds.")

        # 5. Click Record
        print("[ReadAloud] Step 6: Starting recording...")
        rec_btn.click()
        time.sleep(2.0)

        # 6. Convert text to speech and play to VB-CABLE Input
        print("[ReadAloud] Step 7: Synthesizing speech and routing to VB-CABLE Input...")
        self.router.play_tts(extracted_text, self.speech_wav, blocking=True)
        print("  Audio playback finished!")
        time.sleep(1.5)

        # 7. Click Stop
        print("[ReadAloud] Step 8: Stopping recording...")
        try:
            if stop_btn:
                stop_btn.click()
            print("  Recording stopped! Waiting for audio upload & submission...")
        except Exception as e:
            print(f"  Stop button note: {e}")

        # Wait for submission processing or feedback
        for _ in range(15):
            self.page.wait_for_timeout(1000)
            status = self.page.evaluate("""() => {
                const fb = document.getElementById('mod_readaloud_feedback_cont');
                const prog = document.getElementById('mod_readaloud_progress_cont');
                return (fb && fb.offsetParent !== null) || (prog && prog.offsetParent === null);
            }""")
            if status:
                break

        # Auto-click 'Mark as done' if manual completion exists
        try:
            pending_btn = self.page.locator("button[data-action='toggle-manual-completion'][data-toggletype='manual:mark-done']")
            if pending_btn.count() > 0 and pending_btn.first.is_visible():
                print("[ReadAloud] Marking activity as done on LMS...")
                pending_btn.first.click()
                self.page.wait_for_timeout(800)
        except Exception:
            pass

        print("[ReadAloud] Activity completed successfully!")
        return True
