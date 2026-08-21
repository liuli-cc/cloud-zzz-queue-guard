#!/usr/bin/env python3
"""macOS / Windows 通用版云·绝区零排队监测窗口。

用 Tkinter 提供桌面窗口，同时在一个后台线程里跟随云·绝区零进程，
读取客户端 SQLite 日志中的排队状态。排队成功且当前网络被判断为热点时，
会播放系统提示音。
"""

from __future__ import annotations

import json
import argparse
import logging
import os
import pathlib
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any

try:
    import tkinter as tk
except ImportError:
    tk = None

try:
    import winsound
except ImportError:
    winsound = None


def runtime_dir() -> pathlib.Path:
    if sys.platform == "darwin":
        base = pathlib.Path.home() / "Library/Application Support/CloudZZZQueueMonitor"
    elif getattr(sys, "frozen", False):
        base = pathlib.Path(sys.executable).resolve().parent
    else:
        base = pathlib.Path(__file__).resolve().parent
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return base
    except OSError:
        fallback = pathlib.Path(
            os.environ.get("LOCALAPPDATA", os.environ.get("APPDATA", pathlib.Path.home()))
        )
        fallback = fallback / "CloudZZZQueueMonitor"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


BASE_DIR = runtime_dir()
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
STATE_FILE = STATE_DIR / "status.json"
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "app_process_keywords": [
        "CloudGame.exe",
        "云绝区零",
        "cloudgame",
    ],
    "log_db_path": "auto",
    "poll_interval_seconds": 1.0,
    "idle_check_seconds": 2.0,
    "queue_success_statuses": ["FINISHED"],
    "queue_waiting_statuses": ["QUEUEING", "QUEUED"],
    "hotspot_gateways": [
        "172.20.10.1",
        "192.168.43.1",
        "192.168.137.1",
        "192.168.42.129",
    ],
    "hotspot_gateway_prefixes": [
        "172.20.10.",
        "192.168.43.",
        "192.168.137.",
        "192.168.42.",
    ],
    "hotspot_ssid_keywords": [
        "iphone",
        "ipad",
        "oppo",
        "vivo",
        "redmi",
        "xiaomi",
        "huawei",
        "honor",
        "oneplus",
        "samsung",
        "realme",
        "meizu",
        "热点",
        "手机",
    ],
    "sound_repeat": 3,
    "require_hotspot": False,
}


def load_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            user_cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(user_cfg, dict):
                cfg.update(user_cfg)
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("queue_guard")
    log.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_DIR / "guard.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    log.handlers.clear()
    log.addHandler(handler)
    return log


def run_cmd(args: list[str], timeout: float = 8.0) -> str:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=creationflags,
        )
        return result.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def is_cloud_game_running(cfg: dict[str, Any]) -> bool:
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["pgrep", "-f", "CloudGame.app/CloudGame"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    keywords = [str(x).lower() for x in cfg.get("app_process_keywords", [])]
    for keyword in keywords:
        out = run_cmd(["tasklist", "/FI", f"IMAGENAME eq {keyword}"], timeout=5)
        if keyword.lower() in out.lower():
            return True

    ps = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -match 'CloudGame|YunJueQuLing|绝区零' -or "
        "$_.CommandLine -match 'CloudGame|绝区零' } | "
        "Select-Object -First 1 -ExpandProperty Name"
    )
    out = run_cmd(["powershell", "-NoProfile", "-Command", ps], timeout=8)
    return bool(out.strip())


def has_plat_cloudgame_table(path: pathlib.Path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=2)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return any(row[0] == "plat_cloudgame" for row in rows)
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def process_install_dirs() -> list[pathlib.Path]:
    if sys.platform != "win32":
        return []
    ps = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -match 'CloudGame|YunJueQuLing|绝区零' -and $_.ExecutablePath } | "
        "Select-Object -ExpandProperty ExecutablePath -Unique"
    )
    out = run_cmd(["powershell", "-NoProfile", "-Command", ps], timeout=8)
    dirs: list[pathlib.Path] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        path = pathlib.Path(line.strip())
        if path.exists():
            dirs.append(path.parent)
            dirs.append(path.parent.parent)
    return dirs


