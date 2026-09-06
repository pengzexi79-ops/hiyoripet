#!/usr/bin/env python3
# 分块 Range 下载器 v3：get_total 与分片拉取统一走「重试+指数退避」，硬扛代理间歇 502。
import os, sys, time, urllib.request, urllib.error, zipfile

URL = "https://github.com/brechtsanders/winlibs_mingw/releases/download/16.2.0posix-14.0.0-ucrt-r1/winlibs-x86_64-posix-seh-gcc-16.2.0-mingw-w64ucrt-14.0.0-r1.zip"
ZIP = r"D:/codex/pet/_installers/mingw.zip"
OUT = r"D:/codex/pet/.mingw"
CHUNK = 8 * 1024 * 1024
CONN_TO = 60
UA = {"User-Agent": "Mozilla/5.0 (compatible; dl/1.0)"}

def backoff(i):
    return min(3 * (2 ** (i - 1)), 90)

def http_range(start, end):
    """带无限重试的 Range GET，返回 bytes。502/超时等一律退避后重试。"""
    i = 1
    while True:
        try:
            req = urllib.request.Request(URL, headers={**UA, "Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=CONN_TO) as r:
                if r.status != 206:
                    raise RuntimeError(f"unexpected status {r.status}")
                return r.read()
        except Exception as e:
            w = backoff(i)
            print(f"  retry {i} [{start}-{end}]: {type(e).__name__} {e} -> {w}s", flush=True)
            time.sleep(w)
            i += 1

def get_total():
    data = http_range(0, 0)
    # 0-0 返回 1 字节；Content-Range 在异常路径拿不到，改用一次 0-0 的 header
    # 直接再发一次拿 header
    i = 1
    while True:
        try:
            req = urllib.request.Request(URL, headers={**UA, "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=CONN_TO) as r:
                cr = r.headers.get("Content-Range", "")
                return int(cr.split("/")[-1])
        except Exception as e:
            w = backoff(i)
            print(f"  get_total retry {i}: {type(e).__name__} {e} -> {w}s", flush=True)
            time.sleep(w)
            i += 1

def main():
    total = get_total()
    print(f"TOTAL={total}", flush=True)
    have = os.path.getsize(ZIP) if os.path.exists(ZIP) else 0
    print(f"HAVE={have}", flush=True)
    with open(ZIP, "r+b") as f:
        pos = have
        while pos < total:
            end = min(pos + CHUNK - 1, total - 1)
            data = http_range(pos, end)
            f.seek(pos)
            f.write(data)
            f.flush()
            pos += len(data)
            print(f"chunk {pos*100//total}% ({pos}/{total})", flush=True)
    print("DOWNLOAD_DONE size=%d" % os.path.getsize(ZIP), flush=True)

    try:
        zf = zipfile.ZipFile(ZIP)
        bad = zf.testzip()
        print("ZIP_OK" if bad is None else f"ZIP_BAD:{bad}", flush=True)
        if bad:
            sys.exit(3)
    except Exception as e:
        print("ZIP_ERR:", e, flush=True)
        sys.exit(3)

    os.makedirs(OUT, exist_ok=True)
    zf.extractall(OUT)
    print("EXTRACT_DONE", flush=True)

    cand = [
        os.path.join(OUT, "bin", "x86_64-w64-mingw32-gcc.exe"),
        os.path.join(OUT, "mingw64", "bin", "x86_64-w64-mingw32-gcc.exe"),
    ]
    gcc = next((c for c in cand if os.path.exists(c)), None)
    if not gcc:
        print("GCC_NOT_FOUND", flush=True)
        sys.exit(4)
    print("GCC_PATH=" + gcc, flush=True)

if __name__ == "__main__":
    main()
