"""
Activity Selector Module for Poodle LMS Automation.

Provides an interactive GUI Checkbox Dialog (via Tkinter) and a CLI fallback
to prompt the user on which activities to automate, featuring:
- Master '(all)' option to select/deselect all activities
- Similarity-based grouping (Read-Aloud, H5P, WordCards, Solo, Generic)
- Group-level toggles
- Filter/search support
- Pending-only quick filter
- Seamless CLI fallback for headless or non-GUI environments
"""

import sys
import re
from typing import Optional

GROUP_DEFINITIONS = [
    {
        "id": "readaloud",
        "name": "Read - Aloud",
        "description": "Speech pronunciation and reading exercises",
        "match_types": ["readaloud"]
    },
    {
        "id": "hvp",
        "name": "H5P / Interactive Video",
        "description": "Interactive video queries, drag-and-drop & quiz questions",
        "match_types": ["hvp", "h5pactivity"]
    },
    {
        "id": "wordcards",
        "name": "WordCards",
        "description": "Vocabulary recognition and flashcard drills",
        "match_types": ["wordcards"]
    },
    {
        "id": "solo",
        "name": "Solo Speaking",
        "description": "Continuous speech monologue and speaking prompts",
        "match_types": ["solo"]
    },
    {
        "id": "quiz",
        "name": "Quiz & Assessments",
        "description": "Online quizzes, multiple choice and practice tests",
        "match_types": ["quiz"]
    },
    {
        "id": "generic",
        "name": "Other Activities",
        "description": "Standard Moodle course resources and modules",
        "match_types": []
    }
]

THEME_CYCLE = ["dark", "light", "glass"]

THEMES = {
    "dark": {
        "id": "dark",
        "name": "Dark",
        "icon": "🌙",
        "button_label": "🎨 Theme: Dark",
        "alpha": 1.0,
        "window_bg": "#181825",
        "header_bg": "#181825",
        "card_bg": "#1e1e2e",
        "card_border": "#313244",
        "group_header_bg": "#181825",
        "item_bg": "#1e1e2e",
        "item_border": "#313244",
        "canvas_bg": "#181825",
        "text_primary": "#cdd6f4",
        "text_secondary": "#a6adc8",
        "accent": "#89b4fa",
        "entry_bg": "#1e1e2e",
        "entry_fg": "#cdd6f4",
        "btn_bg": "#313244",
        "btn_fg": "#cdd6f4",
        "btn_active_bg": "#45475a",
        "primary_btn_bg": "#89b4fa",
        "primary_btn_fg": "#11111b",
        "primary_btn_active_bg": "#b4befe",
        "theme_btn_bg": "#313244",
        "theme_btn_fg": "#89b4fa",
        "badge_completed_bg": "#1e3a2f",
        "badge_completed_fg": "#a6e3a1",
        "badge_retry_bg": "#452026",
        "badge_retry_fg": "#f38ba8",
        "badge_pending_bg": "#3d341a",
        "badge_pending_fg": "#f9e2af",
        "scrollbar_trough": "#181825",
        "scrollbar_bg": "#313244",
        "separator_bg": "#313244",
        "checkbutton_bg": "#181825",
        "checkbutton_fg": "#cdd6f4",
        "checkbutton_active_fg": "#89b4fa",
        "checkbutton_indicator": "#1e1e2e",
    },
    "light": {
        "id": "light",
        "name": "Light",
        "icon": "☀️",
        "button_label": "🎨 Theme: Light",
        "alpha": 1.0,
        "window_bg": "#f8f9fa",
        "header_bg": "#f8f9fa",
        "card_bg": "#f8f9fa",
        "card_border": "#dee2e6",
        "group_header_bg": "#e9ecef",
        "item_bg": "#ffffff",
        "item_border": "#dee2e6",
        "canvas_bg": "#ffffff",
        "text_primary": "#212529",
        "text_secondary": "#555555",
        "accent": "#004085",
        "entry_bg": "#ffffff",
        "entry_fg": "#212529",
        "btn_bg": "#e9ecef",
        "btn_fg": "#212529",
        "btn_active_bg": "#dee2e6",
        "primary_btn_bg": "#004085",
        "primary_btn_fg": "#ffffff",
        "primary_btn_active_bg": "#0056b3",
        "theme_btn_bg": "#e9ecef",
        "theme_btn_fg": "#212529",
        "badge_completed_bg": "#d4edda",
        "badge_completed_fg": "#155724",
        "badge_retry_bg": "#f8d7da",
        "badge_retry_fg": "#721c24",
        "badge_pending_bg": "#fff3cd",
        "badge_pending_fg": "#856404",
        "scrollbar_trough": "#f8f9fa",
        "scrollbar_bg": "#ced4da",
        "separator_bg": "#dee2e6",
        "checkbutton_bg": "#f8f9fa",
        "checkbutton_fg": "#212529",
        "checkbutton_active_fg": "#004085",
        "checkbutton_indicator": "#ffffff",
    },
    "glass": {
        "id": "glass",
        "name": "Transparent (Glass)",
        "icon": "🪟",
        "button_label": "🎨 Theme: Glass",
        "alpha": 0.85,
        "window_bg": "#11111b",
        "header_bg": "#11111b",
        "card_bg": "#181825",
        "card_border": "#313244",
        "group_header_bg": "#1e1e2e",
        "item_bg": "#181825",
        "item_border": "#313244",
        "canvas_bg": "#11111b",
        "text_primary": "#cdd6f4",
        "text_secondary": "#bac2de",
        "accent": "#89b4fa",
        "entry_bg": "#181825",
        "entry_fg": "#ffffff",
        "btn_bg": "#1e1e2e",
        "btn_fg": "#cdd6f4",
        "btn_active_bg": "#313244",
        "primary_btn_bg": "#89b4fa",
        "primary_btn_fg": "#11111b",
        "primary_btn_active_bg": "#b4befe",
        "theme_btn_bg": "#1e1e2e",
        "theme_btn_fg": "#89b4fa",
        "badge_completed_bg": "#16382b",
        "badge_completed_fg": "#a6e3a1",
        "badge_retry_bg": "#452026",
        "badge_retry_fg": "#f38ba8",
        "badge_pending_bg": "#3d341a",
        "badge_pending_fg": "#f9e2af",
        "scrollbar_trough": "#11111b",
        "scrollbar_bg": "#313244",
        "separator_bg": "#313244",
        "checkbutton_bg": "#11111b",
        "checkbutton_fg": "#cdd6f4",
        "checkbutton_active_fg": "#89b4fa",
        "checkbutton_indicator": "#1e1e2e",
    }
}


