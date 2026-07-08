"""
tray_icon.py

Puts the app in the Windows system tray instead of a plain console window,
so it can't be closed by accidentally clicking the terminal's X button.
Right-click the tray icon for Show/Hide Console and Quit.
"""

import os
import ctypes
import pystray
from PIL import Image, ImageDraw

SW_HIDE = 0
SW_SHOW = 5


def _get_console_hwnd():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    return kernel32.GetConsoleWindow()


def show_console(visible: bool):
    """Show or hide the console window, if one exists (only applies when
    launched via python.exe - pythonw.exe never creates one at all)."""
    hwnd = _get_console_hwnd()
    if not hwnd:
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow(hwnd, SW_SHOW if visible else SW_HIDE)


def _make_icon_image():
    """A simple dark-circle-with-accent icon matching the popup's color theme."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(30, 30, 46, 255))       # dark base
    draw.ellipse((14, 14, 50, 50), outline=(137, 180, 250, 255), width=4)  # accent ring
    return img


def run_tray(on_quit, log_path=None):
    """
    Blocks in the calling thread running the tray icon's event loop.
    `on_quit` is called when the user selects Quit from the tray menu.
    `log_path`, if given, adds an "Open Log File" item - used when there's
    no console at all (launched via pythonw.exe) to still see output.
    """
    console_visible = {"value": True}
    hwnd = _get_console_hwnd()

    def toggle_console(icon, item):
        console_visible["value"] = not console_visible["value"]
        show_console(console_visible["value"])

    def open_log(icon, item):
        if log_path and os.path.isfile(log_path):
            os.startfile(log_path)

    def quit_app(icon, item):
        icon.stop()
        on_quit()

    items = []
    if hwnd:
        # Launched via python.exe - a real console exists, can toggle it
        items.append(pystray.MenuItem("Show/Hide Console", toggle_console))
    elif log_path:
        # Launched via pythonw.exe - no console exists at all (no taskbar
        # entry ever, like Steam) - offer the log file instead
        items.append(pystray.MenuItem("Open Log File", open_log))
    items.append(pystray.MenuItem("Quit Ultron", quit_app))

    menu = pystray.Menu(*items)
    icon = pystray.Icon("ultron", _make_icon_image(), "Ultron - AI Agent", menu)
    icon.run()