"""把录屏剪成 16:9 宣传片：卡片 + 实机操作 + 静帧推移 + 旁白 + 字幕。

所有时间以 beats.json 为基准（beats 的 0 点 = 放行动作的瞬间，
比录屏开头晚 LEAD 秒）。跑完输出 out/promo_1080p.mp4。
"""
from __future__ import annotations

import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "clips", "raw.mp4")
BEATS = json.load(open(os.path.join(HERE, "beats.json"), encoding="utf-8"))
CLIPS = os.path.join(HERE, "clips")
OUT = os.path.join(HERE, "out")
AUD = os.path.join(HERE, "audio")

LEAD = 1.2          # 录屏起点比动作 0 点早这么多秒
W, H = 1920, 1080
UI_W, UI_H = 1684, 1000          # 录屏原尺寸，等比放到 1814x1080
PAPER = "0xF4F1EA"
FPS = 30


def beat(name: str) -> float:
    for k, t in BEATS:
        if k == name:
            return t
    raise KeyError(name)


def raw_t(offset: float) -> float:
    """beats 时间 → 录屏里的秒数"""
    return offset + LEAD


def run(cmd: list[str], cwd: str | None = None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + " ".join(cmd) + "\n" + (p.stderr or "")[-2000:])


def ui_filter(extra: str = "") -> str:
    chain = [f"scale=1814:1080:flags=lanczos", f"pad={W}:{H}:53:0:color={PAPER}",
             "setsar=1", f"fps={FPS}"]
    if extra:
        chain.insert(0, extra)
    return ",".join(chain)


def seg_from_raw(name: str, start: float, end: float):
    out = os.path.join(CLIPS, f"seg_{name}.mp4")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", RAW,
         "-vf", ui_filter(), "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", out])
    return out


def seg_still(name: str, png: str, seconds: float, zoom_from=1.0, zoom_to=1.10,
              focus=(0.5, 0.5)):
    """静帧垫画面。用户要求实机画面固定不推近，所以默认不缩放。"""
    out = os.path.join(CLIPS, f"seg_{name}.mp4")
    frames = int(seconds * FPS)
    if abs(zoom_to - zoom_from) < 1e-6:
        vf = (f"scale=1814:1080:flags=lanczos,"
              f"pad=1920:1080:53:0:color=0xF4F1EA,setsar=1,format=yuv420p")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-loop", "1", "-framerate", str(FPS), "-i", png,
             "-vf", vf, "-t", f"{seconds:.3f}", "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", out])
        return out
    # 先把静帧放大到 2 倍，再 zoompan，避免缩放糊
    fx, fy = focus
    z = f"{zoom_from}+({zoom_to}-{zoom_from})*on/{frames}"
    x = f"iw*{fx}-(iw/zoom/2)"
    y = f"ih*{fy}-(ih/zoom/2)"
    vf = (f"scale=3628:2160:flags=lanczos,"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
          f"setsar=1,format=yuv420p")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", png, "-vf", vf, "-frames:v", str(frames), "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", out])
    return out


def seg_file(name: str, path: str, seconds: float):
    """把已经做好的素材（片头动画）统一成 1920x1080 / 30fps。"""
    out = os.path.join(CLIPS, f"seg_{name}.mp4")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", path,
         "-vf", "scale=1920:1080:flags=lanczos,fps=30,setsar=1",
         "-t", f"{seconds:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", out])
    return out


def seg_clip(name: str, path: str, start: float, seconds: float):
    """截一段外部素材（VS Code 录屏），统一成 1920x1080 / 30fps。"""
    out = os.path.join(CLIPS, f"seg_{name}.mp4")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start:.3f}", "-i", path,
         "-vf", "scale=1920:1080:flags=lanczos,fps=30,setsar=1",
         "-t", f"{seconds:.3f}", "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", out])
    return out


