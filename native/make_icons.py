from PIL import Image, ImageDraw, ImageFont
import os
GOLD = (212, 175, 55, 255); DARK = (10, 14, 26, 255)

def make(sz):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(sz * 0.22)
    d.rounded_rectangle([0, 0, sz - 1, sz - 1], radius=r, fill=DARK)
    w = max(2, int(sz * 0.035))
    d.rounded_rectangle([w // 2, w // 2, sz - 1 - w // 2, sz - 1 - w // 2], radius=r, outline=GOLD, width=w)
    font = None
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if os.path.exists(p):
            font = ImageFont.truetype(p, int(sz * 0.58)); break
    if font is None:
        font = ImageFont.load_default()
    bb = d.textbbox((0, 0), "S", font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((sz - tw) / 2 - bb[0], (sz - th) / 2 - bb[1]), "S", font=font, fill=GOLD)
    return img

P = "/home/user/build/proj"
os.chdir(P + "/apk")
for k, v in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
    os.makedirs("res/mipmap-%s" % k, exist_ok=True)
    make(v).save("res/mipmap-%s/ic_launcher.png" % k)
big = make(512)
os.makedirs(P + "/golaunch", exist_ok=True)
os.makedirs(P + "/eapp/build", exist_ok=True)
for p in [P + "/golaunch/icon.ico", P + "/eapp/build/icon.ico"]:
    big.save(p, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
big.save(P + "/eapp/build/icon.png")
print("icons ok")
