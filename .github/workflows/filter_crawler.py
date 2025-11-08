import urllib.request
import re
import base64
import json
import os

emoji_to_country = {
    '🇨🇳': 'CN', '🇺🇸': 'US', '🇸🇬': 'SG', '🇯🇵': 'JP',
    '🇰🇷': 'KR', '🇹🇼': 'TW', '🇭🇰': 'HK'
}

country_code_to_name = {
    'CN': '中国', 'US': '美国', 'SG': '新加坡', 'JP': '日本',
    'KR': '韩国', 'TW': '台湾', 'HK': '香港', '未知': '未知'
}

TARGET_COUNTRIES = ["US", "TW", "HK", "JP", "KR", "SG"]

class BsbbCrawler:
    def __init__(self):
        self.base_url = "https://www.bsbb.cc/V2RAY.txt"
        self.nodes = []

    def fetch_node_data(self):
        try:
            print("正在获取节点数据...")
            with urllib.请求.urlopen(self.base_url, timeout=15) as res:
                return res.read().decode('utf-8').strip().split('\n')
        except Exception as e:
            print(f"❌ 获取节点失败: {e}")
            return []

    def parse_node(self, line):
        match = re.match(r'([^:]+)://', line)
        if not match:
            return None
        protocol = match.group(1).lower()
        remark = re.search(r'#(.+)$', line)
        remark = remark.group(1) if remark else ""
        flag = re.search(r'^([\U0001F1E6-\U0001F1FF]{2})', remark)
        latency = re.search(r'(\d+)ms$', remark)
        country = emoji_to_country.get(flag.group(1), "未知") if flag else "未知"
        delay = int(latency.group(1)) if latency else 9999
        return {"raw": line, "country": country, "delay": delay, "protocol": protocol}

    def crawl(self):
        data = self.fetch_node_data()
        for line in data:
            if line.strip():
                node = self.parse_node(line.strip())
                if node:
                    self.nodes.append(node)
        print(f"✅ 获取到 {len(self.nodes)} 个节点")
        return self.nodes

    def filter_nodes(self):
        result = []
        for c in TARGET_COUNTRIES:
            nodes = [n for n in self.nodes if n["country"] == c]
            nodes = sorted(nodes, key=lambda x: x["delay"])[:5]
            result += nodes
            print(f"{country_code_to_name[c]} 保留 {len(nodes)} 个节点")
        self.nodes = result

    def save_to_root(self):
        """强制保存到仓库根目录"""
        root_path = os.getenv("GITHUB_WORKSPACE", os.path.abspath("../../"))
        save_path = os.path.join(root_path, "v2ray.txt")

        with open(save_path, "w", encoding="utf-8") as f:
            for node in self.nodes:
                f.write(f"{node['raw']}\n")

        print(f"✅ 已保存 {len(self.nodes)} 个节点到 {save_path}")

if __name__ == "__main__":
    crawler = BsbbCrawler()
    if crawler.crawl():
        crawler.filter_nodes()
        crawler.save_to_root()
