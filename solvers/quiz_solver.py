import re
import time
from playwright.sync_api import Page
from config import Config
from solvers.activity_tracker import ActivityTracker
from solvers.gemini_generator import answer_multiple_choice_question, answer_fill_in_the_blanks
from utils.score_parser import is_page_score_passing, parse_score_value


class QuizSolver:
    """
    Automated solver for standard Moodle Quiz activities (/mod/quiz/view.php and /mod/quiz/attempt.php).
    Features:
    - Inspects previous attempt summary tables and highest grades.
    - Evaluates marks against the passing threshold (Skips if passing, Re-does if failing).
    - Starts fresh or re-attempt attempts.
    - Solves multiple-choice, true/false, and short-answer questions using Gemini AI.
    - Submits and finishes attempts, capturing final review marks.
    """

    def __init__(self, page: Page, tracker: ActivityTracker = None, title: str = ""):
        self.page = page
        self.tracker = tracker
        self.title = title

        # Auto-accept browser dialogs
        try:
            self.page.on("dialog", lambda d: (print(f"[Quiz Dialog] Auto-accepting: {d.message}"), d.accept()))
        except Exception:
            pass

    def solve(self) -> bool:
        print("\n" + "=" * 60)
        print(f"[Quiz Solver] Starting Moodle Quiz Solver: {self.title or self.page.url}")
        print("=" * 60)

        # -------------------------------------------------------------
        # 1. LIVE PAGE MARKS & THRESHOLD CHECK (ON VIEW PAGE)
        # -------------------------------------------------------------
        if "attempt.php" not in self.page.url.lower():
            is_passing, score_str, marks_pct, threshold = is_page_score_passing(self.page, "quiz")

            if is_passing:
                print(f"[Quiz Solver] Activity already has passing grade on LMS ({score_str} >= {threshold}% threshold). Skipping!")
                if self.tracker:
                    self.tracker.record_activity(self.page.url, self.title or self.page.title(), "quiz", score=score_str, status="Completed")
                self._check_manual_completion()
                return True
            elif marks_pct is not None:
                print(f"[Quiz Solver] Previous attempt marks ({score_str}) are below threshold ({threshold}%). Re-attempting Quiz!")
            else:
                print("[Quiz Solver] No previous attempt detected. Starting fresh Quiz attempt...")

        # -------------------------------------------------------------
        # 2. START / RE-ATTEMPT QUIZ
        # -------------------------------------------------------------
        if "attempt.php" not in self.page.url.lower():
            started = self._start_or_resume_quiz()
            if not started:
                print("[Quiz Solver Warning] Could not start or resume quiz attempt.")
                self._check_manual_completion()
                return False

        # -------------------------------------------------------------
        # 3. SOLVE QUESTIONS PAGE BY PAGE
        # -------------------------------------------------------------
        page_num = 1
        max_pages = 30

        while page_num <= max_pages:
            url_lower = self.page.url.lower()

            if "summary.php" in url_lower:
                print(f"[Quiz Solver] Reached Summary page (Page {page_num}). Submitting quiz...")
                break

            if "review.php" in url_lower:
                print("[Quiz Solver] Reached Review page directly.")
                break

            print(f"\n[Quiz Solver] Solving questions on attempt page {page_num}...")
            self._solve_questions_on_page()

            # Click Next page or Finish attempt
            next_btn = self.page.locator(
                "#mod_quiz-next-nav, input[value*='Next'], input[value*='Finish attempt'], "
                "button:has-text('Next page'), button:has-text('Finish attempt'), "
                "button.btn-primary:has-text('Next'), a:has-text('Next page')"
            )

            if next_btn.count() > 0 and next_btn.first.is_visible():
                btn_txt = (next_btn.first.inner_text() or next_btn.first.get_attribute("value") or "").strip()
                print(f"[Quiz Solver] Clicking '{btn_txt}' button...")
                next_btn.first.click()
                self.page.wait_for_load_state("domcontentloaded")
                self.page.wait_for_timeout(1500)
                page_num += 1
            else:
                # Check for explicit Finish Attempt link in quiz navigation block
                finish_link = self.page.locator("a.endtestlink, a:has-text('Finish attempt')")
                if finish_link.count() > 0 and finish_link.first.is_visible():
                    print("[Quiz Solver] Clicking Quiz navigation 'Finish attempt...' link...")
                    finish_link.first.click()
                    self.page.wait_for_load_state("domcontentloaded")
                    self.page.wait_for_timeout(1500)
                    break
                else:
                    print("[Quiz Solver] No next/finish button found on attempt page.")
                    break

        # -------------------------------------------------------------
        # 4. SUBMIT ALL AND FINISH
        # -------------------------------------------------------------
        self._submit_all_and_finish()

        # -------------------------------------------------------------
        # 5. REVIEW AND RECORD FINAL GRADE
        # -------------------------------------------------------------
        final_score = self._extract_review_grade()
        print(f"[Quiz Solver] Quiz completed! Achieved final grade: {final_score}")

        if self.tracker:
            self.tracker.record_activity(
                self.page.url,
                self.title or self.page.title(),
                "quiz",
                score=final_score,
                status="Completed"
            )

        self._finish_review()
        self._check_manual_completion()
        return True

    def _start_or_resume_quiz(self) -> bool:
        """Clicks Attempt quiz now, Re-attempt quiz, or Continue the last attempt."""
        attempt_btn_selectors = [
            "button:has-text('Attempt quiz now')",
            "button:has-text('Re-attempt quiz')",
            "button:has-text('Continue the last attempt')",
            "input[value='Attempt quiz now']",
            "input[value='Re-attempt quiz']",
            "input[value='Continue the last attempt']",
            ".quizattempt button[type='submit']",
            "button:has-text('Preview quiz now')",
            "input[value='Preview quiz now']"
        ]

        btn = None
        for sel in attempt_btn_selectors:
            loc = self.page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                btn = loc.first
                break

        if not btn:
            return False

        btn_txt = btn.inner_text().strip() or btn.get_attribute("value") or "Start"
        print(f"[Quiz Solver] Clicking '{btn_txt}' button...")
        btn.click()
        self.page.wait_for_timeout(1500)

        # Handle modal confirmation (e.g. "Start attempt" dialog)
        modal_confirm = self.page.locator(
            ".modal-content input[value='Start attempt'], "
            ".modal-content button:has-text('Start attempt'), "
            "#id_submitbutton, "
            "button[data-action='save']:has-text('Start attempt')"
        )
        if modal_confirm.count() > 0 and modal_confirm.first.is_visible():
            print("[Quiz Solver] Confirming 'Start attempt' modal dialog...")
            modal_confirm.first.click()
            self.page.wait_for_load_state("domcontentloaded")
            self.page.wait_for_timeout(2000)

        return "attempt.php" in self.page.url.lower()

    def _solve_questions_on_page(self):
        """Finds each question block on the page and answers it."""
        questions = self.page.locator("div.que").all()
        print(f"[Quiz Solver] Found {len(questions)} question(s) on current page.")

        for idx, q in enumerate(questions, 1):
            try:
                q_class = q.get_attribute("class") or ""
                qtext_loc = q.locator("div.qtext")
                if qtext_loc.count() == 0:
                    continue

                q_text = " ".join(qtext_loc.first.inner_text().split())

                # 1. Multiple Choice / True-False questions
                if "multichoice" in q_class or "truefalse" in q_class:
                    answers = q.locator(".answer div.r0, .answer div.r1, .answer label, .answer .form-check").all()
                    options = []
                    for opt in answers:
                        txt = " ".join(opt.inner_text().split())
                        if txt:
                            options.append(txt)

                    if options:
                        ans_indices = answer_multiple_choice_question(q_text, options, single_choice=True)
                        if isinstance(ans_indices, int):
                            ans_indices = [ans_indices]
                        elif not isinstance(ans_indices, list):
                            ans_indices = [0]
                        if not ans_indices:
                            ans_indices = [0]

                        # Click selected option elements
                        for selected_idx in ans_indices:
                            if 0 <= selected_idx < len(answers):
                                opt_el = answers[selected_idx]
                                radio = opt_el.locator("input[type='radio'], input[type='checkbox']").first
                                if radio.count() > 0:
                                    radio.check(force=True)
                                else:
                                    opt_el.click()
                                print(f"  [Q{idx}] Answered MC (Option {selected_idx}): \"{options[selected_idx][:60]}\"")

                # 2. Short Answer / Fill in Blanks
                elif "shortanswer" in q_class or q.locator("input[type='text'].form-control, input.form-control").count() > 0:
                    inputs = q.locator("input[type='text']").all()
                    for inp in inputs:
                        if inp.is_visible():
                            ans = answer_fill_in_the_blanks(q_text)
                            inp.fill(ans)
                            print(f"  [Q{idx}] Filled short answer: \"{ans[:60]}\"")

            except Exception as e:
                print(f"[Quiz Solver Warning] Error answering question {idx}: {e}")

    def _submit_all_and_finish(self):
        """Navigates through summary page and confirms final submission."""
        try:
            # Check for Submit all and finish on summary page
            submit_btn = self.page.locator(
                "button:has-text('Submit all and finish'), input[value='Submit all and finish'], "
                ".btn-finishattempt button, form.btn-finishattempt input"
            )
            if submit_btn.count() > 0 and submit_btn.first.is_visible():
                print("[Quiz Solver] Clicking 'Submit all and finish' on summary page...")
                submit_btn.first.click()
                self.page.wait_for_timeout(1000)

            # Confirm modal dialog
            modal_submit = self.page.locator(
                ".modal-content button:has-text('Submit all and finish'), "
                ".modal-content input[value='Submit all and finish'], "
                ".confirmation-buttons input[value='Submit all and finish'], "
                ".moodle-dialogue-confirm button.btn-primary"
            )
            if modal_submit.count() > 0 and modal_submit.first.is_visible():
                print("[Quiz Solver] Confirming modal 'Submit all and finish'...")
                modal_submit.first.click()
                self.page.wait_for_load_state("domcontentloaded")
                self.page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[Quiz Solver Warning] Submission sequence note: {e}")

    def _extract_review_grade(self) -> str:
        """Extracts the achieved grade/marks from review screen or attempts table."""
        try:
            main_loc = self.page.locator("#region-main")
            main_text = main_loc.inner_text() if main_loc.count() > 0 else ""

            # Check for "Grade: X / Y (Z%)" or "Marks: X / Y"
            grade_m = re.search(r"(?:grade|marks?)[:\s]+([\d\.]+(?:\s*(?:/|out of)\s*[\d\.]+)?(?:\s*\([\d\.]+%?\))?)", main_text, re.IGNORECASE)
            if grade_m:
                return grade_m.group(0).strip()

            if self.tracker:
                score = self.tracker.extract_score_from_page(self.page)
                if score and score != "Completed":
                    return score
        except Exception:
            pass
        return "Completed"

    def _finish_review(self):
        """Clicks Finish Review on review page to return to view.php."""
        try:
            finish_rev = self.page.locator("a:has-text('Finish review'), .mod_quiz-next-nav a, a[href*='view.php']")
            if finish_rev.count() > 0 and finish_rev.first.is_visible():
                print("[Quiz Solver] Clicking 'Finish review' to return to quiz summary...")
                finish_rev.first.click()
                self.page.wait_for_load_state("domcontentloaded")
                self.page.wait_for_timeout(1000)
        except Exception:
            pass

    def _check_manual_completion(self):
        """Auto-clicks manual completion button if available."""
        try:
            manual_btn = self.page.locator("button[data-action='toggle-manual-completion'][data-toggletype='manual:mark-done']")
            if manual_btn.count() > 0 and manual_btn.first.is_visible():
                print("[Quiz Solver] Clicking 'Mark as done' manual completion toggle...")
                manual_btn.first.click()
                self.page.wait_for_timeout(800)
        except Exception:
            pass
