"""Pull card scans straight from a shared Google Drive folder and import them into the library.

Works with nothing but the folder link: public folders are listed through Drive's embedded folder view and files are
fetched through the public download endpoint. If Google starts throttling the anonymous route, a Drive API key
(Google Cloud console -> APIs & Services -> Credentials, Drive API enabled) can be supplied and the same calls go
through the official API instead. One folder ("unit": a hero, a campaign box, a modular set...) is downloaded at a
time into drive_tmp/, run through mc_import, and deleted again, so disk use stays at one unit's worth of scans.
"""
import html, json, os, re, shutil, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
import requests

import mc_import

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "library")
TMP = os.path.join(HERE, "drive_tmp")
SCANS = os.path.join(HERE, "scans")
DONE_FILE = os.path.join(LIB, "drive_done.json")
TREE_FILE = os.path.join(LIB, "drive_tree.json")
DEFAULT_FOLDER = "https://drive.google.com/drive/folders/1FO7FRfJbqGsmAkfePhkzpmEqmW1-VwF2"
IMG_EXT = (".tif", ".tiff", ".jpg", ".jpeg", ".png")
# top-level folders whose sub-folders are each one importable unit; anything else at the top is a unit by itself
CATEGORY_FOLDERS = {"heros", "heroes", "expansion campaings", "expansion campaigns", "scenario packs", "modular sets", "aspects"}
UA = {"User-Agent": "Mozilla/5.0 (MC Autofill)"}


def folder_id(link):
    link = (link or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]{10,})", link) or re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", link)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", link):
        return link
    raise ValueError("That does not look like a Google Drive folder link")


# ---------- listing ----------
def _list_public(fid, session):
    t = session.get(f"https://drive.google.com/embeddedfolderview?id={fid}#list", headers=UA, timeout=60)
    t.raise_for_status()
    out = []
    for m in re.finditer(r'<div class="flip-entry" id="entry-([^"]+)".*?<a href="([^"]+)".*?<div class="flip-entry-title">(.*?)</div>',
                         t.text, re.S):
        i, href, title = m.groups()
        out.append({"id": i, "name": html.unescape(title), "folder": "/folders/" in href})
    if not out and "flip-entries" not in t.text:
        raise RuntimeError("Google did not return a folder listing (is the folder shared with 'anyone with the link'?)")
    return out


def _list_api(fid, key, session):
    out, token = [], None
    while True:
        r = session.get("https://www.googleapis.com/drive/v3/files", timeout=60, headers=UA, params={
            "q": f"'{fid}' in parents and trashed=false", "fields": "nextPageToken,files(id,name,mimeType,size)",
            "pageSize": 1000, "key": key, "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
            **({"pageToken": token} if token else {})})
        if r.status_code != 200:
            raise RuntimeError(f"Drive API error {r.status_code}: {r.text[:200]}")
        j = r.json()
        for f in j.get("files", []):
            out.append({"id": f["id"], "name": f["name"], "folder": f["mimeType"] == "application/vnd.google-apps.folder",
                        "size": int(f.get("size", 0) or 0)})
        token = j.get("nextPageToken")
        if not token:
            return out


def list_folder(fid, key=None, session=None):
    session = session or requests.Session()
    return _list_api(fid, key, session) if key else _list_public(fid, session)


def walk_files(fid, key, session, prefix=""):
    """Every image file below a folder as (relative path, file id, size)."""
    out = []
    for e in list_folder(fid, key, session):
        if e["folder"]:
            out.extend(walk_files(e["id"], key, session, prefix + e["name"] + "/"))
        elif e["name"].lower().endswith(IMG_EXT):
            out.append((prefix + e["name"], e["id"], e.get("size", 0)))
    return out


def load_done():
    return json.load(open(DONE_FILE, encoding="utf-8")) if os.path.exists(DONE_FILE) else {}


_TREE_LOCK = threading.Lock()
COUNTING = {"running": False, "done": 0, "total": 0, "root": None}


def _structure(fid, key, s):
    """Top two levels of the folder: enough to show the table straight away."""
    top = list_folder(fid, key, s)
    units = []
    for e in top:
        if not e["folder"]:
            continue
        if e["name"].strip().lower() in CATEGORY_FOLDERS:
            for sub in list_folder(e["id"], key, s):
                if sub["folder"]:
                    units.append({"id": sub["id"], "name": sub["name"], "path": f"{e['name']}/{sub['name']}", "category": e["name"]})
        else:
            units.append({"id": e["id"], "name": e["name"], "path": e["name"], "category": "Other"})
    return units


