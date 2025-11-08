import urllib.request
import re
import base64
import json
from datetime import datetime, timezone, timedelta

# emoji 到国家代码映射
emoji_to_country = {
    '🇨🇳': 'CN', '🇺🇸': 'US', '🇸🇬': 'SG', '🇩🇪': 'DE', '🇬🇧': 'GB',
    '🇯🇵': 'JP', '🇰🇷': 'KR', '🇫🇷': 'FR', '🇷🇺': 'RU', '🇮🇳': 'IN',
    '🇧🇷': 'BR', '🇨🇦': 'CA', '🇦🇺': 'AU', '🇳🇱': 'NL', '🇮🇩': 'ID',
    '🇹🇭': 'TH', '🇻🇳': 'VN', '🇵🇭': 'PH', '🇲🇾': 'MY', '🇹🇼': 'TW',
    '🇭🇰': 'HK', '🇲🇴': 'MO', '🇨🇼': 'CW', '🇪🇸': 'ES', '🇹🇷': 'TR',
    '🇳🇴': 'NO', '🇺🇦': 'UA', '🇱🇻': 'LV', '🇰🇭': 'KH', '🇸🇪': 'SE',
    '🇫🇮': 'FI', '🇷🇴': 'RO', '🇧🇪': 'BE'
}

# 国家代码到中文名映射
country_code_to_name = {
    'CN': '中国', 'US': '美国', 'SG': '新加坡', 'JP': '日本',
    'KR': '韩国', 'TW': '台湾', 'HK': '香港', '未知': '未知'
}

# ✅ 仅保留以下国家
TARGET_COUNTRIES = ["US", "TW", "HK", "JP", "KR", "SG"]

class BsbbCrawler:
    def __init__(self):
        self.base_url = "https://www.bsbb.cc"
        self.node_file_url = f"{self.base_url}/V2RAY.txt"
        self.nodes = []

    def fetch_node_data(self):
        """获取节点数据"""
        try:
            response = urllib.request.urlopen(self.node_file_url, timeout=15)
            data = response.read().decode('utf-8')
            return data.strip().split('\n')
        except Exception as e:
            print(f"获取节点数据时出错: {e}")
            return []

    def parse_node(self, node_line):
        """解析单个节点"""
        protocol_match = re.match(r'([^:]+)://', node_line)
        if not protocol_match:
            return None
        protocol = protocol_match.group(1).lower()
        remark_match = re.search(r'#(.+)$', node_line)
        remark = remark_match.group(1) if remark_match else ""

        # 提取 emoji 国家
        country_emoji_match = re.search(r'^([\U0001F1E6-\U0001F1FF]{2})', remark)
        latency_match = re.search(r'(\d+)ms$', remark)

        if country_emoji_match:
            country_emoji = country_emoji_match.group(1)
            country_code = emoji_to_country.get(country_emoji, "未知")
        else:
            country_code = "未知"

        latency = int(latency_match.group(1)) if latency_match else 9999
        host, port = self.extract_host_port(node_line, protocol)
        return {
            "protocol": protocol,
            "country_code": country_code,
            "latency": latency,
            "host": host,
            "port": port,
            "raw": node_line
        }

    def extract_host_port(self, node_line, protocol):
        """提取主机端口"""
        try:
            if protocol == "vmess":
                encoded_data = node_line[8:]
                missing_padding = len(encoded_data) % 4
                if missing_padding:
                    encoded_data += '=' * (4 - missing_padding)
                decoded_data = base64.b64decode(encoded_data.encode('ascii')).decode('utf-8')
                data = json.loads(decoded_data)
                return data.get("add", ""), data.get("port", "")
            else:
                url_part = node_line.split("?")[0].split("#")[0]
                host_port = url_part.split("@")[-1].split(":")
                host = host_port[0] if len(host_port) > 0 else ""
                port = host_port[1] if len(host_port) > 1 else ""
                return host, port
        except Exception:
            return "", ""

    def crawl(self):
        """爬取节点"""
        print("开始爬取 www.bsbb.cc 节点...")
        node_lines = self.fetch_node_data()
        if not node_lines:
            print("未获取到节点数据")
            return
        for line in node_lines:
            if line.strip():
                info = self.parse_node(line.strip())
                if info:
                    self.nodes.append(info)
        print(f"爬取完成，共 {len(self.nodes)} 条节点")
        return self.nodes

    def filter_nodes(self):
        """筛选延迟最低的节点"""
        # 按国家分组
        grouped = {country: [] for country in TARGET_COUNTRIES}
        for node in self.nodes:
            if node["country_code"] in TARGET_COUNTRIES:
                grouped[node["country_code"]].append(node)

        # 每个国家按延迟排序，取前5
        filtered = []
        for country, nodes in grouped.items():
            nodes_sorted = sorted(nodes, key=lambda x: x["latency"])
            top_nodes = nodes_sorted[:5]
            filtered.extend(top_nodes)
            print(f"{country_code_to_name[country]} 保留 {len(top_nodes)} 个节点")

        self.nodes = filtered
        print(f"筛选后总计 {len(filtered)} 个节点")

    def save_to_file(self, filename="v2ray.txt"):
        """保存结果到仓库根目录"""
        unique_nodes = list(dict.fromkeys(node['raw'] for node in self.nodes))
        with open(filename, "w", encoding="utf-8") as f:
            for node_raw in unique_nodes:
                f.write(f"{node_raw}\n")
        print(f"✅ 已保存 {len(unique_nodes)} 个节点到 {filename}")

if __name__ == "__main__":
    crawler = BsbbCrawler()
    nodes = crawler.crawl()
    if nodes:
        crawler.filter_nodes()
        crawler.save_to_file("v2ray.txt")  # 保存到仓库根目录