def classify_activity(act: dict) -> str:
    """Returns the group ID for an activity based on its type or URL."""
    act_type = str(act.get("type", "")).lower()
    url = str(act.get("url", "")).lower()

    for grp in GROUP_DEFINITIONS:
        for t in grp["match_types"]:
            if t == act_type or f"/mod/{t}/" in url:
                return grp["id"]
    return "generic"


def group_activities(activities: list[dict]) -> list[dict]:
    """
    Groups activities into structured similarity buckets with global 1-based indexing.
    Returns a list of group dictionaries:
    [
        {
            "id": "readaloud",
            "name": "Read - Aloud",
            "description": "...",
            "items": [(1, act1), (2, act2)]
        },
        ...
    ]
    """
    buckets = {grp["id"]: [] for grp in GROUP_DEFINITIONS}

    for idx, act in enumerate(activities, 1):
        grp_id = classify_activity(act)
        buckets[grp_id].append((idx, act))

    result = []
    for grp in GROUP_DEFINITIONS:
        items = buckets[grp["id"]]
        if items:
            result.append({
                "id": grp["id"],
                "name": grp["name"],
                "description": grp["description"],
                "items": items
            })
    return result


class ActivitySelectorDialog:
    """Tkinter-based GUI Checkbox dialog with grouping, '(all)' toggle, and live multi-theme support."""

    def __init__(self, activities: list[dict], course_name: str = "", tracker=None, initial_theme: str = "dark"):
        self.activities = activities
        self.course_name = course_name or "Moodle Course"
        self.tracker = tracker
        self.grouped = group_activities(activities)
        self.selected_activities: list[dict] = []
        self.cancelled = False

        # Theme attributes - Default to Dark mode directly on startup
        self.current_theme: str = initial_theme if initial_theme in THEMES else "dark"
        self.theme_mode: str = self.current_theme
        self.root = None
        self.style = None
        self.theme_btn = None
        self.canvas = None
        self.scrollable_frame = None
        self.search_entry = None
        self.group_ui_elements: dict[str, dict] = {}
        self.item_ui_elements: dict[int, dict] = {}

        # GUI Tkinter variables
        self.all_var = None
        self.item_vars: dict[int, any] = {}      # idx -> BooleanVar
        self.group_vars: dict[str, any] = {}     # grp_id -> BooleanVar
        self.item_widgets: dict[int, any] = {}   # idx -> (frame, act) for filtering
        self.group_widgets: dict[str, any] = {}  # grp_id -> frame widget for filtering
        self.selection_label = None

    def _get_theme_button_label(self) -> str:
        """Returns the formatted theme button text indicating current theme."""
        cfg = THEMES.get(self.current_theme, THEMES["dark"])
        return cfg.get("button_label", f"🎨 Theme: {cfg['name']}")

    def _cycle_theme(self):
        """Cycles seamlessly through Dark -> Light -> Transparent (Glass) -> Dark."""
        try:
            curr_idx = THEME_CYCLE.index(self.current_theme)
            next_theme = THEME_CYCLE[(curr_idx + 1) % len(THEME_CYCLE)]
        except ValueError:
            next_theme = "dark"
        self.set_theme(next_theme)

    def cycle_theme(self):
        """Public alias to cycle theme."""
        self._cycle_theme()

    def set_theme(self, theme_name: str):
        """Switches to the specified theme in real-time without restarting."""
        if theme_name not in THEMES:
            return
        self.current_theme = theme_name
        self.theme_mode = theme_name
        self._apply_theme(theme_name)

    def _apply_theme(self, theme_name: str):
        """
        Updates all widgets, canvas, scroll regions, search inputs, badges,
        and window alpha in real time without restarting.
        """
        theme = THEMES.get(theme_name, THEMES["dark"])
        self.current_theme = theme_name
        self.theme_mode = theme_name

        # 1. Update window background & opacity (alpha)
        if self.root:
            try:
                self.root.configure(bg=theme["window_bg"])
                self.root.attributes("-alpha", theme["alpha"])
            except Exception:
                pass

        # 2. Update TTK styles
        if self.style:
            try:
                self.style.configure("TFrame", background=theme["window_bg"])
                self.style.configure("Main.TFrame", background=theme["window_bg"])
                self.style.configure(
                    "Header.TLabel",
                    font=("Segoe UI", 13, "bold"),
                    background=theme["header_bg"],
                    foreground=theme["text_primary"]
                )
                self.style.configure(
                    "SubHeader.TLabel",
                    font=("Segoe UI", 9),
                    background=theme["header_bg"],
                    foreground=theme["text_secondary"]
                )
                self.style.configure(
                    "GroupHeader.TLabel",
                    font=("Segoe UI", 10, "bold"),
                    background=theme["group_header_bg"],
                    foreground=theme["accent"]
                )
                self.style.configure(
                    "GroupHeader.TCheckbutton",
                    font=("Segoe UI", 10, "bold"),
                    background=theme["group_header_bg"],
                    foreground=theme["accent"]
                )
                self.style.map(
                    "GroupHeader.TCheckbutton",
                    background=[("active", theme["group_header_bg"])],
                    foreground=[("active", theme["accent"])],
                    indicatorcolor=[("selected", theme["accent"])]
                )
                self.style.configure(
                    "AllCheck.TCheckbutton",
                    font=("Segoe UI", 11, "bold"),
                    background=theme["window_bg"],
                    foreground=theme["text_primary"]
                )
                self.style.map(
                    "AllCheck.TCheckbutton",
                    background=[("active", theme["window_bg"])],
                    foreground=[("active", theme["accent"])],
                    indicatorcolor=[("selected", theme["accent"])]
                )
                self.style.configure(
                    "ItemCheck.TCheckbutton",
                    font=("Segoe UI", 9),
                    background=theme["item_bg"],
                    foreground=theme["text_primary"]
                )
                self.style.map(
                    "ItemCheck.TCheckbutton",
                    background=[("active", theme["item_bg"])],
                    foreground=[("active", theme["accent"])],
                    indicatorcolor=[("selected", theme["accent"])]
                )
                self.style.configure(
                    "TCheckbutton",
                    background=theme["window_bg"],
                    foreground=theme["text_primary"],
                    indicatorcolor=theme["checkbutton_indicator"]
                )
                self.style.map(
                    "TCheckbutton",
                    background=[("active", theme["window_bg"])],
                    foreground=[("active", theme["accent"])],
                    indicatorcolor=[("selected", theme["accent"])]
                )
                self.style.configure(
                    "Search.TLabel",
                    font=("Segoe UI", 9),
                    background=theme["window_bg"],
                    foreground=theme["text_primary"]
                )
                self.style.configure(
                    "TEntry",
                    fieldbackground=theme["entry_bg"],
                    foreground=theme["entry_fg"],
                    insertcolor=theme["accent"]
                )
                self.style.configure(
                    "TButton",
                    font=("Segoe UI", 9),
                    background=theme["btn_bg"],
                    foreground=theme["btn_fg"],
                    borderwidth=1,
                    focuscolor="none"
                )
                self.style.map(
                    "TButton",
                    background=[("active", theme["btn_active_bg"]), ("pressed", theme["btn_bg"])],
                    foreground=[("active", theme["btn_fg"])]
                )
                self.style.configure(
                    "Primary.TButton",
                    font=("Segoe UI", 10, "bold"),
                    background=theme["primary_btn_bg"],
                    foreground=theme["primary_btn_fg"],
                    borderwidth=1,
                    focuscolor="none"
                )
                self.style.map(
                    "Primary.TButton",
                    background=[("active", theme["primary_btn_active_bg"]), ("pressed", theme["primary_btn_bg"])],
                    foreground=[("active", theme["primary_btn_fg"])]
                )
                self.style.configure(
                    "Theme.TButton",
                    font=("Segoe UI", 9, "bold"),
                    background=theme["theme_btn_bg"],
                    foreground=theme["theme_btn_fg"],
                    borderwidth=1,
                    focuscolor="none"
                )
                self.style.map(
                    "Theme.TButton",
                    background=[("active", theme["btn_active_bg"]), ("pressed", theme["theme_btn_bg"])],
                    foreground=[("active", theme["accent"])]
                )
                self.style.configure(
                    "Footer.TLabel",
                    font=("Segoe UI", 10, "bold"),
                    background=theme["window_bg"],
                    foreground=theme["accent"]
                )
                self.style.configure(
                    "Vertical.TScrollbar",
                    troughcolor=theme["scrollbar_trough"],
                    background=theme["scrollbar_bg"],
                    bordercolor=theme["window_bg"],
                    arrowcolor=theme["text_primary"]
                )
                self.style.map("Vertical.TScrollbar", background=[("active", theme["btn_active_bg"])])
                self.style.configure("TSeparator", background=theme["separator_bg"])
                self.style.configure("Card.TFrame", background=theme["canvas_bg"])
            except Exception:
                pass

        # 3. Update theme toggle button text
        if self.theme_btn:
            try:
                self.theme_btn.configure(text=self._get_theme_button_label())
            except Exception:
                pass

        # 4. Update canvas & scroll region background
        if self.canvas:
            try:
                self.canvas.configure(bg=theme["canvas_bg"], highlightbackground=theme["canvas_bg"])
            except Exception:
                pass
        if self.scrollable_frame:
            try:
                self.scrollable_frame.configure(bg=theme["canvas_bg"])
            except Exception:
                pass

        # 5. Update group boxes & headers
        for grp_id, el in self.group_ui_elements.items():
            try:
                if el.get("box") and el["box"].winfo_exists():
                    el["box"].configure(
                        bg=theme["card_bg"],
                        highlightbackground=theme["card_border"],
                        highlightcolor=theme["card_border"]
                    )
                if el.get("header") and el["header"].winfo_exists():
                    el["header"].configure(bg=theme["group_header_bg"])
                if el.get("desc") and el["desc"].winfo_exists():
                    el["desc"].configure(bg=theme["group_header_bg"], fg=theme["text_secondary"])
                if el.get("items_frame") and el["items_frame"].winfo_exists():
                    el["items_frame"].configure(bg=theme["card_bg"])
            except Exception:
                pass

        # 6. Update item rows, labels, & status badges
        for idx, el in self.item_ui_elements.items():
            try:
                if el.get("row") and el["row"].winfo_exists():
                    el["row"].configure(
                        bg=theme["item_bg"],
                        highlightbackground=theme["item_border"],
                        highlightcolor=theme["item_border"]
                    )
                if el.get("title") and el["title"].winfo_exists():
                    el["title"].configure(bg=theme["item_bg"], fg=theme["text_primary"])
                if el.get("badge") and el["badge"].winfo_exists():
                    st = el.get("status", "pending")
                    if st == "completed":
                        el["badge"].configure(bg=theme["badge_completed_bg"], fg=theme["badge_completed_fg"])
                    elif st == "retry":
                        el["badge"].configure(bg=theme["badge_retry_bg"], fg=theme["badge_retry_fg"])
                    else:
                        el["badge"].configure(bg=theme["badge_pending_bg"], fg=theme["badge_pending_fg"])
            except Exception:
                pass

        # 7. Update footer selection count label
        if self.selection_label:
            try:
                if self.selection_label.winfo_exists():
                    self.selection_label.configure(foreground=theme["accent"])
            except Exception:
                pass

        # 8. Refresh canvas scroll region
        if self.canvas:
            try:
                if self.canvas.winfo_exists():
                    self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            except Exception:
                pass

    def show(self) -> Optional[list[dict]]:
        """Displays the dialog and returns the selected activities, or None if cancelled."""
        try:
            import tkinter as tk
            from tkinter import ttk
        except ImportError:
            return None

        root = tk.Tk()
        self.root = root
        root.title(f"Select Activities - {self.course_name}")
        root.geometry("820x680")
        root.minsize(680, 480)

        # Style configuration
        style = ttk.Style(root)
        self.style = style
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Apply initial theme configuration (defaults directly to Dark Mode on startup)
        self._apply_theme(self.current_theme)

        # Setup variables
        self.all_var = tk.BooleanVar(value=True)

        for grp in self.grouped:
            self.group_vars[grp["id"]] = tk.BooleanVar(value=True)
            for idx, act in grp["items"]:
                self.item_vars[idx] = tk.BooleanVar(value=True)

        theme_cfg = THEMES.get(self.current_theme, THEMES["dark"])

        # 1. Top Header Frame with Toggle Theme Button in top-right corner
        header_frame = ttk.Frame(root, padding="16 12 16 8", style="Main.TFrame")
        header_frame.pack(fill=tk.X)

        header_top = ttk.Frame(header_frame, style="Main.TFrame")
        header_top.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header_top,
            text=f"📚 Course: {self.course_name}",
            style="Header.TLabel"
        )
        title_lbl.pack(side=tk.LEFT, anchor=tk.W)

        # Toggle Theme Button (🎨 Theme) positioned in the top-right corner of the header bar
        self.theme_btn = ttk.Button(
            header_top,
            text=self._get_theme_button_label(),
            style="Theme.TButton",
            command=self._cycle_theme,
            cursor="hand2"
        )
        self.theme_btn.pack(side=tk.RIGHT, anchor=tk.E)

        sub_text = f"Discovered {len(self.activities)} activities across {len(self.grouped)} categories. Select the activities you wish to automate:"
        sub_lbl = ttk.Label(header_frame, text=sub_text, style="SubHeader.TLabel")
        sub_lbl.pack(anchor=tk.W, pady=(4, 8))

        # 2. Controls & Filter Bar
        ctrl_frame = ttk.Frame(root, padding="16 4 16 8", style="Main.TFrame")
        ctrl_frame.pack(fill=tk.X)

        # Master (all) Checkbox
        all_cb = ttk.Checkbutton(
            ctrl_frame,
            text="(all)  Select / Deselect All Activities",
            variable=self.all_var,
            command=self._on_toggle_all,
            style="AllCheck.TCheckbutton"
        )
        all_cb.pack(side=tk.LEFT)

        # Quick action buttons
        btn_frame = ttk.Frame(ctrl_frame, style="Main.TFrame")
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="Select Pending Only", command=self._select_pending_only).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Select All", command=lambda: self._set_all(True)).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Clear All", command=lambda: self._set_all(False)).pack(side=tk.LEFT, padx=3)

        # Search / Filter Bar
        search_frame = ttk.Frame(root, padding="16 0 16 6", style="Main.TFrame")
        search_frame.pack(fill=tk.X)

        ttk.Label(search_frame, text="🔍 Filter:", style="Search.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._filter_activities())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=35)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(search_frame, text="✕ Clear", width=8, command=lambda: self.search_var.set("")).pack(side=tk.LEFT, padx=6)

        # Separator line
        ttk.Separator(root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=16, pady=4)

        # 3. Scrollable Activities Canvas
        container = ttk.Frame(root, padding="16 4 16 4", style="Main.TFrame")
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(
            container,
            borderwidth=0,
            highlightthickness=0,
            background=theme_cfg["canvas_bg"]
        )
        self.canvas = canvas
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, background=theme_cfg["canvas_bg"])
        self.scrollable_frame = scrollable_frame

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mousewheel scrolling support for Windows
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Populate Grouped Activities
        for grp in self.grouped:
            grp_id = grp["id"]
            grp_box = tk.Frame(
                scrollable_frame,
                background=theme_cfg["card_bg"],
                bd=1,
                relief=tk.SOLID,
                highlightbackground=theme_cfg["card_border"],
                highlightcolor=theme_cfg["card_border"],
                highlightthickness=1,
                padx=10,
                pady=8
            )
            grp_box.pack(fill=tk.X, expand=True, pady=6, padx=2)
            self.group_widgets[grp_id] = grp_box

            # Group Header
            gh_frame = tk.Frame(grp_box, background=theme_cfg["group_header_bg"], padx=8, pady=4)
            gh_frame.pack(fill=tk.X)

            grp_cb = ttk.Checkbutton(
                gh_frame,
                text=f"{grp['name']} ({len(grp['items'])} activities)",
                variable=self.group_vars[grp_id],
                command=lambda gid=grp_id: self._on_toggle_group(gid),
                style="GroupHeader.TCheckbutton"
            )
            grp_cb.pack(side=tk.LEFT)

            desc_lbl = tk.Label(
                gh_frame,
                text=grp["description"],
                font=("Segoe UI", 8, "italic"),
                fg=theme_cfg["text_secondary"],
                bg=theme_cfg["group_header_bg"]
            )
            desc_lbl.pack(side=tk.RIGHT, padx=6)

            # Items inside group
            items_frame = tk.Frame(grp_box, background=theme_cfg["card_bg"], pady=4)
            items_frame.pack(fill=tk.X)

            self.group_ui_elements[grp_id] = {
                "box": grp_box,
                "header": gh_frame,
                "cb": grp_cb,
                "desc": desc_lbl,
                "items_frame": items_frame,
            }

            for idx, act in grp["items"]:
                item_row = tk.Frame(
                    items_frame,
                    background=theme_cfg["item_bg"],
                    padx=8,
                    pady=4,
                    bd=1,
                    relief=tk.GROOVE,
                    highlightbackground=theme_cfg["item_border"],
                    highlightcolor=theme_cfg["item_border"],
                    highlightthickness=1
                )
                item_row.pack(fill=tk.X, pady=2)
                self.item_widgets[idx] = (item_row, act)

                # Checkbox
                cb = ttk.Checkbutton(
                    item_row,
                    variable=self.item_vars[idx],
                    command=lambda i=idx, gid=grp_id: self._on_toggle_item(i, gid),
                    style="ItemCheck.TCheckbutton"
                )
                cb.pack(side=tk.LEFT, padx=(0, 6))

                # Index & Title Label
                num_tag = f"#{idx:02d}"
                title_text = f"{num_tag}  [{act.get('type', 'act')}]  {act['title']}"
                title_lbl = tk.Label(
                    item_row,
                    text=title_text,
                    font=("Segoe UI", 9),
                    anchor="w",
                    bg=theme_cfg["item_bg"],
                    fg=theme_cfg["text_primary"],
                    cursor="hand2"
                )
                title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
                title_lbl.bind("<Button-1>", lambda e, i=idx, gid=grp_id: self._toggle_single_item(i, gid))

                # Status Badge
                is_done = False
                score_str = ""
                raw_score = self.tracker.get_score(act["url"]) if self.tracker else ""
                if self.tracker and self.tracker.is_completed(act["url"]):
                    is_done = True
                    score_str = str(raw_score)

                if is_done:
                    badge_status = "completed"
                    badge_text = f"✓ COMPLETED ({score_str})" if score_str else "✓ COMPLETED"
                    badge_bg = theme_cfg["badge_completed_bg"]
                    badge_fg = theme_cfg["badge_completed_fg"]
                elif raw_score:
                    badge_status = "retry"
                    badge_text = f"● RETRY ({raw_score})"
                    badge_bg = theme_cfg["badge_retry_bg"]
                    badge_fg = theme_cfg["badge_retry_fg"]
                else:
                    badge_status = "pending"
                    badge_text = "● PENDING"
                    badge_bg = theme_cfg["badge_pending_bg"]
                    badge_fg = theme_cfg["badge_pending_fg"]

                badge_lbl = tk.Label(
                    item_row,
                    text=badge_text,
                    font=("Segoe UI", 8, "bold"),
                    fg=badge_fg,
                    bg=badge_bg,
                    padx=8,
                    pady=2
                )
                badge_lbl.pack(side=tk.RIGHT, padx=4)

                self.item_ui_elements[idx] = {
                    "row": item_row,
                    "title": title_lbl,
                    "badge": badge_lbl,
                    "cb": cb,
                    "status": badge_status,
                    "score": score_str,
                    "act": act
                }

        # 4. Bottom Footer & Action Buttons
        footer_frame = ttk.Frame(root, padding="16 10 16 14", style="Main.TFrame")
        footer_frame.pack(fill=tk.X)

        self.selection_label = ttk.Label(
            footer_frame,
            text="",
            style="Footer.TLabel"
        )
        self.selection_label.pack(side=tk.LEFT)

        action_box = ttk.Frame(footer_frame, style="Main.TFrame")
        action_box.pack(side=tk.RIGHT)

        cancel_btn = ttk.Button(
            action_box,
            text="Cancel (Esc)",
            command=lambda: self._close(cancelled=True, root=root)
        )
        cancel_btn.pack(side=tk.LEFT, padx=6)

        start_btn = ttk.Button(
            action_box,
            text="🚀 Start Automation (Enter)",
            style="Primary.TButton",
            command=lambda: self._close(cancelled=False, root=root)
        )
        start_btn.pack(side=tk.LEFT)

        # Keyboard bindings
        root.bind("<Return>", lambda e: self._close(cancelled=False, root=root))
        root.bind("<Escape>", lambda e: self._close(cancelled=True, root=root))

        # Re-apply theme to ensure all freshly constructed widgets are synchronized
        self._apply_theme(self.current_theme)
        self._update_selection_count()

        # Center Window on screen
        root.update_idletasks()
        w = root.winfo_width()
        h = root.winfo_height()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        root.geometry(f"{w}x{h}+{x}+{y}")

        # Bring dialog to front and ensure alpha is preserved
        try:
            root.lift()
            root.attributes("-topmost", True)
            root.after(300, lambda: (root.attributes("-topmost", False), root.attributes("-alpha", THEMES[self.current_theme]["alpha"])))
            root.focus_force()
        except Exception:
            pass

        root.mainloop()

        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass

        if self.cancelled:
            return None
        return self.selected_activities

    def _toggle_single_item(self, idx: int, group_id: str):
        var = self.item_vars.get(idx)
        if var:
            var.set(not var.get())
            self._on_toggle_item(idx, group_id)

    def _on_toggle_all(self):
        val = self.all_var.get()
        self._set_all(val)

    def _set_all(self, val: bool):
        self.all_var.set(val)
        for g_var in self.group_vars.values():
            g_var.set(val)
        for i_var in self.item_vars.values():
            i_var.set(val)
        self._update_selection_count()

    def _select_pending_only(self):
        for idx, act in enumerate(self.activities, 1):
            is_done = self.tracker.is_completed(act["url"]) if self.tracker else False
            self.item_vars[idx].set(not is_done)

        for grp in self.grouped:
            grp_id = grp["id"]
            all_in_grp = all(self.item_vars[i].get() for i, _ in grp["items"])
            self.group_vars[grp_id].set(all_in_grp)

        all_selected = all(v.get() for v in self.item_vars.values())
        self.all_var.set(all_selected)
        self._update_selection_count()

    def _on_toggle_group(self, grp_id: str):
        val = self.group_vars[grp_id].get()
        for grp in self.grouped:
            if grp["id"] == grp_id:
                for idx, _ in grp["items"]:
                    self.item_vars[idx].set(val)
                break
        all_selected = all(v.get() for v in self.item_vars.values())
        self.all_var.set(all_selected)
        self._update_selection_count()

    def _on_toggle_item(self, idx: int, grp_id: str):
        for grp in self.grouped:
            if grp["id"] == grp_id:
                all_grp = all(self.item_vars[i].get() for i, _ in grp["items"])
                self.group_vars[grp_id].set(all_grp)
                break
        all_selected = all(v.get() for v in self.item_vars.values())
        self.all_var.set(all_selected)
        self._update_selection_count()

    def _filter_activities(self):
        query = (self.search_var.get() or "").strip().lower()
        for grp in self.grouped:
            grp_id = grp["id"]
            any_visible = False
            for idx, act in grp["items"]:
                row_widget, _ = self.item_widgets[idx]
                text_match = (
                    query in act["title"].lower()
                    or query in act.get("type", "").lower()
                    or query in f"#{idx}"
                )
                if text_match or not query:
                    row_widget.pack(fill="x", pady=2)
                    any_visible = True
                else:
                    row_widget.pack_forget()

            grp_widget = self.group_widgets.get(grp_id)
            if grp_widget:
                if any_visible:
                    grp_widget.pack(fill="x", expand=True, pady=6, padx=2)
                else:
                    grp_widget.pack_forget()

    def _update_selection_count(self):
        if not self.selection_label:
            return
        theme = THEMES.get(self.current_theme, THEMES["dark"])
        total = len(self.activities)
        selected = sum(1 for v in self.item_vars.values() if v.get())
        pending_count = 0
        if self.tracker:
            pending_count = sum(
                1 for i, act in enumerate(self.activities, 1)
                if self.item_vars[i].get() and not self.tracker.is_completed(act["url"])
            )
            self.selection_label.config(
                text=f"Selected: {selected} / {total} activities ({pending_count} pending)",
                foreground=theme["accent"]
            )
        else:
            self.selection_label.config(
                text=f"Selected: {selected} / {total} activities",
                foreground=theme["accent"]
            )

    def _close(self, cancelled: bool, root):
        self.cancelled = cancelled
        if not cancelled:
            self.selected_activities = [
                act for idx, act in enumerate(self.activities, 1)
                if self.item_vars[idx].get()
            ]
        root.destroy()


