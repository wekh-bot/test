#!/usr/bin/env python3
import asyncio
import aiohttp
import os

# 你的 IP:PORT 列表
ips = [
    "183.188.22.119:6000",
    "183.188.159.5:6000",
    "116.179.149.75:6000",
    "171.119.207.249:6000",
    "118.79.12.76:6000",
    "118.79.119.188:6000",
    "183.188.21.178:6000",
    "171.119.204.148:6000",
    "171.119.204.139:6000",
    "116.179.149.240:6000",
    "183.188.29.16:6000",
    "118.79.115.112:6000",
    "118.79.115.129:6000",
    "171.125.90.145:6000",
    "116.179.149.88:6000",
    "183.188.21.43:6000",
    "118.79.139.102:6000",
    "183.188.229.36:6000",
    "118.79.113.25:6000",
]

OUTPUT_FILE = "tvlive/zbip.txt"

async def test_ip(session, ip):
    url = f"http://{ip}/status"
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                print(f"✅ 可用: {ip}")
                return ip
    except:
        pass
    print(f"❌ 不可用: {ip}")
    return None

async def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE) or ".", exist_ok=True)
    connector = aiohttp.TCPConnector(limit=50)  # 并发限制
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_ip(session, ip) for ip in ips]
        results = await asyncio.gather(*tasks)
    available = [ip for ip in results if ip]
    with open(OUTPUT_FILE, "w") as f:
        for ip in available:
            f.write(ip + "\n")
    print(f"\n✅ 总共可用 IP: {len(available)}")
    for ip in available:
        print(ip)

if __name__ == "__main__":
    asyncio.run(main())
