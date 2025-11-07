#!/usr/bin/env python3
"""
真实代理测速（基于 xray/v2ray-core）
步骤：
 1. 解析节点（vmess/vless/trojan/ss）
 2. 为单条节点生成 xray 简单 config（outbound = 节点，inbound = 本地 socks5）
 3. 启动 xray 子进程，等待本地 socks 监听
 4. 用 curl 通过 socks5 本地代理请求外网目标并测 time_total
 5. 记录延迟，停止 xray，继续下一个
 6. 并发控制、保存前 MAX_NODES 到 v2ray.txt
"""

import asyncio
import base64
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from urllib.parse import urlparse

# config
SOURCES = [
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/Flikify/Free-Node/main/v2ray.txt",
    "https://raw.githubusercontent.com/free-nodes/v2rayfree/main/v2",
    "https://raw.githubusercontent.com/free18/v2ray/main/v.txt",
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub"
]
OUTPUT_V2RAY = "v2ray.txt"
MAX_NODES = 20
CONCURRENCY = 4           # 同时测试多少个节点（xray 进程）
XRAY_ZIP_URL = "https://github.com/xtls/xray-core/releases/latest/download/xray-linux-64.zip"
XRAY_BIN = "./xray"       # 解压后放这里
TEST_TARGET = "https://www.google.com/generate_204"
CURL_TIMEOUT = 8         # curl 最大超时（秒）
XRAY_START_WAIT = 0.8    # 启动 xray 后等待多少秒再测试（给 xray 建立监听时间）
TMP_DIR = "tmp_xray"


# ---------------- utilities ----------------
def ensure_xray():
    """下载并解压 xray（只在本地或 CI 第一次运行时）"""
    if os.path.exists(XRAY_BIN) and os.access(XRAY_BIN, os.X_OK):
        return XRAY_BIN

    os.makedirs("bin", exist_ok=True)
    zip_path = "xray.zip"
    # 下载 zip
    print("Downloading xray...")
    cmd = ["curl", "-L", XRAY_ZIP_URL, "-o", zip_path]
    subprocess.check_call(cmd)
    # 解压到 bin/
    print("Unzipping...")
    subprocess.check_call(["unzip", "-o", zip_path, "-d", "bin"])
    # 寻找 xray 可执行文件
    candidate = None
    for root, _, files in os.walk("bin"):
        for f in files:
            if f == "xray" or f == "xray.exe":
                candidate = os.path.join(root, f)
                break
        if candidate:
            break
    if not candidate:
        raise RuntimeError("xray binary not found inside zip")
    shutil.copy(candidate, XRAY_BIN)
    os.chmod(XRAY_BIN, 0o755)
    print("xray ready:", XRAY_BIN)
    return XRAY_BIN


import aiohttp, asyncio
async def fetch_text(session, url):
    try:
        async with session.get(url, timeout=20) as r:
            if r.status == 200:
                return await r.text()
    except Exception:
        return ""
    return ""


def decode_base64_if_needed(text: str) -> str:
    try:
        decoded = base64.b64decode(text).decode("utf-8", errors="ignore")
        if any(proto in decoded for proto in ("vmess", "vless", "trojan", "ss://")):
            return decoded
    except Exception:
        pass
    return text


def extract_nodes(text: str):
    pattern = r"(vmess://[A-Za-z0-9+/=._-]+|vless://[^\s]+|ss://[^\s]+|trojan://[^\s]+)"
    return re.findall(pattern, text)


async def collect_all_nodes():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_text(session, url) for url in SOURCES]
        texts = await asyncio.gather(*tasks)
    nodes = []
    for t in texts:
        t2 = decode_base64_if_needed(t)
        nodes += extract_nodes(t2)
    # uniq
    nodes = list(dict.fromkeys(nodes))
    print(f"collected {len(nodes)} nodes")
    return nodes


