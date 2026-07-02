#!/usr/bin/env python3
"""
Hall PC -> NOMAD Uploader
=========================
Converts Hall measurement folders (produced by d3.bat) into
ELNMeasurement archive.json entries and uploads them to a NOMAD Oasis.

Usage:
    python hall_uploader.py                  # interactive (recommended)
    python hall_uploader.py <folder>         # process a specific folder
    python hall_uploader.py --dry-run <folder>
"""

import argparse
import json
import os
import re
import sys
import zipfile
import io
import time
from datetime import datetime, timezone
from pathlib import Path
from getpass import getpass

import requests

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ─────────────────────────────────────────────────────────────────────────────
# Config  (config.yml next to the script)
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.yml"

def load_config() -> dict:
    if CONFIG_PATH.exists() and HAS_YAML:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def save_config(cfg: dict):
    if HAS_YAML:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

def get_user_cfg(cfg: dict, username: str) -> dict:
    return cfg.get("users", {}).get(username, {})

def set_user_cfg(cfg: dict, username: str, key: str, value):
    cfg.setdefault("users", {}).setdefault(username, {})[key] = value

# ─────────────────────────────────────────────────────────────────────────────
# Terminal helpers
# ─────────────────────────────────────────────────────────────────────────────

def yn(question: str, default: str = "y") -> bool:
    tag = "[Y/n]" if default == "y" else "[y/N]"
    while True:
        sys.stdout.write(f"  {question} {tag}: ")
        sys.stdout.flush()
        ans = input().strip().lower()
        if ans == "":
            return default == "y"
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False

