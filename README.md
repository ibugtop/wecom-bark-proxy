# notify-proxy

一个极简的 **企业微信 → Bark** 通知中转代理。

## 功能

- 接收企业微信 Webhook
- 支持文本消息
- 支持图片消息（Base64 图片）
- 支持“文本 + 图片”合并转发到 Bark
- Bark 通过内网 `bark-server:8080` 转发，减少一次公网跳转

## 当前保留的入口

| 路径 | 说明 |
|---|---|
| `GET /` | 健康检查 |
| `POST /cgi-bin/webhook/send` | 企业微信 Webhook 入口 |
| `GET /download/{image_key}` | 图片下载（供 Bark 展示图片用） |

## 部署方式

项目目录：

```text
/docker/notify-proxy/
```

启动：

```bash
cd /docker/notify-proxy
docker compose up -d --build
```

重启：

```bash
cd /docker/notify-proxy
docker compose restart
```

查看日志：

```bash
docker logs -f notify-proxy
```

## 依赖网络

本服务默认采用 **IP + 端口** 的最简单方式，不依赖额外 Docker 网络。你只需要把容器端口映射到宿主机即可。
## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `BARK_URL` | `http://<BARK_SERVER_IP>:8080/<BARK_DEVICE_KEY>` | 需要替换为你自己的 Bark 服务地址和设备 key |
| `LISTEN_PORT` | `55304` | 监听端口，通常不用改 |
| `SERVER_BASE_URL` | `http://<YOUR_SERVER_IP>:55304` | 需要替换为你自己的服务器公网 IP 或域名 |
| `IMAGES_DIR` | `/data/images` | 图片持久化目录 |

## 企业微信配置建议

企业微信里把 Webhook 填成：

```text
http://<YOUR_SERVER_IP>:55304/cgi-bin/webhook/send
```

如果你的上游会自动拼签名参数，确保基础地址后面已经有路径和 `?`，避免变成非法 URL。

如果你打算自己通过域名访问，也可以替换成自己的域名，例如：

```text
https://notify.example.com
```

具体填什么，取决于你自己的接入程序要求。对于这份公开版，**默认示例是 IP + 端口**。

## 说明

企业微信图片不是通过 URL 直传，而是以 `{"image":{"base64":"..."}}` 形式到达代理。代理会：

1. 解码 Base64 图片
2. 保存到本地 `/data/images`
3. 返回图片 URL 给 Bark
4. Bark 再把图片展示给手机

这样就能同时支持文本和图片。

## 备注

飞书、钉钉、Telegram 的中转逻辑已移除，只保留企业微信，代码更干净。
