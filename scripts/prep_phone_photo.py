#!/usr/bin/env python3
"""Turn a photo of a handset on a plain background into the demo phone skin.

Cuts the handset out (navy body, silver keys, dark shadows count as handset; warm wood does not),
straightens and brightens it, finds the LCD and the twelve keys, places the soft keys from the 3310's
proportions, and writes web/public/phone.webp plus web/src/phone-layout.json (positions in % of the image).

Usage: uv run --with pillow --with numpy python scripts/prep_phone_photo.py photo.jpg [debug_dir]
Check debug_dir/debug2.png: red = LCD, blue = hit areas. Re-run with another photo any time.
"""
import json, math, sys
from collections import deque
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageOps, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1]); dbg_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "demo" / "phone-debug"
web_public = ROOT / "web" / "public"; layout_out = ROOT / "web" / "src" / "phone-layout.json"
dbg_dir.mkdir(parents=True, exist_ok=True)
im = Image.open(src).convert("RGB"); W, H = im.size
a = np.asarray(im).astype(np.int16); r, g, b = a[...,0], a[...,1], a[...,2]
warm = r - b; mx = a.max(axis=2); mn = a.min(axis=2); sat = mx - mn
# handset = navy body (blue over red), silver (bright, colourless) or deep shadow; grey wood is warm and mid-bright
phone = (warm < 2) | ((sat < 14) & (mx > 120)) | ((sat < 22) & (mx < 95))
m = Image.fromarray((phone*255).astype(np.uint8)).filter(ImageFilter.MedianFilter(15)).filter(ImageFilter.MinFilter(7))
mask = np.asarray(m) > 127