def build_code_cuts():
    """三段代码快剪：拼版内核 → 页面骨架 → 主窗口；每段都是真滚轮快速下滑。"""
    plan = [("codeA.mp4", 0.70, 3.70), ("codeB.mp4", 0.50, 2.90),
            ("codeC.mp4", 0.45, 3.05)]
    parts = []
    for i, (src, a, b) in enumerate(plan):
        out = os.path.join(CLIPS, f"code_cut{i}.mp4")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{a:.2f}", "-i", os.path.join(CLIPS, src),
             "-t", f"{b - a:.2f}",
             "-vf", "scale=1920:1080:flags=lanczos,fps=30,setsar=1", "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", out])
        parts.append(out)
    lst = os.path.join(CLIPS, "code_cuts.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for q in parts:
            f.write(f"file '{q.replace(os.sep, '/')}'\n")
    out = os.path.join(CLIPS, "seg_code.mp4")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
         "-safe", "0", "-i", lst, "-c", "copy", out])
    return out


def seg_card(name: str, png: str, seconds: float, fade: float = 0.6):
    out = os.path.join(CLIPS, f"seg_{name}.mp4")
    vf = (f"scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS},"
          f"fade=t=in:st=0:d={fade},format=yuv420p")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-loop", "1", "-t", f"{seconds:.3f}", "-i", png,
         "-vf", vf, "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", out])
    return out


def grab_frame(t: float, path: str):
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{t:.3f}", "-i", RAW, "-frames:v", "1", path])


def build():
    os.makedirs(OUT, exist_ok=True)

    # ---------- 画面段落 ----------
    title_png = os.path.join(HERE, "assets", "card_title.png")
    outro_png = os.path.join(HERE, "assets", "card_outro.png")
    cover_still = os.path.join(HERE, "assets", "still_cover.png")
    print_still = os.path.join(HERE, "assets", "still_print.png")

    grab_frame(raw_t(beat("cover_page") + 2.6), cover_still)   # 书脊算完那一刻
    grab_frame(raw_t(beat("print_page") + 1.9), print_still)

    shots = []
    intro_mp4 = os.path.join(HERE, "clips", "intro.mp4")
    shots.append(("intro", seg_file("intro", intro_mp4, 7.0), 7.0))
    # 片头之后接 VS Code 源码镜头：证明这是自己写的
    # 代码段：不是录屏，是按片头那套纸墨语言逐帧画的代码纸（code_anim.py）
    code_mp4 = os.path.join(CLIPS, "code_anim.mp4")
    if not os.path.exists(code_mp4):
        raise SystemExit("缺 clips/code_anim.mp4：先跑 python code_anim.py")
    shots.append(("code", seg_clip("code", code_mp4, 0.0, 9.0), 9.0))

    home_a, home_b = beat("home") + 0.4, beat("booklet_page") - 0.55
    # 小册子页有 3.7 秒在等选文件，空界面不进片，从"文件已载入"前 1 秒起

    shots.append(("home", seg_from_raw("home", raw_t(home_a), raw_t(home_b)),
                  round(home_b - home_a, 3)))

    bk_a, bk_b = beat("file_loaded") - 1.0, beat("cover_page") - 1.0
    shots.append(("booklet", seg_from_raw("booklet", raw_t(bk_a), raw_t(bk_b)),
                  round(bk_b - bk_a, 3)))

    cv_a, cv_b = beat("cover_page") - 1.0, beat("print_page") - 0.3
    shots.append(("cover", seg_from_raw("cover", raw_t(cv_a), raw_t(cv_b)),
                  round(cv_b - cv_a, 3)))

    # 实机画面固定不推近：静帧只做短暂停留，宁短勿长
    shots.append(("cover_still", seg_still("cover_still", cover_still, 3.2,
                                           zoom_from=1.0, zoom_to=1.0), 3.2))

    pr_a, pr_b = beat("print_page") - 0.8, beat("home_again") - 0.2
    shots.append(("print", seg_from_raw("print", raw_t(pr_a), raw_t(pr_b)),
                  round(pr_b - pr_a, 3)))

    shots.append(("print_still", seg_still("print_still", print_still, 3.4,
                                           zoom_from=1.0, zoom_to=1.0), 3.4))

    shots.append(("outro", seg_card("outro", outro_png, 10.0), 10.0))

    # ---------- 拼接 ----------
    lst = os.path.join(CLIPS, "concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for _, path, _ in shots:
            f.write(f"file '{path.replace(os.sep, '/')}'\n")
    base = os.path.join(OUT, "base.mp4")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", base])

    # ---------- 时间轴 ----------
    # 用编码后文件的真实长度算位置：计划时长和实际常有几十毫秒差，
    # 差几次之后字幕/配音就会整体错位。
    def real_dur(path: str) -> float:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True).stdout.strip()
        return float(out)

    starts, t, fixed = {}, 0.0, []
    for name, path, dur in shots:
        d = real_dur(path)
        fixed.append((name, path, round(d, 3)))
        starts[name] = round(t, 3)
        t = round(t + d, 3)
    shots = fixed
    total = t
    print("shots:", {k: starts[k] for k in starts}, "total", total)

    # ---------- 旁白位置 ----------
    vo = [("v1", 0.35), ("v2", starts["code"] + 0.35),
          ("v3", starts["booklet"] + 0.4), ("v4", starts["cover"] + 0.4),
          ("v5", starts["print"] + 0.15), ("v6", starts["outro"] + 1.2)]

    def wav_dur(name: str) -> float:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", os.path.join(AUD, f"{name}.wav")],
            capture_output=True, text=True).stdout.strip()
        return float(out)

    # 字幕用 edge-tts 导出的逐词时间，跟声音严格对齐
    with open(os.path.join(AUD, "timing.json"), encoding="utf-8") as f:
        timing = json.load(f)
    subs, at = [], dict(vo)
    for vid, info in timing.items():
        for s in info.get("subs", []):
            subs.append((at[vid] + s["start"] + 0.10, at[vid] + s["end"] + 0.10,
                         s["text"], "High" if vid == "v6" else "Main"))
    ass = os.path.join(OUT, "subs.ass")
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Microsoft YaHei,44,&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,0,0,0,0,100,100,1,0,1,2.6,0.8,2,80,80,66,1
Style: High,Microsoft YaHei,44,&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,0,0,0,0,100,100,1,0,1,2.6,0.8,2,80,80,150,1

