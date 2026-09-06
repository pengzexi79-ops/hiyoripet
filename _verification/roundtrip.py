import json
import os
import subprocess
import time
import urllib.request

desk = r"D:\Users\Windows\Desktop\zz-roundtrip.lnk"


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("http://127.0.0.1:8000" + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read().decode())


def make_lnk():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s'); $s.TargetPath='C:\\Windows\\notepad.exe'; $s.Save()" % desk], check=True)


time.sleep(1)
for it in req("GET", "/api/box")["items"]:
    if it["path"].lower() == desk.lower():
        req("DELETE", "/api/box/" + it["id"])
for leftover in (desk, desk + ".lnk"):
    if os.path.exists(leftover):
        os.remove(leftover)
make_lnk()
added = req("POST", "/api/box", {"path": desk})
print("consumed", added["item"].get("consumed"), "lnk-gone", not os.path.exists(desk))
exp = req("POST", "/api/box/export", {"id": added["item"]["id"]})
time.sleep(1)
print("exported", os.path.exists(exp["shortcut"]), exp["shortcut"])
req("DELETE", "/api/box/" + added["item"]["id"])
for leftover in (desk, desk + ".lnk", exp["shortcut"]):
    if os.path.exists(leftover):
        os.remove(leftover)
print("final-items", len(req("GET", "/api/box")["items"]))
