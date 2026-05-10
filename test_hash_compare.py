"""
对比 scrcpy 有损帧 vs adb 无损截图的 hash 差异
"""
import base64
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from scene_index import image_fingerprint, _hamming_hex


def compare_hashes(scrcpy_path: Path, adb_path: Path):
    """对比两张图的 hash 差异"""
    fp1 = image_fingerprint(scrcpy_path)
    fp2 = image_fingerprint(adb_path)

    d_dist = _hamming_hex(fp1["dhash"], fp2["dhash"])
    a_dist = _hamming_hex(fp1["ahash"], fp2["ahash"])
    combined = min(64, int(d_dist * 0.75 + a_dist * 0.25))

    return {
        "scrcpy_dhash": fp1["dhash"],
        "scrcpy_ahash": fp1["ahash"],
        "adb_dhash": fp2["dhash"],
        "adb_ahash": fp2["ahash"],
        "dhash_dist": d_dist,
        "ahash_dist": a_dist,
        "combined_dist": combined,
    }


if __name__ == "__main__":
    # 找最近的 scrcpy 帧和对应的 adb 截图
    scrcpy_frames = sorted(Path("screenshots").glob("scene_*.png"))
    adb_shots = []
    for d in Path("screenshots").iterdir():
        if d.is_dir() and d.name.startswith("op_"):
            for f in d.glob("*.png"):
                adb_shots.append(f)

    print(f"scrcpy 帧: {len(scrcpy_frames)} 张")
    print(f"adb 截图: {len(adb_shots)} 张")
    print()

    if not scrcpy_frames or not adb_shots:
        print("需要同时有 scrcpy 帧和 adb 截图才能对比")
        print("建议：先运行程序生成 scrcpy 帧，同时用 adb 截一张同画面图")
        exit(1)

    # 取最近的各一张对比
    scrcpy = scrcpy_frames[-1]
    adb = adb_shots[-1]

    print(f"对比:")
    print(f"  scrcpy: {scrcpy.name}")
    print(f"  adb:    {adb.name}")
    print()

    result = compare_hashes(scrcpy, adb)
    print(f"dhash 汉明距离: {result['dhash_dist']}")
    print(f"ahash 汉明距离: {result['ahash_dist']}")
    print(f"综合距离:       {result['combined_dist']}")
    print()
    print(f"阈值参考:")
    print(f"  0-5:   几乎相同（置信度 >92%）")
    print(f"  6-10:  轻微差异（置信度 85-92%）")
    print(f"  11-15: 明显差异（置信度 77-85%）")
    print(f"  >15:   不同画面（置信度 <77%）")
