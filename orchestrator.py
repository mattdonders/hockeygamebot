import os
import random
import subprocess
import time
from pathlib import Path


def main() -> None:
    """
    Multi-bot orchestrator for hockeygamebot.

    Looks for config/*.yaml (excluding *sample*),
    launches each bot with jitter, and logs to logs/.
    """

    # repo root is this file's directory
    repo_root = Path(__file__).resolve().parent
    logs_dir = repo_root / "logs"
    config_dir = repo_root / "config"
    logs_dir.mkdir(exist_ok=True)

    launch_log = logs_dir / "hgb-launch.out"

    # --- 1. Collect config files ---
    configs = [cfg for cfg in config_dir.glob("*.yaml") if "sample" not in cfg.name]

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    with launch_log.open("a") as lf:
        lf.write(
            "\n"
            "################################################################################\n"
            f"# HockeyGameBot Orchestrator Launch\n"
            f"# Timestamp: {timestamp}\n"
            f"# Host: {os.uname().nodename}\n"
            f"# Found configs: {[c.name for c in configs]}\n"
            "################################################################################\n\n"
        )

    if not configs:
        with launch_log.open("a") as lf:
            lf.write("[HGB] No config files found. Exiting orchestrator.\n")
        return

    # --- 2. Kill old bots ---
    subprocess.run(
        ["pkill", "-f", "python -m hockeygamebot"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)

    # --- 3. Launch each config ---
    for idx, cfg in enumerate(configs):
        cfg_name = cfg.name  # example: config-njd.yaml

        # Determine bot ID based on config filename
        bot_id = cfg_name.replace(".yaml", "").replace("config-", "")
        if bot_id == "config":
            bot_id = "default"

        out_log = logs_dir / f"hgb-{bot_id}.out"
        err_log = logs_dir / f"hgb-{bot_id}.err"

        # Base command: main entry is hockeygamebot.py (module)
        cmd = [
            "python",
            "-m",
            "hockeygamebot",
        ]

        # Only pass --config if not legacy config.yaml
        if cfg_name != "config.yaml":
            cmd += ["--config", f"config/{cfg_name}"]

        # Environment
        env = os.environ.copy()
        env["HOCKEYBOT_MODE"] = "prod"

        # Spawn detached process
        out_f = out_log.open("a")
        err_f = err_log.open("a")

        proc = subprocess.Popen(
            cmd,
            cwd=repo_root,
            stdout=out_f,
            stderr=err_f,
            stdin=subprocess.DEVNULL,
            env=env,
        )

        with launch_log.open("a") as lf:
            lf.write(f"[HGB] Started bot '{bot_id}' | Config: {cfg_name} | PID: {proc.pid}\n")

        # Jitter between launches
        if idx < len(configs) - 1:
            sleep_time = random.randint(30, 60)
            with launch_log.open("a") as lf:
                lf.write(f"[HGB] Sleeping {sleep_time}s before next bot...\n")
            time.sleep(sleep_time)

    with launch_log.open("a") as lf:
        lf.write(f"[HGB] Launched {len(configs)} bots successfully.\n")


if __name__ == "__main__":
    main()
