import os
import subprocess
import json
import shutil

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

START_MENU_DIRS = [
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
]

MAX_CANDIDATES = 10  # cap how many ambiguous matches we show at once
MAX_SEARCH_DEPTH = 6  # don't descend deeper than this under an allowed folder
MAX_SCAN_MATCHES = 30  # stop scanning early once we have plenty of matches

# Folder names to never descend into - these are either huge, irrelevant,
# or system-managed, and skipping them is what makes search fast.
SKIP_DIR_NAMES = {
    "node_modules", ".git", ".venv", "venv", "__pycache__",
    "$recycle.bin", "system volume information", "appdata",
    ".cache", "dist", "build",
}

_INSTALLED_APPS_CACHE = None  # populated once via Get-StartApps, then reused


def _get_installed_apps() -> list[tuple[str, str]]:
   
    global _INSTALLED_APPS_CACHE
    if _INSTALLED_APPS_CACHE is not None:
        return _INSTALLED_APPS_CACHE

    apps = []
    try:
        ps_command = "Get-StartApps | ForEach-Object { $_.Name + '|' + $_.AppID }"
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True, text=True, timeout=10,
        )
        for line in completed.stdout.splitlines():
            if "|" in line:
                name, app_id = line.split("|", 1)
                apps.append((name.strip(), app_id.strip()))
    except Exception:
        apps = []

    _INSTALLED_APPS_CACHE = apps
    return apps


def prewarm_app_cache():
    """Call once at startup so the first user command doesn't pay the
    PowerShell lookup cost."""
    _get_installed_apps()


def _search_installed_apps(name: str) -> list[str]:
    """Find installed apps (including Store/UWP apps) whose name contains
    `name`. Returns 'shell:appsFolder\\<AppID>' pseudo-paths - handled
    specially by open_path()."""
    name = name.lower()
    matches = []
    for app_name, app_id in _get_installed_apps():
        if name in app_name.lower():
            matches.append(f"shell:appsFolder\\{app_id}")
    return matches


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_path_allowed(path: str, config: dict) -> bool:
    """Only allow paths that live inside an explicitly allowed base folder."""
    abs_path = os.path.abspath(path)
    for base in config.get("allowed_base_dirs", []):
        base_abs = os.path.abspath(base)
        if abs_path.startswith(base_abs):
            return True
    return False


def _find_on_path(name: str) -> str | None:
    """
    Resolve a name to a real executable on Windows' PATH (e.g. 'notepad' ->
    'C:\\Windows\\System32\\notepad.exe'). Returns None if not found.
    Safe because shutil.which only returns a path that genuinely exists
    as an executable - it doesn't execute anything or go through a shell.
    """
    found = shutil.which(name)
    if found:
        return found
    if not name.lower().endswith(".exe"):
        found = shutil.which(name + ".exe")
        if found:
            return found
    return None


def _search_start_menu(name: str) -> list[str]:
    """Find .lnk shortcuts whose filename contains `name` (case-insensitive)."""
    name = name.lower()
    matches = []
    for base in START_MENU_DIRS:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                if f.lower().endswith(".lnk") and name in f.lower():
                    matches.append(os.path.join(root, f))
    return matches


def _search_allowed_dirs(name: str, config: dict) -> list[str]:
    """Find files/folders whose name contains `name`, only inside allowed_base_dirs.
    Skips known-heavy folders, caps recursion depth, and stops early once
    plenty of matches are found - this is what keeps search fast."""
    name = name.lower()
    matches = []
    for base in config.get("allowed_base_dirs", []):
        if not os.path.isdir(base):
            continue
        base_depth = os.path.abspath(base).rstrip("\\/").count(os.sep)
        for root, dirs, files in os.walk(base, topdown=True):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIR_NAMES]

            depth = os.path.abspath(root).rstrip("\\/").count(os.sep) - base_depth
            if depth >= MAX_SEARCH_DEPTH:
                dirs[:] = []  # don't go any deeper from here

            for entry in dirs + files:
                if name in entry.lower():
                    matches.append(os.path.join(root, entry))
                    if len(matches) >= MAX_SCAN_MATCHES:
                        return matches
    return matches


def _display_name(path: str) -> str:
    """Same logic popup.py uses to show a candidate - used here to detect
    two paths that are really 'the same thing' (e.g. duplicate shortcuts)."""
    if path.lower().startswith("shell:"):
        name = path.split("\\")[-1]
    else:
        name = os.path.basename(path)
        if name.lower().endswith(".lnk"):
            name = name[:-4]
    return name.strip().lower()


def _dedupe_by_display_name(paths: list[str]) -> list[str]:
    """Collapse candidates that would show as the same name (e.g. a shortcut
    that exists in two Start Menu folders) down to a single entry."""
    seen = set()
    deduped = []
    for p in paths:
        key = _display_name(p)
        if key not in seen:
            seen.add(key)
            deduped.append(p)
    return deduped


