import urllib.request
import re
import base64
import json
import os
from datetime import datetime, timezone, timedelta

emoji_to_country = {
    '🇨🇳': 'CN', '🇺🇸': 'US', '🇸🇬': 'SG', '🇯🇵': 'JP',
    '🇰🇷': 'KR', '🇹🇼': 'TW', '🇭🇰': 'HK'
}

country_code_to_name = {
    'CN': '中国', 'US': '美国', 'JP': '日本', 'HK': '香港', '未知': '未知'
}

TARGET_COUNTRIES = ["US", "JP", "HK"]  # 只要这三个国家
MAX_PER_COUNTRY = 10  # 每个国家最多10个节点


class BsbbCrawler:
    def __init__(self):
        self.url = "https://www.bsbb.cc/V2RAY.txt"
        self.nodes = []

    def fetch_node_data(self):
        """获取节点原始数据"""
        try:
            print("正在获取节点数据...")
            response = urllib.请求.urlopen(self.url, timeout=15)
            data = response.read().decode("utf-8")
            return data.strip().split("\n")
        except Exception as e:
            print(f"获取节点数据失败: {e}")
            return []

    def parse_node(self, line):
        """解析单个节点"""
        protocol_match = re.match(r'([^:]+)://', line)
        if not protocol_match:
            return None
        protocol = protocol_match.group(1).lower()
        if protocol != "vless" and protocol != "vmess" and protocol != "trojan":
            return None  # 非 ws 节点协议不处理

        # ws协议识别（包含ws、wss）
        if "ws" not in line.lower():
            return None

        remark_match = re.search(r'#(.+)$', line)
        remark = remark_match.group(1) if remark_match else ""
        emoji_match = re.search(r'^([\U0001F1E6-\U0001F1FF]{2})', remark)
        latency_match = re.search(r'(\d+)ms$', remark)
        country = emoji_to_country.get(emoji_match.group(1), "未知") if emoji_match else "未知"
        latency = int(latency_match.group(1)) if latency_match else 9999

        return {"raw": line, "country": country, "latency": latency, "protocol": protocol}

    def crawl(self):
        """执行爬取"""
        raw_lines = self.fetch_node_data()
        for line in raw_lines:
            if line.strip():
                node = self.parse_node(line.strip())
                if node:
                    self.nodes.append(node)
        print(f"共爬取到 {len(self.nodes)} 个节点")
        return self.nodes

    def filter_nodes(self):
        """筛选符合要求的节点"""
        filtered = []
        for country in TARGET_COUNTRIES:
            nodes = [n for n in self.nodes if n["country"] == country]
            nodes = sorted(nodes, key=lambda x: x["latency"])[:MAX_PER_COUNTRY]
            filtered.extend(nodes)
            print(f"{country_code_to_name[country]} 保留 {len(nodes)} 个 ws 节点")
        self.nodes = filtered
        print(f"筛选后共 {len(filtered)} 个节点")

    def save_to_files(self):
        """保存 config.txt 和更新 README.md"""
        workspace = os.getenv("GITHUB_WORKSPACE", os.path.abspath("../../"))

        # 保存 config.txt
        config_path = os.path.join(workspace, "config.txt")
        with open(config_path, "w", encoding="utf-8") as f:
            for node in self.nodes:
                f.write(node["raw"] + "\n")
        print(f"✅ 已保存 {len(self.nodes)} 个节点到 {config_path}")

        # 更新 README.md，仅更新时间
        readme_path = os.path.join(workspace, "README.md")
        china_tz = timezone(timedelta(hours=8))
        now = datetime.now(china_tz).strftime("%Y-%m-%d %H:%M:%S")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"# 更新时间\n\n最后更新: {now}\n")
        print(f"✅ README.md 更新时间已写入: {now}")


if __name__ == "__main__":
    crawler = BsbbCrawler()
    if crawler.crawl():
        crawler.filter_nodes()
        crawler.save_to_files()
