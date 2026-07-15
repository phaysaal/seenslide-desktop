"""Build a self-contained HTML film strip from a run directory.

For click steps, the AI-located bounding box is drawn in red and the click
point as a crosshair — visual proof of exactly what the vision locator found
and where the harness clicked.

Usage:
    venv/bin/python3 -m tests_gui_agent.report_html tests_gui_agent/runs/<ts>/
"""
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

THUMB_W = 960


def _img_data_uri(path, bbox=None, click=None):
    im = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(im)
    if bbox:
        x0, y0, x1, y1 = bbox
        for w in range(4):
            d.rectangle([x0 - w, y0 - w, x1 + w, y1 + w], outline=(255, 40, 40))
    if click:
        cx, cy = click
        r = 14
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 200, 0), width=4)
        d.line([cx - 24, cy, cx + 24, cy], fill=(255, 200, 0), width=3)
        d.line([cx, cy - 24, cx, cy + 24], fill=(255, 200, 0), width=3)
    scale = THUMB_W / im.width
    im = im.resize((THUMB_W, int(im.height * scale)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=72)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build(run_dir: str) -> str:
    run = Path(run_dir)
    rep = json.loads((run / "report.json").read_text())
    rows = []
    for i, e in enumerate(rep["steps"], 1):
        (kind, spec), = e["step"].items()
        badge = ("<span class='ok'>PASS</span>" if e["ok"]
                 else "<span class='fail'>FAIL</span>")
        img_html = ""
        if e.get("shot") and Path(e["shot"]).exists():
            uri = _img_data_uri(e["shot"], e.get("bbox"), e.get("click"))
            img_html = f"<img src='{uri}'>"
        rows.append(f"""
        <div class='step'>
          <h3>Step {i}: <code>{kind}</code> {badge}</h3>
          <p class='spec'>{json.dumps(spec) if not isinstance(spec, str) else spec}</p>
          <p class='detail'>{e.get('detail', '')}</p>
          {img_html}
        </div>""")

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>GUI run: {rep['scenario']}</title>
<style>
 body {{ font-family: system-ui, sans-serif; background:#101017; color:#e8ecf2;
        max-width: 1020px; margin: 24px auto; padding: 0 16px; }}
 h1 {{ font-size: 22px; }} h3 {{ margin: 4px 0; }}
 .summary {{ color:#9aa3b2; margin-bottom: 20px; }}
 .step {{ border:1px solid #2a2a38; border-radius:10px; padding:14px 16px;
          margin:14px 0; background:#16161f; }}
 .spec {{ color:#8ab4ff; font-size:13px; margin:4px 0; }}
 .detail {{ color:#9aa3b2; font-size:12px; margin:4px 0; }}
 .ok {{ color:#0f1116; background:#22c55e; padding:1px 8px; border-radius:8px;
        font-size:12px; font-weight:700; }}
 .fail {{ color:#fff; background:#ef4444; padding:1px 8px; border-radius:8px;
          font-size:12px; font-weight:700; }}
 img {{ width:100%; border-radius:8px; border:1px solid #2a2a38; margin-top:8px; }}
 .legend {{ font-size:12px; color:#9aa3b2; }}
 .r {{ color:#ff5050; }} .y {{ color:#ffc800; }}
</style></head><body>
<h1>GUI harness run — {rep['scenario']}: {'PASS' if rep['ok'] else 'FAIL'}</h1>
<p class='summary'>{len(rep['steps'])} steps · {rep['ai_calls']} AI calls ·
 artifacts: {run}</p>
<p class='legend'><span class='r'>■</span> red box = element located by the
 vision model &nbsp; <span class='y'>+</span> yellow crosshair = actual click
 point</p>
{''.join(rows)}
</body></html>"""
    out = run / "report.html"
    out.write_text(html)
    return str(out)


if __name__ == "__main__":
    print(build(sys.argv[1]))
