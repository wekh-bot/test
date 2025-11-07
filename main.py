import aiohttp
import asyncio
import base64
import re
import os
import json
import time
from datetime import datetime
import logging
import socket
from urllib.parse import urlparse

# -----------------------------------
# 基本配置
# -----------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("node-checker")

SOURCES = [
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/Flikify/Free-Node/main/v2ray.txt",
    "https://raw.githubusercontent.com/free-nodes/v2rayfree/main/v2",
    "https://raw.githubusercontent.com/free18/v2ray/main/v.txt",
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub"
]

OUTPUT_V2RAY = "v2ray.txt"
MAX_NODES = 20
CONCURRENCY = 200  # 并发数
TIMEOUT = 2.5      # 单节点最大延迟（秒）


# -----------------------------------
# 工具函数
# -----------------------------------
def decode_base64_if_needed(text: str) -> str:
    """尝试解码 Base64 内容"""
    try:
        decoded = base64.b64decode(text).decode("utf-8", errors="ignore")
        if any(proto in decoded for proto in ["vmess", "vless", "ss://", "trojan://"]):
            return decoded
    except Exception:
        pass
    return text


def extract_nodes(text: str) -> list:
    """提取 vmess/vless/ss/trojan 节点"""
    pattern = r"(vmess://[A-Za-z0-9+/=._-]+|vless://[^\s]+|ss://[^\s]+|trojan://[^\s]+)"
    return re.findall(pattern, text)


async def fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    """异步获取订阅源内容"""
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status == 200:
                logger.info(f"Fetched: {url}")
                return await resp.text()
            else:
                logger.warning(f"Failed {url} - HTTP {resp.status}")
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
    return ""


async def collect_nodes():
    """抓取所有节点"""
    async with aiohttp.ClientSession() as session:
        texts = await asyncio.gather(*[fetch_text(session, url) for url in SOURCES])

    all_nodes = []
    for content in texts:
        decoded = decode_base64_if_needed(content)
        all_nodes.extend(extract_nodes(decoded))

    all_nodes = list(set(all_nodes))  # 去重
    logger.info(f"共提取节点：{len(all_nodes)} 条")
    return all_nodes


# -----------------------------------
# 节点解析
# -----------------------------------
def parse_host_port(node: str):
    """解析节点获取 host 和 port"""
    node = node.strip()
    try:
        if node.startswith("vmess://"):
            b64 = node[len("vmess://"):]
            raw = base64.b64decode(b64 + '=' * (-len(b64) % 4))
            j = json.loads(raw.decode(errors="ignore"))
            host = j.get("add") or j.get("host")
            port = int(j.get("port", 0))
            return host, port

        if node.startswith(("vless://", "trojan://")):
            p = urlparse(node)
            return p.hostname, p.port

        if node.startswith("ss://"):
            rest = node[len("ss://"):]
            try:
                if "@" in rest:
                    # method:pass@host:port
                    after = rest.split("@", 1)[1]
                    p = urlparse("ss://" + after)
                    return p.hostname, p.port
                else:
                    dec = base64.b64decode(rest + '=' * (-len(rest) % 4)).decode(errors="ignore")
                    if "@" in dec:
                        after = dec.split("@", 1)[1]
                        p = urlparse("ss://" + after)
                        return p.hostname, p.port
            except Exception:
                return None, None

        if "://" in node:
            p = urlparse(node)
            return p.hostname, p.port

        if ":" in node:
            parts = node.split(":")
            return parts[0], int(parts[1]) if parts[1].isdigit() else None
    except Exception:
        pass
    return None, None


# -----------------------------------
# 极速真延迟检测（TCP握手）
# -----------------------------------
async def tcp_latency(host, port):
    """TCP三次握手测延迟（毫秒），失败返回 None"""
    try:
        start = time.perf_counter()
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=TIMEOUT)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        end = time.perf_counter()
        return int((end - start) * 1000)
    except Exception:
        return None


async def check_node(node: str):
    host, port = parse_host_port(node)
    if not host or not port:
        return None
    delay = await tcp_latency(host, port)
    if delay is None:
        return None
    return (node, delay)


async def test_nodes(nodes, max_nodes=20, concurrency=200):
    """并发检测节点"""
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def _wrap(node):
        async with sem:
            res = await check_node(node)
            if res:
                results.append(res)

    tasks = [asyncio.create_task(_wrap(n)) for n in nodes]
    await asyncio.gather(*tasks)
    results.sort(key=lambda x: x[1])
    return results[:max_nodes]


# -----------------------------------
# 保存结果
# -----------------------------------
def save_v2ray(nodes_with_delay):
    with open(OUTPUT_V2RAY, "w", encoding="utf-8") as f:
        f.write(f"# 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        for node, delay in nodes_with_delay:
            f.write(f"{node}  # 延迟: {delay}ms\n")
    logger.info(f"已保存 {len(nodes_with_delay)} 条可用节点到 {OUTPUT_V2RAY}")


# -----------------------------------
# 主逻辑
# -----------------------------------
async def main():
    logger.info("开始抓取订阅源...")
    all_nodes = await collect_nodes()
    if not all_nodes:
        logger.warning("未获取到任何节点")
        return

    logger.info("开始测速...")
    available_nodes = await test_nodes(all_nodes)
    if not available_nodes:
        logger.warning("无可用节点")
        return

    save_v2ray(available_nodes)
    logger.info("✅ 检测与保存完成")


if __name__ == "__main__":
    asyncio.run(main())
