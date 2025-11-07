import aiohttp
import asyncio
import base64
import re
import os
from datetime import datetime
import logging
import time

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
async def check_node(session: aiohttp.ClientSession, node: str):
    """检测节点是否可用（返回延迟ms）"""
    start = time.time()
    try:
        async with session.get("https://www.cloudflare.com/cdn-cgi/trace", proxy=node, timeout=5) as resp:
            if resp.status == 200:
                delay = int((time.time() - start) * 1000)
                return node, delay
    except Exception:
        pass
    return None


async def test_nodes(nodes):
    """异步检测节点可用性"""
    available = []
    async with aiohttp.ClientSession() as session:
        tasks = [check_node(session, node) for node in nodes]
        results = await asyncio.gather(*tasks)

    for res in results:
        if res:
            available.append(res)

    available.sort(key=lambda x: x[1])  # 按延迟排序
    logger.info(f"可用节点：{len(available)} 条")
    return available[:MAX_NODES]


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
