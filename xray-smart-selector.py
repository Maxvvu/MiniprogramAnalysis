#!/usr/bin/env python3
"""
Xray 智能节点选择器
功能：
1. 解析订阅地址
2. Ping 所有节点
3. 自动选择最快的节点
4. 生成配置文件
5. 重启 Xray
"""

import json
import subprocess
import base64
import re
import time
from urllib.parse import urlparse, parse_qs, unquote
from typing import List, Dict, Optional
import requests

# 订阅地址
SUBSCRIPTION_URLS = [
    "https://d7b12d59-21aa-9561-087f-89c834ac7fe8.372372.xyz/api/v1/client/subscribe?token=e99c185b01429293fe416e6882dc2522",
    "https://api0.bigmelook.com/BigME/Subscription/api/v1/client/subscribe?token=3adc3b5e83e6467d070cf61f4eca08d1"
]

def fetch_subscription(url: str) -> List[str]:
    """获取订阅内容"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = base64.b64decode(response.text).decode('utf-8')
        # 分割每一行（每行一个节点）
        nodes = [line.strip() for line in content.split('\n') if line.strip()]
        return nodes
    except Exception as e:
        print(f"❌ 获取订阅失败 {url}: {e}")
        return []

def parse_vless_node(vless_url: str) -> Optional[Dict]:
    """解析 VLESS 节点"""
    try:
        # vless://uuid@host:port?params#name
        if not vless_url.startswith('vless://'):
            return None

        # 移除协议前缀
        url_without_protocol = vless_url[8:]

        # 分离备注名称
        if '#' in url_without_protocol:
            url_part, name = url_without_protocol.rsplit('#', 1)
            name = unquote(name)
        else:
            url_part = url_without_protocol
            name = "Unknown"

        # 分离参数
        if '?' in url_part:
            user_host_port, params_str = url_part.split('?', 1)
            params = parse_qs(params_str)
        else:
            user_host_port = url_part
            params = {}

        # 解析 UUID@host:port
        uuid_host_port = user_host_port
        if '@' in uuid_host_port:
            uuid, host_port = uuid_host_port.split('@', 1)
        else:
            return None

        if ':' in host_port:
            host, port = host_port.rsplit(':', 1)
            port = int(port)
        else:
            return None

        # 提取参数
        node = {
            'name': name,
            'uuid': uuid,
            'host': host,
            'port': port,
            'type': params.get('type', ['tcp'])[0],
            'security': params.get('security', ['none'])[0],
            'sni': params.get('sni', [''])[0],
            'fp': params.get('fp', ['chrome'])[0],
            'pbk': params.get('pbk', [''])[0],
            'sid': params.get('sid', [''])[0],
            'serviceName': params.get('serviceName', [''])[0],
        }

        return node

    except Exception as e:
        print(f"❌ 解析节点失败: {e}")
        return None

def parse_trojan_node(trojan_url: str) -> Optional[Dict]:
    """解析 Trojan 节点"""
    try:
        # trojan://password@host:port?params#name
        if not trojan_url.startswith('trojan://'):
            return None

        url_without_protocol = trojan_url[9:]

        if '#' in url_without_protocol:
            url_part, name = url_without_protocol.rsplit('#', 1)
            name = unquote(name)
        else:
            url_part = url_without_protocol
            name = "Unknown"

        if '?' in url_part:
            password_host_port, params_str = url_part.split('?', 1)
            params = parse_qs(params_str)
        else:
            password_host_port = url_part
            params = {}

        if '@' in password_host_port:
            password, host_port = password_host_port.split('@', 1)
        else:
            return None

        if ':' in host_port:
            host, port = host_port.rsplit(':', 1)
            port = int(port)
        else:
            return None

        node = {
            'name': name,
            'password': password,
            'host': host,
            'port': port,
            'type': 'trojan',
            'sni': params.get('sni', [host])[0],
        }

        return node

    except Exception as e:
        print(f"❌ 解析 Trojan 节点失败: {e}")
        return None

def ping_node(host: str, count: int = 3, timeout: int = 2) -> Optional[float]:
    """Ping 节点，返回平均延迟（毫秒），失败返回 None"""
    try:
        # 使用 ping 命令
        cmd = ['ping', '-c', str(count), '-W', str(timeout), host]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return None

        # 解析延迟
        # 示例输出: rtt min/avg/max/mdev = 10.123/15.456/20.789/5.012 ms
        match = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/', result.stdout)
        if match:
            avg_latency = float(match.group(1))
            return avg_latency

        return None

    except Exception as e:
        return None

def generate_vless_config(node: Dict, local_port: int = 10808) -> Dict:
    """生成 VLESS Xray 配置"""
    config = {
        "log": {
            "loglevel": "warning"
        },
        "inbounds": [
            {
                "port": local_port,
                "protocol": "http",
                "listen": "127.0.0.1",
                "settings": {
                    "timeout": 300
                }
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": node['host'],
                            "port": node['port'],
                            "users": [
                                {
                                    "id": node['uuid'],
                                    "encryption": "none"
                                }
                            ]
                        }
                    ]
                },
                "streamSettings": {
                    "network": node['type'],
                    "security": node['security']
                }
            }
        ]
    }

    # 添加 reality 配置
    if node['security'] == 'reality':
        config['outbounds'][0]['streamSettings']['realitySettings'] = {
            "serverName": node['sni'],
            "fingerprint": node['fp'],
            "publicKey": node['pbk'],
            "shortId": node['sid']
        }

    # 添加 grpc 配置
    if node['type'] == 'grpc':
        config['outbounds'][0]['streamSettings']['grpcSettings'] = {
            "serviceName": node['serviceName']
        }

    return config

def generate_trojan_config(node: Dict, local_port: int = 10808) -> Dict:
    """生成 Trojan Xray 配置"""
    config = {
        "log": {
            "loglevel": "warning"
        },
        "inbounds": [
            {
                "port": local_port,
                "protocol": "http",
                "listen": "127.0.0.1",
                "settings": {
                    "timeout": 300
                }
            }
        ],
        "outbounds": [
            {
                "protocol": "trojan",
                "settings": {
                    "servers": [
                        {
                            "address": node['host'],
                            "port": node['port'],
                            "password": node['password']
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "tls",
                    "tlsSettings": {
                        "serverName": node['sni']
                    }
                }
            }
        ]
    }

    return config

def main():
    print("=" * 60)
    print("🚀 Xray 智能节点选择器")
    print("=" * 60)

    # 1. 获取所有订阅
    all_nodes_raw = []
    for sub_url in SUBSCRIPTION_URLS:
        print(f"\n📥 获取订阅: {sub_url[:50]}...")
        nodes = fetch_subscription(sub_url)
        all_nodes_raw.extend(nodes)
        print(f"   ✅ 获取 {len(nodes)} 个节点")

    if not all_nodes_raw:
        print("\n❌ 没有获取到任何节点！")
        return

    print(f"\n📊 总共获取 {len(all_nodes_raw)} 个节点")

    # 2. 解析节点
    print("\n🔍 解析节点...")
    all_nodes = []
    for node_url in all_nodes_raw:
        if node_url.startswith('vless://'):
            node = parse_vless_node(node_url)
            if node:
                all_nodes.append(node)
        elif node_url.startswith('trojan://'):
            node = parse_trojan_node(node_url)
            if node:
                all_nodes.append(node)

    print(f"   ✅ 成功解析 {len(all_nodes)} 个节点")

    if not all_nodes:
        print("\n❌ 没有可用节点！")
        return

    # 3. Ping 测试
    print(f"\n🏓 Ping 测试（共 {len(all_nodes)} 个节点）...")
    print("-" * 60)

    available_nodes = []
    for i, node in enumerate(all_nodes, 1):
        print(f"[{i}/{len(all_nodes)}] {node['name'][:30]:<30} {node['host']:<25} ", end='', flush=True)

        latency = ping_node(node['host'], count=2, timeout=2)

        if latency:
            print(f"✅ {latency:.1f} ms")
            node['latency'] = latency
            available_nodes.append(node)
        else:
            print("❌ 超时")

    print("-" * 60)

    if not available_nodes:
        print("\n❌ 没有可用节点（所有节点 Ping 都超时）！")
        print("\n💡 建议：")
        print("   1. 检查网络连接")
        print("   2. 尝试使用 Exa Search API（不需要代理）")
        return

    # 4. 选择最快节点
    available_nodes.sort(key=lambda x: x['latency'])
    best_node = available_nodes[0]

    print(f"\n🏆 最优节点:")
    print(f"   名称: {best_node['name']}")
    print(f"   地址: {best_node['host']}:{best_node['port']}")
    print(f"   延迟: {best_node['latency']:.1f} ms")

    # 5. 生成配置
    print(f"\n⚙️  生成 Xray 配置...")
    if 'uuid' in best_node:
        config = generate_vless_config(best_node)
    else:
        config = generate_trojan_config(best_node)

    config_path = '/opt/xray/config.json'
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"   ✅ 配置已保存: {config_path}")

    # 6. 重启 Xray
    print(f"\n🔄 重启 Xray 服务...")
    try:
        # 停止旧进程
        subprocess.run(['pkill', '-f', 'xray run'], check=False)
        time.sleep(1)

        # 启动新进程
        subprocess.Popen(
            ['nohup', '/opt/xray/xray', 'run', '-c', config_path],
            stdout=open('/opt/xray/xray.log', 'w'),
            stderr=subprocess.STDOUT,
            cwd='/opt/xray'
        )

        time.sleep(3)

        # 检查进程
        result = subprocess.run(['pgrep', '-f', 'xray run'], capture_output=True)
        if result.returncode == 0:
            print("   ✅ Xray 启动成功")

            # 测试代理
            print(f"\n🧪 测试代理连接...")
            test_result = subprocess.run(
                ['curl', '-x', 'http://127.0.0.1:10808', '-s', '--max-time', '10',
                 'https://www.google.com', '-I'],
                capture_output=True,
                text=True,
                timeout=15
            )

            if 'HTTP' in test_result.stdout:
                print("   ✅ 代理测试成功！")
                print("\n" + "=" * 60)
                print("🎉 配置完成！代理地址: http://127.0.0.1:10808")
                print("=" * 60)
            else:
                print("   ⚠️  代理连接测试超时，可能需要等待或切换节点")
        else:
            print("   ❌ Xray 启动失败")

    except Exception as e:
        print(f"   ❌ 重启失败: {e}")

    # 7. 显示其他可用节点
    if len(available_nodes) > 1:
        print(f"\n📋 其他可用节点（前5个）:")
        for node in available_nodes[1:6]:
            print(f"   • {node['name'][:40]:<40} {node['host']:<25} {node['latency']:.1f} ms")

if __name__ == "__main__":
    main()
