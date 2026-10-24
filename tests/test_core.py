from pathlib import Path
import os, sys, time, tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
from core import pdfops

TMP = tempfile.gettempdir()
src = os.path.join(TMP, "_t206.pdf")
if not os.path.exists(src):
    d = fitz.open()
    for i in range(206):
        p = d.new_page(width=419.53, height=595.28)
        p.insert_text((40, 70), f"{i+1}", fontname="helv", fontsize=72)
        p.insert_text((40, 140), "test page " * 8, fontname="china-s", fontsize=10)
    d.save(src); d.close()

print("页数:", len(fitz.open(src)))
plan = pdfops.booklet_plan(206, max_sheets=5)
print("帖数:", len(plan), "各帖页数:", [p["count"] for p in plan])
print("纸张总数:", sum(len(p["sheets"]) for p in plan))

t0 = time.time()
st = pdfops.impose_booklet(src, os.path.join(TMP, "_out_booklet.pdf"), max_sheets=5)
t = time.time() - t0
print(f"拼版 {t:.2f}s ->", st)

doc = fitz.open(os.path.join(TMP, "_out_booklet.pdf"))
print("输出面数:", len(doc), "尺寸:", doc[0].rect)
# 渲染第一张正面，看两半的页码
pix = doc[0].get_pixmap(dpi=100)
pix.save(os.path.join(TMP, "_booklet_first.png"))

# 4 堆叠
t0 = time.time()
st2 = pdfops.impose_fourstack(src, os.path.join(TMP, "_out_fs.pdf"))
print(f"四堆叠 {time.time()-t0:.2f}s ->", st2)

# A5→A4
t0 = time.time()
st3 = pdfops.impose_a5a4(src, os.path.join(TMP, "_out_a5.pdf"))
print(f"A5→A4 {time.time()-t0:.2f}s ->", st3)

# 4合1
t0 = time.time()
st4 = pdfops.impose_fourup(src, os.path.join(TMP, "_out_4up.pdf"), layout="C", start_page=3)
print(f"4合1 {time.time()-t0:.2f}s ->", st4)

# 合并
t0 = time.time()
st5 = pdfops.merge_pdfs([src, os.path.join(TMP, "_out_4up.pdf")], os.path.join(TMP, "_out_merge.pdf"))
print(f"合并 {time.time()-t0:.2f}s ->", st5)
