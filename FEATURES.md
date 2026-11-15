# Features and Technical Capabilities

This document outlines the core architecture, technical implementations, edge cases handled, and optimization strategies integrated into the Poodll LMS Automation platform.

---

## 1. Virtual Audio Injection & Routing Pipeline
* **Zero Hardware Interference:** Directs synthesized audio exclusively through **VB-Audio Virtual Cable**, leaving physical microphones untouched.
* **SAPI5 Speech Synthesis:** High-clarity native Windows text-to-speech with tunable speaking rates (`TTS_RATE`) and calibrated output volume (`TTS_VOLUME`).
* **Targeted getUserMedia Shim:** Automatically replaces Chromium microphone constraints via `browser/media_shim.js`, binding `CABLE Output` device IDs directly into page context before scripts execute.
* **CloudPoodll SDK Interceptor:** Injects `browser/cloudpoodll_shim.js` to override recorder initialization, guaranteeing clean transmission to Poodll speech evaluation servers.

---

## 2. Comprehensive LMS Activity Solvers
* **Poodll Read-Aloud (`readaloud`):**
  - Parses reading passages, cleans punctuation and special tokens, and injects spoken audio into CloudPoodll mic evaluators.
  - Monitors accuracy scores and completion indicators against the configured threshold.
* **H5P & Interactive Video (`hvp`, `h5pactivity`):**
  - Traverses nested cross-domain iframes, detects overlay interaction points, drag-and-drops, and video quiz checkpoints.
  - Evaluates contextual questions with Google Gemini AI and confirms final score submission.
* **Poodll WordCards (`wordcards`):**
  - Detects vocabulary drill stages (definition matching, voice flashcards, listen-and-type).
  - Handles multi-step card deck workflows until the target passing percentage is reached.
* **Poodll Solo Speaking (`solo`):**
  - Reads monologue prompts and generates cohesive, contextually accurate spoken responses via Gemini AI.
  - Automatically records and uploads speech to meet target speaking duration and quality standards.
* **Moodle Quizzes & Assessments (`quiz`):**
  - Automates multiple-choice, true/false, fill-in-the-blanks, and numerical assessments.
  - Employs resilient selector strategies to handle diverse themes and modal submission confirmation dialogs.

---

## 3. Intelligent Activity Selector & Dynamic Theme Engine
* **Tkinter Interactive GUI Checkbox Dialog:**
  - Grouped category containers (Read-Aloud, H5P / Video, WordCards, Solo Speaking, Quizzes, Other).
  - Master `(all)` toggle and category-level selection controls.
  - Real-time text search and filter query engine.
  - "Select Pending Only" quick button to bypass already completed activities.
* **Multi-Theme Engine (🎨 Theme):**
  - **🌙 Dark (Default):** Deep charcoal & slate (`#181825` / `#1e1e2e`) with soft blue accents (`#89b4fa`) and dark pill badges. Opacity `1.0`.
  - **☀️ Light:** Clean white & cool gray (`#f8f9fa` / `#ffffff`) with crisp dark text (`#212529`). Opacity `1.0`.
  - **🪟 Transparent (Frosted Glass):** Semi-transparent acrylic glass (`#11111b`) with window opacity `0.85` allowing wallpaper to subtly show through while maintaining full contrast and readability.
  - **Instant Runtime Switching:** Toggle button in the top-right corner updates all widgets, canvas, scroll regions, badges, and window alpha in real time without restarting.
* **Seamless Headless CLI Fallback:** Automatically reverts to interactive console selector in headless, Docker, or non-GUI environments.

---

## 4. Resilience, Telemetry & Authentication
* **Session Persistence:** Saves session cookies to local storage, bypassing repeated username/password logins.
* **DOM Wait Helpers:** Eliminates arbitrary `sleep` timeouts with polling wait conditions, mutation checks, and selector timeouts.
* **Performance Benchmark Telemetry:** Detailed console matrix tracking elapsed time per activity, retry counts, AI latency, and overall efficiency.
* **Score Tracking & Caching:** Prevents redundant executions by tracking previously achieved scores and passing marks.
