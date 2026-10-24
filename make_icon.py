"""生成本程序的图标（朱红底 + 白「书」）。"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")

size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, size - 8, size - 8], radius=48, fill=(178, 58, 46, 255))

# 字体不随仓库分发，按平台常见中文字体挑一个
CANDIDATES = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simsun.ttc"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc"),
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
f = None
for path in CANDIDATES:
    if os.path.exists(path):
        try:
            f = ImageFont.truetype(path, 150)
            break
        except OSError:
            continue
if f is None:
    raise SystemExit("找不到能画中文的字体，请安装思源黑体/宋体后重试")

bbox = d.textbbox((0, 0), "书", font=f)
w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), "书", font=f,
       fill=(251, 247, 240, 255))

img.save(os.path.join(ASSETS, "icon.png"))
img.save(os.path.join(ASSETS, "icon.ico"),
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon ok")