def _save_tree(result):
    os.makedirs(LIB, exist_ok=True)
    json.dump(result, open(TREE_FILE, "w", encoding="utf-8"), indent=1)


def _count_files(result, key):
    """Background: count the image files in every unit (one listing per sub-folder), saving as it goes."""
    s = requests.Session()
    units = [u for u in result["units"] if u.get("files") is None and not u.get("error")]
    COUNTING.update(running=True, done=0, total=len(units), root=result["root"])

    def count(u):
        try:
            files = walk_files(u["id"], key, s)
            u["files"], u["bytes"] = len(files), sum(f[2] for f in files)
            u.pop("error", None)
        except Exception as ex:  # noqa: BLE001
            u["files"], u["error"] = None, str(ex)
        with _TREE_LOCK:
            COUNTING["done"] += 1
            if COUNTING["done"] % 10 == 0:
                _save_tree(result)
    try:
        with ThreadPoolExecutor(6) as pool:
            list(pool.map(count, units))
    finally:
        with _TREE_LOCK:
            _save_tree(result)
            COUNTING["running"] = False


def tree(link, key=None, refresh=False, wait=False):
    """Importable units of a shared folder: [{id, name, path, category, files}], cached in library/drive_tree.json.

    Returns quickly with the folder structure; file counts are filled in by a background thread (COUNTING says how
    far it is) unless wait=True, which counts before returning (used by the import job)."""
    fid = folder_id(link)
    cache = json.load(open(TREE_FILE, encoding="utf-8")) if os.path.exists(TREE_FILE) else {}
    if refresh or cache.get("root") != fid:
        cache = {"root": fid, "units": _structure(fid, key, requests.Session()), "listed_at": time.time()}
        _save_tree(cache)
    if refresh:
        for u in cache["units"]:
            u.pop("error", None)
    if any(u.get("files") is None and not u.get("error") for u in cache["units"]):
        if wait:
            _count_files(cache, key)
        elif not COUNTING["running"]:
            threading.Thread(target=_count_files, args=(cache, key), daemon=True).start()
    cache["counting"] = COUNTING["running"] and COUNTING["root"] == fid
    cache["counted"] = COUNTING["done"] if cache["counting"] else None
    cache["count_total"] = COUNTING["total"] if cache["counting"] else None
    return cache


