"""Creative Studio engines for Smash AI Pro.

DesignForge  - template-based graphic design, QR codes, icon packs (Pillow, sync).
VideoForge   - trim/resize/speed/text/GIF/audio-extract (ffmpeg, async jobs).
3DForge      - lives entirely client-side (three.js) - no server cost.

Outputs land in CREATIVE_DIR (default /tmp/smash-creative) and are served
through /creative-file/{name} with strict traversal protection.
(C) 2026 Ruwayne Campher - Smash AI Pro.
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageDraw, ImageFilter, ImageFont

router = APIRouter()

OUT_DIR = Path(os.environ.get("CREATIVE_DIR", "/tmp/smash-creative"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_VIDEO_BYTES = 60 * 1024 * 1024  # 60 MB upload cap (free-tier RAM friendly)
JOB_TTL = 3600  # 1 hour

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


def _font_path():
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _font(size):
    p = _font_path()
    try:
        if p:
            return ImageFont.truetype(p, size)
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _ffmpeg():
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise HTTPException(500, "ffmpeg unavailable on this host")


def _hex(c, default="#D4AF37"):
    if isinstance(c, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", c.strip()):
        return c.strip() if c.strip().startswith("#") else "#" + c.strip()
    return default


def _new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _safe_out(name):
    """Resolve a served filename strictly inside OUT_DIR."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", name or ""):
        raise HTTPException(404, "not found")
    p = (OUT_DIR / name).resolve()
    if not str(p).startswith(str(OUT_DIR.resolve())) or not p.exists():
        raise HTTPException(404, "not found")
    return p


# ============================== DesignForge ==============================

TEMPLATES = {
    "youtube": (1280, 720),
    "ig-post": (1080, 1080),
    "story": (1080, 1920),
    "x-post": (1200, 675),
    "linkedin": (1584, 396),
    "card": (1050, 600),
    "poster": (1240, 1754),
    "quote": (1080, 1080),
}

PALETTES = {
    "gold":    {"bg1": "#0A0E1A", "bg2": "#1A1F33", "accent": "#D4AF37", "text": "#E8E6DF", "muted": "#9A978C"},
    "ocean":   {"bg1": "#04121F", "bg2": "#0A2A43", "accent": "#38BDF8", "text": "#EAF6FF", "muted": "#7FA8C4"},
    "mono":    {"bg1": "#101010", "bg2": "#232323", "accent": "#F5F5F5", "text": "#FAFAFA", "muted": "#9C9C9C"},
    "sunset":  {"bg1": "#2B0B1A", "bg2": "#7A1F3D", "accent": "#FB923C", "text": "#FFF3E8", "muted": "#D3A08C"},
    "forest":  {"bg1": "#071A10", "bg2": "#123524", "accent": "#4ADE80", "text": "#EDFBF1", "muted": "#8FB79C"},
    "royal":   {"bg1": "#120A2B", "bg2": "#2C1A63", "accent": "#A78BFA", "text": "#F3EEFF", "muted": "#A99BD4"},
}