def largest_component(mask, scale):
    small = mask[::scale, ::scale]; h, w = small.shape; seen = np.zeros_like(small, dtype=bool); best = None
    for y0 in range(h):
        for x0 in range(w):
            if small[y0, x0] and not seen[y0, x0]:
                q = deque([(y0, x0)]); seen[y0, x0] = True; pts = []
                while q:
                    y, x = q.popleft(); pts.append((y, x))
                    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                        ny, nx = y+dy, x+dx
                        if 0 <= ny < h and 0 <= nx < w and small[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True; q.append((ny, nx))
                if best is None or len(pts) > len(best): best = pts
    comp = np.zeros_like(small, dtype=bool); comp[[p[0] for p in best], [p[1] for p in best]] = True
    return np.kron(comp, np.ones((scale, scale), dtype=bool))[:mask.shape[0], :mask.shape[1]]

comp = largest_component(mask, 4)
comp = np.asarray(Image.fromarray((comp*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))) > 127  # undo erosion
filled = np.zeros_like(comp)
for y in range(H):
    row = np.where(comp[y])[0]
    if len(row): filled[y, row.min():row.max()+1] = True
# smooth the per-row extents (removes small side bumps)
rows = np.where(filled.any(axis=1))[0]
L = np.array([np.where(filled[y])[0].min() for y in rows]); R = np.array([np.where(filled[y])[0].max() for y in rows])
def smooth(v, k=31):
    pad = np.pad(v, (k//2, k//2), mode="edge"); return np.convolve(pad, np.ones(k)/k, mode="valid")
Ls, Rs = smooth(L), smooth(R)
lower = slice(int(len(rows)*0.4), len(rows))
cfit = np.polyfit(rows[lower], (Ls[lower] + Rs[lower]) / 2, 1)
width_med = float(np.median((Rs - Ls)[lower]))
filled2 = np.zeros_like(filled)
for i, y in enumerate(rows):
    cx = np.polyval(cfit, y); half = 0.53 * width_med
    lo = int(max(L[i], Ls[i] - 4, cx - half)); hi = int(min(R[i], Rs[i] + 4, cx + half))
    if hi > lo: filled2[y, lo:hi + 1] = True
mid = rows[int(len(rows)*0.15):int(len(rows)*0.85)]
center = (Ls[int(len(rows)*0.15):int(len(rows)*0.85)] + Rs[int(len(rows)*0.15):int(len(rows)*0.85)]) / 2
angle = math.degrees(math.atan(np.polyfit(mid, center, 1)[0]))
print(f"tilt {angle:.2f} deg, width at middle {np.median(Rs-Ls):.0f}px")
rgba = im.convert("RGBA")
rgba.putalpha(Image.fromarray((filled2*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0)))
rgba = rgba.rotate(angle, resample=Image.BICUBIC, expand=False, center=(W/2, H/2))
bbox = rgba.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox(); pad = 4
crop = rgba.crop((max(0, bbox[0]-pad), max(0, bbox[1]-pad), min(W, bbox[2]+pad), min(H, bbox[3]+pad)))
rgb = crop.convert("RGB"); al = crop.getchannel("A")
rgb = ImageOps.autocontrast(rgb, cutoff=1); rgb = ImageEnhance.Brightness(rgb).enhance(1.05)
rgb = ImageEnhance.Color(rgb).enhance(0.92); rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.4, percent=55, threshold=3))
crop = rgb.convert("RGBA"); crop.putalpha(al); cw, ch = crop.size
print(f"crop {cw}x{ch}")
ca = np.asarray(crop.convert("RGB")).astype(np.int16); cal = np.asarray(al) > 128
cr, cg, cb = ca[...,0], ca[...,1], ca[...,2]
# LCD: rows in the upper 60 % where a wide greenish run exists
lcd = (cg > cr + 6) & (cg > cb + 10) & (cg > 90) & cal; lcd[int(ch*0.6):] = False
lcd = np.asarray(Image.fromarray((lcd*255).astype(np.uint8)).filter(ImageFilter.MedianFilter(11))) > 127
rowcount = lcd.sum(axis=1); wide = np.where(rowcount > 0.6 * rowcount.max())[0]
y0, y1 = wide.min(), wide.max(); cols = np.where(lcd[y0:y1].sum(axis=0) > 0.6*(y1-y0))[0]; x0, x1 = cols.min(), cols.max()
lcd_box = (int(x0), int(y0), int(x1), int(y1))
lcd_pixels = ca[y0:y1, x0:x1].reshape(-1, 3); lcd_color = tuple(int(v) for v in np.median(lcd_pixels, axis=0))
print("lcd", lcd_box, "median color", "#%02x%02x%02x" % lcd_color)
# keys: bright low-saturation blobs in the lower half
cmx = ca.max(axis=2); cmn = ca.min(axis=2)
keys = ((cmx - cmn) < 40) & (cmx > 150) & cal; keys[:int(ch*0.62)] = False
kmask = np.asarray(Image.fromarray((keys*255).astype(np.uint8)).filter(ImageFilter.MedianFilter(7))) > 127
sc = 2; sm = kmask[::sc, ::sc]; hh, ww = sm.shape; seen = np.zeros_like(sm, dtype=bool); blobs = []
for yy in range(hh):
    for xx in range(ww):
        if sm[yy, xx] and not seen[yy, xx]:
            q = deque([(yy, xx)]); seen[yy, xx] = True; pts = []
            while q:
                y, x = q.popleft(); pts.append((y, x))
                for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < hh and 0 <= nx < ww and sm[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True; q.append((ny, nx))
            if len(pts) > 150:
                ys = [p[0]*sc for p in pts]; xs = [p[1]*sc for p in pts]
                blobs.append((min(xs), min(ys), max(xs), max(ys)))
if len(blobs) != 12:
    print("blobs before filtering:", [(b, ) for b in blobs])
    areas = [(b[2]-b[0])*(b[3]-b[1]) for b in blobs]; med = float(np.median(areas))
    blobs = sorted(blobs, key=lambda b: abs((b[2]-b[0])*(b[3]-b[1]) - med))[:12]
assert len(blobs) == 12, f"expected 12 key blobs, got {len(blobs)}"
# order: rows by y (middle column sits lower), columns by x
blobs.sort(key=lambda b: (b[1] + b[3]) / 2)
rows4 = [sorted(blobs[i*3:(i+1)*3], key=lambda b: b[0]) for i in range(4)]
labels = [["1","2","3"],["4","5","6"],["7","8","9"],["*","0","#"]]
def pct(x0, y0, x1, y1, grow=1.12):
    cx, cy = (x0+x1)/2, (y0+y1)/2; w, h = (x1-x0)*grow, (y1-y0)*grow
    return {"x": round((cx-w/2)/cw*100, 2), "y": round((cy-h/2)/ch*100, 2), "w": round(w/cw*100, 2), "h": round(h/ch*100, 2)}
hits = []
for row, labs in zip(rows4, labels):
    for bl, lab in zip(row, labs):
        hits.append({"key": lab, **pct(*bl)})
# soft keys and select key from screen/keypad geometry (proportions measured on the 3310)
lx0, ly0, lx1, ly1 = lcd_box; lw = lx1 - lx0; gap = rows4[0][0][1] - ly1
sel = (lx0 + 0.22*lw, ly1 + 0.26*gap, lx1 - 0.22*lw, ly1 + 0.42*gap)
cky = (lx0 + 0.03*lw, ly1 + 0.47*gap, lx0 + 0.30*lw, ly1 + 0.84*gap)
arw = (lx1 - 0.42*lw, ly1 + 0.52*gap, lx1 - 0.02*lw, ly1 + 0.90*gap)
hits.append({"key": "select", **pct(*sel, grow=1.0)}); hits.append({"key": "clear", **pct(*cky, grow=1.0)}); hits.append({"key": "mode", **pct(*arw, grow=1.0)})
layout = {"aspect": round(ch/cw, 4), "lcd": pct(lx0, ly0, lx1, ly1, grow=1.0), "lcdColor": "#%02x%02x%02x" % lcd_color, "keys": hits}
layout_out.write_text(json.dumps(layout, indent=2) + "\n")
# debug overlay
dbg = crop.copy(); d = ImageDraw.Draw(dbg)
def box(p): return (p["x"]/100*cw, p["y"]/100*ch, (p["x"]+p["w"])/100*cw, (p["y"]+p["h"])/100*ch)
d.rectangle(box(layout["lcd"]), outline=(255,0,0,255), width=3)
for hk in hits: d.rectangle(box(hk), outline=(0,120,255,255), width=3)
dbg.save(dbg_dir / "debug2.png")
# export: webp with alpha, 2x of the on-screen size (240 css px wide)
target_w = 480; out = crop.resize((target_w, round(ch * target_w / cw)), Image.LANCZOS)
web_public.mkdir(parents=True, exist_ok=True)
out.save(web_public / "phone.webp", "WEBP", quality=84, method=6)
out.save(dbg_dir / "phone_final.png")
print("saved", web_public / "phone.webp", (web_public / "phone.webp").stat().st_size, "bytes", out.size)
