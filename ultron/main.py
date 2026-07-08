import os
import sys
import threading
from actions import ACTION_REGISTRY, load_config, open_path, prewarm_app_cache
from intent_parser import parse_intent
from popup import run_command_popup, get_selection
from hotkey_listener import listen
from tray_icon import run_tray, show_console

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ultron.log")


def resolve(user_text: str) -> tuple[str, object]:
    """
    Runs in a background thread (called from popup.py). Parses the
    command and runs the matching whitelisted action. Returns:
      ("opened", message)      - something opened
      ("ambiguous", list[str]) - multiple candidates, caller shows a picker
      ("not_found", message)   - nothing matched / error
    """
    intent = parse_intent(user_text)
    action_name = intent.get("action")
    target = intent.get("target", "")

    print(f"Parsed intent: {intent}")

    action_fn = ACTION_REGISTRY.get(action_name)
    if action_fn is None:
        return ("not_found", f"No matching action for '{action_name}'.")

    result = action_fn(target)

    if isinstance(result, list):
        return ("ambiguous", result)
    if isinstance(result, str) and result.startswith("Opened"):
        return ("opened", result)
    return ("not_found", result)


def handle_trigger():
    status, payload = run_command_popup(resolve)

    if status == "ambiguous":
        chosen = get_selection(payload)
        if chosen is None:
            print("Selection cancelled.")
            return
        print(open_path(chosen))
    elif status == "cancelled":
        pass
    else:  # "opened" or "not_found"
        print(payload)


def _redirect_output_if_no_console():
    """
    When launched via pythonw.exe, there's no console at all (this is what
    makes it disappear from the taskbar completely, like Steam does) - but
    that also means sys.stdout/stderr are None, so print() would crash.
    Redirect them to a log file instead.
    """
    if sys.stdout is None or sys.stderr is None:
        log_file = open(LOG_PATH, "a", buffering=1, encoding="utf-8")
        sys.stdout = log_file
        sys.stderr = log_file


def main():
    _redirect_output_if_no_console()

    if not os.environ.get("GROQ_API_KEY"):
        print("WARNING: GROQ_API_KEY is not set. Set it before running.")
        return

    print("Warming up installed-apps cache...")
    prewarm_app_cache()

    config = load_config()
    hotkey = config.get("hotkey", "ctrl+alt+space")

    # Hotkey listener runs in the background; the tray icon owns the main
    # thread and keeps the process alive until "Quit" is chosen.
    listener_thread = threading.Thread(
        target=lambda: listen(hotkey, handle_trigger), daemon=True
    )
    listener_thread.start()

    print("Minimizing to system tray.")
    show_console(False)  # only does anything if a console exists (python.exe)

    def on_quit():
        os._exit(0)

    run_tray(on_quit, log_path=LOG_PATH)


if __name__ == "__main__":
    main()