def _bg_image(style, w, h, pal):
    bg1, bg2, acc = _hex(pal["bg1"]), _hex(pal["bg2"]), _hex(pal["accent"])
    img = Image.new("RGB", (w, h), bg1)
    if style == "solid":
        return img
    d = ImageDraw.Draw(img)
    if style in ("gradient", "diagonal"):
        c1 = tuple(int(bg1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        c2 = tuple(int(bg2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        steps = w + h if style == "diagonal" else h
        px = img.load()
        for s in range(steps):
            t = s / max(1, steps - 1)
            col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
            if style == "diagonal":
                d.line([(s, 0), (0, s)], fill=col)
                d.line([(s, h), (w, s - (w - h) if s > w else 0)], fill=col)
            else:
                d.line([(0, s), (w, s)], fill=col)
    elif style == "radial":
        c2 = tuple(int(bg2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        for r in range(int((w + h) / 1.4), 0, -6):
            t = r / max(1, (w + h) / 1.4)
            col = tuple(int(255 * 0 + c2[i] * (1 - t) + int(bg1.lstrip("#")[i:i + 2], 16) * t) for i in range(3))
            d.ellipse([w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r], fill=col)
    elif style == "grid":
        img = _bg_image("gradient", w, h, pal)
        d = ImageDraw.Draw(img)
        step = max(40, w // 16)
        for x in range(0, w, step):
            d.line([(x, 0), (x, h)], fill=acc, width=1)
        for y in range(0, h, step):
            d.line([(0, y), (w, y)], fill=acc, width=1)
        img = img.filter(ImageFilter.GaussianBlur(0.4))
        ov = Image.new("RGB", (w, h), bg1)
        img = Image.blend(img, ov, 0.55)
    elif style == "waves":
        img = _bg_image("gradient", w, h, pal)
        d = ImageDraw.Draw(img, "RGBA")
        import math
        acc_rgba = tuple(int(acc.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (60,)
        for k in range(5):
            pts = []
            for x in range(0, w + 8, 8):
                y = h * (0.25 + 0.13 * k) + math.sin(x / (140 + 40 * k) + k * 1.7) * h * 0.05
                pts.append((x, y))
            d.line(pts, fill=acc_rgba, width=max(2, h // 320))
    return img


def _fit_text(d, text, max_w, start, min_size=18):
    size = start
    while size > min_size:
        f = _font(size)
        bb = d.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= max_w:
            return f, bb
        size = int(size * 0.92)
    return _font(min_size), d.textbbox((0, 0), text, font=_font(min_size))


def _wrap(d, text, max_w, size):
    f = _font(size)
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textbbox((0, 0), t, font=f)[2] <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines, f


def render_design(d):
    tpl = d.get("template", "youtube")
    w, h = TEMPLATES.get(tpl, (1280, 720))
    pal = dict(PALETTES.get(d.get("palette", "gold"), PALETTES["gold"]))
    for k in ("bg1", "bg2", "accent", "text", "muted"):
        if d.get("colors", {}).get(k):
            pal[k] = _hex(d["colors"][k], pal[k])
    img = _bg_image(d.get("style", "gradient"), w, h, pal).convert("RGBA")
    dr = ImageDraw.Draw(img)
    layout = d.get("layout", "center")
    title = (d.get("title") or "YOUR HEADLINE").strip()[:90]
    sub = (d.get("subtitle") or "").strip()[:140]
    cta = (d.get("cta") or "").strip()[:30]
    acc, txt, mut = _hex(pal["accent"]), _hex(pal["text"]), _hex(pal["muted"])

    logo_img = None
    logo_data = d.get("logo") or ""
    if logo_data.startswith("data:image"):
        try:
            raw = base64.b64decode(logo_data.split(",", 1)[1])
            logo_img = Image.open(io.BytesIO(raw)).convert("RGBA")
            lw = int(w * 0.14)
            logo_img.thumbnail((lw, lw))
        except Exception:
            logo_img = None

    if layout == "center":
        ty0 = int(h * 0.30 if logo_img else h * 0.36)
        if logo_img:
            img.paste(logo_img, ((w - logo_img.width) // 2, int(h * 0.12)), logo_img)
        f, bb = _fit_text(dr, title, int(w * 0.86), int(h * 0.16))
        dr.text(((w - (bb[2] - bb[0])) / 2 - bb[0], ty0), title, font=f, fill=acc)
        if sub:
            lines, sf = _wrap(dr, sub, int(w * 0.8), max(20, int(h * 0.042)))
            y = ty0 + (bb[3] - bb[1]) + int(h * 0.05)
            for ln in lines[:3]:
                lbb = dr.textbbox((0, 0), ln, font=sf)
                dr.text(((w - (lbb[2] - lbb[0])) / 2 - lbb[0], y), ln, font=sf, fill=txt)
                y += int((lbb[3] - lbb[1]) * 1.35)
    elif layout == "left":
        x0 = int(w * 0.07)
        dr.rectangle([x0, int(h * 0.18), x0 + max(4, w // 160), int(h * 0.62)], fill=acc)
        x1 = x0 + max(4, w // 160) + int(w * 0.03)
        y = int(h * 0.20)
        if logo_img:
            img.paste(logo_img, (x1, int(h * 0.06)), logo_img)
        lines, f = _wrap(dr, title, int(w * 0.8), int(h * 0.11))
        for ln in lines[:3]:
            dr.text((x1, y), ln, font=f, fill=acc)
            y += int((f.size) * 1.18)
        if sub:
            y += int(h * 0.02)
            slines, sf = _wrap(dr, sub, int(w * 0.72), max(18, int(h * 0.042)))
            for ln in slines[:3]:
                dr.text((x1, y), ln, font=sf, fill=txt)
                y += int(sf.size * 1.4)
    else:  # bottom - thumbnail style
        if logo_img:
            img.paste(logo_img, (int(w * 0.05), int(h * 0.06)), logo_img)
        lines, f = _wrap(dr, title.upper(), int(w * 0.9), int(h * 0.17))
        y = h - int(h * 0.10)
        for ln in reversed(lines[:3]):
            lbb = dr.textbbox((0, 0), ln, font=f)
            lh = lbb[3] - lbb[1]
            y -= int(lh * 1.12)
            dr.text((int(w * 0.05) - lbb[0] + 3, y + 3), ln, font=f, fill="#000000")
            dr.text((int(w * 0.05) - lbb[0], y), ln, font=f, fill=acc)
        if sub:
            sbb_lines, sf = _wrap(dr, sub, int(w * 0.85), max(18, int(h * 0.045)))
            if sbb_lines:
                dr.text((int(w * 0.05), int(h * 0.08 if not logo_img else h * 0.24)), sbb_lines[0], font=sf, fill=txt)

    if cta:
        cf = _font(max(18, int(h * 0.038)))
        cbb = dr.textbbox((0, 0), cta, font=cf)
        cw, ch = cbb[2] - cbb[0] + int(w * 0.06), cbb[3] - cbb[1] + int(h * 0.05)
        cx = (w - cw) // 2 if layout == "center" else int(w * 0.07)
        cy = int(h * 0.80)
        dr.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=ch // 2, fill=acc)
        dr.text((cx + int(w * 0.03) - cbb[0], cy + (ch - (cbb[3] - cbb[1])) / 2 - cbb[1]), cta, font=cf, fill="#0A0E1A")

    wm = _font(max(13, int(h * 0.020)))
    dr.text((w - dr.textlength("Smash AI Pro\u2122", font=wm) - 16, h - int(h * 0.045)),
            "Smash AI Pro\u2122", font=wm, fill=mut)
    out = img.convert("RGB")
    name = _new_id("design") + ".png"
    out.save(OUT_DIR / name, "PNG", optimize=True)
    return name, w, h


@router.post("/api/design")
async def api_design(request: Request):
    try:
        d = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    name, w, h = render_design(d)
    return {"id": name, "url": f"/creative-file/{name}", "width": w, "height": h}


@router.post("/api/design/qr")
async def api_qr(request: Request):
    import qrcode
    d = await request.json()
    text = (d.get("text") or "").strip()[:2000]
    if not text:
        raise HTTPException(400, "text required")
    pal = PALETTES.get(d.get("palette", "gold"), PALETTES["gold"])
    qr = qrcode.QRCode(border=2, box_size=16)
    qr.add_data(text)
    qr.make(fit=True)
    imgc = qr.make_image(fill_color=_hex(pal["accent"]), back_color=_hex(pal["bg1"])).convert("RGB")
    name = _new_id("qr") + ".png"
    imgc.save(OUT_DIR / name, "PNG")
    return {"id": name, "url": f"/creative-file/{name}"}


@router.post("/api/design/icons")
async def api_icons(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "image too large (8 MB cap)")
    try:
        src = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        raise HTTPException(400, "not a readable image")
    name = _new_id("icons")
    zpath = OUT_DIR / (name + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        sizes = {"16": 16, "32": 32, "48": 48, "72": 72, "96": 96, "144": 144, "192": 192, "512": 512}
        ico_frames = []
        for label, sz in sizes.items():
            ic = src.copy()
            ic.thumbnail((sz, sz))
            canvas = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
            canvas.paste(ic, ((sz - ic.width) // 2, (sz - ic.height) // 2), ic)
            z.writestr(f"icon-{label}.png", _png_bytes(canvas))
            if sz in (16, 32, 48):
                ico_frames.append(canvas)
        mask = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        m = src.copy()
        m.thumbnail((410, 410))
        mask.paste(m, ((512 - m.width) // 2, (512 - m.height) // 2), m)
        z.writestr("icon-maskable-512.png", _png_bytes(mask))
        bio = io.BytesIO()
        ico_frames[0].save(bio, "ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=ico_frames[1:])
        z.writestr("favicon.ico", bio.getvalue())
    return {"id": name + ".zip", "url": f"/creative-file/{name}.zip"}


def _png_bytes(img):
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


# ============================== VideoForge ==============================

_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()

RESIZE_PRESETS = {
    "720p": (1280, 720), "1080p": (1920, 1080), "square": (1080, 1080),
    "story": (1080, 1920), "x-post": (1200, 675),
}


def _cleanup_jobs():
    now = time.time()
    with _JOBS_LOCK:
        for jid in [k for k, v in _JOBS.items() if now - v.get("created", now) > JOB_TTL]:
            job = _JOBS.pop(jid, None)
            for key in ("in", "out"):
                try:
                    if job and job.get(key):
                        (OUT_DIR / job[key]).unlink(missing_ok=True)
                except Exception:
                    pass


def _atempo_chain(speed):
    filters = []
    s = speed
    while s > 2.0:
        filters.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        filters.append("atempo=0.5")
        s /= 0.5
    filters.append(f"atempo={s:.4f}")
    return filters


def _video_worker(job_id, ops):
    job = _JOBS[job_id]
    try:
        ff = _ffmpeg()
        src = str(OUT_DIR / job["in"])
        mode = ops.get("mode", "mp4")
        cmd = [ff, "-y"]
        start = float(ops.get("start") or 0)
        end = float(ops.get("end") or 0)
        if start > 0:
            cmd += ["-ss", f"{start:.3f}"]
        if end > start > 0 or (end > 0 and start == 0):
            cmd += ["-to", f"{end:.3f}"]
        cmd += ["-i", src]
        vf, af = [], []
        speed = float(ops.get("speed") or 1.0)
        if speed and abs(speed - 1.0) > 0.01:
            speed = min(max(speed, 0.25), 4.0)
            vf.append(f"setpts=PTS/{speed}")
            af += _atempo_chain(speed)
        preset = RESIZE_PRESETS.get(ops.get("resize") or "")
        if preset:
            rw, rh = preset
            vf.append(f"scale={rw}:{rh}:force_original_aspect_ratio=decrease")
            vf.append(f"pad={rw}:{rh}:(ow-iw)/2:(oh-ih)/2:color=0x0A0E1A")
            vf.append("setsar=1")
        text = (ops.get("text") or "").strip()[:120]
        if text and mode != "mp3":
            fp = _font_path()
            if fp:
                esc = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
                vf.append(
                    f"drawtext=fontfile={fp}:text='{esc}':fontcolor=white:fontsize=h/14:"
                    f"box=1:boxcolor=black@0.55:boxborderw=18:x=(w-text_w)/2:y=h-th-h/16")
        out_name = job_id + (".gif" if mode == "gif" else ".mp3" if mode == "mp3" else ".mp4")
        out = OUT_DIR / out_name
        if mode == "mp3":
            cmd += ["-vn"] + (["-af", ",".join(af)] if af else []) + ["-c:a", "libmp3lame", "-q:a", "2", str(out)]
            r = subprocess.run(cmd, capture_output=True, timeout=600)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode(errors="ignore")[-800:])
        elif mode == "gif":
            pal = OUT_DIR / (job_id + "-pal.png")
            gvf = list(vf) + ["fps=12", "scale=480:-1:flags=lanczos"]
            base = cmd + ["-vf", ",".join(gvf + ["palettegen=stats_mode=diff"]), str(pal)]
            subprocess.run(base, capture_output=True, timeout=600, check=True)
            flt = ",".join(gvf)
            cmd2 = cmd + ["-i", str(pal), "-filter_complex",
                          f"[0:v]{flt}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4", str(out)]
            r = subprocess.run(cmd2, capture_output=True, timeout=900)
            pal.unlink(missing_ok=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode(errors="ignore")[-800:])
        else:
            if vf:
                cmd += ["-vf", ",".join(vf)]
            if af:
                cmd += ["-af", ",".join(af)]
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    "-c:a", "aac", "-b:a", "128k", str(out)]
            r = subprocess.run(cmd, capture_output=True, timeout=900)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode(errors="ignore")[-800:])
        with _JOBS_LOCK:
            job["status"] = "done"
            job["out"] = out_name
            job["url"] = f"/creative-file/{out_name}"
            job["size"] = out.stat().st_size
    except Exception as e:
        with _JOBS_LOCK:
            job["status"] = "failed"
            job["error"] = str(e)[-500:]


@router.post("/api/video")
async def api_video(file: UploadFile = File(...), ops: str = Form("{}")):
    _cleanup_jobs()
    try:
        ops_d = json.loads(ops)
    except Exception:
        raise HTTPException(400, "ops must be JSON")
    job_id = _new_id("vid")
    ext = os.path.splitext(file.filename or "in.mp4")[1].lower() or ".mp4"
    if ext not in (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".mp3", ".wav", ".m4a"):
        raise HTTPException(400, "unsupported file type")
    in_name = job_id + "-in" + ext
    written = 0
    with open(OUT_DIR / in_name, "wb") as fh:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_VIDEO_BYTES:
                fh.close()
                (OUT_DIR / in_name).unlink(missing_ok=True)
                raise HTTPException(413, f"file too large ({MAX_VIDEO_BYTES // (1024*1024)} MB cap)")
            fh.write(chunk)
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "working", "created": time.time(), "in": in_name}
    threading.Thread(target=_video_worker, args=(job_id, ops_d), daemon=True).start()
    return {"job": job_id}


@router.get("/api/video/{job_id}")
def api_video_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "unknown or expired job")
        return JSONResponse({k: v for k, v in job.items() if k != "in"})


# ============================== file serving ==============================

@router.get("/creative-file/{name}")
def creative_file(name: str):
    p = _safe_out(name)
    return FileResponse(p, headers={"Cache-Control": "no-store"})
