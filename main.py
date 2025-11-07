import aiohttp
import asyncio
import base64
import re
import os
from datetime import datetime
import logging
from helpers import safe_get  # 如果没有 helpers.py，可直接改为 requests.get

# -----------------------------------
# 基本配置
# -----------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("collector")

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


# -----------------------------------
# 工具函数
# -----------------------------------
def decode_base64_if_needed(text: str) -> str:
    """尝试解码 Base64 内容"""
    try:
        decoded = base64.b64decode(text).decode("utf-8", errors="ignore")
        if "vmess" in decoded or "vless" in decoded or "ss://" in decoded:
            return decoded
    except Exception:
        pass
    return text


def extract_nodes(text: str) -> list:
    """提取 vmess/vless/ss/trojan 节点"""
    pattern = r"(vmess://[A-Za-z0-9+/=._-]+|vless://[^\s]+|ss://[^\s]+|trojan://[^\s]+)"
    return re.findall(pattern, text)


async def fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    """异步获取文本"""
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

    # 去重
    all_nodes = list(set(all_nodes))
    logger.info(f"共提取节点：{len(all_nodes)} 条")
    return all_nodes


def convert_to_clash(nodes: list) -> str:
    """生成简单 Clash YAML 配置"""
    yaml_lines = [
        "proxies:",
    ]
    for node in nodes:
        yaml_lines.append(f"  - {node}")
    return "\n".join(yaml_lines)


async def main():
    logger.info("开始抓取节点订阅源...")
    nodes = await collect_nodes()

    if not nodes:
        logger.warning("未获取到任何节点，可能源失效")
        return

    # 保存 V2Ray 格式
    with open(OUTPUT_V2RAY, "w", encoding="utf-8") as f:
        for node in nodes:
            f.write(node.strip() + "\n")
    logger.info(f"已保存：{OUTPUT_V2RAY}")

    # 保存 Clash 格式
    clash_content = convert_to_clash(nodes)
    with open(OUTPUT_CLASH, "w", encoding="utf-8") as f:
        f.write(f"# 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(clash_content)
    logger.info(f"已保存：{OUTPUT_CLASH}")

    logger.info("任务完成。")


if __name__ == "__main__":
    asyncio.run(main())
