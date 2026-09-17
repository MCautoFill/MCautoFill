# Uploading to MPC

`Build & autofill…` writes the order folder and then runs the embedded mpc-autofill desktop tool. Nothing else needs to be installed; the tool's console prompts are shown in the app instead of a terminal.

## Settings dialog

| Setting | Meaning |
| --- | --- |
| Upload as | **New project** creates a fresh MPC project. **Add to a saved project** appends these cards to an existing project. **Continue project** lets you resume editing one; the app asks you to open it in the browser when it is ready. |
| Browser | Chrome, Edge, Firefox or Brave. Selenium downloads the matching driver automatically. |
| Site | MakePlayingCards is the default. The other sites the desktop tool supports are listed too. |
| Auto-save to your account | Saves the project to your MPC account every N cards. Needs you to be signed in: the app pauses and shows a sign-in banner until you are. Recommended for large orders so a browser hiccup does not lose the upload. |
| Post-process images | Off by default. Downscales images above the given DPI before upload. The library is already at 600 DPI so this is normally unnecessary. |
| Allow PC to sleep | Off by default, which keeps the machine awake during the upload. |
| Browser binary | Only if your browser is installed somewhere unusual. |

Settings are remembered between runs.

## What happens

1. The order folder is built (a toast tells you how many cards, and how many were skipped for lack of an image).
2. A browser window opens on a landing page and is then driven by the tool. Do not use that window while the upload runs.
3. The strip at the top of the app shows the state, the current action, a progress bar and the last few log lines. Questions from the tool (for example which saved project to add to) appear there as buttons.
4. When auto-save is on and you are not signed in, the strip turns yellow and waits. Sign in inside the automated browser window; the upload resumes on its own.
5. When it finishes, the browser is left on the MPC project page. Check the preview, then add to cart and order from the site as usual.

**Stop** aborts the run and closes the automated browser.

## Limits and checks

- MPC projects hold at most **612 cards**. The Selected cards tab warns when the order is over. Split large orders by hero or by expansion.
- Double-sided cards are uploaded as front and back pairs; everything else gets the card back for its type.
- The stock is written into `order.xml` as `(S30) Standard Smooth`. Change it on the MPC site before ordering if you want a different one.
- Do a small order (one hero) first and look at MPC's preview: the artwork should run past the card edge into the bleed, and the frame and text box should sit well inside the trim line.
