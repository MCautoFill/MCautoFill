"""Run the mpc-autofill desktop tool (vendored, GPL-3, see vendor/mpc_autofill) inside the app.

The tool is written for a console: it prints progress bars and asks questions with input() / InquirerPy.
Here it runs on a background thread, its state/progress/log lines are collected into JOB for the UI to poll,
and every console question is turned into a JOB.question the UI answers through /api/autofill/answer.
"""
import logging, os, re, sys, threading, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "vendor", "mpc_autofill")
if VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)

from src import driver as mpc_driver          # noqa: E402  (vendored tool)
from src import utils as mpc_utils            # noqa: E402
from src import order as mpc_order            # noqa: E402
from src.constants import Browsers, TargetSites, OrderFulfilmentMethod, States, ImageResizeMethods  # noqa: E402
from src.processing import ImagePostProcessingConfig  # noqa: E402
from src.logging import logger as mpc_logger  # noqa: E402
from src.formatting import TEXT_BOLD, TEXT_END  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Aborted(Exception):
    pass


class Job:
    """State of the current (single) autofill run, shared between the worker thread and the web API."""

    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.running = False
        self.finished = False
        self.error = None
        self.aborted = False
        self.state = "Idle"
        self.action = None
        self.log = []
        self.uploaded = self.to_upload = 0
        self.question = None          # {"id", "kind": "choice"|"continue", "message", "choices"}
        self.answer = None
        self._qid = 0
        self.order_name = None
        self.folder = None
        self.started_at = None
        self.driver = None

    def snapshot(self):
        with self.lock:
            return {"running": self.running, "finished": self.finished, "error": self.error, "aborted": self.aborted,
                    "state": self.state, "action": self.action, "log": self.log[-60:], "uploaded": self.uploaded,
                    "to_upload": self.to_upload, "question": self.question, "order": self.order_name,
                    "folder": self.folder, "elapsed": int(time.time() - self.started_at) if self.started_at else 0}

    def add_log(self, msg):
        msg = ANSI.sub("", str(msg)).replace(TEXT_BOLD, "").replace(TEXT_END, "").strip()
        if not msg:
            return
        if self.aborted and ("uncaught exception" in msg.lower() or "HTTPConnectionPool" in msg):
            return  # the browser was closed on purpose; the tool's error chatter is noise here
        with self.lock:
            for line in msg.splitlines():
                if line.strip():
                    self.log.append(line.strip())
            self.log = self.log[-400:]

    # ----- questions: block the worker until the UI answers -----
    def ask(self, kind, message, choices=None, default=None):
        with self.lock:
            self._qid += 1
            self.question = {"id": self._qid, "kind": kind, "message": ANSI.sub("", str(message)).replace(TEXT_BOLD, "").replace(TEXT_END, "").strip(),
                             "choices": [str(c) for c in (choices or [])], "default": str(default) if default is not None else None}
            self.answer = None
            qid = self._qid
        while True:
            if self.aborted:
                with self.lock:
                    self.question = None
                raise Aborted()
            with self.lock:
                if self.answer is not None and self.answer[0] == qid:
                    ans = self.answer[1]
                    self.question = None
                    self.answer = None
                    return ans
            time.sleep(0.2)

    def reply(self, qid, value):
        with self.lock:
            if self.question and self.question["id"] == qid:
                self.answer = (qid, value)
                return True
        return False


JOB = Job()


# ----- console replacements the vendored modules get instead of the real ones -----
class _FakeSelect:
    def __init__(self, message, choices, default=None, **kw):
        self.message, self.choices, self.default = message, list(choices), default

    def execute(self):
        if JOB.aborted:
            return "Terminate" if "Terminate" in [str(c) for c in self.choices] else self.choices[0]
        ans = JOB.ask("choice", self.message, self.choices, self.default)
        for c in self.choices:
            if str(c) == str(ans):
                return c
        return self.choices[0]


class _FakeInquirer:
    @staticmethod
    def select(message, choices, default=None, **kw):
        return _FakeSelect(message, choices, default)


def _fake_input(prompt=""):
    JOB.add_log(prompt)
    JOB.ask("continue", prompt)
    return ""


class _Bar:
    """Stands in for an enlighten progress bar / status bar; feeds counts into JOB."""

    def __init__(self, role):
        self.role, self.count, self.total = role, 0, 0

    def update(self, incr=1, **kw):
        if "state" in kw or "action" in kw:      # status bar
            return
        self.count += incr
        if self.role == "upload":
            with JOB.lock:
                JOB.uploaded, JOB.to_upload = self.count, self.total

    def refresh(self, **kw):
        if self.role == "upload":
            with JOB.lock:
                JOB.uploaded, JOB.to_upload = self.count, self.total

    def close(self):
        pass


