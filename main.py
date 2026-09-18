from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
import urllib.parse
import base64
import json
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
        textarea { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-size: 14px; margin-bottom: 18px; outline: none; transition: border-color 0.2s; height: 120px; resize: vertical; font-family: monospace; }
        textarea:focus { border-color: #0070f3; }
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
        <p class="subtitle">轻松转换小火箭节点/订阅为完整 Sing-box 配置文件</p>
        
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
            if (!input) {
                alert('请先输入节点链接或订阅地址！');
                return null;
            }
            const baseUrl = window.location.origin + '/convert?url=';
            return baseUrl + encodeURIComponent(input);
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

def decode_b64(s: str) -> str:
    s = s.strip()
    padding = len(s) % 4
    if padding:
        s += '=' * (4 - padding)
    try:
        return base64.urlsafe_b64decode(s).decode('utf-8', errors='ignore')
    except Exception:
        return base64.b64decode(s).decode('utf-8', errors='ignore')

def parse_vless(url_str: str) -> dict:
    u = urllib.parse.urlparse(url_str)
    q = urllib.parse.parse_qs(u.query)
    tag = urllib.parse.unquote(u.fragment) if u.fragment else u.hostname
    
    user_info = urllib.parse.unquote(u.username or "")
    if '@' in user_info:
        uuid_str = user_info.split('@')[-1]
    else:
        uuid_str = user_info
        
    node = {
        "type": "vless",
        "tag": tag,
        "server": u.hostname,
        "server_port": u.port or 443,
        "uuid": uuid_str
    }
    
    # 兼容获取传输类型（支持 type 或 obfs）
    net = q.get('type', [q.get('obfs', ['tcp'])[0]])[0]
    
    # 处理 path 并解码
    raw_path = q.get('path', ['/'])[0]
    path = urllib.parse.unquote(raw_path)
    
    # 提取 Host（优先从 obfsParam 的 JSON 中解析，其次从 host 参数取）
    host = q.get('host', [''])[0]
    obfs_param = q.get('obfsParam', [''])[0]
    if obfs_param:
        try:
            param_json = json.loads(obfs_param)
            if "Host" in param_json:
                host = param_json["Host"]
        except Exception:
            pass
            
    security = q.get('security', ['tls' if u.scheme=='vless' and (q.get('tls',[''])[0]=='1' or q.get('tls',[''])[0]=='true') else ''])[0]
    sni = q.get('sni', [q.get('peer', [host])[0]])[0]
    fp = q.get('fp', [q.get('fingerprint', ['chrome'])[0]])[0]

    if net in ["ws", "websocket"]:
        node["transport"] = {"type": "ws", "path": path}
        if host:
            node["transport"]["headers"] = {"Host": host}
    elif net == "grpc":
        node["transport"] = {"type": "grpc", "service_name": q.get('serviceName', [''])[0]}

    if security in ["tls", "1", "true"] or q.get('tls', [''])[0] in ['1', 'true']:
        node["tls"] = {
            "enabled": True,
            "server_name": sni or host or u.hostname,
            "insecure": q.get('allowInsecure', ['0'])[0] in ['1', 'true'],
            "utls": {"enabled": True, "fingerprint": fp}
        }
        if security == "reality" or q.get('security', [''])[0] == "reality":
            node["tls"]["reality"] = {
                "enabled": True,
                "public_key": q.get('pbk', [''])[0],
                "short_id": q.get('sid', [''])[0]
            }
    return node

def parse_vmess(url_str: str) -> dict:
    raw = decode_b64(url_str[8:])
    data = json.loads(raw)
    tag = data.get("ps", data.get("add"))
    node = {
        "type": "vmess",
        "tag": tag,
        "server": data.get("add"),
        "server_port": int(data.get("port", 443)),
        "uuid": data.get("id"),
        "security": data.get("scy", "auto"),
        "alter_id": int(data.get("aid", 0))
    }
    if data.get("net") == "ws":
        node["transport"] = {
            "type": "ws",
            "path": data.get("path", ""),
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
    tag = urllib.parse.unquote(u.fragment) if u.fragment else u.hostname
    sni = q.get('sni', [q.get('peer', [''])[0]])[0]
    return {
        "type": "trojan",
        "tag": tag,
        "server": u.hostname,
        "server_port": u.port or 443,
        "password": u.username,
        "tls": {
            "enabled": True,
            "server_name": sni or u.hostname
        }
    }

def parse_ss(url_str: str) -> dict:
    u = urllib.parse.urlparse(url_str)
    tag = urllib.parse.unquote(u.fragment) if u.fragment else "Shadowsocks"
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
    if line.startswith("vless://"): return parse_vless(line)
    if line.startswith("vmess://"): return parse_vmess(line)
    if line.startswith("trojan://"): return parse_trojan(line)
    if line.startswith("ss://"): return parse_ss(line)
    return None

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_CONTENT

@app.get("/convert")
def convert(url: str = Query(..., description="订阅链接或节点内容")):
    if url.startswith("http://") or url.startswith("https://"):
        try:
            resp = requests.get(url, timeout=10)
            content = resp.text
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"拉取订阅失败: {str(e)}")
    else:
        content = url

    if not any(content.startswith(p) for p in ["vless://", "vmess://", "trojan://", "ss://"]):
        decoded = decode_b64(content)
        if "://" in decoded:
            content = decoded

    parsed_nodes = []
    node_tags = []
    for line in content.splitlines():
        try:
            node = parse_line(line)
            if node:
                parsed_nodes.append(node)
                node_tags.append(node["tag"])
        except Exception:
            continue

    if not parsed_nodes:
        raise HTTPException(status_code=400, detail="未发现可解析的节点")

    with open("template.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    base_outbounds = []
    group_outbounds = []
    
    for o in config.get("outbounds", []):
        if o.get("type") in ["direct", "block"]:
            base_outbounds.append(o)
        elif o.get("type") in ["urltest", "selector"]:
            group_outbounds.append(o)

    new_outbounds = base_outbounds + parsed_nodes

    for g in group_outbounds:
        if g.get("type") == "urltest":
            g["outbounds"] = node_tags
        elif g.get("type") == "selector":
            reserved = [t for t in g.get("outbounds", []) if t in ["DIRECT", "REJECT", "♻️ 自动选择", "🚀 节点选择"]]
            g["outbounds"] = reserved + node_tags
        new_outbounds.append(g)

    config["outbounds"] = new_outbounds
    return HTMLResponse(content=json.dumps(config, indent=2, ensure_ascii=False), media_type="application/json")