def discover_log_db() -> pathlib.Path | None:
    if sys.platform == "darwin":
        known = (
            pathlib.Path.home()
            / "Library/Containers/com.miHoYo.cloudgames.Nap"
            / "Data/Library/Application Support/kibana/log.db"
        )
        if known.exists() and has_plat_cloudgame_table(known):
            return known
        return None

    env = os.environ
    roots: list[pathlib.Path] = []
    for key in ("LOCALAPPDATA", "APPDATA", "PROGRAMDATA"):
        value = env.get(key)
        if value:
            roots.append(pathlib.Path(value))
    documents = env.get("USERPROFILE")
    if documents:
        roots.append(pathlib.Path(documents) / "Documents")
    roots.extend(process_install_dirs())

    pruned = {
        "node_modules",
        ".git",
        "__pycache__",
        "Microsoft",
        "Packages",
        "Temp",
        "Cache",
        "caches",
        "CrashReports",
    }
    file_names = {"log.db", "kibana_log.db", "cloudgame_log.db"}

    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirpath_obj = pathlib.Path(dirpath)
            try:
                depth = len(dirpath_obj.relative_to(root).parts)
            except ValueError:
                depth = 0
            if depth > 10:
                dirnames[:] = []
                continue
            dirnames[:] = [
                name
                for name in dirnames
                if name.lower() not in pruned and not name.startswith(".")
            ]
            for filename in filenames:
                if filename.lower() in file_names or "kibana" in filename.lower():
                    candidate = dirpath_obj / filename
                    if has_plat_cloudgame_table(candidate):
                        return candidate
    return None


def resolve_log_db(cfg: dict[str, Any]) -> pathlib.Path | None:
    configured = cfg.get("log_db_path", "auto")
    if configured and str(configured).lower() != "auto":
        path = pathlib.Path(str(configured)).expanduser()
        if path.exists():
            return path
    if sys.platform == "darwin":
        return discover_log_db()
    return discover_log_db()


def snapshot_log_db(source: pathlib.Path) -> pathlib.Path | None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_dir = STATE_DIR / "db_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_dir / source.name
    for suffix in ("", "-wal", "-shm"):
        target = pathlib.Path(str(snapshot) + suffix)
        try:
            target.unlink()
        except FileNotFoundError:
            pass

    try:
        shutil.copy2(source, snapshot)
        for suffix in ("-wal", "-shm"):
            sidecar = pathlib.Path(str(source) + suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, pathlib.Path(str(snapshot) + suffix))
        return snapshot
    except OSError:
        return None


def query_new_rows(
    db_path: pathlib.Path,
    last_id: int | None,
) -> tuple[int | None, list[tuple[int, float, str]]]:
    snapshot = snapshot_log_db(db_path)
    if snapshot is None:
        return None, []
    try:
        conn = sqlite3.connect(str(snapshot), timeout=3)
        try:
            conn.execute("PRAGMA query_only=ON")
            current_max = conn.execute(
                "SELECT MAX(id) FROM plat_cloudgame"
            ).fetchone()[0]
            if current_max is None:
                return 0, []
            if last_id is None:
                return int(current_max), []
            if current_max < last_id:
                return int(current_max), []
            rows = conn.execute(
                "SELECT id, createdAt, content FROM plat_cloudgame "
                "WHERE id > ? ORDER BY id ASC",
                (last_id,),
            ).fetchall()
            return int(current_max), [
                (int(r[0]), float(r[1]), str(r[2])) for r in rows
            ]
        finally:
            conn.close()
    except sqlite3.Error:
        return None, []


