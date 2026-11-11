#!/usr/bin/env python3
"""
批改网自动写作 - 图形化前端服务器
================================
运行: python server.py
然后打开浏览器访问 http://localhost:5000
"""

import json
import os
import sys
import threading
import time
from flask import Flask, render_template, request, jsonify

from llm_client import PROVIDER_PRESETS

# 配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "user_config.json")

# 默认配置 (首次运行时会加载 config.example.json 或用户手动填写)
DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "rid": "",
    "profile": {
        "name": "",
        "student_id": "",
        "class_name": "",
        "school": "",
        "email": "",
    },
    "class": {
        "class_id": "",
        "teacher_name": "",
        "cid": "",
    },
    "target_score": 90,
    "headless": False,
    "skip_profile": False,
    "skip_class": False,
    "grind_mode": False,
    "api": {
        "provider": "longcat",
        "protocol": "anthropic",
        "key": "",
        "base_url": "https://api.longcat.chat/anthropic",
        "model": "LongCat-2.0",
        "max_tokens": 8000,
    },
}

# 全局运行状态
run_state = {
    "running": False,
    "logs": [],
    "score": None,
    "error": None,
}

app = Flask(__name__)


def normalize_config(config):
    """补全旧配置缺失的字段，确保向后兼容"""
    if not isinstance(config, dict):
        return DEFAULT_CONFIG.copy()

    api = config.get("api")
    if not isinstance(api, dict):
        config["api"] = dict(DEFAULT_CONFIG["api"])
        return config

    # 旧配置无 protocol 字段 -> 根据 base_url 推断
    if "protocol" not in api:
        base_url = api.get("base_url", "")
        api["protocol"] = "anthropic" if "longcat" in base_url else "openai"

    if "provider" not in api:
        api["provider"] = "custom"

    return config


def load_config():
    """加载用户配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return normalize_config(json.load(f))
        except:
            pass
    return normalize_config(DEFAULT_CONFIG.copy())


def save_config(config):
    """保存用户配置"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def log_message(msg):
    """添加日志"""
    timestamp = time.strftime("%H:%M:%S")
    run_state["logs"].append(f"[{timestamp}] {msg}")
    # 保持最近200条
    if len(run_state["logs"]) > 200:
        run_state["logs"] = run_state["logs"][-200:]


def run_automation(config):
    """在后台线程中运行自动化"""
    try:
        run_state["running"] = True
        run_state["logs"] = []
        run_state["score"] = None
        run_state["error"] = None

        # 动态导入并修改配置
        sys.path.insert(0, os.path.dirname(__file__))
        from pigai_auto import PigaiAutomator

        # 自动检测 Edge 浏览器路径
        import platform
        system = platform.system()
        if system == "Windows":
            edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            import os
            if not os.path.exists(edge_path):
                edge_path = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        elif system == "Darwin":
            edge_path = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
        else:
            edge_path = "/usr/bin/microsoft-edge"
        config = normalize_config(config)
        runtime_config = {
            "username": config["username"],
            "password": config["password"],
            "rid": config["rid"],
            "profile": config.get("profile", {}),
            "class": config.get("class", {}),
            "target_score": config.get("target_score", 90),
            "skip_profile": config.get("skip_profile", False),
            "skip_class": config.get("skip_class", False),
            "grind_mode": config.get("grind_mode", False),
            "edge_path": edge_path,
            "headless": config.get("headless", False),
            "api": config.get("api", DEFAULT_CONFIG["api"]),
        }

        log_message(f"开始执行 - 作文号: {config['rid']}")

        automator = PigaiAutomator(runtime_config)

        # 重写 automator 的 print 输出到日志
        import builtins
        original_print = builtins.print

        def logged_print(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            log_message(text)
            original_print(*args, **kwargs)

        builtins.print = logged_print

        try:
            automator.start()
            log_message("浏览器已启动")

            # 登录
            log_message("步骤 1/6: 登录...")
            automator.login()

            # 完善资料
            log_message("步骤 2/6: 完善个人资料...")
            automator.fill_profile()

            # 加入班级
            log_message("步骤 3/6: 加入班级...")
            automator.join_class()

            # 获取要求
            log_message("步骤 4/6: 获取作文要求...")
            requirements = automator.get_requirements()
            log_message(f"题目: {requirements['title']}")
            log_message(f"字数: {requirements['min_words']}~{requirements['max_words']}")

            # 撰写作文
            log_message("步骤 5/6: 撰写作文并提交...")
            essay = automator.write_essay(requirements)
            log_message(f"作文长度: {len(essay.split())} 词")

            submit_url = automator.submit_essay(essay)
            log_message("提交成功!")

            # 等待批改
            log_message("步骤 6/6: 等待批改结果...")
            time.sleep(30)

            score = automator.check_score()
            run_state["score"] = score

            if score is not None:
                log_message(f"★ 最终分数: {score}")
                if score >= config.get("target_score", 90):
                    log_message(f"✓ 达标! 目标 {config.get('target_score', 90)}")
                else:
                    log_message(f"✗ 未达标, 目标 {config.get('target_score', 90)}")
            else:
                log_message("分数尚未生成, 请稍后查看")

            # 保持浏览器打开
            log_message("浏览器保持打开中...")

        except Exception as e:
            run_state["error"] = str(e)
            log_message(f"错误: {e}")
        finally:
            builtins.print = original_print

    except Exception as e:
        run_state["error"] = str(e)
        log_message(f"致命错误: {e}")
    finally:
        run_state["running"] = False


# ----------------------------------------------------------
# Flask 路由
# ----------------------------------------------------------

@app.route("/")
def index():
    """主页面"""
    config = load_config()
    return render_template("index.html", config=config)


@app.route("/api/presets")
def api_presets():
    """返回模型供应商预设"""
    return jsonify(PROVIDER_PRESETS)


@app.route("/api/save_config", methods=["POST"])
def api_save_config():
    """保存配置"""
    config = request.json
    save_config(config)
    return jsonify({"status": "ok", "message": "配置已保存"})


@app.route("/api/run", methods=["POST"])
def api_run():
    """启动自动化"""
    if run_state["running"]:
        return jsonify({"status": "error", "message": "正在运行中, 请等待完成"})

    config = request.json
    save_config(config)

    # 在后台线程运行
    thread = threading.Thread(target=run_automation, args=(config,), daemon=True)
    thread.start()

    return jsonify({"status": "ok", "message": "已启动"})


@app.route("/api/status")
def api_status():
    """获取运行状态"""
    return jsonify({
        "running": run_state["running"],
        "logs": run_state["logs"],
        "score": run_state["score"],
        "error": run_state["error"],
    })


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """停止 (标记为不运行)"""
    run_state["running"] = False
    return jsonify({"status": "ok"})


# ----------------------------------------------------------
# 入口
# ----------------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("批改网自动写作 - 图形化前端")
    print("=" * 50)
    print()
    print("请在浏览器中打开: http://localhost:5000")
    print()
    print("按 Ctrl+C 停止服务器")
    print("=" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False)