def parse_cli_selection(user_input: str, total_count: int, activities: list[dict], tracker=None) -> list[int]:
    """
    Parses CLI user input into a list of 1-based activity indices.
    Supports:
    - 'all', '0', '' -> all indices
    - 'pending' -> indices of activities not marked as completed
    - group keywords ('readaloud', 'hvp', 'wordcards', 'solo')
    - comma-separated numbers and ranges ('1, 3, 5-8')
    """
    raw = user_input.strip().lower()

    if not raw or raw in ("all", "0", "*"):
        return list(range(1, total_count + 1))

    if raw == "pending":
        if not tracker:
            return list(range(1, total_count + 1))
        return [
            i for i, act in enumerate(activities, 1)
            if not tracker.is_completed(act["url"])
        ]

    # Check for group match
    for grp in GROUP_DEFINITIONS:
        if raw == grp["id"] or raw == grp["name"].lower() or raw.replace(" ", "") == grp["id"]:
            matching_indices = []
            for i, act in enumerate(activities, 1):
                if classify_activity(act) == grp["id"]:
                    matching_indices.append(i)
            if matching_indices:
                return matching_indices

    # Parse numerical expressions like '1, 3, 5-8'
    indices = set()
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    for tok in tokens:
        if "-" in tok:
            parts = tok.split("-", 1)
            try:
                start, end = int(parts[0].strip()), int(parts[1].strip())
                for i in range(min(start, end), max(start, end) + 1):
                    if 1 <= i <= total_count:
                        indices.add(i)
            except ValueError:
                pass
        else:
            try:
                val = int(tok)
                if 1 <= val <= total_count:
                    indices.add(val)
            except ValueError:
                pass

    return sorted(list(indices))