[Events]
Format: Layer, Start, End, Style, Name, Effect, Text
"""
    def ts(x: float) -> str:
        h = int(x // 3600); m = int(x % 3600 // 60); s = x % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    with open(ass, "w", encoding="utf-8") as f:
        f.write(header)
        for a, b, text, style in subs:
            f.write(f"Dialogue: 0,{ts(a)},{ts(b)},{style},,0,{text}\n")

    inputs, filt, labels = [], [], []
    idx = 1
    for name, at in vo:
        inputs += ["-i", os.path.join(AUD, f"{name}.wav")]
        ms = int(at * 1000)
        filt.append(f"[{idx}:a]aresample=48000,adelay={ms}|{ms},apad[a{idx}]")
        labels.append(f"[a{idx}]")
        idx += 1
    # 配乐：垫在人声下面 20 dB，人声一起就自动闪避（sidechaincompress）
    inputs += ["-i", os.path.join(AUD, "music.wav")]
    midx = idx
    fc = (";".join(filt)
          + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0,"
            "loudnorm=I=-15.5:TP=-1.5:LRA=11,aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo[vn]"
          + f";[{midx}:a]atrim=duration={total:.3f},asetpts=N/SR/TB,volume=-17dB,"
            f"afade=t=in:st=0:d=1.5,afade=t=out:st={total - 3.2:.2f}:d=3.2,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo[mus]"
          + ";[vn]asplit=2[vn1][vn2]"
          + ";[mus][vn1]sidechaincompress=threshold=0.025:ratio=5:attack=12:release=420[md]"
          + ";[vn2][md]amix=inputs=2:normalize=0,volume=3dB,"
            "alimiter=limit=0.95[aout]")

    final = os.path.join(OUT, "promo_1080p.mp4")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", base] + inputs +
        ["-filter_complex", fc,
         "-map", "0:v", "-map", "[aout]",
         "-vf", f"ass=subs.ass,fade=t=out:st={total-0.9:.2f}:d=0.9",
         "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", final], cwd=OUT)
    # 自检：音频必须是 48k 立体声、且不是静音（96k mono 在部分播放器里没声）
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=sample_rate,channels", "-of", "csv=p=0", final],
        capture_output=True, text=True).stdout.strip()
    if probe.replace(",", " ") != "48000 2":
        raise RuntimeError(f"音频参数不对：{probe}（应为 48000,2）")
    print("✓", final)


if __name__ == "__main__":
    build()
