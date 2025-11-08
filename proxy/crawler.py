import urllib.request
import re
import base64
import json
import os
from datetime import datetime, timezone, timedelta

# emoji到国家代码的映射
emoji_to_country = {
    '🇨🇳': 'CN', '🇺🇸': 'US', '🇸🇬': 'SG', '🇩🇪': 'DE', '🇬🇧': 'GB',
    '🇯🇵': 'JP', '🇰🇷': 'KR', '🇫🇷': 'FR', '🇷🇺': 'RU', '🇮🇳': 'IN',
    '🇧🇷': 'BR', '🇨🇦': 'CA', '🇦🇺': 'AU', '🇳🇱': 'NL', '🇮🇩': 'ID',
    '🇹🇭': 'TH', '🇻🇳': 'VN', '🇵🇭': 'PH', '🇲🇾': 'MY', '🇹🇼': 'TW',
    '🇭🇰': 'HK', '🇲🇴': 'MO', '🇨🇼': 'CW', '🇪🇸': 'ES', '🇹🇷': 'TR',
    '🇳🇴': 'NO', '🇺🇦': 'UA', '🇱🇻': 'LV', '🇰🇭': 'KH', '🇸🇪': 'SE',
    '🇫🇮': 'FI', '🇷🇴': 'RO', '🇧🇪': 'BE'
}

# 目标国家：美国、日本、香港
TARGET_COUNTRIES = ["US", "JP", "HK"]

# 国家代码到中文名称的映射
country_code_to_name = {
    'CN': '中国', 'US': '美国', 'SG': '新加坡', 'DE': '德国', 'GB': '英国',
    'JP': '日本', 'KR': '韩国', 'FR': '法国', 'RU': '俄罗斯', 'IN': '印度',
    'BR': '巴西', 'CA': '加拿大', 'AU': '澳大利亚', 'NL': '荷兰', 'ID': '印度尼西亚',
    'TH': '泰国', 'VN': '越南', 'PH': '菲律宾', 'MY': '马来西亚', 'TW': '台湾',
    'HK': '香港', 'MO': '澳门', 'CW': '库拉索', 'ES': '西班牙', 'TR': '土耳其',
    'NO': '挪威', 'UA': '乌克兰', 'LV': '拉脱维亚', 'KH': '柬埔寨', 'SE': '瑞典',
    'FI': '芬兰', 'RO': '罗马尼亚', 'BE': '比利时', '未知': '未知'
}

class BsbbCrawler:
    def __init__(self):
        self.base_url = "https://www.bsbb.cc"
        self.node_file_url = f"{self.base_url}/V2RAY.txt"
        self.nodes = []

    def fetch_node_data(self):
        """获取节点数据"""
        try:
            response = urllib.request.urlopen(self.node_file_url, timeout=10)
            data = response.read().decode('utf-8')
            return data.strip().split('\n')
        except Exception as e:
            print(f"获取节点数据时出错: {e}")
            return []

    def parse_node(self, node_line):
        """解析单个节点信息"""
        protocol_match = re.match(r'([^:]+)://', node_line)
        if not protocol_match:
            return None
        protocol = protocol_match.group(1).lower()
        remark_match = re.search(r'#(.+)$', node_line)
        remark = remark_match.group(1) if remark_match else ""
        country_emoji_match = re.search(r'^([\U0001F1E6-\U0001F1FF]{2})', remark)
        country_code_match = re.search(r'([A-Z]{2})\s*www\.bsbb\.cc\s*[a-zA-Z]+-([A-Z]{2})', remark)
        latency_match = re.search(r'(\d+)ms$', remark)
        if country_emoji_match:
            country_emoji = country_emoji_match.group(1)
            country_code = emoji_to_country.get(country_emoji, "未知")
        elif country_code_match:
            country_code = country_code_match.group(2)
        else:
            country_code = "未知"
        latency = int(latency_match.group(1)) if latency_match else None
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
        """从节点链接中提取主机和端口"""
        try:
            if protocol == "vmess":
                encoded_data = node_line[8:]
                missing_padding = len(encoded_data) % 4
                if missing_padding:
                    encoded_data += '=' * (4 - missing_padding)
                decoded_data = base64.b64decode(encoded_data.encode('ascii')).decode('utf-8')
                data = json.loads(decoded_data)
                host = data.get("add", "")
                port = data.get("port", "")
                return host, port
            else:
                if "?" in node_line:
                    url_part = node_line.split("?")[0]
                else:
                    url_part = node_line.split("#")[0]
                host_port = url_part.split("@")[-1].split(":")
                host = host_port[0] if len(host_port) > 0 else ""
                port = host_port[1] if len(host_port) > 1 else ""
                return host, port
        except Exception:
            return "", ""

    def crawl(self):
        """执行爬取任务"""
        print("开始爬取 www.bsbb.cc 节点信息...")
        node_lines = self.fetch_node_data()
        if not node_lines:
            print("未能获取到节点数据")
            return
        for line in node_lines:
            if line.strip():
                node_info = self.parse_node(line.strip())
                if node_info:
                    self.nodes.append(node_info)
        print(f"爬取完成，共获取到 {len(self.nodes)} 个节点信息")
        return self.nodes

    def analyze_nodes(self):
        """分析节点信息"""
        if not self.nodes:
            print("没有节点数据可供分析")
            return
        country_count = {country: 0 for country in TARGET_COUNTRIES}
        for node in self.nodes:
            country = node['country_code']
            if country in TARGET_COUNTRIES:
                country_count[country] += 1
        print(f"\n目标国家节点统计:")
        for country in TARGET_COUNTRIES:
            print(f"{country_code_to_name[country]}: {country_count[country]} 个节点")
        return country_count

    def save_to_file(self, filename="proxy/v2ray.txt"):
        """只保存香港、美国、日本节点，每个国家最多10个"""
        country_limits = {c: 0 for c in TARGET_COUNTRIES}
        max_per_country = 10
        filtered_nodes = []
        for node in self.nodes:
            cc = node['country_code']
            if cc in TARGET_COUNTRIES and country_limits[cc] < max_per_country:
                filtered_nodes.append(node['raw'])
                country_limits[cc] += 1
        with open(filename, "w", encoding="utf-8") as f:
            for raw in filtered_nodes:
                f.write(raw + "\n")
        print(f"已保存 {len(filtered_nodes)} 个节点（{', '.join(TARGET_COUNTRIES)} 各最多10个）到 {filename}")

if __name__ == "__main__":
    crawler = BsbbCrawler()
    nodes = crawler.crawl()
    if nodes:
        country_count = crawler.analyze_nodes()
        crawler.save_to_file("proxy/v2ray.txt")
