"""Render each workflow JSON into a clean diagram (HTML -> PNG via headless Chrome).

Usage: python3 docs/render.py
"""

import html
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"

STYLE = {
    "gmailTrigger": ("#ea4335", "✉", "Gmail Trigger"),
    "gmail": ("#ea4335", "✉", "Gmail"),
    "webhook": ("#ff6d5a", "⚡", "Webhook"),
    "code": ("#f0a020", "{ }", "Code"),
    "httpRequest": ("#10a37f", "✦", "OpenAI"),
    "if": ("#8b5cf6", "◇", "IF"),
    "slack": ("#4a154b", "#", "Slack"),
    "googleSheets": ("#0f9d58", "▦", "Google Sheets"),
    "respondToWebhook": ("#ff6d5a", "↩", "Respond"),
    "extractFromFile": ("#3b82f6", "PDF", "Extract"),
}

W, H = 180, 92  # node box size


def render(path: Path) -> Path:
    wf = json.loads(path.read_text())
    nodes = {n["name"]: n for n in wf["nodes"]}
    xs = [n["position"][0] for n in nodes.values()]
    ys = [n["position"][1] for n in nodes.values()]
    minx, miny = min(xs), min(ys)
    pad = 80
    width = max(xs) - minx + W + pad * 2
    height = max(ys) - miny + H + pad * 2 + 70

    def pos(n):
        return n["position"][0] - minx + pad, n["position"][1] - miny + pad + 70

    edges = []
    for src, v in wf["connections"].items():
        for out_idx, outs in enumerate(v["main"]):
            for t in outs:
                sx, sy = pos(nodes[src])
                tx, ty = pos(nodes[t["node"]])
                x1, y1 = sx + W, sy + H / 2
                x2, y2 = tx, ty + H / 2
                c = (x2 - x1) / 2
                label = ""
                if nodes[src]["type"].endswith(".if"):
                    label = "true" if out_idx == 0 else "false"
                edges.append((f"M{x1},{y1} C{x1 + c},{y1} {x2 - c},{y2} {x2},{y2}", label, (x1 + x2) / 2, (y1 + y2) / 2))

    boxes = []
    for n in nodes.values():
        key = n["type"].split(".")[-1]
        color, icon, kind = STYLE.get(key, ("#64748b", "•", key))
        x, y = pos(n)
        boxes.append(f"""
        <div class="node" style="left:{x}px;top:{y}px;--c:{color}">
          <div class="icon">{icon}</div>
          <div class="txt"><div class="kind">{html.escape(kind)}</div><div class="name">{html.escape(n['name'])}</div></div>
        </div>""")

    paths = "".join(
        f'<path d="{d}" /><text x="{lx}" y="{ly - 8}">{lab}</text>' for d, lab, lx, ly in edges
    )
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:{width}px;height:{height}px;background:#0f1117;font-family:Inter,'Segoe UI',Arial,sans-serif;position:relative;overflow:hidden;
      background-image:radial-gradient(#262a36 1px,transparent 1px);background-size:22px 22px}}
    h1{{position:absolute;left:{pad}px;top:28px;color:#fff;font-size:24px;font-weight:700}}
    h1 span{{color:#ff6d5a}}
    svg{{position:absolute;inset:0}}
    path{{fill:none;stroke:#6b7280;stroke-width:2.5}}
    text{{fill:#a5b4fc;font-size:13px;text-anchor:middle}}
    .node{{position:absolute;width:{W}px;height:{H}px;background:#1b1e27;border:2px solid var(--c);border-radius:14px;display:flex;align-items:center;gap:12px;padding:12px;box-shadow:0 8px 24px rgba(0,0,0,.35)}}
    .icon{{flex:none;width:44px;height:44px;border-radius:10px;background:var(--c);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:18px}}
    .kind{{color:#9ca3af;font-size:11px;text-transform:uppercase;letter-spacing:.5px}}
    .name{{color:#f3f4f6;font-size:14px;font-weight:600;line-height:1.25;margin-top:2px}}
    </style></head><body>
    <h1><span>n8n</span> · {html.escape(wf['name'])}</h1>
    <svg width="{width}" height="{height}">{paths}</svg>
    {''.join(boxes)}
    </body></html>"""

    OUT.mkdir(parents=True, exist_ok=True)
    html_path = OUT / f"{path.stem}.html"
    png_path = OUT / f"{path.stem}.png"
    html_path.write_text(page)
    subprocess.run(
        ["google-chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={int(width)},{int(height)}", f"--screenshot={png_path}", html_path.as_uri()],
        check=True, capture_output=True,
    )
    html_path.unlink()
    return png_path


if __name__ == "__main__":
    for f in sorted((ROOT / "workflows").glob("*.json")):
        print(render(f))