def prompt(label: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    sys.stdout.write(f"  {label}{hint}: ")
    sys.stdout.flush()
    val = input().strip()
    return val if val else default

def header(text: str):
    print(f"\n{'─'*60}")
    print(f"  {text}")
    print(f"{'─'*60}")

def step(n: int, text: str):
    print(f"\n  [{n}] {text}")

def ok(text: str):
    print(f"      ✓  {text}")

def warn(text: str):
    print(f"      ⚠  {text}")

def err(text: str):
    print(f"      ✗  {text}")

def info(text: str):
    print(f"      →  {text}")

# ─────────────────────────────────────────────────────────────────────────────
# Folder / file parsing
# ─────────────────────────────────────────────────────────────────────────────

FOLDER_RE = re.compile(r"^(?P<date>\d{8})_(?P<time>\d{4})_(?P<samples>.+)$")

def parse_folder_name(folder_name: str):
    """
    Parse d3.bat folder name  YYYYMMDD_HHMM_<SampleIDs>
    Returns (datetime_iso, [sample_ids])
    """
    m = FOLDER_RE.match(folder_name)
    if not m:
        raise ValueError(
            f"'{folder_name}' does not match YYYYMMDD_HHMM_<SampleIDs> pattern."
        )
    dt = datetime.strptime(m.group("date") + m.group("time"), "%Y%m%d%H%M").replace(
        tzinfo=timezone.utc
    )
    sample_ids = _split_samples(m.group("samples").split("_"))
    return dt.isoformat(), sample_ids

def _split_samples(tokens: list) -> list:
    """
    ['m84317', 'C']      → ['m84317_C']
    ['M81', 'M82']        → ['M81', 'M82']
    """
    if not tokens:
        return []
    merged = [tokens[0]]
    for tok in tokens[1:]:
        if len(tok) <= 2 and merged[-1][0].isalpha():
            merged[-1] += "_" + tok
        else:
            merged.append(tok)
    return merged

def find_dat_files(folder: Path) -> list:
    return sorted(folder.glob("*.dat"))

def find_all_raw_files(folder: Path) -> list:
    """All files in folder except generated .archive.json and .zip."""
    skip_suffixes = {".archive.json", ".zip"}
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and not any(p.name.endswith(s) for s in skip_suffixes)
    )

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def dat_to_html(text: str) -> str:
    """Convert plain .dat text to the HTML format NOMAD stores in result fields."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraphs, current = [], []
    for line in lines:
        if line.strip() == "":
            if current:
                paragraphs.append(current)
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append(current)

    parts = []
    for para in paragraphs:
        inner = "<br />\n".join(
            ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
              .replace("\t", " &nbsp;&nbsp;&nbsp;")
              .replace("  ", "&nbsp;&nbsp;")
            for ln in para
        )
        parts.append(f"<p>{inner}</p>")
    return "\n".join(parts)

# ─────────────────────────────────────────────────────────────────────────────
# Archive JSON
# ─────────────────────────────────────────────────────────────────────────────

def build_archive(
    name: str,
    datetime_iso: str,
    sample_ids: list,
    instrument_id: str,
    dat_files: list,          # [(filename, html_content), ...]
) -> dict:
    return {
        "data": {
            "m_def": "nomad.datamodel.metainfo.eln.ELNMeasurement",
            "name": name,
            "datetime": datetime_iso,
            "samples": [{"lab_id": sid} for sid in sample_ids],
            "instruments": [{"lab_id": instrument_id}],
            "results": [{"name": fn, "result": content} for fn, content in dat_files],
        }
    }

# ─────────────────────────────────────────────────────────────────────────────
# Zip packaging
# ─────────────────────────────────────────────────────────────────────────────

def build_zip(archive: dict, archive_filename: str, folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(archive_filename, json.dumps(archive, indent=2))
        for fpath in find_all_raw_files(folder):
            zf.writestr(fpath.name, fpath.read_bytes())
    return buf.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# NOMAD API
# ─────────────────────────────────────────────────────────────────────────────

def nomad_login(base_url: str, username: str, password: str) -> str:
    """Return Bearer token or raise RuntimeError."""
    url = base_url.rstrip("/") + "/auth/token"
    r = requests.post(
        url,
        data={"grant_type": "password", "username": username, "password": password},
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Login failed ({r.status_code}): {r.text[:200]}")
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("Login response missing access_token.")
    return token

def nomad_new_upload(base_url: str, token: str, zip_bytes: bytes, upload_name: str) -> str:
    """Create a new upload, return upload_id."""
    url = base_url.rstrip("/") + "/uploads"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params={"upload_name": upload_name},
        data=zip_bytes,
        timeout=120,
    )
    r.raise_for_status()
    uid = r.json().get("upload_id")
    if not uid:
        raise RuntimeError(f"No upload_id in response: {r.text[:300]}")
    return uid

def nomad_add_to_upload(base_url: str, token: str, upload_id: str,
                        zip_bytes: bytes, subfolder: str) -> bool:
    """Add files (as zip) into an existing upload under subfolder. Returns True on success."""
    url = base_url.rstrip("/") + f"/uploads/{upload_id}/raw/{subfolder}"
    r = requests.put(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        },
        params={"overwrite_if_exists": "true", "auto_decompress": "true"},
        data=zip_bytes,
        timeout=300,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Upload failed ({r.status_code}): {r.text[:300]}")
    return True

def nomad_wait(base_url: str, token: str, upload_id: str, timeout: int = 180) -> str:
    """
    Poll upload status until SUCCESS/FAILURE or timeout.
    Returns final status string.
    """
    url = base_url.rstrip("/") + f"/uploads/{upload_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    deadline = time.time() + timeout
    last_status = "UNKNOWN"
    dots = 0
    sys.stdout.write("      Processing")
    sys.stdout.flush()
    while time.time() < deadline:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json().get("data", {})
                last_status = data.get("process_status", "PENDING")
                if last_status in ("SUCCESS", "FAILURE"):
                    sys.stdout.write(" done.\n")
                    sys.stdout.flush()
                    return last_status
        except Exception:
            pass
        sys.stdout.write(".")
        sys.stdout.flush()
        dots += 1
        time.sleep(3)
    sys.stdout.write(f" timed out (last: {last_status}).\n")
    return "TIMEOUT"

def nomad_upload_url(base_url: str, upload_id: str) -> str:
    """Build the direct GUI URL to the upload page."""
    # base_url is like  http://host/nomad-oasis/api/v1
    # GUI is at         http://host/nomad-oasis/gui/user/uploads/upload/id/<id>
    gui_base = re.sub(r"/api/v1/?$", "", base_url.rstrip("/"))
    return f"{gui_base}/gui/user/uploads/upload/id/{upload_id}"

# ─────────────────────────────────────────────────────────────────────────────
# Core: process one folder into (archive, zip_bytes, filenames)
# ─────────────────────────────────────────────────────────────────────────────

def process_folder(folder: Path, instrument_id: str,
                   datetime_override: str = None, samples_override: list = None):
    """
    Parse folder, build archive JSON and zip.
    Writes .archive.json and .zip into the folder.
    Returns (archive_dict, zip_bytes, zip_filename) or (None, None, None) on skip.
    """
    folder_name = folder.name

    # --- Metadata ---
    if datetime_override or samples_override:
        dt_iso     = datetime_override or datetime.now(timezone.utc).isoformat()
        sample_ids = samples_override or [folder_name]
    else:
        try:
            dt_iso, sample_ids = parse_folder_name(folder_name)
        except ValueError as e:
            warn(str(e))
            dt_iso     = datetime.now(timezone.utc).isoformat()
            sample_ids = [folder_name]

    info(f"Datetime  : {dt_iso}")
    info(f"Sample(s) : {', '.join(sample_ids)}")
    info(f"Instrument: {instrument_id}")

    # --- .dat files ---
    dat_paths = find_dat_files(folder)
    if not dat_paths:
        warn("No .dat files found — skipping this folder.")
        return None, None, None

    info(f"Found {len(dat_paths)} .dat file(s): {[p.name for p in dat_paths]}")

    dat_files = [(p.name, dat_to_html(read_text(p))) for p in dat_paths]

    # --- Build names ---
    primary    = sample_ids[0]
    ts         = dt_iso[:16].replace("-","").replace("T","_").replace(":","")
    meas_name  = f"{primary}__Hall_{ts}_norefs"
    arch_fname = f"{meas_name}.archive.json"
    zip_fname  = f"{meas_name}.zip"

    archive = build_archive(
        name=meas_name,
        datetime_iso=dt_iso,
        sample_ids=sample_ids,
        instrument_id=instrument_id,
        dat_files=dat_files,
    )

    zip_bytes = build_zip(archive, arch_fname, folder)

    # Always write files into the folder
    (folder / arch_fname).write_text(json.dumps(archive, indent=2), encoding="utf-8")
    (folder / zip_fname).write_bytes(zip_bytes)
    ok(f"Saved {arch_fname}")
    ok(f"Saved {zip_fname}  ({len(zip_bytes)//1024} KB)")

    return archive, zip_bytes, zip_fname

# ─────────────────────────────────────────────────────────────────────────────
# Interactive mode
# ─────────────────────────────────────────────────────────────────────────────

def interactive():
    header("Hall PC → NOMAD Uploader")
    cfg = load_config()

    # ── STEP 1: Login ───────────────────────────────────────────────────────
    step(1, "Log in to NOMAD")

    # Username — no hint shown, silently fall back to last used if Enter pressed
    last_user = cfg.get("last_user", "")
    sys.stdout.write("  NOMAD username: ")
    sys.stdout.flush()
    username_input = input().strip()
    username = username_input if username_input else last_user
    if not username:
        err("Username is required.")
        return

    # Base URL — if already saved for this user, show and confirm; don't re-prompt
    user_cfg  = get_user_cfg(cfg, username)
    saved_url = user_cfg.get("base_url", "")

    if saved_url:
        info(f"Server: {saved_url}")
        if not yn("Use this server?", default="y"):
            sys.stdout.write("  NOMAD Oasis URL: ")
            sys.stdout.flush()
            saved_url = input().strip()
            if not saved_url:
                err("NOMAD URL is required.")
                return
    else:
        sys.stdout.write("  NOMAD Oasis URL: ")
        sys.stdout.flush()
        saved_url = input().strip()
        if not saved_url:
            err("NOMAD URL is required.")
            return

    base_url = saved_url
    password = getpass("  Password: ")

    try:
        token = nomad_login(base_url, username, password)
        ok(f"Logged in as {username}")
    except Exception as e:
        err(f"Login failed: {e}")
        return

    # Save URL for this user
    set_user_cfg(cfg, username, "base_url", base_url)
    cfg["last_user"] = username
    save_config(cfg)

    # ── STEP 2: Select folder ───────────────────────────────────────────────
    step(2, "Select measurement folder")

    saved_folder = cfg.get("last_folder", "")

    if saved_folder:
        info(f"Folder: {saved_folder}")
        if yn("Use this folder?", default="y"):
            folder_input = saved_folder
        else:
            sys.stdout.write("  Measurement folder path: ")
            sys.stdout.flush()
            folder_input = input().strip().strip('"').strip("'")
    else:
        sys.stdout.write("  Measurement folder path: ")
        sys.stdout.flush()
        folder_input = input().strip().strip('"').strip("'")

    if not folder_input:
        err("No folder provided.")
        return

    folder = Path(folder_input).expanduser().resolve()
    if not folder.is_dir():
        err(f"Not a directory: {folder}")
        return

    cfg["last_folder"] = str(folder)
    save_config(cfg)

    # ── STEP 3: Process files ───────────────────────────────────────────────
    step(3, f"Building archive from  {folder.name}")

    instrument = cfg.get("instrument", "PDI_Hall_Setup")
    archive, zip_bytes, zip_fname = process_folder(folder, instrument)
    if archive is None:
        return

    # ── STEP 4: Choose upload target ────────────────────────────────────────
    step(4, "Choose upload target")

    saved_uid = user_cfg.get("upload_id", "")

    if saved_uid:
        info(f"Last used upload ID for {username}: {saved_uid}")
        use_saved = yn(f"Add files to this existing upload?", default="y")
        if use_saved:
            upload_id = saved_uid
            use_existing = True
        else:
            uid_input = prompt("Enter upload ID to use (or press Enter for new upload)", default="")
            upload_id     = uid_input or None
            use_existing  = bool(upload_id)
    else:
        uid_input = prompt("Enter an existing upload ID to add to (or press Enter to create new)", default="")
        upload_id    = uid_input or None
        use_existing = bool(upload_id)

    # ── STEP 5: Upload ──────────────────────────────────────────────────────
    step(5, "Uploading to NOMAD")

    try:
        if use_existing and upload_id:
            info(f"Adding to upload  {upload_id} ...")
            nomad_add_to_upload(base_url, token, upload_id, zip_bytes, folder.name)
            ok("Files added.")
        else:
            info("Creating new upload ...")
            upload_id = nomad_new_upload(base_url, token, zip_bytes, zip_fname)
            ok(f"Upload created  (ID: {upload_id})")
    except Exception as e:
        err(f"Upload failed: {e}")
        return

    # Save upload_id for this user
    set_user_cfg(cfg, username, "upload_id", upload_id)
    save_config(cfg)

    # ── STEP 6: Wait for processing ─────────────────────────────────────────
    step(6, "Waiting for NOMAD to process the files")
    status = nomad_wait(base_url, token, upload_id)

    print()
    if status == "SUCCESS":
        url = nomad_upload_url(base_url, upload_id)
        ok("Processing complete!")
        ok(f"View your upload here:")
        print(f"\n      {url}\n")
    elif status == "FAILURE":
        err("Processing finished with errors. Check the upload page.")
        url = nomad_upload_url(base_url, upload_id)
        print(f"\n      {url}\n")
    else:
        warn(f"Processing timed out (status: {status}).")
        info("Files were uploaded — check NOMAD in a moment.")
        url = nomad_upload_url(base_url, upload_id)
        print(f"\n      {url}\n")

# ─────────────────────────────────────────────────────────────────────────────
# CLI mode  (non-interactive, for scripting)
# ─────────────────────────────────────────────────────────────────────────────

def cli(args):
    cfg        = load_config()
    instrument = args.instrument or cfg.get("instrument", "PDI_Hall_Setup")

    results = []
    for folder_str in args.folders:
        folder = Path(folder_str).expanduser().resolve()
        if not folder.is_dir():
            err(f"Not a directory: {folder}")
            continue

        header(f"Processing  {folder.name}")
        archive, zip_bytes, zip_fname = process_folder(folder, instrument)
        if archive is not None:
            results.append((folder, zip_bytes, zip_fname))

    if args.dry_run or not results:
        return

    # Auth
    step("A", "Login")
    last_user = cfg.get("last_user", "")
    if last_user:
        info(f"Last user: {last_user}")
    sys.stdout.write("  NOMAD username: ")
    sys.stdout.flush()
    username_input = input().strip()
    username = username_input if username_input else last_user
    if not username:
        err("Username is required.")
        return

    user_cfg  = get_user_cfg(cfg, username)
    saved_url = user_cfg.get("base_url", "")
    if saved_url:
        info(f"Server: {saved_url}")
        if not yn("Use this server?", default="y"):
            sys.stdout.write("  NOMAD Oasis URL: ")
            sys.stdout.flush()
            saved_url = input().strip()
    else:
        sys.stdout.write("  NOMAD Oasis URL: ")
        sys.stdout.flush()
        saved_url = input().strip()
    if not saved_url:
        err("NOMAD URL is required.")
        return
    base_url = saved_url
    password  = getpass("  Password: ")

    try:
        token = nomad_login(base_url, username, password)
        ok(f"Logged in as {username}")
    except Exception as e:
        err(f"Login failed: {e}")
        return

    saved_uid    = user_cfg.get("upload_id", "")
    uid_input    = prompt("Upload ID (Enter = new)", default=saved_uid)
    upload_id    = uid_input or None
    use_existing = bool(upload_id)

    for folder, zip_bytes, zip_fname in results:
        step("B", f"Uploading {zip_fname}")
        try:
            if use_existing and upload_id:
                nomad_add_to_upload(base_url, token, upload_id, zip_bytes, folder.name)
                ok("Added to existing upload.")
            else:
                upload_id = nomad_new_upload(base_url, token, zip_bytes, zip_fname)
                ok(f"New upload created  (ID: {upload_id})")

            status = nomad_wait(base_url, token, upload_id)
            if status == "SUCCESS":
                ok("Done!  " + nomad_upload_url(base_url, upload_id))
            else:
                warn(f"Status: {status}  " + nomad_upload_url(base_url, upload_id))

        except Exception as e:
            err(f"Failed: {e}")

    set_user_cfg(cfg, username, "base_url", base_url)
    set_user_cfg(cfg, username, "upload_id", upload_id or "")
    cfg["last_user"] = username
    save_config(cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) == 1:
        interactive()
        return

    parser = argparse.ArgumentParser(description="Hall PC → NOMAD uploader")
    parser.add_argument("folders", nargs="+", help="Measurement folder(s)")
    parser.add_argument("--dry-run", action="store_true", help="Build files only, skip upload")
    parser.add_argument("--instrument", default=None, help="Instrument lab_id override")
    args = parser.parse_args()
    cli(args)


if __name__ == "__main__":
    main()