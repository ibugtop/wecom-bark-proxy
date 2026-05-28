"""
企业微信到 Bark 通知中转代理
只保留企业微信入口，拦截消息并转发到自建 Bark 服务器
"""

import base64
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

# ============ 配置 ============
BARK_URL = os.environ.get("BARK_URL", "https://bark.example.com/<BARK_DEVICE_KEY>")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "55304"))
SERVER_BASE_URL = os.environ.get("SERVER_BASE_URL", "http://<YOUR_SERVER_IP>:55304")
IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", "/data/images"))
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# 内存中暂存已上传的图片 {image_key: bytes}
_image_store: dict[str, bytes] = {}

# 企业微信文本+图片合并：暂存最近一条文本，等图片到了一起发
_wecom_pending: dict = {"text": None, "ts": 0}

app = FastAPI(title="WeCom to Bark Proxy")


# ============ 工具函数 ============

def gen_image_key() -> str:
    return f"img_{uuid.uuid4().hex[:20]}"


def gen_fake_token() -> str:
    return f"t-fake-{uuid.uuid4().hex[:40]}"


def save_base64_image(b64_data: str) -> str:
    image_key = gen_image_key()
    img_bytes = base64.b64decode(b64_data)
    _image_store[image_key] = img_bytes
    save_path = IMAGES_DIR / f"{image_key}.jpg"
    save_path.write_bytes(img_bytes)
    print(f"[Base64图片] 保存: {save_path} ({len(img_bytes)} bytes) -> {image_key}")
    return image_key


async def send_to_bark(title: str, body: str, image_key: str = None):
    payload = {"title": title, "body": body}
    if image_key:
        payload["image"] = f"{SERVER_BASE_URL}/download/{image_key}"

    async with httpx.AsyncClient(timeout=15, verify=False) as client:
        resp = await client.post(BARK_URL, json=payload)
        return resp.json()


# ============ 企业微信解析 ============

def extract_wecom_content(body: dict) -> tuple[str, str | None]:
    msgtype = body.get("msgtype", "")
    if msgtype == "text":
        return body.get("text", {}).get("content", ""), None
    elif msgtype == "markdown":
        return body.get("markdown", {}).get("content", ""), None
    else:
        return f"[企业微信 {msgtype} 消息]", None


# ============ 企业微信 Webhook ============

@app.post("/cgi-bin/webhook/send")
async def wecom_webhook(request: Request):
    body = await request.json()
    text, _ = extract_wecom_content(body)
    print(f"[企业微信消息] {text[:100]}")
    result = await send_to_bark(title="企业微信通知", body=text)
    print(f"[Bark 响应] {result}")
    return {"errcode": 0, "errmsg": "ok"}


# ============ 图片下载 ============

@app.get("/download/{image_key}")
async def download_image(image_key: str):
    for f in IMAGES_DIR.iterdir():
        if f.stem == image_key:
            return FileResponse(f)
    return JSONResponse({"error": "image not found"}, status_code=404)


# ============ 健康检查 ============

@app.get("/")
async def root():
    return {"status": "running", "port": LISTEN_PORT, "mode": "wecom-only"}


# ============ 兜底路由（仅企业微信图片处理） ============

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(path: str, request: Request):
    method = request.method

    if method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
        except Exception:
            body = None

        if body and isinstance(body, dict):
            # 企业微信图片：{"image": {"base64": "..."}}
            if "image" in body and isinstance(body["image"], dict) and "base64" in body["image"]:
                b64_data = body["image"]["base64"]
                image_key = save_base64_image(b64_data)

                pending = _wecom_pending
                if pending["text"] and (time.time() - pending["ts"] < 5):
                    text = pending["text"]
                    pending["text"] = None
                    pending["ts"] = 0
                    print(f"[企微合并] 文本+图片 -> {text[:50]}")
                    result = await send_to_bark(title="企业微信通知", body=text, image_key=image_key)
                else:
                    print("[企微图片] 无配对文本，单独发送图片")
                    result = await send_to_bark(title="企业微信通知", body="[图片]", image_key=image_key)

                print(f"[Bark 响应] {result}")
                return {"code": 0, "msg": "forwarded to bark"}

            # 企业微信文本先暂存，再转发
            if "msgtype" in body and body["msgtype"] == "text":
                text = body.get("text", {}).get("content", "")
                if text:
                    _wecom_pending["text"] = text
                    _wecom_pending["ts"] = time.time()
                    print(f"[企微文本] 暂存并转发: {text[:80]}")
                    result = await send_to_bark(title="企业微信通知", body=text)
                    print(f"[Bark 响应] {result}")
                    return {"code": 0, "msg": "forwarded to bark"}

            # 其他兜底文本
            text = None
            for key in ("text", "content", "body", "message", "msg", "description"):
                if key in body:
                    val = body[key]
                    if isinstance(val, str):
                        text = val
                        break
                    elif isinstance(val, dict) and "content" in val:
                        text = val["content"]
                        break
                    elif isinstance(val, dict) and "text" in val:
                        text = val["text"]
                        break
            if text:
                print(f"[兜底转发] /{path} -> {text[:80]}")
                await send_to_bark(title=f"通知 (/{path})", body=text)
                return {"code": 0, "msg": "forwarded to bark"}

    return {"code": 0, "msg": "ok"}


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 WeCom Proxy starting on port {LISTEN_PORT}")
    print(f"📡 Bark target: {BARK_URL}")
    print(f"🔗 Image base: {SERVER_BASE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT, log_level="info")
