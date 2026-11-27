import os
from pathlib import Path
import stat

def directory_size(root):
    total = 0
    for directory, _, files in os.walk(root, followlinks=False):
        for filename in files:
            info = (Path(directory) / filename).lstat()
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    return total