# ---------------- parse node -> xray outbound config ----------------
def parse_vmess(node: str):
    b64 = node[len("vmess://"):]
    raw = base64.b64decode(b64 + '=' * (-len(b64) % 4))
    j = json.loads(raw.decode(errors="ignore"))
    # typical fields: add, port, id, alterId, net, type, host, path, tls
    return j

def parse_host_port_simple(node: str):
    """fallback parsing host:port"""
    if "://" in node:
        p = urlparse(node)
        return p.hostname, p.port
    if ":" in node:
        a = node.split(":")
        return a[0], int(a[1])
    return None, None

def make_xray_config_for_node(node: str, listen_port: int):
    """
    Construct minimal xray config JSON for a single outbound node and an inbound socks listener on listen_port.
    Supports vmess, vless, trojan, ss (best-effort).
    """
    outbound = None
    tag = "out-1"
    # vmess
    if node.startswith("vmess://"):
        j = parse_vmess(node)
        # build vmess outbound
        vm = {
            "v": j.get("v", "2"),
            "ps": j.get("ps") or "",
            "add": j.get("add") or j.get("host"),
            "port": int(j.get("port", 0) or 0),
            "id": j.get("id"),
            "aid": str(j.get("aid", j.get("alterId", 0))),
            "net": j.get("net", "tcp"),
            "type": j.get("type", "none"),
            "host": j.get("host", ""),
            "path": j.get("path", ""),
            "tls": j.get("tls", "")
        }
        outbound = {
            "protocol": "vmess",
            "settings": {"vnext":[{"address": vm["add"], "port": vm["port"], "users":[{"id": vm["id"], "alterId": int(vm["aid"] or 0), "security":"auto"}]}]},
            "streamSettings": {}
        }
        # stream settings minimal:
        net = vm["net"]
        ss = {}
        if net == "ws":
            ss["network"] = "ws"
            ss["wsSettings"] = {"path": vm.get("path",""), "headers":{"Host": vm.get("host","")}}
        elif net == "h2":
            ss["network"] = "http"
        else:
            ss["network"] = "tcp"
        if vm.get("tls"):
            ss["security"] = "tls"
        if ss:
            outbound["streamSettings"] = ss

    elif node.startswith("vless://"):
        p = urlparse(node)
        host = p.hostname
        port = p.port
        query = p.query
        # attempt to read ?type=ws&security=tls&path=...
        qs = {}
        for kv in query.split("&"):
            if "=" in kv:
                k,v = kv.split("=",1)
                qs[k]=v
        user = p.username
        outbound = {
            "protocol": "vless",
            "settings": {"vnext":[{"address": host, "port": port or 443, "users":[{"id": user or "", "encryption":"none"}]}]},
            "streamSettings": {}
        }
        if qs.get("type") == "ws":
            outbound["streamSettings"]["network"] = "ws"
            outbound["streamSettings"]["wsSettings"] = {"path": qs.get("path",""), "headers": {"Host": qs.get("host","")}}
        if qs.get("security") == "tls":
            outbound["streamSettings"]["security"] = "tls"

    elif node.startswith("trojan://"):
        p = urlparse(node)
        host = p.hostname
        port = p.port or 443
        passwd = p.username
        outbound = {
            "protocol": "trojan",
            "settings": {"servers": [{"address": host, "port": port, "password": passwd}]},
            "streamSettings": {}
        }
        qs = p.query
        if "type=ws" in qs:
            outbound["streamSettings"]["network"]="ws"

    elif node.startswith("ss://"):
        # best-effort parse; many ss forms exist - if cannot parse, fallback to tcp connect test only
        rest = node[len("ss://"):]
        host, port = None, None
        if "@" in rest and "/" not in rest:
            # form method:pass@host:port
            try:
                tail = rest.split("@",1)[1]
                p = urlparse("ss://"+tail)
                host, port = p.hostname, p.port
            except Exception:
                host, port = None, None
        else:
            try:
                dec = base64.b64decode(rest + '=' * (-len(rest) % 4)).decode(errors="ignore")
                if "@" in dec:
                    tail = dec.split("@",1)[1]
                    p = urlparse("ss://"+tail)
                    host, port = p.hostname, p.port
            except Exception:
                host, port = None, None
        if host:
            outbound = {
                "protocol":"shadowsocks",
                "settings":{"servers":[{"address":host,"port":port or 8388,"method":"aes-128-gcm","password":""}]},
                "streamSettings":{}
            }

    # Fallback: if outbound missing, we still return None meaning cannot create full xray outbound
    if not outbound:
        return None

    # minimal config structure
    cfg = {
        "log": {"loglevel":"none"},
        "inbounds":[
            {"port": listen_port, "protocol":"socks", "settings": {"auth": "noauth", "udp": True}, "sniffing":{"enabled":False}}
        ],
        "outbounds":[
            outbound,
            {"protocol":"freedom","tag":"direct"}
        ],
        "routing":{"domainStrategy":"AsIs"}
    }
    return cfg


