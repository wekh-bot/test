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
        
        # 仅保留 "ws" 协议的节点
        if protocol != "ws":
            return None
        
        # 提取备注信息（包含国家和延迟）
        remark_match = re.search(r'#(.+)$', node_line)
        remark = remark_match.group(1) if remark_match else ""
        
        # 提取国家代码和延迟
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
        
        # 提取主机和端口
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
        try:
            if protocol == "vmess":
                encoded_data = node_line[8:]  # 去掉"vmess://"
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
        except Exception as e:
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

    def filter_nodes(self):
        """筛选指定地区的节点，每个地区最多保留10个"""
        filtered = []
        for country in TARGET_COUNTRIES:
            country_nodes = [node for node in self.nodes if node["country_code"] == country]
            country_nodes_sorted = sorted(country_nodes, key=lambda x: x["latency"])[:10]
            filtered.extend(country_nodes_sorted)
            print(f"{country_code_to_name[country]} 保留 {len(country_nodes_sorted)} 个节点")

        self.nodes = filtered
        print(f"筛选后共 {len(filtered)} 个节点")
    
    def save_to_file(self, filename="config.txt"):
        """保存节点信息到文件（去重后）"""
        unique_nodes = list(set(node['raw'] for node in self.nodes))
        with open(filename, "w", encoding="utf-8") as f:
            for node_raw in unique_nodes:
                f.write(f"{node_raw}\n")
        print(f"去重后的节点信息已保存到 {filename}，共 {len(unique_nodes)} 个节点")

    def encode_to_v2ray(self, input_file="config.txt", output_file="v2ray.txt"):
        """将 config.txt 编码为 v2ray.txt"""
        with open(input_file, "r", encoding="utf-8") as f:
            content = f.read()
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(encoded)
        print(f"编码后的内容已保存到 {output_file}")

    def update_readme(self):
        """更新 README.md 文件"""
        readme_content = """
# Bsbb Crawler

## 更新时间
- **最后更新时间**: [填写更新时间]

## 防失联自用
- 本工具用于定期更新节点数据，确保节点的有效性和可用性。
- 本工具可通过 GitHub Actions 自动定期运行，也可以手动触发更新任务。
"""
        with open("README.md", "w", encoding="utf-8") as f:
            f.write(readme_content)
        
        print("✅ 已更新 README.md 文件")

if __name__ == "__main__":
    crawler = BsbbCrawler()
    nodes = crawler.crawl()
    if nodes:
        crawler.filter_nodes()
        crawler.save_to_file("config.txt")  # 生成 config.txt
        crawler.encode_to_v2ray("config.txt", "v2ray.txt")  # 将 config.txt 编码为 v2ray.txt
        crawler.update_readme()  # 更新 README.md