def cli_activity_selector(activities: list[dict], course_name: str = "", tracker=None) -> list[dict]:
    """Console-based fallback selector with similarity grouping and '(all)' option."""
    grouped = group_activities(activities)
    total_count = len(activities)

    print("\n" + "=" * 68)
    print(f"ACTIVITIES SELECTION - {course_name or 'Course'}")
    print("=" * 68)
    print(f"Extracted {total_count} activities across {len(grouped)} groups.\n")
    print("  [0] (all) - Select All Activities Across All Groups")

    for grp in grouped:
        print(f"\n--- {grp['name']} ({len(grp['items'])} activities) ---")
        for idx, act in grp["items"]:
            status_text = "[PENDING]"
            raw_score = tracker.get_score(act["url"]) if tracker else ""
            if tracker and tracker.is_completed(act["url"]):
                status_text = f"[COMPLETED | Score: {raw_score}]"
            elif raw_score:
                status_text = f"[RETRY NEEDED | Score: {raw_score}]"
            print(f"  [{idx:2d}] [{act.get('type', 'act'):10s}] {act['title']} {status_text}")

    print("\n" + "-" * 68)
    print("Selection Options:")
    print("  - Type 'all' or '0' (or press Enter) to automate ALL activities")
    print("  - Type 'pending' to automate only incomplete activities")
    print("  - Type a group name (e.g. 'readaloud', 'hvp', 'wordcards', 'solo')")
    print("  - Type numbers or ranges (e.g. '1, 3, 5' or '1-4')")
    print("  - Type 'none' or 'q' to cancel and exit")
    print("-" * 68)

    while True:
        try:
            choice = input("\nEnter your selection [default: (all)]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Activity Selector] Operation cancelled by user.")
            return []

        if choice.lower() in ("none", "q", "cancel", "exit"):
            print("[Activity Selector] Skipping activities upon user request.")
            return []

        selected_indices = parse_cli_selection(choice, total_count, activities, tracker)
        if selected_indices:
            selected = [activities[i - 1] for i in selected_indices]
            print(f"\n[Activity Selector] Selected {len(selected)} / {total_count} activities to automate.")
            return selected
        else:
            print("[!] Invalid selection. Please enter valid numbers, 'all', 'pending', or 'q' to cancel.")


