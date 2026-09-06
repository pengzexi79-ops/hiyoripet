import json
import urllib.request
from pathlib import Path


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("http://127.0.0.1:8000" + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read().decode())


have = {i["path"].lower() for i in req("GET", "/api/box")["items"]}
cands = []
for base in (Path(r"D:\Users\Windows\Desktop"), Path(r"C:\Users\Windows\Desktop")):
    cands += [p for p in base.glob("*豆包*.lnk") if p.is_file()]
for base in (Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"), Path(r"D:\Users\Windows\AppData\Roaming\Microsoft\Windows\Start Menu\Programs")):
    for folder in base.glob("*税务*"):
        cands += [p for p in folder.glob("*.lnk") if "卸载" not in p.name]
added = 0
for p in cands:
    if str(p).lower() in have:
        continue
    req("POST", "/api/box", {"path": str(p)})
    added += 1
print("added", added)
print([i["name"] for i in req("GET", "/api/box")["items"]])
