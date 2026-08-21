#!/usr/bin/env python3
"""云·绝区零排队监测与热点提醒工具。

程序会作为常驻的轻量监督进程运行：
1. 检测云·绝区零客户端是否正在运行；
2. 客户端打开后开始读取米哈游客户端写入的排队日志数据库；
3. 识别 QUEUEING/FINISHED 等排队状态；
4. 排队成功时，若当前默认网络是热点则播放声音提醒。
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import pathlib
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any


PROJECT_DIR = pathlib.Path(__file__).resolve().parent
STATE_DIR = PROJECT_DIR / "state"
STATE_FILE = STATE_DIR / "status.json"
SNAPSHOT_DIR = STATE_DIR / "db_snapshot"

DEFAULT_CONFIG: dict[str, Any] = {
    "app_process_pattern": "CloudGame.app/CloudGame",
    "log_db_path": str(
        pathlib.Path.home()
        / "Library/Containers/com.miHoYo.cloudgames.Nap"
        / "Data/Library/Application Support/kibana/log.db"
    ),
    "poll_interval_seconds": 1.0,
    "idle_check_seconds": 2.0,
    "queue_success_statuses": ["FINISHED"],
    "queue_waiting_statuses": ["QUEUEING", "QUEUED"],
    "hotspot_interfaces": ["en0"],
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
        "samsung galaxy",
        "realme",
        "meizu",
        "热点",
        "手机",
    ],
    "sound_file": "/System/Library/Sounds/Glass.aiff",
    "sound_repeat": 3,
    "also_say": True,
    "require_hotspot": False,
    "island_app_path": str(PROJECT_DIR / "云绝区零排队提醒.app"),
}


def load_config(path: pathlib.Path) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path.exists():
        try:
            user_cfg = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(user_cfg, dict):
                cfg.update(user_cfg)
        except (OSError, json.JSONDecodeError) as exc:
            logging.getLogger("guard").warning("读取配置失败，使用默认配置: %s", exc)
    return cfg


def launch_island_app(cfg: dict[str, Any], log: logging.Logger) -> None:
    """Launch the UI only while CloudGame is running.

    The LaunchAgent remains the lightweight process watcher. The native island
    receives --external-core so it does not start a second monitor process.
    """
    if sys.platform != "darwin":
        return
    app_path = pathlib.Path(str(cfg.get("island_app_path") or "")).expanduser()
    if not app_path.exists():
        log.warning("未找到绝区零灵动岛 App：%s", app_path)
        return
    result = run_cmd(
        [
            "open",
            "-g",
            "-a",
            str(app_path),
            "--args",
            "--external-core",
            "--state-file",
            str(STATE_FILE),
        ],
        timeout=5,
    )
    if result.returncode != 0:
        log.warning("启动绝区零灵动岛失败：%s", result.stdout.strip())


def stop_island_app(log: logging.Logger) -> None:
    """Quit the native island when CloudGame exits."""
    if sys.platform != "darwin":
        return
    result = run_cmd(
        [
            "osascript",
            "-e",
            'tell application id "com.liuli.cloud-zzz-queue-monitor" to quit',
        ],
        timeout=5,
    )
    if result.returncode != 0 and "not running" not in result.stdout.lower():
        log.debug("关闭绝区零灵动岛时返回：%s", result.stdout.strip())


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    root.handlers.clear()
    root.addHandler(handler)


def atomic_write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def run_cmd(args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )


def is_cloud_game_running(pattern: str) -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def snapshot_log_db(db_path: str) -> pathlib.Path | None:
    """把米哈游客户端容器内的 SQLite 日志复制到本程序可写目录。

    LaunchAgent 进程通常没有写入 App Container 的权限，而 SQLite 读取 WAL
    时可能需要创建 shm 文件。把主库和 WAL/SHM 一起复制到 state/db_snapshot
    后，本程序就能安全地读取最新日志。
    """

    source = pathlib.Path(db_path).expanduser()
    if not source.exists():
        return None

    snapshot = SNAPSHOT_DIR / source.name
    snapshot_wal = pathlib.Path(str(snapshot) + "-wal")
    snapshot_shm = pathlib.Path(str(snapshot) + "-shm")
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    for path in (snapshot, snapshot_wal, snapshot_shm):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    main_tmp = SNAPSHOT_DIR / (source.name + ".main.tmp")
    shutil.copy2(source, main_tmp)
    os.replace(main_tmp, snapshot)

    for suffix, dest in (("-wal", snapshot_wal), ("-shm", snapshot_shm)):
        sidecar = pathlib.Path(str(source) + suffix)
        if sidecar.exists():
            sidecar_tmp = SNAPSHOT_DIR / (source.name + suffix + ".tmp")
            shutil.copy2(sidecar, sidecar_tmp)
            os.replace(sidecar_tmp, dest)

    return snapshot


def query_db_rows(
    db_path: str,
    after_id: int | None = None,
) -> tuple[int | None, list[tuple[int, float, str]]]:
    """返回 (当前最大 id, id 大于 after_id 的行)。

    after_id 为 None 时只建立基线，不返回旧日志。
    """

    snapshot = snapshot_log_db(db_path)
    if snapshot is None:
        return None, []

    conn = sqlite3.connect(str(snapshot), timeout=3)
    try:
        conn.execute("PRAGMA query_only=ON")
        current_max = conn.execute("SELECT MAX(id) FROM plat_cloudgame").fetchone()[0]
        if current_max is None:
            return 0, []

        if after_id is None:
            return int(current_max), []

        if current_max < after_id:
            # 数据库可能被应用重建/轮换，重新建立基线。
            return int(current_max), []

        rows = conn.execute(
            "SELECT id, createdAt, content FROM plat_cloudgame "
            "WHERE id > ? ORDER BY id ASC",
            (after_id,),
        ).fetchall()
        return int(current_max), [(int(r[0]), float(r[1]), str(r[2])) for r in rows]
    except sqlite3.Error:
        return None, []
    finally:
        conn.close()


def query_latest_rows(db_path: str, limit: int = 10) -> list[tuple[int, float, str]]:
    snapshot = snapshot_log_db(db_path)
    if snapshot is None:
        return []

    conn = sqlite3.connect(str(snapshot), timeout=3)
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(
            "SELECT id, createdAt, content FROM plat_cloudgame "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(int(r[0]), float(r[1]), str(r[2])) for r in reversed(rows)]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def parse_http_info(http_info: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    if "Value: " not in http_info:
        return info

    start = http_info.find("Value: ") + len("Value: ")
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
    info["ticket_status"] = data.get("ticket_status")
    info["finish_result"] = data.get("finish_result")

    queue_info = data.get("queue_info") or {}
    info["queue_type"] = queue_info.get("queue_type")
    info["node_name"] = (
        queue_info.get("node_name")
        or queue_info.get("node_alias")
        or queue_info.get("node_id")
    )
    info["query_interval"] = to_int(queue_info.get("query_interval"))
    info["queue_length"] = to_int(
        queue_info.get("queue_length") or queue_info.get("branch_queue_len")
    )
    info["queue_rank"] = to_int(queue_info.get("queue_rank"))
    info["waiting_time_min"] = to_float(queue_info.get("waiting_time_min"))
    return info


def to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_queue_row(
    row_id: int,
    created_at: float,
    content: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "row_id": row_id,
        "timestamp": created_at,
        "source": None,
        "ticket_status": None,
        "finish_result": None,
        "queue_length": None,
        "queue_rank": None,
        "waiting_time_min": None,
        "queue_type": None,
        "node_name": None,
        "queueing": False,
        "queue_success": False,
    }

    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        return info

    if not isinstance(obj, dict):
        return info

    module_name = obj.get("module_name")
    task_name = obj.get("taskName")
    data = obj.get("data") or ""
    http_info = obj.get("http_info") or ""

    if module_name == "Launcher" and isinstance(data, str):
        match = re.search(r"\[Queuing\] queueLength：(\d+), rank: (\d+)", data)
        if match:
            info.update(
                {
                    "source": "launcher",
                    "task_name": task_name,
                    "queue_length": to_int(match.group(1)),
                    "queue_rank": to_int(match.group(2)),
                    "queueing": True,
                }
            )

    if isinstance(http_info, str) and http_info:
        http_parsed = parse_http_info(http_info)
        if http_parsed:
            info.update({"source": "http", **http_parsed})

    status = info.get("ticket_status")
    finish_result = info.get("finish_result")
    if status in cfg.get("queue_waiting_statuses", ["QUEUEING", "QUEUED"]):
        info["queueing"] = True
    if status in cfg.get("queue_success_statuses", ["FINISHED"]):
        info["queue_success"] = True
        info["queueing"] = False
    if finish_result not in (None, "", [], {}):
        info["queue_success"] = True
        info["queueing"] = False

    return info


def get_default_route() -> tuple[str | None, str | None]:
    result = run_cmd(["route", "-n", "get", "default"], timeout=3)
    gateway = None
    interface = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("gateway:"):
            gateway = stripped.split(":", 1)[1].strip() or None
        elif stripped.lower().startswith("interface:"):
            interface = stripped.split(":", 1)[1].strip() or None
    return gateway, interface


def get_wifi_ssid() -> str | None:
    try:
        result = run_cmd(["system_profiler", "SPAirPortDataType", "-json"], timeout=5)
        data = json.loads(result.stdout)
        interfaces = data.get("SPAirPortDataType", [{}])[0].get(
            "spairport_airport_interfaces", []
        )
        for interface in interfaces:
            current = interface.get("spairport_current_network_information")
            if current:
                name = current.get("_name")
                if name and name != "<redacted>":
                    return str(name)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError):
        return None
    return None


def is_hotspot_network(cfg: dict[str, Any]) -> bool:
    gateway, interface = get_default_route()
    if not gateway:
        return False

    allowed_interfaces = {str(x) for x in cfg.get("hotspot_interfaces", ["en0"])}
    if interface and allowed_interfaces and interface not in allowed_interfaces:
        return False

    gateways = {str(x) for x in cfg.get("hotspot_gateways", [])}
    prefixes = [str(x) for x in cfg.get("hotspot_gateway_prefixes", [])]
    if gateway in gateways or any(gateway.startswith(prefix) for prefix in prefixes):
        return True

    ssid = get_wifi_ssid()
    if ssid:
        lowered = ssid.lower()
        if any(str(k).lower() in lowered for k in cfg.get("hotspot_ssid_keywords", [])):
            return True
    return False


def network_summary(cfg: dict[str, Any]) -> dict[str, Any]:
    gateway, interface = get_default_route()
    hotspot = is_hotspot_network(cfg)
    return {
        "gateway": gateway,
        "interface": interface,
        "hotspot": hotspot,
        "checked_at": time.time(),
    }


def play_alert(cfg: dict[str, Any]) -> None:
    sound = str(cfg.get("sound_file") or "")
    repeat = max(1, int(cfg.get("sound_repeat", 1)))
    if sound and pathlib.Path(sound).exists():
        for _ in range(repeat):
            subprocess.Popen(["afplay", sound])
            time.sleep(0.8)
    if cfg.get("also_say"):
        subprocess.Popen(["say", "云绝区零排队成功"])


def write_status(state: dict[str, Any]) -> None:
    state["updated_at"] = time.time()
    atomic_write_json(STATE_FILE, state)


def read_status() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def test_network(cfg: dict[str, Any]) -> int:
    summary = network_summary(cfg)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["hotspot"]:
        print("判定结果：当前网络是热点")
    else:
        print("判定结果：当前网络不是热点")
    return 0


def test_log(cfg: dict[str, Any]) -> int:
    rows = query_latest_rows(cfg["log_db_path"], limit=10)
    if not rows:
        print("当前日志数据库为空。")
        return 0
    for row_id, created_at, content in rows:
        info = parse_queue_row(row_id, created_at, content, cfg)
        print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
    return 0


def run_monitor(cfg: dict[str, Any]) -> int:
    log = logging.getLogger("guard")
    running = False
    last_id: int | None = None
    alerted = False
    consecutive_errors = 0
    island_launched = False
    state: dict[str, Any] = {
        "app_running": False,
        "queue_state": "未运行",
        "last_queue": None,
        "last_event": None,
        "last_success": None,
        "current_network": None,
        "last_network": None,
        "last_alert": None,
    }

    def reset_session() -> None:
        nonlocal last_id, alerted
        last_id = None
        alerted = False

    def stop_requested(_signum: int, _frame: Any) -> None:
        nonlocal island_launched
        if island_launched:
            stop_island_app(log)
            island_launched = False
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop_requested)
    signal.signal(signal.SIGINT, stop_requested)

    while True:
        try:
            app_running = is_cloud_game_running(str(cfg["app_process_pattern"]))
        except Exception as exc:  # 进程检测失败时保持上一状态，避免误判。
            log.warning("检测客户端进程失败: %s", exc)
            app_running = running

        if app_running and not running:
            log.info("检测到云·绝区零已启动，开始监测排队状态。")
            running = True
            launch_island_app(cfg, log)
            island_launched = True
            reset_session()
            state.update(
                {
                    "app_running": True,
                    "queue_state": "等待排队日志",
                    "last_queue": None,
                    "last_event": None,
                    "last_success": None,
                    "current_network": None,
                    "last_network": None,
                    "last_alert": None,
                }
            )
            state["current_network"] = network_summary(cfg)
            write_status(state)

        if not app_running and running:
            log.info("云·绝区零已关闭，停止排队监测。")
            running = False
            if island_launched:
                stop_island_app(log)
                island_launched = False
            reset_session()
            state.update(
                {
                    "app_running": False,
                    "queue_state": "未运行",
                    "last_queue": None,
                    "last_event": None,
                    "last_success": None,
                    "current_network": None,
                    "last_network": None,
                    "last_alert": None,
                }
            )
            state["current_network"] = network_summary(cfg)
            write_status(state)

        if not running:
            time.sleep(float(cfg["idle_check_seconds"]))
            continue

        try:
            current_max, rows = query_db_rows(cfg["log_db_path"], after_id=last_id)
            if current_max is None:
                time.sleep(float(cfg["poll_interval_seconds"]))
                continue

            if last_id is None:
                last_id = current_max
            else:
                for row_id, created_at, content in rows:
                    info = parse_queue_row(row_id, created_at, content, cfg)
                    if info.get("source"):
                        state["last_event"] = info

                    if info.get("queue_success"):
                        if not alerted:
                            state["queue_state"] = "排队成功"
                            state["last_success"] = info
                            summary = network_summary(cfg)
                            state["last_network"] = summary
                            log.info(
                                "排队成功：rank=%s length=%s ticket_status=%s finish_result=%s",
                                info.get("queue_rank"),
                                info.get("queue_length"),
                                info.get("ticket_status"),
                                info.get("finish_result"),
                            )
                            if summary["hotspot"]:
                                log.info("当前网络为热点，播放提醒声音。")
                                play_alert(cfg)
                                state["last_alert"] = {
                                    "time": time.time(),
                                    "reason": "queue_success_on_hotspot",
                                }
                            elif cfg.get("require_hotspot"):
                                log.info("当前网络不是热点，按配置不播放声音。")
                                state["last_alert"] = {
                                    "time": time.time(),
                                    "reason": "queue_success_but_not_hotspot",
                                }
                            else:
                                log.info("当前未强制要求热点，播放提醒声音。")
                                play_alert(cfg)
                                state["last_alert"] = {
                                    "time": time.time(),
                                    "reason": "queue_success",
                                }
                            alerted = True
                    elif info.get("queueing"):
                        state["queue_state"] = "排队中"
                        if info.get("source") == "http" or state["last_queue"] is None:
                            state["last_queue"] = info
                        # 如果同一客户端生命周期内重新开始排队，允许下一次成功再次提醒。
                        alerted = False
                        log.info(
                            "排队中：rank=%s length=%s waiting_min=%s",
                            info.get("queue_rank"),
                            info.get("queue_length"),
                            info.get("waiting_time_min"),
                        )

                last_id = current_max
                state["current_network"] = network_summary(cfg)
                write_status(state)
                consecutive_errors = 0
        except Exception as exc:
            consecutive_errors += 1
            if consecutive_errors == 1 or consecutive_errors % 30 == 0:
                if isinstance(exc, PermissionError):
                    log.error(
                        "无法读取云·绝区零日志：%s。请在 系统设置 > 隐私与安全性 > "
                        "完全磁盘访问权限 中添加 /usr/bin/python3，然后重新运行 install.sh。",
                        exc,
                    )
                else:
                    log.exception("读取或解析排队日志失败")
            time.sleep(max(float(cfg["poll_interval_seconds"]), 5.0))
            continue

        time.sleep(float(cfg["poll_interval_seconds"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="云·绝区零排队监测与热点提醒")
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        default=PROJECT_DIR / "config.json",
        help="配置文件路径",
    )
    parser.add_argument("--test-network", action="store_true", help="测试热点判断")
    parser.add_argument("--test-log", action="store_true", help="测试排队日志解析")
    parser.add_argument("--status", action="store_true", help="显示当前状态")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.test_network:
        return test_network(cfg)
    if args.test_log:
        return test_log(cfg)
    if args.status:
        print(json.dumps(read_status(), ensure_ascii=False, indent=2, default=str))
        return 0

    setup_logging()
    return run_monitor(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
