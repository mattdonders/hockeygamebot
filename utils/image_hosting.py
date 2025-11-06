from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path

import requests


def _ct(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def upload_b2(cfg: dict, path: Path) -> str:
    import boto3

    s3 = boto3.client(
        "s3",
        region_name=cfg["region"],
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        endpoint_url=f"https://s3.{cfg['region']}.backblazeb2.com",
    )
    key = f"{cfg.get('prefix', '').strip('/')}/{int(time.time())}_{path.name}".strip("/")
    extra = {"ContentType": _ct(path.name), "ACL": "public-read"}
    s3.upload_file(str(path), cfg["bucket"], key, ExtraArgs=extra)
    return f"https://s3.{cfg['region']}.backblazeb2.com/{cfg['bucket']}/{key}"


def upload_github_raw(cfg: dict, path: Path) -> str:
    branch = cfg.get("branch", "main")
    subdir = cfg.get("subdir", "media").strip("/")
    dest = f"{subdir}/{int(time.time())}_{path.name}"
    api = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/{dest}"
    headers = {"Authorization": f"Bearer {cfg['token']}", "Accept": "application/vnd.github+json"}
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {"message": f"Add {path.name}", "content": b64, "branch": branch}
    r = requests.put(api, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return f"https://raw.githubusercontent.com/{cfg['owner']}/{cfg['repo']}/{branch}/{dest}"


def get_public_url(root_cfg: dict, local_path: Path) -> str:
    hosting = root_cfg.get("image_hosting", {}) or {}
    provider = (hosting.get("provider") or "backblaze").lower()
    try_primary = upload_b2 if provider == "backblaze" else upload_github_raw
    try_fallback = upload_github_raw if provider == "backblaze" else upload_b2
    try:
        return try_primary(hosting[provider], local_path)
    except Exception:
        return try_fallback(hosting["github" if provider == "backblaze" else "backblaze"], local_path)