class AppDriver(mpc_driver.AutofillDriver):
    def initialise_bars(self):
        self.status_bar = _Bar("status")
        self.order_progress_bar = _Bar("order")
        self.download_bar = _Bar("download")
        self.upload_bar = _Bar("upload")

    def set_state(self, state, action=None):
        self.state, self.action = state, action
        with JOB.lock:
            JOB.state, JOB.action = str(state), action


class _JobLogHandler(logging.Handler):
    def emit(self, record):
        try:
            JOB.add_log(record.getMessage())
        except Exception:
            pass


_patched = False


def _patch_tool():
    """Reroute the tool's console interactions to the app. Applied once."""
    global _patched
    if _patched:
        return
    mpc_driver.input = _fake_input
    mpc_driver.inquirer = _FakeInquirer
    mpc_utils.inquirer = _FakeInquirer
    mpc_utils.input = _fake_input
    mpc_order.input = _fake_input
    mpc_logger.setLevel(logging.DEBUG)
    h = _JobLogHandler()
    h.setLevel(logging.INFO)
    mpc_logger.addHandler(h)
    _patched = True


def start(folder, settings):
    """Start auto-filling <folder>/order.xml with the given settings on a background thread."""
    if JOB.running:
        raise RuntimeError("an autofill run is already in progress")
    _patch_tool()
    JOB.reset()
    JOB.running = True
    JOB.folder = folder
    JOB.order_name = os.path.basename(folder)
    JOB.started_at = time.time()
    t = threading.Thread(target=_run, args=(folder, settings), daemon=True)
    t.start()
    return JOB.snapshot()


def abort():
    JOB.aborted = True
    JOB.add_log("Abort requested.")
    drv = JOB.driver
    if drv is not None:
        try:
            drv.quit()
        except Exception:
            pass


def _run(folder, s):
    keep = None
    try:
        browser = Browsers[s.get("browser", "chrome")]
        site = TargetSites[s.get("site", "MakePlayingCards")]
        method = OrderFulfilmentMethod[s.get("method", "new_project")]
        auto_save = bool(s.get("auto_save", True))
        threshold = int(s.get("auto_save_threshold", 5) or 5)
        post = None
        if s.get("post_process"):
            post = ImagePostProcessingConfig(max_dpi=int(s.get("max_dpi", 800)), downscale_alg=ImageResizeMethods[s.get("downscale_alg", "LANCZOS")])
        if not s.get("allow_sleep"):
            try:
                from wakepy import keep as _keep
                keep = _keep.running()
                keep.__enter__()
            except Exception:
                keep = None

        JOB.add_log(f"Reading {os.path.join(folder, 'order.xml')}")
        order = mpc_order.CardOrder.from_file_path(working_directory=folder, file_path=os.path.join(folder, "order.xml"))
        JOB.add_log(order.get_overview())
        with JOB.lock:
            JOB.state, JOB.action = "Initialising", f"Starting {browser.name}"
        drv = AppDriver(browser=browser, target_site=site, binary_location=s.get("binary_location") or None,
                        starting_url=s.get("landing_url") or "data:")
        JOB.driver = drv.driver
        drv.execute_order(order=order, fulfilment_method=method, auto_save_threshold=threshold if auto_save else None,
                          post_processing_config=post)
        with JOB.lock:
            JOB.state, JOB.action = str(States.finished), "Review the project in the browser window, then add it to your cart"
        JOB.add_log("Finished. Review the project in the browser window before checking out; the window stays open.")
    except (Aborted, SystemExit):
        with JOB.lock:
            JOB.aborted = True
            JOB.state, JOB.action = "Stopped", None
        JOB.add_log("Autofill stopped.")
    except Exception as e:
        JOB.error = f"{type(e).__name__}: {e}"
        JOB.add_log("ERROR " + JOB.error)
        JOB.add_log(traceback.format_exc().splitlines()[-1])
        with JOB.lock:
            JOB.state, JOB.action = "Error", None
    finally:
        if keep is not None:
            try:
                keep.__exit__(None, None, None)
            except Exception:
                pass
        with JOB.lock:
            JOB.running = False
            JOB.finished = True
            JOB.question = None


def options():
    return {"browsers": [b.name for b in Browsers], "sites": [t.name for t in TargetSites],
            "methods": [{"value": m.name, "label": str(m)} for m in OrderFulfilmentMethod],
            "downscale": [m.name for m in ImageResizeMethods]}
