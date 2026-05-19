# start_with_watchdog.py

import subprocess
import sys
import os

if __name__ == "__main__":
    # Запускаем watchdog
    subprocess.run([sys.executable, "watchdog.py"])