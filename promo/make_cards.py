"""生成宣传片的标题卡/结尾卡（纸色、墨黑、朱红；角上是裁切线母题）。"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1680, 1000
PAPER = (244, 241, 234)
INK = (28, 26, 23)
RED = (178, 58, 46)
GREY = (205, 199, 188)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

SERIF = "C:/Windows/Fonts/NotoSerifSC-VF.ttf"
SANS = "C:/Windows/Fonts/msyh.ttc"
SANSB = "C:/Windows/Fonts/msyhbd.ttc"


def font(path, size):
    return ImageFont.truetype(path, size)


def spaced(draw, xy, text, f, fill, spacing=6):
    """手工字距，中文标题更贵气一点。"""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + spacing


def crop_marks(d, colour=GREY, arm=34, inset=56):
    w = 2
    for x0, y0, sx, sy in ((inset, inset, 1, 1), (W - inset, inset, -1, 1),
                           (inset, H - inset, 1, -1), (W - inset, H - inset, -1, -1)):
        d.line([(x0, y0), (x0 + sx * arm, y0)], fill=colour, width=w)
        d.line([(x0, y0), (x0, y0 + sy * arm)], fill=colour, width=w)


def title_card():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    crop_marks(d)

    # 左侧朱红细线 + 小标签
    d.rectangle([120, 250, 124, 700], fill=RED)
    spaced(d, (170, 258), "XPLUS · BOOK TOOLKIT", font(SANS, 26), RED, 5)

    d.text((168, 330), "书籍制作工具", font=font(SERIF, 168), fill=INK)
    d.text((172, 560), "把 PDF 排成能折、能订、能裁的书",
           font=font(SERIF, 52), fill=(70, 64, 56))

    d.line([(172, 668), (760, 668)], fill=RED, width=3)
    spaced(d, (172, 700), "排版全程本地  ·  文件不上传", font(SANS, 28), (110, 102, 92), 2)

    # 右下角：一叠纸的意象
    for i, (dx, dy) in enumerate(((0, 0), (22, -16), (44, -32))):
        d.rectangle([W - 560 + dx, 560 + dy, W - 210 + dx, 760 + dy],
                    outline=(196, 189, 178), width=2)
    d.line([(W - 385, 560), (W - 385, 760)], fill=RED, width=2)

    img.save(os.path.join(OUT, "card_title.png"))


def outro_card():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    crop_marks(d)

    spaced(d, (150, 150), "我做的印书工具  ·  免费用", font(SANS, 26), RED, 4)
    d.text((146, 220), "拿去用", font=font(SERIF, 150), fill=INK)

    rows = [("拼版", "小册子 / 四堆叠 / 4合1 / A6"),
            ("封面", "书脊厚度自己算，裁切线留在成品外"),
            ("打印", "按面挑，双面走短边还是长边")]
    y = 460
    col = 540                      # 灰色说明统一对齐线
    for big, small in rows:
        d.text((150, y), big, font=font(SERIF, 56), fill=INK)
        d.text((col, y + 18), small, font=font(SANS, 30), fill=(110, 102, 92))
        y += 104

    # 右侧：一叠纸的意象，压住右边的大片留白
    for dx, dy in ((0, 0), (26, -20), (52, -40)):
        d.rectangle([W - 520 + dx, 372 + dy, W - 140 + dx, 650 + dy],
                    outline=(198, 191, 180), width=2)
    d.line([(W - 330, 372), (W - 330, 650)], fill=RED, width=2)

    d.line([(150, 830), (W - 150, 830)], fill=GREY, width=2)
    d.text((150, 862), "作者   LOU0122", font=font(SANS, 30), fill=INK)
    url = "space.bilibili.com/702283845"
    d.text((W - 150 - d.textlength(url, font=font(SANS, 28)), 862), url,
           font=font(SANS, 28), fill=RED)

    img.save(os.path.join(OUT, "card_outro.png"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    title_card()
    outro_card()
    print("cards ok")
