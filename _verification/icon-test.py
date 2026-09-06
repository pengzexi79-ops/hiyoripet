import os
import subprocess

desk = r"D:\Users\Windows\Desktop\zz-icon-test.lnk"
png = os.path.join(os.environ["APPDATA"], "HiyoriPet", "icons", "manual-test.png")
subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s'); $s.TargetPath='C:\\Windows\\notepad.exe'; $s.Save()" % desk],
    check=True,
)
proc = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Add-Type -AssemblyName System.Drawing; $i=[System.Drawing.Icon]::ExtractAssociatedIcon('%s'); $i.ToBitmap().Save('%s')" % (desk, png)],
    capture_output=True, text=True,
)
print("rc", proc.returncode)
print("stderr", proc.stderr[:600])
print("exists", os.path.exists(png))
