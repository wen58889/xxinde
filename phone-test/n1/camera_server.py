#!/usr/bin/env python3
"""
camera_server.py - N1 轻量级按需拍照服务
替代 go2rtc，无视频推流，每次请求拍一张照片返回

接口：
  GET /snapshot      → 拍一张照片，返回 1280×720 JPEG
  GET /health        → 健康检查，返回 "ok"

启动：python3 camera_server.py
端口：1984（与后端 device_camera_port 对应）
依赖：仅需 Python 3 标准库 + opencv-python（或 ffmpeg 作为备选）
"""

import io
import os
import sys
import logging
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────────
CAMERA_DEVICE = os.environ.get("CAMERA_DEVICE", "/dev/video0")
WIDTH  = int(os.environ.get("CAMERA_WIDTH",  "1280"))
HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "720"))
PORT   = int(os.environ.get("CAMERA_PORT",   "1984"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "85"))
# ──────────────────────────────────────────────────────────


# ── 摄像头后端（优先 OpenCV，备选 ffmpeg）───────────────────

def _capture_cv2() -> bytes:
    import cv2
    cap = cv2.VideoCapture(CAMERA_DEVICE)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    # 跳过缓冲帧，拿最新一帧
    for _ in range(3):
        cap.grab()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise RuntimeError("cv2 capture returned no frame")
    _, buf = cv2.imencode(
        ".jpg", frame,
        [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
    )
    return buf.tobytes()


def _capture_ffmpeg() -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", f"{WIDTH}x{HEIGHT}",
            "-i", CAMERA_DEVICE,
            "-vframes", "1",
            "-q:v", "3",
            "-f", "image2",
            "pipe:1",
        ],
        capture_output=True,
        timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[-200:].decode(errors='ignore')}")
    if not result.stdout:
        raise RuntimeError("ffmpeg produced no output")
    return result.stdout


# 选择后端
try:
    import cv2 as _cv2_test
    capture_frame = _capture_cv2
    logger.info("摄像头后端：OpenCV")
except ImportError:
    capture_frame = _capture_ffmpeg
    logger.info("摄像头后端：ffmpeg（OpenCV 未安装）")


# ── HTTP 处理器 ────────────────────────────────────────────

_lock = threading.Lock()   # 防止并发同时开摄像头


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 关闭每次请求的 access log 噪声

    def do_GET(self):
        if self.path.startswith("/snapshot"):
            self._handle_snapshot()
        elif self.path == "/health":
            self._send_text(200, "ok")
        else:
            self._send_text(404, "not found")

    def _handle_snapshot(self):
        with _lock:
            try:
                data = capture_frame()
            except Exception as exc:
                logger.error("拍照失败: %s", exc)
                self._send_text(503, f"Camera error: {exc}")
                return

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        self.wfile.write(data)
        logger.debug("拍照成功 %d bytes", len(data))

    def _send_text(self, code: int, msg: str):
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── 启动 ───────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("摄像头设备: %s  分辨率: %dx%d  端口: %d", CAMERA_DEVICE, WIDTH, HEIGHT, PORT)

    # 启动前检测摄像头是否存在
    if not os.path.exists(CAMERA_DEVICE):
        logger.error("摄像头设备不存在: %s", CAMERA_DEVICE)
        logger.error("可用设备: %s", " ".join(
            f for f in os.listdir("/dev") if f.startswith("video")
        ) or "无")
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    logger.info("拍照服务已启动，监听 :%d/snapshot", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("已停止")
