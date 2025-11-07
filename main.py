import aiohttp
import asyncio
import base64
import re
import os
import json
import ssl
import time
from datetime import datetime
import logging
from urllib.parse import urlparse

# -----------------------------------
# 日志配置
# -----------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("node-checker")

# -----------------------------------
# 节点源列表
# -----------------------------------
SOURCES = [
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/ermaozi01/free_clash_vpn/main/subscribe/clash.yml",
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/learnhard-cn/free_proxy_ss/main/free",
    "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list_raw.txt",
    "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/sub/sub_merge.txt",
]

OUTPUT_V2RAY = "v2ray.txt"
OUTPUT_CLASH = "clash.yaml"
MAX_NODES = 20  # 只保存20个可用节点


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
    """抓取全部节点"""
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
# 检测可用性
# -----------------------------------
async def tcp_check(host: str, port: int, timeout: float = 5.0, do_ssl=False, ssl_sni=None):
    """用于检查节点端口是否开放"""
    try:
        if do_ssl:
            ssl_ctx = ssl.create_default_context()
            # 如果需要特定 SNI：
            server_hostname = ssl_sni or host
            fut = asyncio.open_connection(host=host, port=port, ssl=ssl_ctx, server_hostname=server_hostname)
        else:
            fut = asyncio.open_connection(host=host, port=port)

        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        # 连接成功，立即关闭
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


# -------------------------
# 辅助：从节点字符串解析出 host 与 port
# 返回 (host, port) 或 (None, None) 如果解析失败
# -------------------------
def parse_host_port(node: str):
    node = node.strip()
    try:
        if node.startswith("vmess://"):
            # vmess 后面通常是 base64(json)
            b64 = node[len("vmess://"):]
            try:
                raw = base64.b64decode(b64 + '=' * (-len(b64) % 4))
                j = json.loads(raw.decode(errors="ignore"))
                host = j.get("add") or j.get("host")
                port = int(j.get("port", 0))
                return host, port
            except Exception:
                return None, None

        if node.startswith("vless://") or node.startswith("trojan://"):
            # vless://id@host:port?...
            p = urlparse(node)
            host = p.hostname
            port = p.port
            return host, port

        if node.startswith("ss://"):
            # ss://base64 or ss://method:pass@host:port
            rest = node[len("ss://"):]
            # 有些 ss 是 ss://<base64>@host:port 形式，也有 ss://base64 整体含 host:port
            if "@" in rest and "/" not in rest:
                # method:pass@host:port or base64@host:port
                before_at, after_at = rest.split("@", 1)
                # after_at may include port
                try:
                    parsed = urlparse("ss://" + after_at)
                    return parsed.hostname, parsed.port
                except:
                    return None, None
            else:
                # rest may be base64 encoded "method:pass@host:port" or full "method:pass@host:port"
                try:
                    decoded = base64.b64decode(rest + '=' * (-len(rest) % 4)).decode(errors="ignore")
                    # decoded like "aes-128-gcm:password@1.2.3.4:8388"
                    if "@" in decoded:
                        after_at = decoded.split("@", 1)[1]
                        parsed = urlparse("ss://" + after_at)
                        return parsed.hostname, parsed.port
                except Exception:
                    return None, None

        # 最后尝试通用 URL 解析（fallback）
        if "://" in node:
            p = urlparse(node)
            return p.hostname, p.port

        # fallback: maybe plain host:port
        if ":" in node:
            parts = node.split(":")
            host = parts[0]
            port = int(parts[1]) if parts[1].isdigit() else None
            return host, port
    except Exception:
        return None, None

    return None, None


# -------------------------
# 检测单条节点：先 parse host:port，再做 tcp_check
# 返回 (node, delay_ms) 或 None
# -------------------------
import time
async def check_node(node: str, timeout=5.0):
    host, port = parse_host_port(node)
    if not host or not port:
        return None

    # 测试 TCP 连接
    start = time.time()
    ok = await tcp_check(host, port, timeout=timeout, do_ssl=False)
    if not ok:
        # 有些节点只在 TLS 上响应（例如 trojan/vless over TLS），尝试 TLS
        ok_tls = await tcp_check(host, port, timeout=timeout, do_ssl=True, ssl_sni=host)
        if not ok_tls:
            return None
    delay = int((time.time() - start) * 1000)  # 延迟单位：毫秒
    return node, delay


# -------------------------
# 批量并发检测（替换原 test_nodes）
# nodes: list of node strings
# 返回按延迟排序的可用节点列表 [(node, delay), ...]
# -------------------------
async def test_nodes(nodes, max_nodes=20, concurrency=200):
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def _wrap(node):
        async with sem:
            return await check_node(node, timeout=5.0)

    tasks = [asyncio.create_task(_wrap(n)) for n in nodes]
    for coro in asyncio.as_completed(tasks):
        res = await coro
        if res:
            results.append(res)

    # 排序并截取前 max_nodes
    results.sort(key=lambda x: x[1])
    return results[:max_nodes]


# -----------------------------------
# 生成文件
# -----------------------------------
def save_v2ray(nodes_with_delay):
    with open(OUTPUT_V2RAY, "w", encoding="utf-8") as f:
        for node, delay in nodes_with_delay:
            f.write(node + "\n")
    logger.info(f"已保存 {len(nodes_with_delay)} 条可用节点到 {OUTPUT_V2RAY}")


def save_clash(nodes_with_delay):
    lines = [
        f"# 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "# 自动生成的 Clash 节点文件",
        "proxies:",
    ]
    for node, delay in nodes_with_delay:
        lines.append(f"  - {node}  # 延迟: {delay}ms")

    with open(OUTPUT_CLASH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"已保存 {len(nodes_with_delay)} 条可用节点到 {OUTPUT_CLASH}")


# -----------------------------------
# 主函数
# -----------------------------------
async def main():
    logger.info("开始抓取订阅源...")
    all_nodes = await collect_nodes()
    if not all_nodes:
        logger.warning("未获取到任何节点")
        return

    logger.info("开始检测节点可用性...")
    available_nodes = await test_nodes(all_nodes)
    if not available_nodes:
        logger.warning("无可用节点，终止保存。")
        return

    save_v2ray(available_nodes)
    save_clash(available_nodes)
    logger.info("✅ 检测与保存完成。")


if __name__ == "__main__":
    asyncio.run(main())