# ---------- downloading ----------
def download(file_id, dest, key=None, session=None, retries=4):
    session = session or requests.Session()
    url = (f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={key}" if key
           else f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t")
    last = None
    for attempt in range(retries):
        try:
            with session.get(url, stream=True, timeout=120, headers=UA) as r:
                ctype = r.headers.get("content-type", "")
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {r.status_code}")
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                if ctype.startswith("text/html"):
                    body = r.text[:4000]
                    if "quota" in body.lower() or "too many users" in body.lower():
                        raise RuntimeError("Google Drive download quota hit for this file; try again later or use an API key")
                    raise RuntimeError("Google returned a web page instead of the file (sharing changed or an interstitial page)")
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                tmp = dest + ".part"
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                os.replace(tmp, dest)
                return os.path.getsize(dest)
        except Exception as ex:  # noqa: BLE001
            last = ex
            time.sleep(min(60, 4 * (3 ** attempt)))
    raise RuntimeError(f"download failed after {retries} tries: {last}")


# ---------- background job ----------
class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.running = self.finished = self.aborted = False
        self.error = None
        self.state = "Idle"
        self.action = ""
        self.log = []
        self.unit_index = self.units_total = 0
        self.files_done = self.files_total = 0
        self.converted = 0
        self.results = []
        self.started_at = None
        self._stop = False

    def add_log(self, line):
        with self.lock:
            self.log.append(line)
            self.log = self.log[-200:]

    def snapshot(self):
        with self.lock:
            return {"running": self.running, "finished": self.finished, "aborted": self.aborted, "error": self.error,
                    "state": self.state, "action": self.action, "log": self.log[-40:], "unit_index": self.unit_index,
                    "units_total": self.units_total, "files_done": self.files_done, "files_total": self.files_total,
                    "converted": self.converted, "results": self.results,
                    "elapsed": int(time.time() - self.started_at) if self.started_at else 0}


JOB = Job()


def start(link, unit_ids, key=None, keep_scans=False, redo=False):
    if JOB.running:
        raise RuntimeError("an import is already running")
    JOB.reset()
    JOB.running = True
    JOB.started_at = time.time()
    JOB.state = "Starting"
    t = threading.Thread(target=_run, args=(link, list(unit_ids), key or None, keep_scans, redo), daemon=True)
    t.start()
    return JOB.snapshot()


def abort():
    JOB._stop = True
    JOB.action = "Stopping after the current file…"


def _run(link, unit_ids, key, keep_scans, redo):
    try:
        info = tree(link, key, wait=True)
        units = [u for u in info["units"] if u["id"] in set(unit_ids)]
        done = load_done()
        if not redo:
            units = [u for u in units if u["id"] not in done]
        JOB.units_total = len(units)
        s = requests.Session()
        for n, u in enumerate(units):
            if JOB._stop:
                break
            JOB.unit_index = n
            JOB.state = f"{u['path']} ({n + 1}/{len(units)})"
            JOB.action = "Listing files…"
            files = walk_files(u["id"], key, s)
            JOB.files_total, JOB.files_done = len(files), 0
            dest_root = os.path.join(TMP, *u["path"].split("/"))
            shutil.rmtree(dest_root, ignore_errors=True)
            failed = []

            def fetch(f):
                rel, fid, _ = f
                if JOB._stop:
                    return
                try:
                    download(fid, os.path.join(dest_root, *rel.split("/")), key, s)
                except Exception as ex:  # noqa: BLE001
                    failed.append(f"{rel}: {ex}")
                with JOB.lock:
                    JOB.files_done += 1
                JOB.action = f"Downloading {JOB.files_done}/{JOB.files_total} · {rel}"
            with ThreadPoolExecutor(4) as pool:
                list(pool.map(fetch, files))
            if JOB._stop:
                shutil.rmtree(dest_root, ignore_errors=True)
                break
            JOB.action = "Converting and matching…"
            stats = {"converted": 0, "had": 0, "unmatched": 0, "notes": 0}

            def log(line):
                JOB.add_log(f"{u['name']}: {line.strip()}")
                m = re.match(r"converted (\d+), already had (\d+), ignored \d+ .*?unmatched (\d+), noted (\d+)", line)
                if m:
                    stats.update(converted=int(m[1]), had=int(m[2]), unmatched=int(m[3]), notes=int(m[4]))
                m2 = re.match(r"\s*(\d+) converted", line)
                if m2:
                    JOB.action = f"Converting… {m2[1]} done"
            mc_import.main([dest_root], log=log, stop=lambda: JOB._stop)
            JOB.converted += stats["converted"]
            if keep_scans:
                keep = os.path.join(SCANS, *u["path"].split("/"))
                shutil.rmtree(keep, ignore_errors=True)
                os.makedirs(os.path.dirname(keep), exist_ok=True)
                shutil.move(dest_root, keep)
            else:
                shutil.rmtree(dest_root, ignore_errors=True)
            res = {"id": u["id"], "name": u["name"], "path": u["path"], "files": len(files), "failed": failed, **stats,
                   "when": time.strftime("%Y-%m-%d %H:%M")}
            JOB.results.append(res)
            if not failed and not JOB._stop:
                done = load_done()
                done[u["id"]] = res
                json.dump(done, open(DONE_FILE, "w", encoding="utf-8"), indent=1)
            JOB.add_log(f"{u['path']}: {stats['converted']} converted, {stats['had']} already in library, "
                        f"{stats['unmatched']} unmatched" + (f", {len(failed)} downloads failed" if failed else ""))
        JOB.unit_index = JOB.units_total
        JOB.state = "Stopped" if JOB._stop else "Done"
        JOB.action = f"{JOB.converted} new card images" + (" (stopped early)" if JOB._stop else "")
    except Exception as ex:  # noqa: BLE001
        JOB.error = str(ex)
        JOB.add_log(traceback.format_exc().strip().splitlines()[-1])
        JOB.state = "Error"
    finally:
        JOB.aborted = JOB._stop
        JOB.running = False
        JOB.finished = True
        shutil.rmtree(TMP, ignore_errors=True)
