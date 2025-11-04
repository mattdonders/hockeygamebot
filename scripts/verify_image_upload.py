#!/usr/bin/env python3
import argparse
import base64
import mimetypes
import sys
import time
from pathlib import Path

import yaml

# Optional deps (we validate later with nice errors)
try:
    import boto3  # Backblaze B2 (S3-compatible)
except Exception:
    boto3 = None

try:
    from github import Github  # GitHub
except Exception:
    Github = None


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(f"❌ config.yaml not found at: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def guess_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


# ---------- Backblaze (S3-compatible) ----------
def upload_to_backblaze_b2(cfg: dict, local_path: Path, key_name: str) -> str:
    """
    Uploads to a *public* B2 bucket via S3-compatible API and returns the HTTPS URL.
    """
    if not boto3:
        sys.exit("❌ Missing dependency: boto3 (pip install boto3)")

    region = cfg["region"]
    bucket = cfg["bucket"]
    access_key_id = cfg["access_key_id"]
    secret_access_key = cfg["secret_access_key"]

    endpoint_url = f"https://s3.{region}.backblazeb2.com"
    s3 = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        endpoint_url=endpoint_url,
    )

    extra = {"ContentType": guess_content_type(local_path.name), "ACL": "public-read"}
    s3.upload_file(str(local_path), bucket, key_name, ExtraArgs=extra)

    # Public URL served by B2's S3 endpoint:
    return f"{endpoint_url}/{bucket}/{key_name}"


# ---------- GitHub Raw ----------
def upload_to_github_raw(cfg: dict, local_path: Path, dest_rel_path: str) -> str:
    """
    Uploads a file to a *public* GitHub repo using the Contents API and returns the Raw URL.
    - Creates the file if it doesn't exist; updates it if it does.
    - Ensures the repo stores binary (not base64 literal).
    """
    token = cfg["token"]
    owner = cfg["owner"]
    repo = cfg["repo"]
    branch = cfg.get("branch", "main")

    api_base = f"https://api.github.com/repos/{owner}/{repo}/contents/{dest_rel_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    with open(local_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    # Check if file exists to get its SHA for update
    sha = None
    r_get = requests.get(api_base, headers=headers, params={"ref": branch}, timeout=30)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")

    payload = {
        "message": f"Add/Update media {local_path.name}",
        "content": b64,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r_put = requests.put(api_base, headers=headers, json=payload, timeout=60)
    if not (200 <= r_put.status_code < 300):
        raise RuntimeError(f"GitHub upload failed: {r_put.status_code} {r_put.text}")

    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{dest_rel_path}"


def main():
    ap = argparse.ArgumentParser(
        description="Verify image upload to Backblaze B2 and/or GitHub to obtain a public URL for Threads."
    )
    ap.add_argument("--image", required=True, help="Local image path to upload")
    ap.add_argument(
        "--provider",
        choices=["configured", "backblaze", "github", "both"],
        default="configured",
        help="Where to upload. `configured` uses image_hosting.provider in config.yaml.",
    )
    ap.add_argument(
        "--name", help="Override destination filename (default keeps your local filename, timestamped)."
    )
    ap.add_argument(
        "--only-url",
        action="store_true",
        help="Print URL(s) only (no extra logs) — handy for piping into other scripts.",
    )
    args = ap.parse_args()

    img_path = Path(args.image).expanduser().resolve()
    if not img_path.exists():
        sys.exit(f"❌ File not found: {img_path}")

    cfg = load_config()
    hosting_cfg = cfg.get("image_hosting") or {}
    provider_cfg = (hosting_cfg.get("provider") or "").lower()

    # Build a timestamped destination name to avoid collisions
    ts = int(time.time())
    base_name = args.name or f"{ts}_{img_path.name}"

    urls = []

    def log(msg: str):
        if not args.only_url:
            print(msg)

    # Decide providers to hit
    targets = []
    if args.provider == "configured":
        if provider_cfg in ("backblaze", "github"):
            targets = [provider_cfg]
        else:
            # Try B2, then GitHub if present
            if "backblaze" in hosting_cfg:
                targets.append("backblaze")
            if "github" in hosting_cfg:
                targets.append("github")
            if not targets:
                sys.exit("❌ No image hosting configured in config.yaml (image_hosting.*).")
    elif args.provider == "both":
        targets = [p for p in ("backblaze", "github") if p in hosting_cfg]
        if not targets:
            sys.exit("❌ Neither Backblaze nor GitHub configured in config.yaml.")
    else:
        targets = [args.provider]

    for target in targets:
        try:
            if target == "backblaze":
                b2cfg = hosting_cfg.get("backblaze")
                if not b2cfg:
                    raise RuntimeError("Backblaze block missing in config.yaml")
                prefix = (b2cfg.get("prefix") or "").strip("/")
                key_name = f"{prefix}/{base_name}" if prefix else base_name
                if not args.only_url:
                    log(f"[Backblaze] Uploading to b2://{b2cfg['bucket']}/{key_name} …")
                url = upload_to_backblaze_b2(b2cfg, img_path, key_name)
                urls.append(url)
                log(f"[Backblaze] ✅ {url}")

            elif target == "github":
                ghcfg = hosting_cfg.get("github")
                if not ghcfg:
                    raise RuntimeError("GitHub block missing in config.yaml")
                subdir = (ghcfg.get("subdir") or "").strip("/")
                dest_rel = f"{subdir}/{base_name}" if subdir else base_name
                if not args.only_url:
                    log(
                        f"[GitHub] Committing to {ghcfg['owner']}/{ghcfg['repo']}:{ghcfg.get('branch','main')}/{dest_rel} …"
                    )
                url = upload_to_github_raw(ghcfg, img_path, dest_rel)
                urls.append(url)
                log(f"[GitHub] ✅ {url}")

        except Exception as e:
            log(f"[{target.capitalize()}] ❌ {e}")

    if urls:
        if args.only_url:
            for u in urls:
                print(u)
        else:
            log("\nPublic URL(s) ready for Threads media container:")
            for u in urls:
                print(u)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