def to_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_http_info(http_info: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    start = http_info.find("Value: ")
    if start == -1:
        return info
    start += len("Value: ")
    end = http_info.rfind(";\n}")
    if end == -1:
        end = len(http_info)
    body = http_info[start:end].strip()
    if not body.startswith("{"):
        return info
    try:
        response = json.loads(body)
    except json.JSONDecodeError:
        return info
    data = response.get("data") or {}
    queue_info = data.get("queue_info") or {}
    info.update(
        {
            "ticket_status": data.get("ticket_status"),
            "finish_result": data.get("finish_result"),
            "queue_length": to_int(
                queue_info.get("queue_length") or queue_info.get("branch_queue_len")
            ),
            "queue_rank": to_int(queue_info.get("queue_rank")),
            "waiting_time_min": to_float(queue_info.get("waiting_time_min")),
            "queue_type": queue_info.get("queue_type"),
            "node_name": (
                queue_info.get("node_name")
                or queue_info.get("node_alias")
                or queue_info.get("node_id")
            ),
        }
    )
    return info


def parse_queue_row(row_id: int, content: str, cfg: dict[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = {
        "row_id": row_id,
        "source": None,
        "ticket_status": None,
        "finish_result": None,
        "queue_length": None,
        "queue_rank": None,
        "waiting_time_min": None,
        "queue_type": None,
        "queueing": False,
        "queue_success": False,
    }
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        return info
    if not isinstance(obj, dict):
        return info

    if obj.get("module_name") == "Launcher":
        match = re.search(r"queueLength：(\d+), rank: (\d+)", str(obj.get("data") or ""))
        if match:
            info.update(
                {
                    "source": "launcher",
                    "queue_length": to_int(match.group(1)),
                    "queue_rank": to_int(match.group(2)),
                    "queueing": True,
                }
            )

    http_info = obj.get("http_info")
    if isinstance(http_info, str) and http_info:
        parsed = parse_http_info(http_info)
        if parsed:
            info.update({"source": "http", **parsed})

    status = info.get("ticket_status")
    if status in cfg.get("queue_waiting_statuses", []):
        info["queueing"] = True
    if status in cfg.get("queue_success_statuses", []) or info.get("finish_result") not in (
        None,
        "",
        [],
        {},
    ):
        info["queue_success"] = True
        info["queueing"] = False
    return info


def default_gateway() -> str | None:
    if sys.platform == "darwin":
        out = run_cmd(["route", "-n", "get", "default"], timeout=5)
        for line in out.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("gateway:"):
                value = stripped.split(":", 1)[1].strip()
                return value or None
        return None

    out = run_cmd(["route", "print", "-4", "0.0.0.0"], timeout=8)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
            return parts[2]
    return None


def wifi_ssid() -> str | None:
    if sys.platform != "win32":
        return None
    out = run_cmd(["netsh", "wlan", "show", "interfaces"], timeout=8)
    match = re.search(r"SSID\s*:\s*(.+)", out)
    if match:
        return match.group(1).strip()
    return None


def is_hotspot_network(cfg: dict[str, Any]) -> bool:
    gateway = default_gateway()
    if gateway:
        gateways = {str(x) for x in cfg.get("hotspot_gateways", [])}
        prefixes = [str(x) for x in cfg.get("hotspot_gateway_prefixes", [])]
        if gateway in gateways or any(gateway.startswith(p) for p in prefixes):
            return True
    ssid = wifi_ssid()
    if ssid:
        lowered = ssid.lower()
        if any(str(k).lower() in lowered for k in cfg.get("hotspot_ssid_keywords", [])):
            return True
    return False


def network_summary(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "gateway": default_gateway(),
        "hotspot": is_hotspot_network(cfg),
        "checked_at": time.time(),
    }


def play_alert(cfg: dict[str, Any]) -> None:
    repeat = max(1, int(cfg.get("sound_repeat", 3)))
    if sys.platform == "darwin":
        sound = "/System/Library/Sounds/Glass.aiff"
        for _ in range(repeat):
            subprocess.Popen(["afplay", sound])
            time.sleep(0.8)
        subprocess.Popen(["say", "云绝区零排队成功"])
    elif winsound is not None:
        for _ in range(repeat):
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            time.sleep(0.35)
        winsound.PlaySound(
            "SystemExclamation",
            winsound.SND_ALIAS | winsound.SND_ASYNC,
        )
    else:
        print("排队成功，请回到电脑前查看。", flush=True)


def write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.time()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(tmp, STATE_FILE)


def monitor_loop(
    cfg: dict[str, Any],
    shared: dict[str, Any],
    ui_queue: "queue.Queue[dict[str, Any]]",
    stop_event: threading.Event,
) -> None:
    log = logging.getLogger("queue_guard")
    running = False
    last_id: int | None = None
    alerted = False
    cached_db: pathlib.Path | None = None
    last_db_search = 0.0

    while not stop_event.is_set():
        try:
            app_running = is_cloud_game_running(cfg)
        except Exception:
            app_running = running

        if app_running and not running:
            running = True
            last_id = None
            alerted = False
            cached_db = None
            last_db_search = 0.0
            shared.update(
                {
                    "app_running": True,
                    "queue_state": "等待排队日志",
                    "last_queue": None,
                    "last_success": None,
                    "current_network": network_summary(cfg),
                    "last_alert": None,
                    "log_error": None,
                }
            )
            log.info("检测到云·绝区零已启动，开始监测排队状态。")
            write_state(shared)
            ui_queue.put(dict(shared))

        if not app_running and running:
            running = False
            last_id = None
            alerted = False
            cached_db = None
            last_db_search = 0.0
            shared.update(
                {
                    "app_running": False,
                    "queue_state": "未运行",
                    "last_queue": None,
                    "last_success": None,
                    "last_alert": None,
                }
            )
            log.info("云·绝区零已关闭，停止排队监测。")
            write_state(shared)
            ui_queue.put(dict(shared))

        if not running:
            time.sleep(float(cfg.get("idle_check_seconds", 2.0)))
            continue

        try:
            now = time.time()
            if cached_db is not None and cached_db.exists():
                db_path = cached_db
            elif now - last_db_search >= 5.0:
                db_path = resolve_log_db(cfg)
                last_db_search = now
            else:
                db_path = None
            if db_path is None:
                shared["log_error"] = "未找到云绝区零排队日志数据库"
                ui_queue.put(dict(shared))
                time.sleep(float(cfg.get("poll_interval_seconds", 1.0)))
                continue
            cached_db = db_path
            shared["log_error"] = None

            current_max, rows = query_new_rows(db_path, last_id)
            if current_max is not None:
                if last_id is None:
                    last_id = current_max
                else:
                    for row_id, _, content in rows:
                        info = parse_queue_row(row_id, content, cfg)
                        if info.get("queue_success"):
                            shared["queue_state"] = "排队成功"
                            shared["last_success"] = info
                            summary = network_summary(cfg)
                            shared["current_network"] = summary
                            if not alerted:
                                if summary["hotspot"] or not cfg.get("require_hotspot", False):
                                    log.info("排队成功，播放提示音。")
                                    play_alert(cfg)
                                    shared["last_alert"] = {
                                        "time": time.time(),
                                        "reason": "queue_success",
                                    }
                                else:
                                    log.info("排队成功，当前网络不是热点，不播放提示音。")
                                    shared["last_alert"] = {
                                        "time": time.time(),
                                        "reason": "queue_success_but_not_hotspot",
                                    }
                                alerted = True
                        elif info.get("queueing"):
                            shared["queue_state"] = "排队中"
                            if info.get("source") == "http" or shared.get("last_queue") is None:
                                shared["last_queue"] = info
                            alerted = False
                            log.info(
                                "排队中：rank=%s length=%s waiting_min=%s",
                                info.get("queue_rank"),
                                info.get("queue_length"),
                                info.get("waiting_time_min"),
                            )
                    last_id = current_max
                shared["current_network"] = network_summary(cfg)
                write_state(shared)
                ui_queue.put(dict(shared))
        except Exception as exc:
            log.exception("读取排队日志失败")
            shared["log_error"] = str(exc)
            ui_queue.put(dict(shared))

        time.sleep(float(cfg.get("poll_interval_seconds", 1.0)))


def make_window(shared: dict[str, Any], ui_queue: "queue.Queue[dict[str, Any]]") -> tk.Tk:
    root = tk.Tk()
    root.title("云·绝区零排队监测")
    root.geometry("460x500")
    root.resizable(False, False)
    root.configure(bg="#F3F6F9")

    font_family = "Microsoft YaHei UI"

    def label(
        parent: tk.Widget,
        text: str,
        size: int,
        weight: str = "normal",
        color: str = "#111827",
        anchor: str = "w",
    ) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            font=(font_family, size, weight),
            bg=parent["bg"],
            fg=color,
            anchor=anchor,
            padx=0,
            pady=0,
        )

    def card(x: int, y: int, w: int, h: int) -> tk.Frame:
        frame = tk.Frame(root, bg="#FFFFFF", highlightthickness=1, highlightbackground="#E5E7EB")
        frame.place(x=x, y=y, width=w, height=h)
        return frame

    title = label(root, "云·绝区零排队监测", 22, "bold", "#111827")
    title.place(x=24, y=20)

    app_pill = tk.Label(
        root,
        text="未运行",
        font=(font_family, 13, "bold"),
        fg="#FFFFFF",
        bg="#9CA3AF",
    )
    app_pill.place(x=310, y=24, width=126, height=30)

    queue_card = card(20, 70, 420, 80)
    queue_state = label(queue_card, "等待数据", 30, "bold", "#111827")
    queue_state.place(x=16, y=28, width=250, height=38)
    queue_detail = label(queue_card, "正在读取后台状态", 13, "normal", "#6B7280")
    queue_detail.place(x=16, y=6, width=388, height=20)

    metric_titles = ["前方人数", "总排队人数", "预计等待"]
    metric_cards: list[tuple[tk.Frame, tk.Label, tk.Label]] = []
    for i, title_text in enumerate(metric_titles):
        x = 20 + i * 144
        frame = card(x, 162, 132, 84)
        title = label(frame, title_text, 12, "normal", "#6B7280", "center")
        title.place(x=8, y=58, width=116, height=16)
        value = label(frame, "—", 26, "bold", "#111827", "center")
        value.place(x=8, y=20, width=116, height=32)
        metric_cards.append((frame, title, value))

    network_card = card(20, 258, 420, 78)
    network_title = label(network_card, "当前网络", 12, "normal", "#6B7280")
    network_title.place(x=16, y=54, width=388, height=16)
    network_value = label(network_card, "尚未获取", 18, "bold", "#111827")
    network_value.place(x=16, y=24, width=220, height=24)
    gateway_value = label(network_card, "", 13, "normal", "#6B7280")
    gateway_value.place(x=230, y=24, width=174, height=20)

    alert_card = card(20, 348, 420, 78)
    alert_title = label(alert_card, "提醒状态", 12, "normal", "#6B7280")
    alert_title.place(x=16, y=54, width=220, height=16)
    alert_value = label(alert_card, "等待排队成功", 14, "normal", "#6B7280")
    alert_value.place(x=16, y=24, width=260, height=20)
    updated_value = label(alert_card, "", 13, "normal", "#9CA3AF", "e")
    updated_value.place(x=280, y=24, width=124, height=18)

    footer = label(root, "后台跟随云绝区零自动监测", 11, "normal", "#9CA3AF", "w")
    footer.place(x=24, y=448, width=412, height=20)

    def apply_status(status: dict[str, Any]) -> None:
        app_running = bool(status.get("app_running"))
        app_pill.configure(
            text="运行中" if app_running else "未运行",
            bg="#10B981" if app_running else "#9CA3AF",
        )

        state = status.get("queue_state") or "未知"
        queue_state.configure(text=state)
        if state == "排队中":
            queue_state.configure(fg="#D97706")
            queue_detail.configure(text="正在排队，耐心等待进入")
        elif state == "排队成功":
            queue_state.configure(fg="#059669")
            queue_detail.configure(text="已进入游戏，可以开始游玩")
        elif state == "等待排队日志":
            queue_state.configure(fg="#2563EB")
            queue_detail.configure(text=status.get("log_error") or "等待客户端写入排队信息")
        else:
            queue_state.configure(fg="#111827")
            queue_detail.configure(text="当前没有排队任务")

        last_queue = status.get("last_queue") or {}
        metric_cards[0][2].configure(text=last_queue.get("queue_rank") or "—")
        metric_cards[1][2].configure(text=last_queue.get("queue_length") or "—")
        wait = last_queue.get("waiting_time_min")
        metric_cards[2][2].configure(
            text=(
                f"{float(wait):.1f} 分"
                if isinstance(wait, (int, float))
                else str(wait or "—")
            )
        )

        network = status.get("current_network") or {}
        if network:
            hotspot = bool(network.get("hotspot"))
            network_value.configure(
                text="手机热点" if hotspot else "Wi-Fi / 其他网络",
                fg="#059669" if hotspot else "#2563EB",
            )
            gateway_value.configure(text=f"网关 {network.get('gateway') or '—'}")
        else:
            network_value.configure(text="尚未获取", fg="#6B7280")
            gateway_value.configure(text="")

        alert = status.get("last_alert") or {}
        reason = alert.get("reason") or ""
        if reason == "queue_success_on_hotspot":
            alert_value.configure(text="排队成功，已播放提醒声音", fg="#059669")
        elif reason == "queue_success_but_not_hotspot":
            alert_value.configure(text="排队成功，非热点未播放声音", fg="#6B7280")
        else:
            alert_value.configure(text="等待排队成功", fg="#6B7280")

        updated = status.get("updated_at")
        if isinstance(updated, (int, float)):
            updated_value.configure(
                text=time.strftime("%H:%M:%S", time.localtime(float(updated)))
            )

    def poll_ui() -> None:
        try:
            while True:
                apply_status(ui_queue.get_nowait())
        except queue.Empty:
            pass
        root.after(200, poll_ui)

    root.after(200, poll_ui)
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description="云·绝区零排队监测")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="仅运行后台监测，不显示 Tk 窗口；供 macOS 原生灵动岛使用",
    )
    args = parser.parse_args()

    log = setup_logging()
    cfg = load_config()
    shared: dict[str, Any] = {
        "app_running": False,
        "queue_state": "未运行",
        "last_queue": None,
        "last_success": None,
        "current_network": None,
        "last_alert": None,
        "log_error": None,
    }
    ui_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
    stop_event = threading.Event()

    if args.headless:
        thread = threading.Thread(
            target=monitor_loop,
            args=(cfg, shared, ui_queue, stop_event),
            daemon=False,
        )
        thread.start()
        try:
            thread.join()
        except KeyboardInterrupt:
            stop_event.set()
        return 0

    if tk is None:
        log.error("当前 Python 环境没有 Tkinter，无法显示窗口。")
        return 1

    thread = threading.Thread(
        target=monitor_loop,
        args=(cfg, shared, ui_queue, stop_event),
        daemon=True,
    )
    thread.start()

    root = make_window(shared, ui_queue)
    try:
        root.mainloop()
    finally:
        stop_event.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
