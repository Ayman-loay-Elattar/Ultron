How it works
[HOTKEY] → a small popup appears ↓ you type: "whatsapp" ↓ your command (only the text) is sent to an LLM (via Groq) to parse intent ↓ Ultron checks the result against a whitelist of safe, read-only actions ↓ it searches Windows' own Start Menu, installed apps, and your chosen folders ↓ match found → opens it. multiple matches → pick from a list. no match → tells you, lets you retry

Why it's built this way
The LLM (Llama 3.3 70B via Groq's free API) is used only for turning a loosely-phrased command into structured intent — it never executes anything itself. Every actual filesystem/process action goes through actions.py, which:

-only ever opens things (never deletes, moves, or modifies) -only searches folders you've explicitly allow-listed in config.json -only launches apps that are genuinely installed on the system (verified via Windows' own app registry, PATH, or Start Menu)

Setup
Install Python 3.10+ on Windows.

Open a terminal and install all dependencies in requirements.txt (PIP must be installed on your device): pip install -r requirements.txt (or you can do it one by one)

Get a free API key from console.groq.com/keys (Note that if you want to use another API. you will need to update the intent_parser.py file): then set it as an environment variable (PowerShell): setx GROQ_API_KEY "your-key-here"

(close and reopen your terminal after this so it takes effect)

Edit config.json (important):

Add your own shortcuts (e.g. "lecture_notes": "C:\\...\\notes.pdf").
Add any apps you want to be able to open by name.
Adjust allowed_base_dirs to folders or Drives you're comfortable letting this agent open files from.
Add your own Hotkey
Running it:
Type this in the terminal after opening the folder that has the code files (e.g. cd D:\Codes): pythonw main.py

Close the terminal — it's listening in the background. Press Ctrl+Alt+Space anywhere on your PC, type a command like:

chrome
notepad
downloads and press Enter.
