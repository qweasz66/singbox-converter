from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
import urllib.parse
import base64
import json
import re
import requests

app = FastAPI(title="Sing-box Node Converter")

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sing-box 订阅/节点转换器</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f4f6f9; color: #333; padding: 20px; }
        .container { max-width: 680px; margin: 40px auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.08); padding: 30px; }
        h2 { font-size: 22px; margin-bottom: 8px; color: #111; text-align: center; }
        p.subtitle { font-size: 14px; color: #666; text-align: center; margin-bottom: 24px; }
        label { font-weight: 600; font-size: 14px; display: block; margin-bottom: 8px; color: #444; }
        textarea, select { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-size: 14px; margin-bottom: 18px; outline: none; transition: border-color 0.2s; font-family: inherit; }
        textarea { height: 120px; resize: vertical; font-family: monospace; }
        textarea:focus, select:focus { border-color: #0070f3; }
        .btn-group { display: flex; gap: 12px; margin-bottom: 20px; }
        button { flex: 1; padding: 12px; font-size: 15px; font-weight: 600; color: #fff; background-color: #0070f3; border: none; border-radius: 8px; cursor: pointer; transition: background-color 0.2s; }
        button:hover { background-color: #0051cc; }
        button.secondary { background-color: #10b981; }
        button.secondary:hover { background-color: #059669; }
        .output-box { display: none; margin-top: 20px; }
        .sub-link-box { background: #f8fafc; border: 1px dashed #cbd5e1; padding: 12px; border-radius: 8px; font-family: monospace; font-size: 13px; word-break: break-all; margin-bottom: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🚀 Sing-box 节点转换器</h2>
        <p class="subtitle">自动去重 / 地区分流 / 智能注入</p>
        
        <label for="template-select">选择转换模板：</label>
        <select id="template-select">
            <option value="lite">精简版原版模板 (template.json)</option>
            <option value="acl">全分组高级模板 (template-acl.json)</option>
        </select>

        <label for="input-content">粘贴节点链接或订阅地址：</label>
        <textarea id="input-content" placeholder="支持 vless://, vmess://, trojan://, ss:// 链接，或直接输入 http(s):// 订阅链接..."></textarea>
        
        <div class="btn-group">
            <button onclick="convertNode()">生成转换链接</button>
            <button class="secondary" onclick="downloadConfig()">直接下载 config.json</button>
        </div>

        <div id="output" class="output-box">
            <label>专属 Sing-box 完整订阅链接：</label>
            <div id="sub-url" class="sub-link-box"></div>
            <button onclick="copyUrl()">复制订阅链接</button>
        </div>
    </div>

    <script>
        function getConvertUrl() {
            const input = document.getElementById('input-content').value.trim();
            const template = document.getElementById('template-select').value;
            if (!input) {
                alert('请先输入节点链接或订阅地址！');
                return null;
            }
            const baseUrl = window.location.origin + '/convert?url=';
            return baseUrl + encodeURIComponent(input) + '&template=' + template;
        }

        function convertNode() {
            const url = getConvertUrl();
            if (!url) return;
            document.getElementById('sub-url').innerText = url;
            document.getElementById('output').style.display = 'block';
        }

        function copyUrl() {
            const text = document.getElementById('sub-url').innerText;
            navigator.clipboard.writeText(text).then(() => {
                alert('订阅链接已复制到剪贴板！');
            });
        }

        function downloadConfig() {
            const url = getConvertUrl();
            if (!url) return;
            window.open(url, '_blank');
        }
    </script>
</body>
</html>
"""

REGION_RULES = {
    "🇭🇰 香港节点": re.compile(r"香港|HK|Hong\s*Kong", re.I),
    "🇯🇵 日本节点": re.compile(r"日本|JP|Japan|Tokyo|Osaka", re.I),
    "🇺🇲 美国节点": re.compile(r"美国|US|United\s*States|America", re.I),
    "🇸🇬 狮城节点": re.compile(r"新加坡|狮城|SG|Singapore", re.I),
    "🇨🇳 台湾节点": re.compile(r"台湾|TW|Taiwan|Taipei", re.I),
    "🇰🇷 韩国节点": re.compile(r"韩国|KR|Korea|Seoul", re.I),
}

def decode_b64(s: str) -> str:
    s = s.strip()
    padding = len(s) % 4
    if padding:
        s += '=' * (4 - padding)
    try:
        return base64.urlsafe_b64decode(s).decode('utf-8', errors='ignore')
    except Exception:
        try:
            return base64.b64decode(s).decode('utf-8', errors='ignore')
        except Exception:
            return ""

def clean_uuid(raw_uuid: str) -> str:
    raw_uuid = raw_uuid.lstrip(":").strip()
    if "-" not in raw_uuid and len(raw_uuid) > 20:
        decoded = decode_b64(raw_uuid)
        if decoded:
            cleaned = decoded.lstrip(":").strip()
            if cleaned:
                return cleaned
    return raw_uuid

def parse_vless(url_str: str) -> dict:
    body = url_str[8:] if url_str.startswith("vless://") else url_str
    tag = "vless_node"
    if "#" in body:
        body, frag = body.rsplit("#", 1)
        tag = urllib.parse.unquote(frag)

    query_dict = {}
    if "?" in body:
        body, query_str = body.split("?", 1)
        query_dict = urllib.parse.parse_qs(query_str)
        if 'remarks' in query_dict:
            tag = urllib.parse.unquote(query_dict['remarks'][0])

    uuid_str = ""
    server = ""
    server_port = 443

    ipv6_match = re.search(r'\[([0-9a-fA-F:]+)\]', body)
    if ipv6_match:
        server = ipv6_match.group(1)
        after_bracket = body[body.find("]")+1:]
        port_match = re.search(r':(\d+)', after_bracket)
        if port_match:
            server_port = int(port_match.group(1))
        prefix = body[:body.find("[")]
        uuid_part = prefix.split("@")[0] if "@" in prefix else prefix
        uuid_str = clean_uuid(uuid_part)
    else:
        if "@" in body:
            uuid_part, host_port = body.rsplit("@", 1)
            uuid_str = clean_uuid(uuid_part)
            if ":" in host_port:
                server, port_str = host_port.rsplit(":", 1)
                if port_str.isdigit():
                    server_port = int(port_str)
            else:
                server = host_port
        else:
            decoded_full = decode_b64(body)
            if "@" in decoded_full:
                uuid_part, host_port = decoded_full.rsplit("@", 1)
                uuid_str = clean_uuid(uuid_part)
                if ":" in host_port:
                    server, port_str = host_port.rsplit(":", 1)
                    if port_str.isdigit():
                        server_port = int(port_str)
                else:
                    server = host_port
            else:
                uuid_str = body
                server = "127.0.0.1"

    if not uuid_str or len(uuid_str) < 10:
        uuid_str = "00000000-0000-0000-0000-000000000000"

    node = {
        "type": "vless",
        "tag": tag,
        "server": server,
        "server_port": server_port,
        "uuid": uuid_str
    }
    
    net = query_dict.get('type', [query_dict.get('obfs', ['tcp'])[0]])[0]
    raw_path = query_dict.get('path', ['/'])[0]
    path = urllib.parse.unquote(raw_path)
    host = query_dict.get('host', [''])[0]
    security = query_dict.get('security', ['tls' if (query_dict.get('tls',[''])[0] in ['1','true']) else ''])[0]
    sni = query_dict.get('sni', [query_dict.get('peer', [host])[0]])[0]
    fp = query_dict.get('fp', [query_dict.get('fingerprint', ['chrome'])[0]])[0]
    pbk = query_dict.get('pbk', [''])[0]
    sid = query_dict.get('sid', [''])[0]

    if net in ["ws", "websocket"]:
        node["transport"] = {"type": "ws", "path": path}
        if host:
            node["transport"]["headers"] = {"Host": host}
    elif net == "grpc":
        node["transport"] = {"type": "grpc", "service_name": query_dict.get('serviceName', [''])[0]}

    if security == "reality":
        node["tls"] = {
            "enabled": True,
            "server_name": sni or server,
            "utls": {"enabled": True, "fingerprint": fp},
            "reality": {
                "enabled": True,
                "public_key": pbk,
                "short_id": sid
            }
        }
    elif security in ["tls", "1", "true"] or query_dict.get('tls', [''])[0] in ['1', 'true']:
        node["tls"] = {
            "enabled": True,
            "server_name": sni or host or server,
            "insecure": query_dict.get('allowInsecure', ['0'])[0] in ['1', 'true'],
            "utls": {"enabled": True, "fingerprint": fp}
        }
    return node

def parse_vmess(url_str: str) -> dict:
    raw = decode_b64(url_str[8:])
    data = json.loads(raw)
    tag = data.get("ps", data.get("add", "vmess_node"))
    node = {
        "type": "vmess",
        "tag": tag,
        "server": data.get("add", "127.0.0.1"),
        "server_port": int(data.get("port", 443)),
        "uuid": data.get("id", ""),
        "security": data.get("scy", "auto"),
        "alter_id": int(data.get("aid", 0))
    }
    if data.get("net") == "ws":
        node["transport"] = {
            "type": "ws",
            "path": data.get("path", "/"),
            "headers": {"Host": data.get("host", "")}
        }
    if data.get("tls") == "tls":
        node["tls"] = {
            "enabled": True,
            "server_name": data.get("sni", data.get("host", data.get("add"))),
            "insecure": False
        }
    return node

def parse_trojan(url_str: str) -> dict:
    u = urllib.parse.urlparse(url_str)
    q = urllib.parse.parse_qs(u.query)
    tag = urllib.parse.unquote(u.fragment) if u.fragment else (u.hostname or "trojan_node")
    sni = q.get('sni', [q.get('peer', [''])[0]])[0]
    return {
        "type": "trojan",
        "tag": tag,
        "server": u.hostname or "127.0.0.1",
        "server_port": u.port or 443,
        "password": u.username or "",
        "tls": {
            "enabled": True,
            "server_name": sni or u.hostname or ""
        }
    }

def parse_ss(url_str: str) -> dict:
    u = urllib.parse.urlparse(url_str)
    tag = urllib.parse.unquote(u.fragment) if u.fragment else "Shadowsocks"
    try:
        if '@' in u.netloc:
            userinfo, hostport = u.netloc.split('@', 1)
            method_pw = decode_b64(userinfo)
            method, password = method_pw.split(':', 1)
            server, port = hostport.split(':', 1)
        else:
            decoded = decode_b64(u.netloc)
            method_pw, hostport = decoded.split('@', 1)
            method, password = method_pw.split(':', 1)
            server, port = hostport.split(':', 1)
    except Exception:
        server = "127.0.0.1"
        port = "443"
        method = "aes-256-gcm"
        password = "password"

    return {
        "type": "shadowsocks",
        "tag": tag,
        "server": server,
        "server_port": int(port),
        "method": method,
        "password": password
    }

def parse_line(line: str) -> dict:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("vless://"): return parse_vless(line)
    if line.startswith("vmess://"): return parse_vmess(line)
    if line.startswith("trojan://"): return parse_trojan(line)
    if line.startswith("ss://"): return parse_ss(line)
    return None

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_CONTENT

@app.get("/convert")
def convert(
    url: str = Query(..., description="订阅链接或节点内容"),
    template: str = Query("lite", description="模板类型：lite 或 acl")
):
    if url.startswith("http://") or url.startswith("https://"):
        try:
            resp = requests.get(url, timeout=10)
            content = resp.text
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"拉取订阅失败: {str(e)}")
    else:
        content = url

    if not any(content.strip().startswith(p) for p in ["vless://", "vmess://", "trojan://", "ss://", "{"]):
        decoded_sub = decode_b64(content)
        if "://" in decoded_sub:
            content = decoded_sub

    parsed_nodes = []
    node_tags = []
    seen_tags = {}

    for line in content.splitlines():
        try:
            node = parse_line(line)
            if node:
                # Tag 去重防崩处理
                base_tag = node["tag"].strip() or "Node"
                count = seen_tags.get(base_tag, 0)
                seen_tags[base_tag] = count + 1
                unique_tag = base_tag if count == 0 else f"{base_tag} ({count})"
                node["tag"] = unique_tag
                
                parsed_nodes.append(node)
                node_tags.append(unique_tag)
        except Exception:
            continue

    if not parsed_nodes:
        raise HTTPException(status_code=400, detail="未发现可解析的节点，请检查输入的链接格式")

    template_file = "template-acl.json" if template == "acl" else "template.json"
    try:
        with open(template_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"找不到对应的模板文件: {template_file}")

    # 分类准备：按地区整理节点 tag
    region_tags = {k: [] for k in REGION_RULES}
    for tag in node_tags:
        for reg_name, pattern in REGION_RULES.items():
            if pattern.search(tag):
                region_tags[reg_name].append(tag)

    base_outbounds = []
    group_outbounds = []
    
    for o in config.get("outbounds", []):
        if o.get("type") in ["direct", "block", "dns"]:
            base_outbounds.append(o)
        elif o.get("type") in ["urltest", "selector"]:
            group_outbounds.append(o)

    new_outbounds = base_outbounds + parsed_nodes

    # 智能分流注入
    target_selector_tags = ["🚀 节点选择", "🚀 手动切换", "全局代理"]
    for g in group_outbounds:
        tag_name = g.get("tag", "")
        # 1. 自动测速组
        if g.get("type") == "urltest":
            g["outbounds"] = node_tags
        # 2. 地区专用选择组
        elif tag_name in region_tags:
            matched = region_tags[tag_name]
            g["outbounds"] = matched if matched else ["DIRECT"]
        # 3. 核心节点总控组
        elif tag_name in target_selector_tags:
            static_items = [t for t in g.get("outbounds", []) if t in ["♻️ 自动选择", "DIRECT", "REJECT", "🚀 手动切换"]]
            g["outbounds"] = static_items + node_tags
        new_outbounds.append(g)

    config["outbounds"] = new_outbounds
    return HTMLResponse(content=json.dumps(config, indent=2, ensure_ascii=False), media_type="application/json")
