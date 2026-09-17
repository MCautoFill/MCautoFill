# Installation

## Requirements

- Python 3.10 or newer
- Chrome, Edge, Firefox or Brave (for the automated upload to MPC)
- Disk space for the card library: roughly 2.5 GB for the full game at 600 DPI

## Steps

1. Download or clone the repository:

   ```bash
   git clone https://github.com/MCautoFill/MCautoFill.git
   cd MCautoFill
   ```

2. Install the Python dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

   On macOS use `python3` instead of `python`.

3. Add card backs to a `backs/` folder inside the app folder (see [Building the card library](Building-the-card-library#card-backs)).

4. Build the card library from your scans (see [Building the card library](Building-the-card-library)).

5. Start the app:

   - **Windows:** double-click `Start MC Autofill.bat`, or run `python mc_app.py`.
   - **macOS:** double-click `Start MC Autofill.command` (the first time, right-click → Open, or run `chmod +x "Start MC Autofill.command"` in Terminal), or run `python3 mc_app.py`.

   A browser tab opens at http://127.0.0.1:8765. Leave the terminal window open while you use the app; closing it stops the server.

## Updating

Pull the latest code and reinstall requirements. The library, backs and orders folders are yours and are never touched by updates.

Edits to `ui/index.html` show up on a page refresh. Edits to any `.py` file need the app restarted.

## macOS notes

- The first time the automated browser opens, macOS may ask you to allow Chrome (or the driver) to be controlled. Allow it once.
- Keep-awake during long uploads uses the `wakepy` library, which calls `caffeinate` on macOS. Untick "Allow PC to sleep" in the autofill settings to use it.
- The optional stand-alone desktop tool launch (`Build order folder` then running the tool yourself) is Windows-only. The embedded `Build & autofill…` flow works on both systems.
