# Resolve Script Console - How to Use When You Can't Type

If you have the Script Console open (Workspace > Scripts > Script Console) but cannot enter text or there is no Execute button (common in recent versions):

1. **Focus the input (no button needed in your version)**:
   - In recent Resolve versions the Script Console is a REPL (read-eval-print loop). There may not be a separate "Execute" button - you type/paste in the input area at the bottom and press **Enter** to run (Shift+Enter for newline in multi-line code).
   - Click your mouse **directly in the small text box at the BOTTOM** of the console window (it may be subtle or look like a command prompt).
   - The cursor should appear when focused. If the whole screen looks empty/blank after selecting Py3, the input pane might be collapsed - look for a thin splitter bar or resize the window/sections to reveal the input area at bottom.

2. **Select Python language**:
   - Look at the toolbar at the top of the Script Console.
   - There is usually a dropdown or buttons for "Lua" or "Python".
   - Make sure **Python** is selected.

3. **Test basic input (no Execute button - use Enter)**:
   - With the bottom box focused, type this exactly:
     print("Hello Resolve")
   - Then press **Enter** to execute (in your Resolve version there may be no separate button; the console uses Enter for execution in the input. For multi-line code, paste and use Shift+Enter for lines or just run the block).
   - You should see "Hello Resolve" appear in the output area above, "filling" the previously empty screen.

If typing still does nothing (no cursor, no response) or there is no Execute button:
- In your Resolve version, the console is likely a REPL: focus the bottom input (click it until cursor), paste code, press **Enter** to execute (no button needed; some versions have no button and use Enter or Ctrl+Enter).
- If still no input visible or empty screen, the panes may be hidden - drag the splitters or maximize/resize the console window to show the input area at the bottom.
- **Alternative to GUI typing (use this if no button or can't type)**: Run the code from PowerShell command line using fuscript (this executes your pasted code inside the running Resolve without needing the console input):
  Open PowerShell and run:
  ```powershell
  cd "C:\Users\DavidBaker\Projects\parlayvu-core"
  $env:RESOLVE_PYTHON_API = "C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
  "C:\Program Files\Blackmagic Design\DaVinci Resolve\fuscript.exe" video_system\tools\resolve\activate_api.py
  ```
  (We just ran this - it executed your code and printed "Attached: None Still none". It at least runs the code to try initializing scripting.)
- This is almost always because you are running the **x64 emulated version** of Resolve on your ARM Surface (the warning you saw on launch).
- Emulation breaks the scripting UI and API attach (external Python gets scriptapp() = None).
- **Fix now**:
  a. Close Resolve.
  b. Uninstall current DaVinci Resolve (Settings > Apps).
  c. Go to https://www.blackmagicdesign.com/support/family/davinci-resolve-and-fusion
  d. Download the **Windows ARM** (or ARM64) installer specifically.
  e. Install the native ARM version.
  f. Launch Resolve (no more warning), open a project (e.g. the RamAir one), open Script Console again.
  g. Retry steps 1-3 above or the fuscript command.

Once you can successfully execute `print("Hello Resolve")` and see the output, scripting is working.

Next:
- We can run the resolve_hello.py diagnostic (it is in video_system/tools/resolve/resolve_hello.py).
  To run it:
  - In Resolve, with Script Console open, use the menu if available (some versions have "Load Script" or "Run Script from File").
  - Or, if you have a "Scripts" list in the UI (Workspace > Scripts), you may need to add the folder containing resolve_hello.py.
  - Simpler: copy the contents of resolve_hello.py and paste/execute in the console (once input works).

After console works and test_connection.py succeeds from PowerShell, we will run:
python video_system/tools/resolve/build_timeline.py "video_system\projects\RamAir\Straight_From_The_Hart_Ep05"

This will create the real timeline inside Resolve for your Ep05 draft (using the plan and assets).

If after native ARM install the console still won't let you type, copy the FULL output of running the test_connection.py and paste it here for more debugging.

### For "Py3 provides empty screen"
Selecting Python 3 in the Script Console may show a blank/empty output area at first - this is normal.

- Click your mouse in the **bottom input box** (single line at very bottom of the console window). Make the cursor blink there.
- Type exactly this in the bottom input area, then press **Enter** (in many recent Resolve versions there is no visible "Execute" button - the console is a REPL where Enter executes the code in the input line; use Shift+Enter for new line if multi-line, or Ctrl+Enter in some layouts. If no input area at all, the console might be in a different mode - look for tabs "Console" / "Editor" or resize the window/panes):
  print("hello from Py3")
- The text "hello from Py3" should now appear in the output area above, "filling" the screen. If nothing happens, the Py3 interpreter in this Resolve install may not be active (common with emulated x64 Resolve on ARM - reinstall native ARM version). If no input box is visible, try resizing the console panes or look for a "Console" vs "Editor" tab.

Once you see output from the print, the console is working.

To activate the external Python API attach (so build_timeline succeeds from command line):

In the same Py3 console, type and execute this block (copy-paste into bottom input, then press Enter or use the execute method for your version; no button may mean Enter is the way):

import DaVinciResolveScript as dvr
r = dvr.scriptapp("Resolve")
print("Attached:", r)
if r:
    print("Version:", r.GetVersion())
    pm = r.GetProjectManager()
    proj = pm.GetCurrentProject()
    print("Project:", proj.GetName() if proj else "none")
else:
    print("Still none - make sure project open and foreground")

After executing the above in the console, go back to your PowerShell and re-run the test_connection.py (using full Python 3.12 path as below). It should now say SUCCESS.

Then run the build_timeline the same way. This will use your running Resolve to build the real timeline for the Ep05 draft. 

After build, in Resolve review the new timeline and render your draft from Deliver page to the renders/ folder. 

Use full Python path in commands to avoid any 2.7 launcher issues:

cd "C:\Users\DavidBaker\Projects\parlayvu-core"
$env:RESOLVE_PYTHON_API = "C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
C:\Users\DavidBaker\AppData\Local\Programs\Python\Python312\python.exe video_system\tools\resolve\test_connection.py

(Then the build one after success.)
