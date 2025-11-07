import aiohttp
import asyncio
import base64
import re
import os
from datetime import datetime

# -------------------------------
# 配置部分
# -------------------------------
SOURCES = [
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/ermaozi01/free_clash_vpn/main/subscribe/clash.yml",
    "https://raw.githubusercontent.com/learnhard-cn/free_proxy_ss/main/clash/clash.provider.yaml",
    "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt"
]

OUTPUT_DIR = "output"
RESULT_FILE = os.path.join(OUTPUT_DIR, "result.txt")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------------
# 工具函数
# -------------------------------
def decode_base64_if_needed(text: str) -> str:
    """尝试解码 Base64 内容"""
    try:
        decoded = base64.b64decode(text).decode("utf-8", errors="ignore")
        if "vmess" in decoded or "vless" in decoded:
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
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception:
        pass
    return ""


async def check_node(session: aiohttp.ClientSession, node: str) -> bool:
    """简单检测节点是否能访问 Google"""
    try:
        async with session.get("https://www.google.com", proxy=node, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


# -------------------------------
# 主函数
# -------------------------------
async def main():
    print("[*] 正在从 GitHub 抓取公开节点订阅...")

    async with aiohttp.ClientSession() as session:
        texts = await asyncio.gather(*[fetch_text(session, url) for url in SOURCES])

    all_nodes = []
    for content in texts:
        content = decode_base64_if_needed(content)
        all_nodes.extend(extract_nodes(content))

    all_nodes = list(set(all_nodes))
    print(f"共提取到 {len(all_nodes)} 条节点，开始检测...")

    results = []
    async with aiohttp.ClientSession() as session:
        tasks = [check_node(session, node) for node in all_nodes]
        statuses = await asyncio.gather(*tasks)

        for node, status in zip(all_nodes, statuses):
            results.append((node, "✅ 可用" if status else "❌ 不可用"))

    # 写入结果文件
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"共检测节点：{len(results)} 条\n\n")
        for node, status in results:
            f.write(f"{status} {node}\n")

    available = sum(1 for _, s in results if "✅" in s)
    print(f"检测完成，可用节点：{available}/{len(results)}")
    print(f"结果已保存：{RESULT_FILE}")


# -------------------------------
# 入口
# -------------------------------
if __name__ == "__main__":
    asyncio.run(main())
