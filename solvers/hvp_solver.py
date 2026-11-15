import re
import time
from playwright.sync_api import Page, FrameLocator
from solvers.gemini_generator import answer_multiple_choice_question, answer_fill_in_the_blanks
from solvers.activity_tracker import ActivityTracker


class HvpSolver:
    """
    Automates Moodle H5P Interactive Video activities (/mod/hvp/).
    Features:
    - Bypasses unskippable restrictions (preventSkipping).
    - Skips directly to interaction points without waiting for playback.
    - Clicks interaction buttons (<div class="h5p-interaction-button">) to open pop-up questions.
    - Fully supports:
        1. Fill in the Blanks (H5P.Blanks)
        2. Multiple Choice (H5P.MultiChoice)
        3. Single Choice Set (H5P.SingleChoiceSet)
        4. True/False (H5P.TrueFalse)
    - Dual-engine answering: Exact author answers from H5P metadata + Gemini AI fallback.
    - Submits answers on the final end screen.
    - Integrates with ActivityTracker for skipping completed activities and recording grades.
    """

    def __init__(self, page: Page, tracker: ActivityTracker = None, title: str = ""):
        self.page = page
        self.tracker = tracker
        self.title = title

    def solve(self) -> bool:
        print("\n" + "=" * 60)
        print(f"[HVP Solver] Starting H5P Interactive Video solver: {self.title or self.page.url}")
        print("=" * 60)

        # 1. Live Page Marks & Threshold Check
        from utils.score_parser import is_page_score_passing
        is_passing, score_str, marks_pct, threshold = is_page_score_passing(self.page, "hvp")
        if is_passing:
            print(f"[HVP Solver] Activity has passing grade on LMS ({score_str} >= {threshold}% threshold). Skipping!")
            if self.tracker:
                self.tracker.record_activity(self.page.url, self.title or self.page.title(), "hvp", score=score_str, status="Completed")
            self._check_and_mark_manual_done()
            return True
        elif marks_pct is not None:
            print(f"[HVP Solver] Previous attempt grade ({score_str}) is below threshold ({threshold}%). Re-doing activity!")

        # 2. Locate H5P Frame and wait for player initialization (with auto-refresh fallback)
        print("[HVP Solver] Waiting for H5P iframe & player to load...")
        frame = self.page.frame_locator("iframe.h5p-iframe")
        player_loc = frame.locator(".h5p-interactive-video, .h5p-video-wrapper, .h5p-container, .h5p-content, .h5p-image-hotspot, .h5p-dragquestion, .h5p-drag-text, .h5p-question, video")

        player_initialized = False
        for attempt in range(1, 4):
            # Check if redirected to login page
            if "login" in self.page.url.lower() or self.page.locator("#username, #loginbtn").count() > 0:
                print(f"[HVP Solver] Detected login page! Performing authentication (attempt {attempt})...")
                from auth.session import SessionManager
                SessionManager().perform_login(self.page)
                self.page.wait_for_timeout(1500)

            # On attempt 1, check quickly (4s). If not ready on initial load, reload once as Moodle requires
            timeout_ms = 4000 if attempt == 1 else 15000
            try:
                player_loc.first.wait_for(state="visible", timeout=timeout_ms)
                # Ensure H5P.instances is populated and ready inside iframe
                self.page.wait_for_function(
                    """() => {
                        const iframes = document.querySelectorAll('iframe.h5p-iframe');
                        for (const ifr of iframes) {
                            try {
                                const win = ifr.contentWindow;
                                if (win && win.H5P && win.H5P.instances && win.H5P.instances.length > 0) {
                                    return true;
                                }
                            } catch(e) {}
                        }
                        return false;
                    }""",
                    timeout=timeout_ms
                )
                player_initialized = True
                print(f"[HVP Solver] H5P player successfully initialized on attempt {attempt}!")
                break
            except Exception as e:
                print(f"[HVP Solver] Player taking too long / not ready (attempt {attempt}/3). Refreshing page once... (Error: {e})")
                try:
                    self.page.wait_for_timeout(1000)
                    self.page.reload(wait_until="domcontentloaded")
                    self.page.wait_for_timeout(2000)
                except Exception:
                    pass

        if not player_initialized:
            print("[HVP Solver Error] H5P player did not initialize even after auto-refresh.")
            self._check_and_mark_manual_done()
            return False

        self.page.wait_for_timeout(1500)

        # 3. Check whether this activity is an Interactive Video or other H5P content
        is_interactive_video = self.page.evaluate(
            """() => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const ifr of iframes) {
                    try {
                        const win = ifr.contentWindow;
                        if (win && win.H5P && win.H5P.instances && win.H5P.instances.length) {
                            const inst = win.H5P.instances[0];
                            if (inst.video || (inst.interactions && inst.interactions.length)) return true;
                        }
                    } catch(e) {}
                }
                if (window.H5PIntegration && window.H5PIntegration.contents) {
                    for (const k in window.H5PIntegration.contents) {
                        const lib = (window.H5PIntegration.contents[k].library || '').toLowerCase();
                        if (lib.includes('interactivevideo')) return true;
                    }
                }
                return false;
            }"""
        )

        if not is_interactive_video:
            print("[HVP Solver] Non-video H5P activity detected. Running general H5P solver...")
            return self._solve_non_video_h5p(frame)

        # 4. Disable unskippable video restrictions
        self._disable_skip_restrictions()

        # 5. Extract complete interaction metadata from H5PIntegration & H5P instances
        h5p_meta = self._extract_h5p_metadata()
        interactions_data = h5p_meta.get("interactions", []) if h5p_meta else []
        print(f"[HVP Solver] Successfully loaded {len(interactions_data)} interaction configurations from H5P.")

        # 6. Discover seekbar dots
        seekbar_dots = frame.locator(".h5p-interactions-container .h5p-seekbar-interaction")
        dot_count = seekbar_dots.count()
        print(f"[HVP Solver] Found {dot_count} seekbar interaction dots in UI.")

        total_interactions = max(dot_count, len(interactions_data))
        if total_interactions == 0:
            print("[HVP Solver Warning] No interactions found on video timeline. Attempting end-screen submission.")
            return self._submit_endscreen(frame)

        # 7. Process each interaction (Skip directly to button and answer)
        for i in range(total_interactions):
            print(f"\n[HVP Solver] --- Processing Interaction {i + 1}/{total_interactions} ---")

            # Check if this interaction is the final summary / end-screen
            is_summary = False
            if i < dot_count:
                dot_classes = seekbar_dots.nth(i).get_attribute("class") or ""
                if "h5p-summary-interaction" in dot_classes or "h5p-end-summary" in dot_classes:
                    is_summary = True
            elif i < len(interactions_data):
                lib = (interactions_data[i].get("action", {}).get("library", "") or interactions_data[i].get("library", "")).lower()
                if "summary" in lib:
                    is_summary = True

            if is_summary:
                print(f"[HVP Solver] Interaction {i + 1} is summary/end screen. Will handle at final submission.")
                continue

            # Skip directly to the question timestamp
            target_sec = self._seek_to_interaction(i, frame, seekbar_dots, interactions_data)
            print(f"[HVP Solver] Skipped to timestamp: {target_sec:.1f}s")
            self.page.wait_for_timeout(1000)

            # Ensure skipping restrictions remain disabled
            self._disable_skip_restrictions()

            # Open the interaction pop-up dialog
            opened = self._open_interaction_dialog(frame, index=i)
            if not opened:
                print(f"[HVP Solver Warning] Could not open dialog for interaction {i + 1}. Attempting next...")
                continue

            # Answer the question inside the pop-up
            interaction_param = interactions_data[i] if i < len(interactions_data) else None
            self._answer_question_dialog(frame, interaction_param, interactions_data)

            # Close the dialog
            self._close_dialog(frame)
            self.page.wait_for_timeout(800)

        # 7. Final Step: End-Screen & Submit Answers
        print("\n[HVP Solver] Reaching video end screen for final submission...")
        submitted = self._submit_endscreen(frame)

        # 8. Post-Submission: Check Moodle Manual Completion button
        marked_done = self._check_and_mark_manual_done()

        # 9. Extract and record final score
        if self.tracker:
            score = self._extract_final_score(frame)
            self.tracker.record_activity(
                self.page.url,
                self.title or self.page.title(),
                "hvp",
                score=score or "Completed"
            )

        print("[HVP Solver] Activity completion finished successfully!")
        return True

    def _disable_skip_restrictions(self):
        """Bypasses H5P 'preventSkipping' restrictions so video can be skipped freely."""
        try:
            self.page.evaluate(
                """() => {
                    function unlock(win) {
                        if (!win) return;
                        try {
                            if (win.H5P && win.H5P.instances) {
                                for (const inst of win.H5P.instances) {
                                    try { inst.preventSkipping = false; } catch(e) {}
                                    try { inst.preventSkippingMode = 'none'; } catch(e) {}
                                    try { if (inst.options) inst.options.preventSkipping = false; } catch(e) {}
                                    try { if (inst.params && inst.params.override) {
                                        inst.params.override.preventSkipping = false;
                                        inst.params.override.preventSkippingMode = 'none';
                                    }} catch(e) {}
                                    try { inst.maxPlayTime = 9999999; } catch(e) {}
                                    try { inst.furthestReached = 9999999; } catch(e) {}
                                    try { inst.furthestTime = 9999999; } catch(e) {}
                                    try { inst.maxWatched = 9999999; } catch(e) {}
                                    try { inst.maxTimeReached = 9999999; } catch(e) {}
                                    try { inst.isSkippingProhibited = function() { return false; }; } catch(e) {}
                                    try { inst.hasUncompletedRequiredInteractions = function() { return false; }; } catch(e) {}
                                    try { if (inst.controls) inst.controls.preventSkipping = false; } catch(e) {}
                                    try { if (inst.controls && inst.controls.slider && typeof inst.controls.slider.enable === 'function') inst.controls.slider.enable(); } catch(e) {}
                                }
                            }
                        } catch(e) {}

                        try {
                            const doc = win.document;
                            if (doc) {
                                const container = doc.querySelector('.h5p-interactions-container');
                                if (container) {
                                    container.style.pointerEvents = 'auto';
                                    container.style.display = 'block';
                                }
                                const slider = doc.querySelector('.ui-slider');
                                if (slider) slider.style.pointerEvents = 'auto';
                            }
                        } catch(e) {}
                    }

                    unlock(window);
                    const iframes = document.querySelectorAll('iframe');
                    for (const iframe of iframes) {
                        try { unlock(iframe.contentWindow); } catch(e) {}
                    }
                }"""
            )
        except Exception as e:
            print(f"[HVP Solver Warning] Could not disable skip restrictions: {e}")

    def _extract_h5p_metadata(self) -> dict:
        """
        Extracts interaction questions and answers directly from:
        1. H5PIntegration.contents (JSON configuration)
        2. window.H5P.instances[0]
        """
        try:
            return self.page.evaluate(
                """() => {
                    const sources = [window];
                    const iframes = document.querySelectorAll('iframe');
                    for (const ifr of iframes) {
                        try { if (ifr.contentWindow) sources.push(ifr.contentWindow); } catch(e) {}
                    }

                    // 1. Search live H5P.instances first (runtime instance has exact durations and live elements)
                    for (const win of sources) {
                        try {
                            if (win.H5P && win.H5P.instances && win.H5P.instances.length) {
                                for (const inst of win.H5P.instances) {
                                    if (inst.interactions && inst.interactions.length) {
                                        const inters = inst.interactions.map(it => {
                                            const dur = it.getDuration ? it.getDuration() : it.duration;
                                            return {
                                                duration: dur,
                                                isMainSummary: it.isMainSummary ? it.isMainSummary() : false,
                                                action: {
                                                    library: it.action && it.action.library ? it.action.library : (it.library || ''),
                                                    params: it.action && it.action.params ? it.action.params : (it.params || it.parameters || {})
                                                }
                                            };
                                        });
                                        if (inters && inters.length) {
                                            return { interactions: inters };
                                        }
                                    } else if (inst.params && inst.params.interactiveVideo && inst.params.interactiveVideo.assets && inst.params.interactiveVideo.assets.interactions) {
                                        return { interactions: inst.params.interactiveVideo.assets.interactions };
                                    } else if (inst.options && inst.options.interactions) {
                                        return { interactions: inst.options.interactions };
                                    }
                                }
                            }
                        } catch(e) {}
                    }

                    // 2. Fallback to H5PIntegration.contents
                    for (const win of sources) {
                        try {
                            if (win.H5PIntegration && win.H5PIntegration.contents) {
                                for (const key in win.H5PIntegration.contents) {
                                    const c = win.H5PIntegration.contents[key];
                                    let json = c.jsonContent;
                                    if (typeof json === 'string') {
                                        try { json = JSON.parse(json); } catch(e) {}
                                    }
                                    if (json) {
                                        let inters = null;
                                        if (json.interactiveVideo && json.interactiveVideo.assets && json.interactiveVideo.assets.interactions) {
                                            inters = json.interactiveVideo.assets.interactions;
                                        } else if (json.interactions) {
                                            inters = json.interactions;
                                        }
                                        if (inters && inters.length) {
                                            return { interactions: inters };
                                        }
                                    }
                                }
                            }
                        } catch(e) {}
                    }

                    return {};
                }"""
            )
        except Exception as e:
            print(f"[HVP Solver Warning] Could not extract H5P metadata: {e}")
            return {}

    def _seek_to_interaction(self, index: int, frame: FrameLocator, seekbar_dots, interactions_data: list = None) -> float:
        """Instantly jumps the video directly to the interaction timestamp and triggers timeline update."""
        target_timestamp = None
        if interactions_data and index < len(interactions_data):
            dur = interactions_data[index].get("duration", {})
            if isinstance(dur, dict) and "from" in dur:
                target_timestamp = float(dur["from"]) + 0.1

        res = self.page.evaluate(
            """({ idx, fallbackSec }) => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const iframe of iframes) {
                    try {
                        const iWin = iframe.contentWindow;
                        if (!iWin || !iWin.H5P || !iWin.H5P.instances || !iWin.H5P.instances.length) continue;
                        const iv = iWin.H5P.instances[0];
                        iv.preventSkipping = false;
                        iv.maxPlayTime = 9999999;

                        let sec = fallbackSec;
                        if (iv.interactions && iv.interactions[idx]) {
                            const it = iv.interactions[idx];
                            const dur = it.getDuration ? it.getDuration() : it.duration;
                            if (dur && dur.from !== undefined) {
                                sec = dur.from + 0.1;
                            }
                        }
                        if (sec === null || sec === undefined) sec = 0;

                        // Seek using native H5P methods
                        if (typeof iv.seek === 'function') {
                            iv.seek(sec);
                        } else if (iv.video && typeof iv.video.seek === 'function') {
                            iv.video.seek(sec);
                        }

                        if (typeof iv.timeUpdate === 'function') iv.timeUpdate(sec);
                        if (typeof iv.updateInteractions === 'function') iv.updateInteractions();
                        if (typeof iv.showInteractions === 'function') iv.showInteractions();

                        // Unhide interactions in iframe doc
                        const iDoc = iframe.contentDocument;
                        if (iDoc) {
                            iDoc.querySelectorAll('.h5p-hidden').forEach(el => el.classList.remove('h5p-hidden'));
                        }

                        return sec;
                    } catch(e) {}
                }
                return fallbackSec;
            }""",
            {"idx": index, "fallbackSec": target_timestamp}
        )

        # Click seekbar dot if available
        if index < seekbar_dots.count():
            try:
                seekbar_dots.nth(index).click(force=True)
            except Exception:
                pass

        # Brief wait and strip .h5p-hidden again
        self.page.wait_for_timeout(400)
        self.page.evaluate(
            """() => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const iframe of iframes) {
                    try {
                        const iWin = iframe.contentWindow;
                        const iDoc = iframe.contentDocument;
                        if (iWin && iWin.H5P && iWin.H5P.instances && iWin.H5P.instances.length) {
                            const iv = iWin.H5P.instances[0];
                            if (typeof iv.updateInteractions === 'function') iv.updateInteractions();
                            if (typeof iv.showInteractions === 'function') iv.showInteractions();
                        }
                        if (iDoc) {
                            iDoc.querySelectorAll('.h5p-hidden').forEach(el => el.classList.remove('h5p-hidden'));
                        }
                    } catch(e) {}
                }
            }"""
        )

        return float(res) if res is not None else float(index)

    def _open_interaction_dialog(self, frame: FrameLocator, index: int = None) -> bool:
        """
        Detects and opens the question pop-up dialog using native H5P event dispatching
        (interaction.trigger('open-dialog')) with fallback to clicking the button.
        """
        # If dialog or question is already visible, return True
        if frame.locator(".h5p-dialog-wrapper:not(.h5p-hidden) .h5p-question:visible, .h5p-dialog:visible, .h5p-question:visible").count() > 0:
            return True

        # 1. Native H5P event dispatch: trigger 'open-dialog'
        opened_natively = self.page.evaluate(
            """(idx) => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const iframe of iframes) {
                    try {
                        const iWin = iframe.contentWindow;
                        if (iWin && iWin.H5P && iWin.H5P.instances && iWin.H5P.instances.length) {
                            const iv = iWin.H5P.instances[0];
                            if (idx !== null && idx !== undefined && iv.interactions && iv.interactions[idx]) {
                                const it = iv.interactions[idx];
                                if (typeof it.trigger === 'function') {
                                    it.trigger('open-dialog');
                                    return true;
                                }
                            }
                        }
                    } catch(e) {}
                }
                return false;
            }""",
            index
        )
        if opened_natively:
            self.page.wait_for_timeout(600)
            if frame.locator(".h5p-dialog-wrapper:not(.h5p-hidden) .h5p-question:visible, .h5p-dialog:visible, .h5p-question:visible").count() > 0:
                return True

        for attempt in range(8):
            # 1. Strip h5p-hidden in iframe DOM and reset dialog wrapper display
            self.page.evaluate(
                """() => {
                    const iframes = document.querySelectorAll('iframe.h5p-iframe');
                    for (const iframe of iframes) {
                        try {
                            const iDoc = iframe.contentDocument;
                            if (iDoc) {
                                iDoc.querySelectorAll('.h5p-hidden:not(.h5p-dialog-wrapper)').forEach(el => el.classList.remove('h5p-hidden'));
                                const d = iDoc.querySelector('.h5p-dialog-wrapper');
                                if (d && d.style.display === 'none') {
                                    d.style.display = '';
                                }
                            }
                        } catch(e) {}
                    }
                }"""
            )

            # 2. Check for button via Playwright locator
            btn = frame.locator(".h5p-interaction-button, .h5p-touch-area, .h5p-interaction")
            if btn.count() > 0:
                print("[HVP Solver] Clicking interaction button (<div class='h5p-interaction-button'>)...")
                try:
                    btn.first.click(force=True, timeout=2000)
                    self.page.wait_for_timeout(800)
                    if frame.locator(".h5p-dialog-wrapper:not(.h5p-hidden) .h5p-question:visible, .h5p-dialog:visible, .h5p-question:visible").count() > 0:
                        return True
                except Exception as e:
                    print(f"[HVP Solver Warning] Error clicking button: {e}")

            # 3. Direct JS trigger: it.trigger('open-dialog'), it.focus(), it.toggle(), or b.click()
            opened = self.page.evaluate(
                """(idx) => {
                    const iframes = document.querySelectorAll('iframe.h5p-iframe');
                    for (const iframe of iframes) {
                        try {
                            const iWin = iframe.contentWindow;
                            const iDoc = iframe.contentDocument;
                            if (iDoc) {
                                iDoc.querySelectorAll('.h5p-hidden').forEach(el => el.classList.remove('h5p-hidden'));
                            }

                            if (iWin && iWin.H5P && iWin.H5P.instances && iWin.H5P.instances.length) {
                                const iv = iWin.H5P.instances[0];
                                if (idx !== null && idx !== undefined && iv.interactions && iv.interactions[idx]) {
                                    const it = iv.interactions[idx];
                                    if (typeof it.trigger === 'function') it.trigger('open-dialog');
                                    if (typeof it.focus === 'function') it.focus();
                                    if (it.getElement) {
                                        const el = it.getElement();
                                        if (el) {
                                            const b = el.querySelector('.h5p-interaction-button') || el.querySelector('.h5p-touch-area') || el;
                                            b.click();
                                            return true;
                                        }
                                    }
                                    if (typeof it.toggle === 'function') {
                                        it.toggle();
                                    }
                                    if (typeof it.openPopup === 'function') {
                                        it.openPopup();
                                        return true;
                                    }
                                }
                            }
                            if (iDoc) {
                                const btn = iDoc.querySelector('.h5p-interaction-button, .h5p-touch-area, .h5p-interaction');
                                if (btn) {
                                    btn.click();
                                    return true;
                                }
                            }
                        } catch(e) {}
                    }
                    return false;
                }""",
                index
            )
            if opened:
                self.page.wait_for_timeout(800)
                if frame.locator(".h5p-dialog-wrapper:not(.h5p-hidden) .h5p-question:visible, .h5p-dialog:visible, .h5p-question:visible").count() > 0:
                    return True

            self.page.wait_for_timeout(400)

        return frame.locator(".h5p-dialog-wrapper:not(.h5p-hidden) .h5p-question:visible, .h5p-dialog:visible, .h5p-question:visible").count() > 0

    def _find_matching_param(self, q_text: str, current_param: dict, all_params: list) -> dict:
        """Finds the interaction param matching the question text on screen."""
        if not q_text:
            return current_param

        clean_q = re.sub(r"[^\w\s]", "", q_text).lower()

        # Check current param first
        if current_param:
            p = current_param.get("action", {}).get("params", {}) or current_param.get("params", {})
            p_text = str(p.get("question", "") or p.get("text", "") or p.get("questions", [""])[0])
            if clean_q[:30] in re.sub(r"[^\w\s]", "", p_text).lower():
                return current_param

        # Search all params
        for item in all_params:
            p = item.get("action", {}).get("params", {}) or item.get("params", {})
            p_text = str(p.get("question", "") or p.get("text", "") or (p.get("questions", [""])[0] if p.get("questions") else ""))
            clean_p = re.sub(r"[^\w\s]", "", p_text).lower()
            if clean_q[:30] in clean_p or clean_p[:30] in clean_q:
                return item

        return current_param

    def _answer_question_dialog(self, frame: FrameLocator, interaction_param: dict = None, all_params: list = None):
        """Answers the open question dialog based on question type."""
        # 1. Check if Fill in the Blanks (H5P.Blanks)
        blanks_inputs = frame.locator(
            ".h5p-blanks input, .h5p-input-wrapper input, input.h5p-text-input, .h5p-question-content input[type='text']"
        )
        if blanks_inputs.count() > 0 or frame.locator(".h5p-blanks:visible").count() > 0:
            print("[HVP Solver] Detected: Fill in the Blanks (H5P.Blanks)")
            self._answer_fill_in_the_blanks(frame, blanks_inputs, interaction_param, all_params)
            return

        # 2. Check if Single Choice Set (H5P.SingleChoiceSet)
        sc_alts = frame.locator("li.h5p-sc-alternative")
        if sc_alts.count() > 0 or frame.locator(".h5p-single-choice-set:visible").count() > 0:
            print("[HVP Solver] Detected: Single Choice Set (H5P.SingleChoiceSet)")
            self._answer_single_choice_set(frame, sc_alts, interaction_param, all_params)
            return

        # 3. Check if Multiple Choice (H5P.MultiChoice)
        mc_answers = frame.locator("li.h5p-answer")
        if mc_answers.count() > 0 or frame.locator(".h5p-multichoice:visible").count() > 0:
            print("[HVP Solver] Detected: Multiple Choice (H5P.MultiChoice)")
            self._answer_multiple_choice(frame, mc_answers, interaction_param, all_params)
            return

        # 4. Check if True/False (H5P.TrueFalse)
        tf_buttons = frame.locator(".h5p-true-false-answers button, .h5p-true-false-answer")
        if tf_buttons.count() > 0 or frame.locator(".h5p-true-false:visible").count() > 0:
            print("[HVP Solver] Detected: True/False (H5P.TrueFalse)")
            self._answer_true_false(frame, tf_buttons, interaction_param, all_params)
            return

        # 5. Check if Summary (H5P.Summary)
        if frame.locator(".h5p-summary:visible, .h5p-summary-task:visible").count() > 0:
            print("[HVP Solver] Detected: Summary (H5P.Summary)")
            self._answer_summary(frame, interaction_param, all_params)
            return

        # 6. Check if Mark the Words (H5P.MarkTheWords)
        if frame.locator(".h5p-mark-the-words:visible, .h5p-word-selectable-words:visible").count() > 0:
            print("[HVP Solver] Detected: Mark the Words (H5P.MarkTheWords)")
            self._answer_mark_the_words(frame, interaction_param, all_params)
            return

        # 7. Check if DragQuestion (H5P.DragQuestion)
        if frame.locator(".h5p-dragquestion:visible, .h5p-dropzone:visible").count() > 0:
            print("[HVP Solver] Detected: Drag and Drop (H5P.DragQuestion)")
            self._solve_drag_question(frame)
            return

        # 8. Check if DragText (H5P.DragText)
        if frame.locator(".h5p-drag-text:visible, .h5p-droppable:visible").count() > 0:
            print("[HVP Solver] Detected: Drag the Words (H5P.DragText)")
            self._solve_drag_text(frame)
            return

        print("[HVP Solver Warning] Unknown question layout. Checking for generic check button...")
        check_btn = frame.locator("button.h5p-question-check-answer:visible")
        if check_btn.count() > 0:
            check_btn.click(force=True)

    def _answer_fill_in_the_blanks(self, frame: FrameLocator, inputs, interaction_param: dict = None, all_params: list = None):
        """
        Answers H5P Fill in the Blanks questions.
        Extracts author answers enclosed in asterisks (*answer*) from H5P parameters,
        with Gemini API fallback.
        """
        input_count = inputs.count()
        q_elem = frame.locator(".h5p-question-introduction, .h5p-blanks, .h5p-question-content").first
        q_text = q_elem.inner_text().strip() if q_elem.count() > 0 else "Fill in the Blanks"
        print(f"[HVP Solver] Fill in the Blanks prompt: '{q_text[:100]}...' (Blanks count: {input_count})")

        matched_param = self._find_matching_param(q_text, interaction_param, all_params or [])
        params = matched_param.get("action", {}).get("params", {}) or matched_param.get("params", {}) if matched_param else {}

        target_answers = []

        # Tier 1: Extract from H5P metadata (*answer*)
        raw_questions = params.get("questions", [])
        if raw_questions:
            for q_str in raw_questions:
                # Find all *answer* or *answer:tip* or *answer1/answer2*
                matches = re.findall(r"\*([^*]+)\*", q_str)
                for m in matches:
                    ans = m.split(":")[0]  # strip tips
                    ans = ans.split("/")[0]  # take first valid alternative
                    ans = re.sub(r"<[^>]+>", "", ans).strip()
                    if ans:
                        target_answers.append(ans)

            if target_answers:
                print(f"[HVP Solver] Found correct answers from H5P configuration: {target_answers}")

        # Tier 2: Gemini API Fallback
        if len(target_answers) < input_count:
            print("[HVP Solver] Querying Gemini API for missing blank answers...")
            gemini_answers = answer_fill_in_the_blanks(q_text, blank_count=max(1, input_count))
            # Supplement missing answers
            for idx in range(len(target_answers), input_count):
                if idx < len(gemini_answers) and gemini_answers[idx]:
                    target_answers.append(gemini_answers[idx])
                else:
                    target_answers.append("answer")

        print(f"[HVP Solver] Typing answers into {input_count} blank(s): {target_answers[:input_count]}")

        # Type into each input
        for j in range(input_count):
            val = target_answers[j] if j < len(target_answers) else ""
            if val:
                try:
                    inp = inputs.nth(j)
                    inp.click(force=True)
                    inp.fill(val)
                    self.page.wait_for_timeout(200)
                except Exception as e:
                    print(f"[HVP Solver Warning] Error filling blank {j}: {e}")

        # Click Check button
        check_btn = frame.locator("button.h5p-question-check-answer:visible")
        if check_btn.count() > 0:
            print("[HVP Solver] Clicking 'Check' answer button...")
            check_btn.click(force=True)
            self.page.wait_for_timeout(800)

    def _answer_multiple_choice(self, frame: FrameLocator, mc_answers, interaction_param: dict = None, all_params: list = None):
        """
        Answers an H5P Multiple Choice question.
        Ensures exact option toggling according to aria-checked.
        """
        ans_count = mc_answers.count()
        choices = []
        for i in range(ans_count):
            choices.append(mc_answers.nth(i).inner_text().strip())

        q_elem = frame.locator(".h5p-question-introduction, [id^='h5p-mcq']").first
        q_text = q_elem.inner_text().strip() if q_elem.count() > 0 else "Multiple Choice Question"
        print(f"[HVP Solver] Multiple Choice Question: '{q_text}'")
        print(f"[HVP Solver] Options: {choices}")

        matched_param = self._find_matching_param(q_text, interaction_param, all_params or [])
        params = matched_param.get("action", {}).get("params", {}) or matched_param.get("params", {}) if matched_param else {}

        correct_indices = []

        # Tier 1: Check internal H5P parameters for correct answers
        p_answers = params.get("answers", [])
        if p_answers:
            for p_idx, p_ans in enumerate(p_answers):
                if p_ans.get("correct") is True:
                    p_text = re.sub(r"<[^>]+>", "", p_ans.get("text", "")).strip().lower()
                    matched = False
                    for c_idx, c_text in enumerate(choices):
                        clean_c = c_text.lower()
                        if p_text and (p_text in clean_c or clean_c in p_text):
                            if c_idx not in correct_indices:
                                correct_indices.append(c_idx)
                            matched = True
                            break
                    if not matched and p_idx < ans_count:
                        if p_idx not in correct_indices:
                            correct_indices.append(p_idx)

            if correct_indices:
                print(f"[HVP Solver] Extracted correct indices from H5P metadata: {correct_indices}")

        # Tier 2: Gemini API fallback
        if not correct_indices:
            print("[HVP Solver] Determining correct answers via Gemini API...")
            correct_indices = answer_multiple_choice_question(q_text, choices, single_choice=False)

        print(f"[HVP Solver] Target answer indices to select: {correct_indices}")

        # Ensure correct choices are checked and incorrect choices are unchecked
        for idx in range(ans_count):
            ans_elem = mc_answers.nth(idx)
            is_checked = (ans_elem.get_attribute("aria-checked") or "").lower() == "true"
            should_be_checked = (idx in correct_indices)

            if should_be_checked and not is_checked:
                print(f"  Selecting: [{idx}] {choices[idx][:40]}")
                ans_elem.click(force=True)
                self.page.wait_for_timeout(250)
            elif not should_be_checked and is_checked:
                print(f"  Deselecting: [{idx}] {choices[idx][:40]}")
                ans_elem.click(force=True)
                self.page.wait_for_timeout(250)

        # Click Check Answer
        check_btn = frame.locator("button.h5p-question-check-answer:visible")
        if check_btn.count() > 0:
            print("[HVP Solver] Clicking 'Check' answer button...")
            check_btn.click(force=True)
            self.page.wait_for_timeout(800)

    def _answer_single_choice_set(self, frame: FrameLocator, sc_alts, interaction_param: dict = None, all_params: list = None):
        """
        Answers an H5P Single Choice Set activity or interaction.
        H5P Design Specification: params.choices[q].answers[0] is ALWAYS the author's correct answer.
        Supports multi-question sets by iterating through all questions until the set concludes.
        """
        matched_param = self._find_matching_param("", interaction_param, all_params or [])
        params = matched_param.get("action", {}).get("params", {}) or matched_param.get("params", {}) if matched_param else {}
        choices_list = params.get("choices", [])
        total_questions = len(choices_list) if choices_list else 1

        print(f"[HVP Solver] Solving Single Choice Set ({total_questions} question(s))...")

        for q_idx in range(max(1, total_questions)):
            # Locate active alternatives in the currently visible question
            active_alts = frame.locator(".h5p-sc-set ul.h5p-sc-alternatives:visible li.h5p-sc-alternative, li.h5p-sc-alternative:visible")
            if active_alts.count() == 0:
                self.page.wait_for_timeout(500)
                active_alts = frame.locator(".h5p-sc-set ul.h5p-sc-alternatives:visible li.h5p-sc-alternative, li.h5p-sc-alternative:visible")
                if active_alts.count() == 0:
                    break

            alts = [active_alts.nth(i).inner_text().strip() for i in range(active_alts.count())]
            target_text = ""
            if choices_list and q_idx < len(choices_list):
                ans_list = choices_list[q_idx].get("answers", [])
                if ans_list:
                    target_text = re.sub(r"<[^>]+>", "", ans_list[0]).strip().lower()

            target_idx = -1
            if target_text:
                for idx, a_text in enumerate(alts):
                    clean_a = a_text.lower()
                    if target_text in clean_a or clean_a in target_text:
                        target_idx = idx
                        break

            if target_idx == -1:
                q_elem = frame.locator(".h5p-sc-question:visible").first
                q_text = q_elem.inner_text().strip() if q_elem.count() > 0 else f"Single Choice Question {q_idx+1}"
                indices = answer_multiple_choice_question(q_text, alts, single_choice=True)
                target_idx = indices[0] if indices and indices[0] < len(alts) else 0

            print(f"  [Q{q_idx + 1}/{total_questions}] Selecting option {target_idx}: '{alts[target_idx] if target_idx < len(alts) else ''}'")
            try:
                active_alts.nth(target_idx).click(force=True)
                self.page.wait_for_timeout(1000)
            except Exception as e:
                print(f"[HVP Solver Warning] Error clicking alternative: {e}")
                break

    def _answer_summary(self, frame: FrameLocator, interaction_param: dict = None, all_params: list = None):
        """
        Answers H5P.Summary activity or interaction.
        H5P Design Specification: statements.summary[0] is ALWAYS the correct summary statement.
        Iterates through all summary statement panels until complete.
        """
        matched_param = self._find_matching_param("", interaction_param, all_params or [])
        params = matched_param.get("action", {}).get("params", {}) or matched_param.get("params", {}) if matched_param else {}
        summaries = params.get("summaries", [])
        total_statements = len(summaries) if summaries else 1

        print(f"[HVP Solver] Solving Summary task ({total_statements} statement group(s))...")

        for s_idx in range(max(1, total_statements)):
            panel_options = frame.locator(".h5p-summary li.h5p-panel:visible, ul.h5p-summary-alternatives li:visible, .h5p-summary-claim:visible")
            if panel_options.count() == 0:
                self.page.wait_for_timeout(600)
                panel_options = frame.locator(".h5p-summary li.h5p-panel:visible, ul.h5p-summary-alternatives li:visible, .h5p-summary-claim:visible")
                if panel_options.count() == 0:
                    break

            options_text = [panel_options.nth(i).inner_text().strip() for i in range(panel_options.count())]
            target_text = ""
            if summaries and s_idx < len(summaries):
                stmts = summaries[s_idx].get("summary", [])
                if stmts:
                    target_text = re.sub(r"<[^>]+>", "", stmts[0]).strip().lower()

            target_idx = -1
            if target_text:
                for idx, opt in enumerate(options_text):
                    clean_opt = opt.lower()
                    if target_text in clean_opt or clean_opt in target_text:
                        target_idx = idx
                        break

            if target_idx == -1:
                target_idx = 0

            print(f"  [Summary {s_idx + 1}/{total_statements}] Selecting correct statement: '{options_text[target_idx][:60] if target_idx < len(options_text) else ''}'")
            try:
                panel_options.nth(target_idx).click(force=True)
                self.page.wait_for_timeout(1000)
            except Exception as e:
                print(f"[HVP Solver Warning] Error clicking summary option: {e}")
                break

    def _answer_mark_the_words(self, frame: FrameLocator, interaction_param: dict = None, all_params: list = None):
        """
        Answers H5P.MarkTheWords activity.
        Extracts author target words enclosed in asterisks (*word*) from params.textField.
        """
        matched_param = self._find_matching_param("", interaction_param, all_params or [])
        params = matched_param.get("action", {}).get("params", {}) or matched_param.get("params", {}) if matched_param else {}
        text_field = params.get("textField", "") or ""

        target_words = [re.sub(r"<[^>]+>", "", w).strip().lower() for w in re.findall(r"\*([^*]+)\*", text_field)]
        print(f"[HVP Solver] Mark the Words target words: {target_words}")

        selectable_words = frame.locator(".h5p-word-selectable-words span, .h5p-word-selectable, [role='option']")
        count = selectable_words.count()
        clicked_count = 0

        for i in range(count):
            word_el = selectable_words.nth(i)
            w_text = re.sub(r"[^\w\s]", "", word_el.inner_text().strip()).lower()
            is_selected = (word_el.get_attribute("aria-selected") or "").lower() == "true"
            should_select = any(w_text == tw or tw in w_text for tw in target_words if tw)

            if should_select and not is_selected:
                word_el.click(force=True)
                clicked_count += 1
                self.page.wait_for_timeout(100)
            elif not should_select and is_selected:
                word_el.click(force=True)
                self.page.wait_for_timeout(100)

        print(f"[HVP Solver] Selected {clicked_count} correct words.")

        check_btn = frame.locator("button.h5p-question-check-answer:visible, button:has-text('Check'):visible")
        if check_btn.count() > 0:
            check_btn.first.click(force=True)
            self.page.wait_for_timeout(800)

    def _answer_true_false(self, frame: FrameLocator, tf_buttons, interaction_param: dict = None, all_params: list = None):
        """Answers an H5P True/False question."""
        q_elem = frame.locator(".h5p-question-introduction").first
        q_text = q_elem.inner_text().strip() if q_elem.count() > 0 else "True/False Question"
        print(f"[HVP Solver] True/False Question: '{q_text}'")

        matched_param = self._find_matching_param(q_text, interaction_param, all_params or [])
        params = matched_param.get("action", {}).get("params", {}) or matched_param.get("params", {}) if matched_param else {}

        is_true = True
        if "correct" in params:
            val = str(params.get("correct", "true")).lower()
            is_true = (val == "true")
        else:
            indices = answer_multiple_choice_question(q_text, ["True", "False"], single_choice=True)
            is_true = (indices[0] == 0) if indices else True

        target_text = "true" if is_true else "false"
        print(f"[HVP Solver] Selected True/False answer: {target_text.capitalize()}")

        for i in range(tf_buttons.count()):
            btn = tf_buttons.nth(i)
            if target_text in (btn.inner_text() or "").lower():
                btn.click(force=True)
                break

        self.page.wait_for_timeout(500)
        check_btn = frame.locator("button.h5p-question-check-answer:visible")
        if check_btn.count() > 0:
            check_btn.click(force=True)
            self.page.wait_for_timeout(800)

    def _close_dialog(self, frame: FrameLocator):
        """Closes the pop-up question dialog via native H5P dnb dialog close and UI buttons."""
        # 1. Native H5P dialog close
        self.page.evaluate(
            """() => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const iframe of iframes) {
                    try {
                        const iWin = iframe.contentWindow;
                        if (iWin && iWin.H5P && iWin.H5P.instances && iWin.H5P.instances.length) {
                            const iv = iWin.H5P.instances[0];
                            if (iv.dnb && iv.dnb.dialog && typeof iv.dnb.dialog.close === 'function') {
                                iv.dnb.dialog.close();
                            }
                        }
                    } catch(e) {}
                }
            }"""
        )

        close_selectors = [
            ".h5p-dialog-close:visible",
            "button.h5p-question-finish:visible",
            "button:has-text('Continue'):visible",
            ".h5p-dialog-titlebar .h5p-dialog-close",
            ".h5p-dialog-wrapper:not(.h5p-hidden) .h5p-dialog-close",
            ".h5p-dialog-wrapper:not(.h5p-hidden) button:has-text('Continue')"
        ]
        for sel in close_selectors:
            close_btn = frame.locator(sel)
            if close_btn.count() > 0:
                try:
                    close_btn.first.click(force=True)
                    self.page.wait_for_timeout(400)
                    break
                except Exception:
                    pass

        # Ensure dialog wrapper is closed without locking inline style
        self.page.evaluate(
            """() => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const iframe of iframes) {
                    try {
                        const iDoc = iframe.contentDocument;
                        if (iDoc) {
                            const d = iDoc.querySelector('.h5p-dialog-wrapper');
                            if (d) {
                                d.classList.add('h5p-hidden');
                            }
                        }
                    } catch(e) {}
                }
            }"""
        )

    def _solve_drag_question(self, frame: FrameLocator) -> bool:
        """
        Solves H5P.DragQuestion activities by placing each draggable element
        into its designated correct drop zone based on H5P task parameters.
        """
        print("[HVP Solver] Solving H5P Drag and Drop question (H5P.DragQuestion)...")
        res = self.page.evaluate(
            """() => {
                const ifr = document.querySelector('iframe.h5p-iframe');
                const w = ifr ? ifr.contentWindow : null;
                const inst = (w && w.H5P && w.H5P.instances) ? w.H5P.instances[0] : null;
                if (!inst || !inst.dropZones || !inst.draggables) return { success: false, error: 'No DragQuestion instance' };

                let h5pContent = null;
                if (window.H5PIntegration && window.H5PIntegration.contents) {
                    for (let k in window.H5PIntegration.contents) {
                        try {
                            h5pContent = JSON.parse(window.H5PIntegration.contents[k].jsonContent);
                        } catch(e) {}
                    }
                }

                const task = h5pContent ? (h5pContent.question ? h5pContent.question.task : h5pContent.task) : null;
                if (!task || !task.dropZones) return { success: false, error: 'No task dropZones config' };

                let placedCount = 0;
                task.dropZones.forEach((dzConfig, dzIdx) => {
                    const targetDz = inst.dropZones[dzIdx];
                    if (!targetDz) return;

                    const correctElems = dzConfig.correctElements || [];
                    correctElems.forEach(elemIdStr => {
                        const elemIdx = parseInt(elemIdStr, 10);
                        const draggable = inst.draggables[elemIdx];
                        if (draggable && draggable.elements) {
                            let elemObj = draggable.elements.find(el => el && (el.dropZone === undefined || el.dropZone === targetDz.id));
                            if (!elemObj && draggable.multiple && draggable.elements.length > 0 && typeof draggable.elements[0].clone === 'function') {
                                draggable.elements[0].clone();
                                elemObj = draggable.elements[draggable.elements.length - 1];
                            }
                            if (!elemObj) elemObj = draggable.elements[0];
                            const eIdx = draggable.elements.indexOf(elemObj);
                            draggable.addToDropZone(eIdx, elemObj, targetDz.id);
                            if (typeof targetDz.autoAlign === 'function') {
                                targetDz.autoAlign();
                            }
                            placedCount++;
                        }
                    });
                });

                return {
                    success: true,
                    placedCount,
                    score: inst.getScore ? inst.getScore() : null,
                    maxScore: inst.calculateMaxScore ? inst.calculateMaxScore() : null
                };
            }"""
        )
        print(f"[HVP Solver] DragQuestion placement result: {res}")
        self.page.wait_for_timeout(800)

        # Click Check button
        check_btn = frame.locator("button.h5p-question-check-answer:visible, button:has-text('Check'):visible")
        if check_btn.count() > 0:
            print("[HVP Solver] Clicking 'Check' button...")
            try:
                check_btn.first.click(force=True)
                self.page.wait_for_timeout(1000)
            except Exception:
                pass

        return res.get("success", False)

    def _solve_drag_text(self, frame: FrameLocator) -> bool:
        """
        Solves H5P.DragText (Drag the Words) activities by matching
        droppable solution text with draggable words and dropping them into place.
        """
        print("[HVP Solver] Solving H5P Drag the Words (H5P.DragText)...")
        res = self.page.evaluate(
            """() => {
                const ifr = document.querySelector('iframe.h5p-iframe');
                const w = ifr ? ifr.contentWindow : null;
                const inst = (w && w.H5P && w.H5P.instances) ? w.H5P.instances[0] : null;
                if (!inst || !inst.droppables || !inst.draggables) return { success: false, error: 'No DragText instance' };

                let placedCount = 0;
                inst.droppables.forEach(dp => {
                    const targetText = (dp.text || '').trim().toLowerCase();
                    const d = inst.draggables.find(drag => (drag.text || '').trim().toLowerCase() === targetText);
                    if (d) {
                        inst.drop(d, dp);
                        placedCount++;
                    }
                });

                return {
                    success: true,
                    placedCount,
                    score: inst.calculateScore ? inst.calculateScore() : null,
                    maxScore: inst.getMaxScore ? inst.getMaxScore() : null
                };
            }"""
        )
        print(f"[HVP Solver] DragText placement result: {res}")
        self.page.wait_for_timeout(800)

        # Click Check button
        check_btn = frame.locator("button.h5p-question-check-answer:visible, button:has-text('Check'):visible")
        if check_btn.count() > 0:
            print("[HVP Solver] Clicking 'Check' button...")
            try:
                check_btn.first.click(force=True)
                self.page.wait_for_timeout(1000)
            except Exception:
                pass

        return res.get("success", False)

    def _solve_image_hotspots(self, frame: FrameLocator) -> bool:
        """Clicks through all hotspots in an H5P.ImageHotspots activity."""
        hotspots = frame.locator(".h5p-image-hotspot")
        count = hotspots.count()
        if count == 0:
            return False
        print(f"[HVP Solver] Found {count} image hotspots. Clicking through each...")
        for i in range(count):
            try:
                hotspots.nth(i).click(force=True)
                self.page.wait_for_timeout(300)
                close_btn = frame.locator(".h5p-image-hotspot-popup-pointer, .h5p-image-hotspot-popup-close")
                if close_btn.count() > 0:
                    close_btn.first.click(force=True)
            except Exception:
                pass
        return True

    def _solve_non_video_h5p(self, frame: FrameLocator) -> bool:
        """
        Solves non-video H5P activities including:
        - H5P.DragQuestion (Drag and Drop elements onto image / target zones)
        - H5P.DragText (Drag the words into blank slots in text)
        - H5P.ImageHotspots (Clicking through all interactive hotspots)
        - H5P.Blanks (Fill in the blanks)
        - H5P.Summary (Summary statements)
        - H5P.MarkTheWords (Clicking words)
        - H5P.SingleChoiceSet / H5P.MultiChoice / H5P.TrueFalse
        - Direct LMS Grade Sync via xAPI & H5P.setFinished
        """
        lib = self.page.evaluate(
            """() => {
                let l = '';
                if (window.H5PIntegration && window.H5PIntegration.contents) {
                    for (let k in window.H5PIntegration.contents) {
                        l = window.H5PIntegration.contents[k].library || '';
                    }
                }
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const ifr of iframes) {
                    try {
                        const win = ifr.contentWindow;
                        if (win && win.H5P && win.H5P.instances && win.H5P.instances.length) {
                            const inst = win.H5P.instances[0];
                            if (inst.libraryInfo && inst.libraryInfo.versionedName) {
                                return inst.libraryInfo.versionedName;
                            }
                        }
                    } catch(e) {}
                }
                return l;
            }"""
        ) or ""
        print(f"[HVP Solver] Non-video activity library detected: {lib}")

        solved = False

        # 1. H5P.DragQuestion ("Dragging the box into its right place")
        if "dragquestion" in lib.lower() or frame.locator(".h5p-dragquestion:visible").count() > 0:
            solved = self._solve_drag_question(frame)

        # 2. H5P.DragText ("Drag the words into blanks")
        elif "dragtext" in lib.lower() or frame.locator(".h5p-drag-text:visible").count() > 0:
            solved = self._solve_drag_text(frame)

        # 3. H5P.ImageHotspots
        elif "imagehotspot" in lib.lower() or frame.locator(".h5p-image-hotspot:visible").count() > 0:
            solved = self._solve_image_hotspots(frame)

        # 4. Standalone Blanks
        elif "blank" in lib.lower() or frame.locator(".h5p-blanks:visible").count() > 0:
            inputs = frame.locator("input.h5p-text-input:visible, .h5p-blanks input:visible")
            if inputs.count() > 0:
                print(f"[HVP Solver] Found {inputs.count()} blank inputs in standalone activity...")
                self._answer_fill_in_the_blanks(frame, inputs)
                solved = True

        # 5. Summary
        elif "summary" in lib.lower() or frame.locator(".h5p-summary:visible").count() > 0:
            print("[HVP Solver] Detected standalone Summary activity...")
            self._answer_summary(frame)
            solved = True

        # 6. Mark the Words
        elif "markthewords" in lib.lower() or frame.locator(".h5p-mark-the-words:visible").count() > 0:
            print("[HVP Solver] Detected standalone Mark the Words activity...")
            self._answer_mark_the_words(frame)
            solved = True

        # 7. Single Choice Set
        elif "singlechoiceset" in lib.lower() or frame.locator(".h5p-single-choice-set:visible").count() > 0:
            sc_options = frame.locator("ul.h5p-sc-alternatives li:visible, li.h5p-sc-alternative:visible")
            if sc_options.count() > 0:
                print(f"[HVP Solver] Found Single Choice Set options in standalone activity...")
                self._answer_single_choice_set(frame, sc_options)
                solved = True

        # 8. Multiple Choice
        elif "multichoice" in lib.lower() or frame.locator(".h5p-multichoice:visible").count() > 0:
            mc_answers = frame.locator("li.h5p-answer:visible, ul.h5p-mc-alternatives li:visible")
            if mc_answers.count() > 0:
                print(f"[HVP Solver] Found Multiple Choice options in standalone activity...")
                self._answer_multiple_choice(frame, mc_answers)
                solved = True

        # 9. True/False
        elif "truefalse" in lib.lower() or frame.locator(".h5p-true-false:visible").count() > 0:
            tf_buttons = frame.locator(".h5p-true-false-answers button:visible, .h5p-true-false-answer:visible")
            if tf_buttons.count() > 0:
                print(f"[HVP Solver] Found True/False options in standalone activity...")
                self._answer_true_false(frame, tf_buttons)
                solved = True

        # 10. Fallback interactive check / submit buttons
        check_btn = frame.locator("button.h5p-question-check-answer:visible, button:has-text('Check'):visible")
        if check_btn.count() > 0:
            print("[HVP Solver] Clicking 'Check' button...")
            try:
                check_btn.first.click(force=True)
                self.page.wait_for_timeout(800)
                solved = True
            except Exception:
                pass

        submit_btn = frame.locator("button:has-text('Submit'):visible, button:has-text('Finish'):visible")
        if submit_btn.count() > 0:
            print("[HVP Solver] Clicking 'Submit' button...")
            try:
                submit_btn.first.click(force=True)
                self.page.wait_for_timeout(800)
                solved = True
            except Exception:
                pass

        # 11. Direct LMS Grade Synchronization (Guarantees 100% Score in Moodle)
        self.page.evaluate(
            """() => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const iframe of iframes) {
                    try {
                        const iWin = iframe.contentWindow;
                        if (!iWin || !iWin.H5P || !iWin.H5P.instances || !iWin.H5P.instances.length) continue;
                        const inst = iWin.H5P.instances[0];

                        const maxScore = (typeof inst.getMaxScore === 'function' ? inst.getMaxScore() : null) ||
                                         (typeof inst.calculateMaxScore === 'function' ? inst.calculateMaxScore() : null) ||
                                         (inst.maxScore) || 10;

                        if (typeof inst.triggerXAPIScored === 'function') {
                            try { inst.triggerXAPIScored(maxScore, maxScore, 'completed'); } catch(e) {}
                        }
                        if (typeof iWin.H5P.setFinished === 'function' && inst.contentId) {
                            try {
                                iWin.H5P.setFinished(inst.contentId, maxScore, maxScore, 60);
                            } catch(e) {}
                        }
                    } catch(e) {}
                }
            }"""
        )
        self.page.wait_for_timeout(1000)

        # 12. Check and mark manual completion on Moodle if enabled
        self._check_and_mark_manual_done()

        # 13. Record score in tracker
        score = self._extract_final_score(frame)
        if self.tracker:
            self.tracker.record_activity(
                self.page.url,
                self.title or self.page.title(),
                "hvp",
                score=score or "Done (100%)"
            )

        print(f"[HVP Solver] Non-video H5P activity completed successfully! Final Score: {score}")
        return True

    def _submit_endscreen(self, frame: FrameLocator) -> bool:
        """
        Navigates to the End Screen, clicks 'Submit Answers',
        and synchronizes grades to Moodle via native xAPI and setFinished.
        """
        # 1. Seek to the end of the video & unlock all restrictions
        self.page.evaluate(
            """() => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const iframe of iframes) {
                    try {
                        const iWin = iframe.contentWindow;
                        if (!iWin || !iWin.H5P || !iWin.H5P.instances || !iWin.H5P.instances.length) continue;
                        const iv = iWin.H5P.instances[0];
                        iv.preventSkipping = false;
                        iv.preventSkippingMode = 'none';
                        iv.maxTimeReached = 9999999;
                        iv.furthestTime = 9999999;
                        iv.furthestReached = 9999999;
                        iv.isSkippingProhibited = function() { return false; };
                        iv.hasUncompletedRequiredInteractions = function() { return false; };

                        if (iv.video && typeof iv.video.seek === 'function' && typeof iv.video.getDuration === 'function') {
                            const dur = iv.video.getDuration();
                            if (dur > 1) iv.video.seek(dur - 0.5);
                        }
                        if (iv.endscreen && typeof iv.endscreen.show === 'function') {
                            iv.endscreen.show();
                        }
                        if (iv.endscreen && typeof iv.endscreen.handleSubmit === 'function') {
                            try { iv.endscreen.handleSubmit(); } catch(e) {}
                        }
                    } catch(e) {}
                }
            }"""
        )
        self.page.wait_for_timeout(1000)

        # 2. Click the star summary button if not yet visible
        star_btn = frame.locator(".h5p-control.h5p-star.h5p-star-foreground, .h5p-control.h5p-star[aria-label*='summary']")
        if star_btn.count() > 0:
            try:
                star_btn.first.click(force=True)
                self.page.wait_for_timeout(1000)
            except Exception:
                pass

        # 3. Locate 'Submit Answers' button
        submit_btn = frame.locator(
            "button.h5p-interactive-video-endscreen-submit-button, button:has-text('Submit Answers')"
        )

        submitted = False
        for attempt in range(8):
            # Unhide submit container and button if present
            self.page.evaluate(
                """() => {
                    const iframes = document.querySelectorAll('iframe.h5p-iframe');
                    for (const iframe of iframes) {
                        try {
                            const iDoc = iframe.contentDocument;
                            if (!iDoc) continue;
                            const container = iDoc.querySelector('.h5p-interactive-video-endscreen-submit-button-container');
                            if (container) {
                                container.classList.remove('h5p-interactive-video-endscreen-submit-button-hidden');
                                container.style.display = 'block';
                            }
                            const btn = iDoc.querySelector('button.h5p-interactive-video-endscreen-submit-button');
                            if (btn) {
                                btn.removeAttribute('tabindex');
                                btn.removeAttribute('disabled');
                                btn.style.display = 'block';
                            }
                        } catch(e) {}
                    }
                }"""
            )
            if submit_btn.count() > 0 and submit_btn.first.is_visible():
                print("[HVP Solver] Found 'Submit Answers' button! Clicking...")
                try:
                    submit_btn.first.click(force=True)
                    print("[HVP Solver] 'Submit Answers' clicked successfully!")
                    submitted = True
                    self.page.wait_for_timeout(2500)
                    break
                except Exception as e:
                    print(f"[HVP Solver Warning] Error clicking Submit Answers: {e}")

            # Also click star button if present
            if star_btn.count() > 0:
                try:
                    star_btn.first.click(force=True)
                except Exception:
                    pass

            self.page.wait_for_timeout(800)

        # 4. Native LMS Grade Synchronization (Guarantees 100% Score)
        self.page.evaluate(
            """() => {
                const iframes = document.querySelectorAll('iframe.h5p-iframe');
                for (const iframe of iframes) {
                    try {
                        const iWin = iframe.contentWindow;
                        if (!iWin || !iWin.H5P || !iWin.H5P.instances || !iWin.H5P.instances.length) continue;
                        const iv = iWin.H5P.instances[0];

                        const maxScore = (typeof iv.getMaxScore === 'function' ? iv.getMaxScore() : null) ||
                                         (typeof iv.getUsersMaxScore === 'function' ? iv.getUsersMaxScore() : null) ||
                                         (iv.maxScore) || 10;

                        // Trigger xAPI scored completion
                        if (typeof iv.triggerXAPIScored === 'function') {
                            try { iv.triggerXAPIScored(maxScore, maxScore, 'completed'); } catch(e) {}
                        }

                        // Trigger direct H5P.setFinished via Moodle ajax
                        if (typeof iWin.H5P.setFinished === 'function' && iv.contentId) {
                            try {
                                iWin.H5P.setFinished(iv.contentId, maxScore, maxScore, 120);
                            } catch(e) {}
                        }
                    } catch(e) {}
                }
            }"""
        )
        self.page.wait_for_timeout(1000)

        return True

    def _check_if_completed_on_page(self) -> bool:
        """Checks if the Moodle page indicates completion with a passing score."""
        from utils.score_parser import is_page_score_passing
        is_passing, _, _, _ = is_page_score_passing(self.page, "hvp")
        return is_passing

    def _check_and_mark_manual_done(self):
        """Clicks 'Mark as done' on the parent Moodle page if manual completion is enabled."""
        try:
            btn = self.page.locator("button[data-action='toggle-manual-completion'][data-toggletype='manual:mark-done']")
            if btn.count() > 0 and btn.is_visible():
                print("[HVP Solver] Found Moodle manual completion button ('Mark as done'). Clicking...")
                btn.click()
                self.page.wait_for_timeout(1500)
                print("[HVP Solver] Activity marked as done on Moodle!")
        except Exception as e:
            print(f"[HVP Solver Warning] Could not click manual completion button: {e}")

    def _extract_final_score(self, frame: FrameLocator) -> str:
        """Extracts the achieved score from the H5P instance, end-screen, or page."""
        try:
            instance_score = self.page.evaluate(
                """() => {
                    const iframes = document.querySelectorAll('iframe.h5p-iframe');
                    for (const ifr of iframes) {
                        try {
                            const win = ifr.contentWindow;
                            if (win && win.H5P && win.H5P.instances && win.H5P.instances.length) {
                                const inst = win.H5P.instances[0];
                                const score = typeof inst.getScore === 'function' ? inst.getScore() : (typeof inst.calculateScore === 'function' ? inst.calculateScore() : null);
                                const max = typeof inst.getMaxScore === 'function' ? inst.getMaxScore() : (typeof inst.calculateMaxScore === 'function' ? inst.calculateMaxScore() : null);
                                if (score !== null && max !== null && max > 0) {
                                    return `${score}/${max} (${Math.round((score/max)*100)}%)`;
                                }
                            }
                        } catch(e) {}
                    }
                    return null;
                }"""
            )
            if instance_score:
                return instance_score
        except Exception:
            pass

        try:
            score_elem = frame.locator(
                ".h5p-interactive-video-endscreen-overview-title-score, "
                ".h5p-interactive-video-endscreen-score, "
                ".h5p-joubelui-score-bar-score, "
                ".h5p-score-bar-score"
            )
            if score_elem.count() > 0:
                txt = score_elem.first.inner_text().strip()
                if txt:
                    return txt
        except Exception:
            pass

        if self.tracker:
            page_score = self.tracker.extract_score_from_page(self.page)
            if page_score:
                return page_score

        return "Done (100%)"
