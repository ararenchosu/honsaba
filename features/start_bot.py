import subprocess
import sys
import time

while True:
    print("\n🚀 Botを起動中...")
    process = subprocess.Popen([sys.executable, "main.py"])
    process.wait()
    
    print("\n⚠️ Botが停止しました。5秒後に自動で再起動します...")
    time.sleep(5)