def find_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_xray_with_config(cfg_json, workdir):
    cfg_path = os.path.join(workdir, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg_json, f)
    xbin = ensure_xray()
    env = os.environ.copy()
    # start xray pointing to cfg_path
    p = subprocess.Popen([xbin, "-c", cfg_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    return p


def stop_process(p):
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except Exception:
        try:
            p.terminate()
        except Exception:
            pass
    p.wait(timeout=5)


def curl_via_socks(local_socks_port, timeout_s=CURL_TIMEOUT):
    # use curl to measure total time. returns float seconds or None
    cmd = [
        "curl", "-s", "-o", "/dev/null",
        "--socks5-hostname", f"127.0.0.1:{local_socks_port}",
        "--max-time", str(timeout_s),
        "-w", "%{time_total}",
        TEST_TARGET
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=timeout_s+2)
        t = float(out.decode().strip())
        return t
    except Exception:
        return None


async def test_single_node_real(node: str):
    """Start xray, test via curl, record time (s) and return (node, ms) or None"""
    # create temp dir per node
    workdir = tempfile.mkdtemp(prefix="xray_")
    try:
        port = find_free_port()
        cfg = make_xray_config_for_node(node, port)
        if not cfg:
            return None
        p = start_xray_with_config(cfg, workdir)
        # wait small time for xray to be ready
        await asyncio.sleep(XRAY_START_WAIT)
        # run curl
        t = curl_via_socks(port)
        # stop xray
        stop_process(p)
        if t is None:
            return None
        return (node, int(t*1000))
    except Exception:
        try:
            p and stop_process(p)
        except Exception:
            pass
        return None
    finally:
        try:
            shutil.rmtree(workdir)
        except Exception:
            pass


async def worker(queue, results):
    while True:
        node = await queue.get()
        if node is None:
            queue.task_done()
            break
        res = await test_single_node_real(node)
        if res:
            print("OK:", res[1], "ms", res[0][:80])
            results.append(res)
        else:
            print("BAD:", node[:80])
        queue.task_done()


async def main():
    nodes = await collect_all_nodes()
    if not nodes:
        print("No nodes collected")
        return

    # concurrency queue
    q = asyncio.Queue()
    for n in nodes:
        q.put_nowait(n)
    # add stop markers for workers
    results = []
    workers = []
    for _ in range(min(CONCURRENCY, len(nodes))):
        workers.append(asyncio.create_task(worker(q, results)))

    # add termination markers after queue empties
    # we will wait for queue.join and then send stop
    await q.join()
    for _ in workers:
        q.put_nowait(None)
    await asyncio.gather(*workers)

    # sort and save top MAX_NODES
    results.sort(key=lambda x: x[1])
    chosen = results[:MAX_NODES]
    with open(OUTPUT_V2RAY, "w", encoding="utf-8") as f:
        f.write(f"# 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        for node, ms in chosen:
            f.write(f"{node}  # 延迟: {ms}ms\n")
    print("Saved", len(chosen), "nodes to", OUTPUT_V2RAY)


if __name__ == "__main__":
    asyncio.run(main())
