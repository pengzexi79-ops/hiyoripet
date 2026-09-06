from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root = Path(r'D:\codex\pet-next\release\HiyoriPet')
out = Path(r'D:\codex\pet-next\release\HiyoriPet_0.1.4_portable.zip')
with ZipFile(out, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        archive.write(path, path.relative_to(root).as_posix())
print(out, out.stat().st_size)