def prompt_activity_selection(
    activities: list[dict],
    course_name: str = "",
    tracker=None,
    headless: bool = False,
    force_cli: bool = False,
    auto_all: bool = False,
    initial_theme: str = "dark"
) -> list[dict]:
    """
    Prompts the user to select which activities to automate.
    Attempts GUI Checkbox Dialog first, smoothly falling back to CLI selector.
    Default GUI theme opens directly in Dark Mode on startup.
    """
    if not activities:
        return []

    if auto_all:
        print(f"\n[Activity Selector] --all flag specified. Automatically selected all {len(activities)} activities.")
        return list(activities)

    # If headless or CLI forced, use CLI selector
    if headless or force_cli:
        return cli_activity_selector(activities, course_name=course_name, tracker=tracker)

    # Attempt Tkinter GUI Dialog
    try:
        dialog = ActivitySelectorDialog(
            activities,
            course_name=course_name,
            tracker=tracker,
            initial_theme=initial_theme
        )
        result = dialog.show()
        if result is not None:
            if not result:
                print("\n[Activity Selector] 0 activities selected in dialog. Skipping course activities.")
            else:
                print(f"\n[Activity Selector] Dialog selection confirmed: {len(result)} / {len(activities)} activities.")
            return result
        else:
            # User clicked cancel in dialog
            print("\n[Activity Selector] Selection cancelled by user in dialog.")
            return []
    except Exception as e:
        print(f"\n[Activity Selector] GUI dialog unavailable ({e}). Falling back to interactive CLI mode.")
        return cli_activity_selector(activities, course_name=course_name, tracker=tracker)