def open_path(path: str) -> str:
    """
    Actually open a resolved path (file, folder, .lnk shortcut, or a
    'shell:appsFolder\\<AppID>' pseudo-path for Store/UWP apps).
    Only called on paths that already came from a trusted source
    (config.json, Start Menu search, installed-apps lookup, PATH lookup,
    or allowed_base_dirs search) - never directly on raw LLM output.
    """
    if path.lower().startswith("shell:"):
        subprocess.Popen(["explorer.exe", path])
        return f"Opened: {path}"

    if not os.path.exists(path):
        return f"'{path}' no longer exists. Not opened."
    os.startfile(path)
    return f"Opened: {path}"


def open_file(target: str) -> str | list[str]:
    """
    Open a file. Checks config.json's 'shortcuts' first, then falls back
    to searching allowed_base_dirs by filename, then finally treats
    `target` as a literal path (only if inside allowed_base_dirs).
    """
    config = load_config()
    shortcuts = config.get("shortcuts", {})

    path = shortcuts.get(target.lower())
    if path is not None:
        if not os.path.isfile(path):
            return f"Shortcut '{target}' points to a missing file: {path}"
        return open_path(path)

    # Not a registered shortcut - search allowed folders by filename
    matches = _search_allowed_dirs(target, config)
    file_matches = [m for m in matches if os.path.isfile(m)]
    if len(file_matches) == 1:
        return open_path(file_matches[0])
    if len(file_matches) > 1:
        return file_matches[:MAX_CANDIDATES]

    # Last resort - treat target as a literal path, only if allowed
    if os.path.isfile(target) and _is_path_allowed(target, config):
        return open_path(target)

    return f"Couldn't find a file for '{target}'. Not opened."


def open_app(target: str) -> str | list[str]:
    """Open an application. Checks config.json's 'apps' first, then falls
    back to Windows PATH, then Start Menu shortcuts."""
    config = load_config()
    apps = config.get("apps", {})
    exe = apps.get(target.lower())

    if exe is not None:
        if os.path.isabs(exe):
            if not os.path.isfile(exe):
                return f"App path for '{target}' does not exist: {exe}"
            return open_path(exe)
        else:
            subprocess.Popen(exe, shell=True)
            return f"Opened app: {target}"

    # Not manually registered - try Windows PATH first (covers built-in
    # tools like notepad, calc, mspaint, explorer, cmd, powershell)
    path_match = _find_on_path(target)
    if path_match:
        subprocess.Popen([path_match])
        return f"Opened app: {path_match}"

    # Then search Start Menu shortcuts + installed apps (covers store/UWP apps too)
    matches = _dedupe_by_display_name(
        _search_start_menu(target) + _search_installed_apps(target)
    )
    if len(matches) == 1:
        return open_path(matches[0])
    if len(matches) > 1:
        return matches[:MAX_CANDIDATES]

    return f"'{target}' is not in the app whitelist and no Start Menu match was found."


def open_folder(target: str) -> str:
    """Open a folder in Explorer, only if inside allowed_base_dirs."""
    config = load_config()

    if not os.path.isdir(target):
        return f"Couldn't find a folder for '{target}'. Not opened."

    if not _is_path_allowed(target, config):
        return f"'{target}' is outside the allowed folders. Not opened for safety."

    return open_path(target)


def open_by_name(target: str) -> str | list[str]:
   
    config = load_config()
    key = target.lower()

    # 1. Exact registered shortcuts/apps still work and are fastest
    if key in config.get("shortcuts", {}):
        return open_file(target)
    if key in config.get("apps", {}):
        return open_app(target)

    # 2. Windows PATH (covers built-in tools: notepad, calc, mspaint, etc.)
    path_match = _find_on_path(target)
    if path_match:
        subprocess.Popen([path_match])
        return f"Opened app: {path_match}"

    # 3. Start Menu shortcuts + installed apps (covers store/UWP apps like WhatsApp)
    start_menu_matches = _dedupe_by_display_name(
        _search_start_menu(target) + _search_installed_apps(target)
    )
    if len(start_menu_matches) == 1:
        return open_path(start_menu_matches[0])
    if len(start_menu_matches) > 1:
        return start_menu_matches[:MAX_CANDIDATES]

    # 4. Files/folders inside allowed folders
    dir_matches = _search_allowed_dirs(target, config)
    if len(dir_matches) == 1:
        return open_path(dir_matches[0])
    if len(dir_matches) > 1:
        return dir_matches[:MAX_CANDIDATES]

    return f"Couldn't find anything matching '{target}'."


# Every action the LLM is allowed to trigger MUST be registered here.
# The intent parser is instructed to only ever choose from these keys.
ACTION_REGISTRY = {
    "open_file": open_file,
    "open_app": open_app,
    "open_folder": open_folder,
    "open": open_by_name,
}