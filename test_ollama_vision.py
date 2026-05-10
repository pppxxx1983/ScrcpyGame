"""
测试 Ollama 本地 vision 模型识别游戏截图
- 对比 2b/4b/8b 模型效果
- 输出格式：名字(4字内) + 说明
"""
import base64
import json
import time
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

# 需要测试的模型
MODELS = [
    "qwen3-vl:2b",
    "qwen3-vl:4b",
    "qwen3-vl:8b",
]

# 自定义 prompt：要求输出名字(4字内) + 说明
PROMPT = """分析这张游戏截图，只输出以下格式（不要解释）：
名字:XXXX
说明:XXXXXXXXXX

名字要求：
- 尽量4个字以内
- 用常见游戏场景命名，如：手机桌面、广告弹窗、logo、loading、登录界面、选人界面、游戏大厅、战斗画面、结算界面、设置菜单、背包界面、商城界面、任务列表、公告弹窗、网络断开、更新提示

说明要求：
- 一句话描述画面内容
- 不超过30字"""


def analyze_with_ollama(image_path: Path, model: str) -> dict:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": PROMPT,
                "images": [image_b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 200},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"model": model, "error": str(e), "cost": 0}

    message = result.get("message", {})
    text = (message.get("content") or "").strip()
    cost = time.perf_counter() - t0

    # 解析名字和说明
    name = ""
    desc = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("名字:") or line.startswith("名称:"):
            name = line.split(":", 1)[1].strip()[:10]
        elif line.startswith("说明:") or line.startswith("描述:"):
            desc = line.split(":", 1)[1].strip()[:50]

    return {
        "model": model,
        "name": name,
        "desc": desc,
        "raw": text[:200],
        "cost": round(cost, 2),
    }


def main():
    screenshots = sorted(Path("screenshots").glob("*.png"))[-5:]
    if not screenshots:
        print("no screenshots found")
        return

    all_results = []
    for img_path in screenshots:
        print(f"processing {img_path.name} ...")
        for model in MODELS:
            result = analyze_with_ollama(img_path, model)
            result["image"] = img_path.name
            all_results.append(result)

    out = Path("ollama_vision_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"results saved to {out}")


if __name__ == "__main__":
    main()
