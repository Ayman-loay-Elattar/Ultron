import os
import ctypes
import threading
import queue
import tkinter as tk

# Theme
BG_COLOR = "#1e1e2e"        # dark slate background
BORDER_COLOR = "#89b4fa"    # soft blue accent border
TEXT_COLOR = "#cdd6f4"      # near-white text
PLACEHOLDER_COLOR = "#6c7086"  # muted gray for placeholder/hint
TRANSPARENT_KEY = "#ff00ff"  # sacrificial color made transparent on Windows


def _force_foreground(hwnd):

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    fg_hwnd = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    cur_thread = kernel32.GetCurrentThreadId()

    attached = False
    if fg_thread and fg_thread != cur_thread:
        attached = user32.AttachThreadInput(fg_thread, cur_thread, True)

    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    user32.SetActiveWindow(hwnd)
    user32.SetFocus(hwnd)

    if attached:
        user32.AttachThreadInput(fg_thread, cur_thread, False)

WIDTH = 480
HEIGHT = 110
CORNER_RADIUS = 18


def _rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def run_command_popup(resolve_fn) -> tuple[str, object]:
  
    result = {"outcome": ("cancelled", None)}

    root = tk.Tk()
    root.overrideredirect(True)          # no title bar / window chrome
    root.attributes("-topmost", True)
    root.configure(bg=TRANSPARENT_KEY)
    root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)  # Windows-only trick for rounded corners

    # Center horizontally, sit near the bottom, clear of the taskbar
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    TASKBAR_MARGIN = 80  # px of clearance above the taskbar - adjust if needed
    x = (screen_w - WIDTH) // 2
    y = screen_h - HEIGHT - TASKBAR_MARGIN
    root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    canvas = tk.Canvas(
        root, width=WIDTH, height=HEIGHT,
        bg=TRANSPARENT_KEY, highlightthickness=0
    )
    canvas.pack(fill="both", expand=True)

    # Accent border (slightly larger rect behind the main panel)
    _rounded_rect(canvas, 2, 2, WIDTH - 2, HEIGHT - 2, CORNER_RADIUS,
                  fill=BORDER_COLOR, outline="")
    # Main dark panel, inset by 2px to create a thin glowing border effect
    _rounded_rect(canvas, 4, 4, WIDTH - 4, HEIGHT - 4, CORNER_RADIUS - 2,
                  fill=BG_COLOR, outline="")

    icon_label = tk.Label(
        root, text="⚡", font=("Segoe UI Emoji", 20),
        bg=BG_COLOR, fg=BORDER_COLOR
    )
    canvas.create_window(34, HEIGHT // 2 - 6, window=icon_label)

    entry = tk.Entry(
        root, font=("Segoe UI", 15), width=28,
        bg=BG_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
        disabledbackground=BG_COLOR, disabledforeground=TEXT_COLOR,
        relief="flat", highlightthickness=0, bd=0,
    )
    canvas.create_window(WIDTH // 2 + 15, HEIGHT // 2 - 10, window=entry)

    # This label doubles as the hint text ("Enter to run...") AND the live
    # status line ("Searching...", "Not found", etc.) - same spot, just
    # whichever is relevant at the moment.
    HINT_TEXT = "Enter to run  ·  Esc to cancel"
    status_label = tk.Label(
        root, text=HINT_TEXT,
        font=("Segoe UI", 9), bg=BG_COLOR, fg=PLACEHOLDER_COLOR
    )
    canvas.create_window(WIDTH // 2 + 15, HEIGHT - 18, window=status_label)

    # Placeholder behavior: light gray hint text that clears on first keystroke
    PLACEHOLDER = "What do you want to do?"
    entry.insert(0, PLACEHOLDER)
    entry.config(fg=PLACEHOLDER_COLOR)
    placeholder_active = {"value": True}

    def on_focus_in(event=None):
        if placeholder_active["value"]:
            entry.delete(0, tk.END)
            entry.config(fg=TEXT_COLOR)
            placeholder_active["value"] = False

    def on_focus_out(event=None):
        if not entry.get().strip():
            entry.insert(0, PLACEHOLDER)
            entry.config(fg=PLACEHOLDER_COLOR)
            placeholder_active["value"] = True

    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)
    root.update()
    _force_foreground(root.winfo_id())
    entry.focus_force()
    entry.focus_set()
    root.after(40, lambda: (_force_foreground(root.winfo_id()), entry.focus_force(), entry.focus_set()))

    def poll_queue(q):
        try:
            outcome = q.get_nowait()
        except queue.Empty:
            root.after(80, lambda: poll_queue(q))
            return

        status, payload = outcome
        result["outcome"] = outcome

        if status == "opened":
            status_label.config(text=f"✅ {payload}", fg="#a6e3a1")
            root.after(500, root.destroy)  # brief pause so the success is visible
        elif status == "ambiguous":
            root.destroy()  # close now - main.py will show the selection popup
        else:  # not_found / error - stay open so the user can retry immediately
            status_label.config(text=f"⚠ {payload}", fg="#f38ba8")
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.config(fg=TEXT_COLOR)
            placeholder_active["value"] = False
            entry.focus_set()

    def submit(event=None):
        text = entry.get().strip()
        if placeholder_active["value"] or not text:
            return  # nothing typed - ignore Enter

        entry.config(state="disabled")
        status_label.config(text="🔎 Searching...", fg=BORDER_COLOR)

        q = queue.Queue()

        def worker():
            q.put(resolve_fn(text))

        threading.Thread(target=worker, daemon=True).start()
        root.after(80, lambda: poll_queue(q))

    def cancel(event=None):
        result["outcome"] = ("cancelled", None)
        root.destroy()

    entry.bind("<Return>", submit)
    entry.bind("<Escape>", cancel)
    root.bind("<Escape>", cancel)  # allow Esc even if focus shifts

    root.mainloop()
    return result["outcome"]


def get_selection(options: list[str]) -> str | None:
    """
    Show a dark-themed list of candidate paths and let the user pick one
    with arrow keys + Enter, or a mouse click. Returns the chosen full path,
    or None if cancelled.
    """
    result = {"choice": None}

    list_width = 520
    row_height = 32
    header_height = 40
    list_height = min(len(options), 8) * row_height
    total_height = header_height + list_height + 16

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=TRANSPARENT_KEY)
    root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = (screen_w - list_width) // 2
    y = (screen_h - total_height) // 2
    root.geometry(f"{list_width}x{total_height}+{x}+{y}")

    canvas = tk.Canvas(
        root, width=list_width, height=total_height,
        bg=TRANSPARENT_KEY, highlightthickness=0
    )
    canvas.pack(fill="both", expand=True)

    _rounded_rect(canvas, 2, 2, list_width - 2, total_height - 2, CORNER_RADIUS,
                  fill=BORDER_COLOR, outline="")
    _rounded_rect(canvas, 4, 4, list_width - 4, total_height - 4, CORNER_RADIUS - 2,
                  fill=BG_COLOR, outline="")

    header = tk.Label(
        root, text=f"⚡ Multiple matches found - pick one",
        font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg=TEXT_COLOR
    )
    canvas.create_window(list_width // 2, 22, window=header)

    listbox_frame = tk.Frame(root, bg=BG_COLOR)
    canvas.create_window(
        list_width // 2, header_height + list_height // 2 + 4,
        window=listbox_frame, width=list_width - 24, height=list_height
    )

    listbox = tk.Listbox(
        listbox_frame, font=("Segoe UI", 11),
        bg=BG_COLOR, fg=TEXT_COLOR,
        selectbackground=BORDER_COLOR, selectforeground=BG_COLOR,
        relief="flat", highlightthickness=0, bd=0,
        activestyle="none",
    )
    listbox.pack(fill="both", expand=True)

    for path in options:
        display = os.path.basename(path)
        if display.lower().endswith(".lnk"):
            display = display[:-4]  # drop .lnk extension for readability
        listbox.insert(tk.END, f"  {display}")

    listbox.selection_set(0)
    root.update()
    _force_foreground(root.winfo_id())
    listbox.focus_force()
    listbox.focus_set()
    root.after(40, lambda: (_force_foreground(root.winfo_id()), listbox.focus_force(), listbox.focus_set()))

    def confirm(event=None):
        sel = listbox.curselection()
        if sel:
            result["choice"] = options[sel[0]]
        root.destroy()

    def cancel(event=None):
        result["choice"] = None
        root.destroy()

    listbox.bind("<Return>", confirm)
    listbox.bind("<Double-Button-1>", confirm)
    listbox.bind("<Escape>", cancel)
    root.bind("<Escape>", cancel)

    root.mainloop()
    return result["choice"]