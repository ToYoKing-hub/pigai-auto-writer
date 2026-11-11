#!/usr/bin/env python3
"""
批改网自动写作脚本 - 可配置版本
================================
使用方法: 修改下方的 CONFIG 配置，然后运行 python pigai_ai_auto.py
"""

import time
import re
import sys

from playwright.sync_api import sync_playwright
from llm_client import LLMClient, LLMError

# ============================================================
# 配置区 - 修改这里即可适配不同作文
# ============================================================
CONFIG = {
    # 批改网账号
    "username": "",
    "password": "",

    # 作文号 (rid) - 修改这里切换不同作业
    "rid": "",

    # 个人信息 (首次使用需要填写，之后会自动保存)
    "profile": {
        "name": "",
        "student_id": "",
        "class_name": "",
        "school": "",
        "email": "",
    },

    # 班级信息 (首次需要加入)
    "class": {
        "class_id": "",       # 班级号
        "teacher_name": "",   # 老师姓名
        "cid": "",            # 班级数字ID
    },

    # 目标分数
    "target_score": 90,

    # 步骤开关 (True=执行, False=跳过)
    "skip_profile": False,      # 跳过完善个人信息
    "skip_class": False,        # 跳过加入班级

    # 浏览器路径 (自动检测，一般不需要修改)
    "edge_path": "",  # 留空则自动检测系统默认 Edge 路径

    # 无头模式 (True=不显示浏览器, False=显示浏览器)
    "headless": False,

    # LLM API 配置 (用于自动生成作文)
    # provider/protocol 可在 Web UI 中切换，预设见 llm_client.PROVIDER_PRESETS
    "api": {
        "provider": "longcat",
        "protocol": "anthropic",
        "key": "",
        "base_url": "https://api.longcat.chat/anthropic",
        "model": "LongCat-2.0",
        "max_tokens": 8000,
    },
}
# ============================================================


class PigaiAutomator:
    """批改网自动化操作类"""

    def __init__(self, config):
        self.config = config
        self.rid = config["rid"]
        self.target = config.get("target_score", 90)
        self.playwright = None
        self.browser = None
        self.page = None
        self.llm = LLMClient(config.get("api", {}))

    def _detect_edge_path(self):
        """自动检测 Edge 浏览器路径"""
        import os
        import platform

        system = platform.system()
        candidates = []
        if system == "Windows":
            candidates = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
        elif system == "Darwin":
            candidates = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
        else:
            candidates = [
                "/usr/bin/microsoft-edge",
                "/usr/bin/microsoft-edge-stable",
            ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None  # 返回 None 则使用 Playwright 内置 Chromium

    def start(self):
        """启动浏览器"""
        self.playwright = sync_playwright().start()
        edge_path = self.config.get("edge_path") or self._detect_edge_path()
        self.browser = self.playwright.chromium.launch(
            executable_path=edge_path,
            headless=self.config.get("headless", False),
            args=["--start-maximized"] if not self.config.get("headless", False) else [],
        )
        self.page = self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        ).new_page()

        # 自动处理弹窗
        self.page.on("dialog", lambda d: d.accept())

    def stop(self):
        """关闭浏览器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _remove_overlays(self):
        """移除页面遮罩层"""
        self.page.evaluate(
            "var el = document.getElementById('icibaWinFloat'); if(el) el.style.display='none';"
        )
        self.page.evaluate(
            "var el = document.getElementById('icibaWin'); if(el) el.style.display='none';"
        )

    # ----------------------------------------------------------
    # 登录
    # ----------------------------------------------------------
    def login(self):
        """登录批改网"""
        print("  [登录] 正在登录...")
        self.page.goto(
            "https://www.pigai.org/index.php?a=loginForm",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(2)

        self.page.query_selector("#username").fill(self.config["username"])
        self.page.query_selector("#password").fill(self.config["password"])
        time.sleep(0.5)
        self.page.query_selector("#ulogin").click()
        time.sleep(5)

        # 检查是否登录成功
        text = self.page.inner_text("body")
        if "用户登录" in text and "账户名" in text:
            raise Exception("登录失败，请检查用户名密码")

        print("  [登录] 成功")
        return True

    # ----------------------------------------------------------
    # 完善个人资料
    # ----------------------------------------------------------
    def fill_profile(self):
        """填写/检查个人资料"""
        print("  [资料] 检查个人资料...")
        self.page.goto(
            "https://www.pigai.org/?a=modifyPassword",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(3)
        self._remove_overlays()

        profile = self.config["profile"]
        filled = 0

        # 姓名
        name_el = self.page.query_selector("#s_truename")
        if name_el and not name_el.input_value().strip():
            name_el.fill(profile["name"])
            filled += 1

        # 学号
        id_el = self.page.query_selector("#studentid")
        if id_el and not id_el.input_value().strip():
            id_el.fill(profile["student_id"])
            filled += 1

        # 班级
        class_el = self.page.query_selector("#studentclass")
        if class_el and not class_el.input_value().strip():
            class_el.fill(profile["class_name"])
            filled += 1

        # 学校
        school_el = self.page.query_selector("#school")
        if school_el and not school_el.input_value().strip():
            school_el.fill(profile["school"])
            filled += 1

        # 邮箱
        email_el = self.page.query_selector("#email")
        if email_el and not email_el.input_value().strip():
            email_el.fill(profile["email"])
            filled += 1

        if filled > 0:
            print(f"  [资料] 填写了 {filled} 项，保存中...")
            self._remove_overlays()
            self.page.evaluate("document.getElementById('modifyinfo').submit()")
            time.sleep(5)
        else:
            print("  [资料] 资料已完整，无需修改")

        return True

    # ----------------------------------------------------------
    # 加入班级
    # ----------------------------------------------------------
    def join_class(self):
        """加入指定班级"""
        cls = self.config["class"]
        print(f"  [班级] 加入班级 {cls['class_id']}...")

        # 检查是否已在班级中
        self.page.goto(
            f"https://www.pigai.org/index.php?c=v2&a=write&rid={self.rid}",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(5)

        text = self.page.inner_text("body")
        if "rq_class" not in text:
            print("  [班级] 已加入班级，无需重复加入")
            return True

        # 加入班级
        join_url = (
            f"https://www.pigai.org/index.php?c=write&a=joinClass"
            f"&cid={cls['cid']}&teacher_name={cls['teacher_name']}"
        )
        self.page.evaluate(f"window.location.href = '{join_url}'")
        time.sleep(5)

        print("  [班级] 加入完成")
        return True

    # ----------------------------------------------------------
    # 获取作文要求
    # ----------------------------------------------------------
    def get_requirements(self):
        """从作文页面提取题目和要求"""
        print(f"  [题目] 获取作文 {self.rid} 的要求...")

        self.page.goto(
            f"https://www.pigai.org/index.php?c=v2&a=write&rid={self.rid}",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(5)

        text = self.page.inner_text("body")

        # 检查是否需要加入班级
        if "rq_class" in text:
            raise Exception("需要先加入班级才能写作文，请检查班级信息")

        # 提取题目
        title_match = re.search(r'题目[：:]\s*\[?\d+\]?\s*(.+?)(?:\n|$)', text)
        title = title_match.group(1).strip() if title_match else "Unknown"

        # 提取要求段落
        req_match = re.search(r'要求\s*\n\s*\n(.+?)(?:\n\s*\n作文号)', text, re.DOTALL)
        requirements = req_match.group(1).strip() if req_match else ""

        # 提取字数要求
        word_range_match = re.search(r'(\d+)\s*[~～到]\s*(\d+)', text)
        if not word_range_match:
            word_range_match = re.search(r'至少(\d+).*?不超过(\d+)', text)
        if not word_range_match:
            word_range_match = re.search(r'at least (\d+).*?no more than (\d+)', text, re.IGNORECASE)

        min_words = int(word_range_match.group(1)) if word_range_match else 120
        max_words = int(word_range_match.group(2)) if word_range_match else 180

        info = {
            "title": title,
            "requirements": requirements,
            "min_words": min_words,
            "max_words": max_words,
        }

        print(f"  [题目] {title}")
        print(f"  [要求] {requirements[:100]}...")
        print(f"  [字数] {min_words} ~ {max_words}")

        return info

    # ----------------------------------------------------------
    # 撰写作文
    # ----------------------------------------------------------
    def write_essay(self, requirements, grind_mode=False, diversity_hint=""):
        """根据要求撰写作文，确保字数在范围内"""
        title = requirements["title"]
        min_w = requirements["min_words"]
        max_w = requirements["max_words"]
        req_text = requirements["requirements"]

        print(f"  [写作] 正在撰写: {title} (要求 {min_w}~{max_w} 词)")

        # 最多尝试3次生成符合字数要求的作文
        for attempt in range(3):
            essay = self._generate_essay(title, req_text, min_w, max_w, grind_mode, diversity_hint)
            word_count = len(essay.split())

            if min_w <= word_count <= max_w:
                print(f"  [写作] 完成 ({word_count} 词) ✓")
                return essay
            else:
                print(f"  [写作] 字数不符 ({word_count} 词)，重新生成... ({attempt+1}/3)")
                # 重新生成时加入字数提示
                diversity_hint = f"MUST be between {min_w} and {max_w} words. Current attempt was {word_count} words."

        # 3次都不符合，返回最后一次生成的
        print(f"  [警告] 3次生成均不符字数要求，使用最后一次结果")
        return essay

    def _generate_essay(self, title, requirements, min_w, max_w, grind_mode=False, diversity_hint=""):
        """
        根据题目生成作文。
        普通模式: 优先匹配预设模板，没有匹配则调用 API。
        刷分模式: 始终调用 API，确保每次生成不同的作文。
        """
        # 刷分模式 -> 强制走 API (API 有温度参数，每次输出不同)
        if not grind_mode:
            title_lower = title.lower()
            req_lower = requirements.lower()

            # ====== 作文模板库 (已知高分模板) ======
            ESSAY_TEMPLATES = {
                "handwriting": self._essay_handwriting,
                "cooking": self._essay_cooking,
                "learning to cook": self._essay_cooking,
            }

            # 匹配已知模板
            for keyword, template_func in ESSAY_TEMPLATES.items():
                if keyword in title_lower or keyword in req_lower:
                    print("  [写作] 使用预设模板")
                    return template_func(min_w, max_w)

        # 没有匹配模板 或 刷分模式 -> 调用 API 生成
        print("  [写作] 调用 LLM API 生成作文...")
        return self._generate_via_api(title, requirements, min_w, max_w, diversity_hint)

    def _generate_via_api(self, title, requirements, min_w, max_w, diversity_hint=""):
        """通过 LLM API 生成作文"""
        # 构建 prompt
        target_words = (min_w + max_w) // 2

        # 多样性指令 (确保每次生成不同作文)
        diversity_instruction = """
CRITICAL WRITING RULES:
- This essay MUST be completely unique and original.
- Use a DIFFERENT opening sentence than typical essays (avoid "In today's digital era" or "With the development of").
- Use DIFFERENT examples and arguments than common essays.
- Vary your sentence structures significantly.
- Do NOT use clichés or template phrases."""
        if diversity_instruction:
            diversity_instruction += f"\n- {diversity_hint}" if diversity_hint else ""

        prompt = f"""Write a high-quality English essay for a college English exam.

Topic: {title}

Requirements:
- Write exactly between {min_w} and {max_w} words
- Use advanced vocabulary and varied sentence structures (compound sentences, complex sentences with clauses, relative clauses, conditional sentences)
- Include specific real-world examples and concrete details (mention specific places, studies, or scenarios)
- Avoid Chinglish and grammatical errors
- Opening paragraph: introduce the topic with a hook and state your thesis
- Body paragraphs: provide 2-3 supporting arguments with specific examples
- Concluding paragraph: summarize and provide a forward-looking statement
- Do NOT include a title
- Output ONLY the essay text, no explanations, no markdown formatting

{diversity_instruction}"""

        try:
            essay = self.llm.generate(prompt)

            # 验证字数
            word_count = len(essay.split())
            print(f"  [API] 生成完成 ({word_count} 词)")

            if word_count < min_w:
                print(f"  [警告] API 生成的作文字数不足 ({word_count} < {min_w})")
            elif word_count > max_w:
                print(f"  [警告] API 生成的作文字数超出 ({word_count} > {max_w})")

            return essay

        except LLMError as e:
            print(f"  [错误] {e}")
            print("  [写作] 回退到通用模板")
            return self._essay_generic(title, min_w, max_w)

    # --- 具体作文模板 ---

    def _essay_handwriting(self, min_w, max_w):
        """手写的重要性"""
        essays = [
            # V1: 高分行列
            """In today's digital era, typing has predominantly replaced handwriting as the primary mode of written communication. Nevertheless, I firmly believe that handwriting retains its unique significance, which should not be underestimated in contemporary society.

To begin with, handwriting offers remarkable cognitive benefits that typing simply cannot replicate. Extensive research, which has been conducted by neuroscientists across the globe, has consistently demonstrated that students who take handwritten notes exhibit superior comprehension and long-term retention of information. The intricate motor processes that are involved in forming letters activate neural pathways associated with learning and memory, thereby enhancing overall intellectual development. Furthermore, handwriting constitutes a distinctive form of personal expression whose authenticity cannot be matched by standardized digital fonts. Each individual script conveys personality and emotion in ways that make handwritten correspondence feel profoundly sincere and meaningful. Additionally, handwriting remains practically indispensable in numerous professional and personal scenarios, including signing legal documents, completing official forms, and recording critical ideas whenever electronic devices are either unavailable or inappropriate.

In conclusion, while digital typing undoubtedly excels in terms of speed and convenience, handwriting fundamentally enriches our cognitive capabilities and emotional expression. Striking a harmonious balance between these two complementary skills is absolutely essential for individuals who aspire to thrive in the modern world.""",
        ]
        return self._pick_by_length(essays, min_w, max_w)

    def _essay_cooking(self, min_w, max_w):
        """学习做饭的重要性"""
        essays = [
            # V1
            """In the digital age, food delivery apps and instant meals have made it easier than ever to avoid cooking. However, I firmly believe that learning to cook remains an essential skill that everyone should develop.

To begin with, cooking promotes a healthier lifestyle. When people prepare their own meals, they have complete control over the ingredients, which allows them to reduce unhealthy additives, excessive oil, and sugar that are commonly found in processed foods and restaurant dishes. Home-cooked meals are therefore generally more nutritious and balanced. Furthermore, cooking serves as a valuable form of creative expression and stress relief. The process of experimenting with different ingredients and flavors provides a satisfying creative outlet that can significantly reduce the pressures of daily life. Additionally, cooking strengthens social bonds and family connections. Sharing a homemade meal with loved ones creates meaningful moments of togetherness that dining out or ordering takeout simply cannot replicate. Learning to cook also cultivates important life skills such as planning, budgeting, and time management.

In conclusion, while digital technology has transformed how we access food, the fundamental importance of learning to cook remains unchanged. Cooking nourishes not only our bodies but also our minds and relationships, making it an indispensable skill in the modern era.""",
            # V2
            """With the rise of food delivery platforms and ready-to-eat meals, cooking seems less necessary than ever before. Despite this trend, I maintain that learning to cook continues to hold profound importance for individuals living in the digital age.

From a health perspective, cooking at home provides significant nutritional advantages. People who prepare their own meals can carefully select fresh ingredients and control portion sizes, thereby avoiding the excessive calories, sodium, and preservatives that characterize most commercially prepared foods. Research consistently shows that home cooks maintain healthier body weights and experience fewer diet-related health problems. Beyond physical health, cooking offers substantial psychological benefits. The act of creating a meal from raw ingredients engages multiple senses and provides a therapeutic break from screen-dominated routines, which can alleviate stress and improve mental well-being. Moreover, cooking preserves cultural heritage and strengthens interpersonal relationships. Traditional recipes passed down through generations connect us to our roots, while the shared experience of preparing and enjoying a meal together fosters deeper connections with family and friends.

In summary, although digital conveniences have changed our relationship with food, cooking remains a fundamentally important skill that supports physical health, mental wellness, and meaningful human connection.""",
        ]
        return self._pick_by_length(essays, min_w, max_w)

    def _essay_generic(self, title, min_w, max_w):
        """通用作文模板"""
        return f"""In contemporary society, the topic of {title} has attracted considerable attention. I firmly believe that this issue deserves thorough examination and thoughtful discussion.

To begin with, there are several compelling reasons why this matter is important. First and foremost, it directly impacts our daily lives in ways that are both obvious and subtle. Research and practical experience have consistently demonstrated that paying attention to this issue yields tangible benefits for individuals and communities alike. Furthermore, addressing this topic contributes to broader social progress and human development. When people recognize its significance, they are better equipped to make informed decisions that positively affect their personal growth and interpersonal relationships. Additionally, understanding this matter helps us navigate the complexities of modern life more effectively.

In conclusion, the importance of {title.lower()} cannot be overstated. It influences multiple aspects of our existence, from personal well-being to social harmony. By acknowledging its significance and taking appropriate action, we can build a better future for ourselves and generations to come."""

    def _pick_by_length(self, essays, min_w, max_w):
        """根据字数要求选择最合适的版本"""
        target = (min_w + max_w) // 2
        best = essays[0]
        best_diff = abs(len(best.split()) - target)
        for e in essays[1:]:
            diff = abs(len(e.split()) - target)
            if diff < best_diff:
                best = e
                best_diff = diff
        return best

    # ----------------------------------------------------------
    # 输入并提交作文
    # ----------------------------------------------------------
    def submit_essay(self, essay_text):
        """将作文输入到编辑器并提交"""
        print("  [提交] 正在输入作文...")

        self.page.goto(
            f"https://www.pigai.org/index.php?c=v2&a=write&rid={self.rid}",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(5)

        # 查找编辑器
        editor = self.page.query_selector("textarea[name='contents']")
        if not editor:
            editor = self.page.query_selector("#contents")
        if not editor:
            raise Exception("找不到作文编辑器")

        # 输入内容 (逐字模拟键盘输入，绕过粘贴限制)
        editor.click()
        time.sleep(0.3)
        editor.fill("")
        time.sleep(0.3)
        # type() 逐字符输入，delay=8ms, timeout=120s 避免超时
        editor.type(essay_text, delay=8, timeout=120000)
        time.sleep(1)

        # 点击提交
        print("  [提交] 点击提交按钮...")
        submit_btn = self.page.query_selector("#dafen")
        if submit_btn:
            submit_btn.click()
            time.sleep(3)

        # 处理弹窗 (标题为空 + 班级未选择)
        for _ in range(5):
            try:
                ok = self.page.query_selector(
                    ".ui-dialog-buttonset button:first-child, "
                    "button:has-text('确定')"
                )
                if ok and ok.is_visible():
                    ok.click()
                    time.sleep(2)
                else:
                    break
            except:
                break

        # 等待提交完成
        time.sleep(10)

        # 检查是否有错误弹窗 (如 "请勿重复提交")
        page_text = self.page.inner_text("body")
        if "请勿重复提交" in page_text or "重复提交" in page_text:
            print("  [警告] 检测到重复提交错误！")
            return "duplicate"

        url = self.page.url
        print(f"  [提交] 完成, URL: {url}")
        return url

    # ----------------------------------------------------------
    # 检查分数
    # ----------------------------------------------------------
    def check_score(self):
        """检查最新提交的分数"""
        print("  [分数] 检查分数...")

        # 导航到我的作文页面
        # 如果已经在查看页面则直接读取，避免重复导航
        if "view" in self.page.url and "eid" in self.page.url:
            print("  [分数] 已在查看页面")
        else:
            # 导航到我的作文页面找到最新提交
            self.page.goto(
                "https://www.pigai.org/index.php?c=write",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            time.sleep(5)
            view_link = self.page.query_selector("a[href*='view'][href*='eid']")
            if not view_link:
                print("  [分数] 未找到查看链接")
                return None
            view_link.click()
            time.sleep(8)

        # 提取分数 (从 circles-text 元素中获取，避免和排行榜最高分混淆)
        score = None
        try:
            integer_el = self.page.query_selector(".circles-integer")
            decimal_el = self.page.query_selector(".circles-decimals")
            if integer_el and decimal_el:
                integer_part = integer_el.inner_text().strip()
                decimal_part = decimal_el.inner_text().strip()
                score = float(f"{integer_part}.{decimal_part}")
        except Exception:
            pass

        # 备用方法: 从 rescoreTxt 元素获取
        if score is None:
            try:
                el = self.page.query_selector("#rescoreTxt")
                if el:
                    t = el.inner_text().strip()
                    if t:
                        score = float(t)
            except Exception:
                pass

        if score is not None:
            print(f"  [分数] {score} 分")
        else:
            print("  [分数] 无法提取分数，可能还在批改中")

        return score

    # ----------------------------------------------------------
    # 提取批改点评
    # ----------------------------------------------------------
    def get_feedback(self):
        """从批改页面提取点评信息"""
        print("  [点评] 读取批改点评...")

        # 确保在查看页面
        text = self.page.inner_text("body")

        feedback = {}

        # 提取分数相关总结 (如 "8处语法错误（2个主谓不一致，3个词性错误...）")
        error_match = re.search(r'\d+处语法错误.*?(?:）|\))', text)
        if error_match:
            feedback["errors"] = error_match.group(0)

        # 提取其他反馈标签
        for keyword in ["中式英语", "学术词汇偏少", "文章结构松散", "词汇基础扎实", "拼写很棒"]:
            if keyword in text:
                feedback.setdefault("comments", []).append(keyword)

        # 提取评语
        comment_match = re.search(r'评语[：:]\s*(.+?)(?:\n|按句点评)', text)
        if comment_match:
            feedback["comment"] = comment_match.group(1).strip()

        # 提取按句点评 (推荐表达、词语错误、学习提示等)
        sentence_feedback = []
        for line in text.split('\n'):
            line = line.strip()
            if any(kw in line for kw in ["词语错误", "推荐表达", "学习提示", "拓展辨析"]):
                sentence_feedback.append(line)
        if sentence_feedback:
            feedback["sentence_tips"] = sentence_feedback[:10]  # 最多取10条

        # 打印提取到的点评
        if feedback.get("errors"):
            print(f"  [点评] 错误: {feedback['errors']}")
        if feedback.get("comment"):
            print(f"  [点评] 评语: {feedback['comment']}")
        if feedback.get("comments"):
            print(f"  [点评] 反馈: {', '.join(feedback['comments'])}")

        return feedback

    # ----------------------------------------------------------
    # 刷分模式: 看点评 → 改作文 → 重提交 → 循环
    # ----------------------------------------------------------
    def _grind_score(self, requirements):
        """
        刷分循环:
        1. 提交作文 → 等批改 → 查分数
        2. 未达标 → 读教师点评 → 根据点评修改原文 → 重提交
        3. 重复直到达标或达到最大次数
        """
        import random
        max_attempts = 10
        score = None
        current_essay = None

        # 角度池 (第一次生成用)
        angles = [
            "Focus on personal growth and self-discipline.",
            "Focus on social relationships and community impact.",
            "Focus on professional/career development.",
            "Focus on mental health and well-being.",
            "Focus on cultural preservation and heritage.",
            "Focus on environmental sustainability.",
        ]

        for attempt in range(1, max_attempts + 1):
            print(f"\n  [刷分] 第 {attempt}/{max_attempts} 次尝试")

            if attempt == 1:
                # 第一次: 从零生成全新作文
                angle_hint = random.choice(angles)
                current_essay = self.write_essay(requirements, grind_mode=True, diversity_hint=angle_hint)
            else:
                # 后续: 根据教师点评修改之前的作文
                print(f"  [刷分] 根据教师点评修改作文...")
                current_essay = self._revise_essay(current_essay, requirements, last_feedback)

            word_count = len(current_essay.split())
            print(f"  [刷分] 作文字数: {word_count}")

            # 提交
            result = self.submit_essay(current_essay)

            # 检查重复提交
            if result == "duplicate":
                print(f"  [刷分] 重复提交被拒，重写一篇完全不同的作文...")
                # 用完全不同的角度重写
                angle_hint = random.choice(angles)
                current_essay = self.write_essay(requirements, grind_mode=True,
                    diversity_hint=f"MUST be completely different from the rejected essay. {angle_hint}")
                result = self.submit_essay(current_essay)
                if result == "duplicate":
                    print(f"  [刷分] 仍然重复，跳过本次...")
                    continue

            # 等待批改
            print(f"  [刷分] 等待批改 (30s)...")
            time.sleep(30)

            # 检查分数
            score = self.check_score()

            if score is not None:
                print(f"  [刷分] 当前分数: {score} / 目标: {self.target}")
                if score >= self.target:
                    print(f"  [刷分] ✓ 达标! 共尝试 {attempt} 次")
                    break
                else:
                    # 未达标 → 读取教师点评，用于下次修改
                    print(f"  [刷分] 未达标，读取教师点评...")
                    last_feedback = self.get_feedback()
                    if last_feedback:
                        print(f"  [刷分] 已获取点评，下次将针对性修改")
                    else:
                        print(f"  [刷分] 未获取到点评")
            else:
                print(f"  [刷分] 分数未生成，继续等待...")
                time.sleep(30)
                score = self.check_score()
                if score and score < self.target:
                    last_feedback = self.get_feedback()

        if score is None or score < self.target:
            print(f"  [刷分] 已达最大次数 ({max_attempts})，最终分数: {score}")

        return score

    def _revise_essay(self, original_essay, requirements, feedback):
        """根据教师点评修改原文"""
        title = requirements["title"]
        min_w = requirements["min_words"]
        max_w = requirements["max_words"]

        # 构建反馈文本
        feedback_text = ""
        if feedback.get("errors"):
            feedback_text += f"Errors found: {feedback['errors']}\n"
        if feedback.get("comment"):
            feedback_text += f"Teacher's comment: {feedback['comment']}\n"
        if feedback.get("comments"):
            feedback_text += f"Feedback: {', '.join(feedback['comments'])}\n"
        if feedback.get("sentence_tips"):
            feedback_text += "Specific issues:\n"
            for tip in feedback.get("sentence_tips", []):
                feedback_text += f"  - {tip}\n"

        prompt = f"""Revise the following essay based on the teacher's feedback.

Topic: {title}
Required word count: {min_w} to {max_w} words (CURRENT: {len(original_essay.split())} words)

ORIGINAL ESSAY:
{original_essay}

TEACHER FEEDBACK:
{feedback_text}

REVISION REQUIREMENTS:
1. Fix ALL errors mentioned in the feedback (grammar, word choice, collocation, articles, etc.)
2. Address the teacher's specific comments
3. Keep the same overall topic and main ideas
4. Ensure the revised essay is between {min_w} and {max_w} words
5. Output ONLY the revised essay text, no explanations"""

        try:
            revised = self.llm.generate(prompt)

            # 验证字数
            wc = len(revised.split())
            print(f"  [修改] 修改完成 ({wc} 词)")
            if wc < min_w or wc > max_w:
                print(f"  [修改] 字数不符，重新生成...")
                return self.write_essay(requirements, grind_mode=True)

            return revised

        except LLMError as e:
            print(f"  [错误] 修改失败: {e}")
            return self.write_essay(requirements, grind_mode=True)

    # ----------------------------------------------------------
    # 主流程
    # ----------------------------------------------------------
    def run(self):
        """执行完整流程"""
        print("=" * 60)
        print(f"批改网自动写作 - 作文号: {self.rid}")
        print("=" * 60)

        try:
            self.start()

            step = 1

            # 1. 登录
            print(f"\n[{step}/6] 登录")
            self.login()
            step += 1

            # 2. 完善资料 (可选)
            if self.config.get("skip_profile", False):
                print(f"\n[{step}/6] 跳过完善个人资料")
            else:
                print(f"\n[{step}/6] 完善个人资料")
                self.fill_profile()
            step += 1

            # 3. 加入班级 (可选)
            if self.config.get("skip_class", False):
                print(f"\n[{step}/6] 跳过加入班级")
            else:
                print(f"\n[{step}/6] 加入班级")
                self.join_class()
            step += 1

            # 4. 获取作文要求
            print(f"\n[{step}/6] 获取作文要求")
            requirements = self.get_requirements()
            step += 1

            # 5. 撰写并提交作文
            grind_mode = self.config.get("grind_mode", False)
            if grind_mode:
                # 刷分模式: 循环提交直到达标
                print(f"\n[{step}/6] 刷分模式 - 目标 {self.target} 分")
                score = self._grind_score(requirements)
            else:
                # 普通模式: 只提交一次
                print(f"\n[{step}/6] 撰写并提交")
                essay = self.write_essay(requirements)
                self.submit_essay(essay)
                step += 1

                # 6. 等待批改并检查分数
                print(f"\n[{step}/6] 等待批改结果...")
                time.sleep(30)
                score = self.check_score()
            step += 1

            # 显示结果
            if score is not None:
                print(f"\n{'='*60}")
                print(f"  最终分数: {score} / 100")
                print(f"  目标分数: {self.target}")
                if score >= self.target:
                    print(f"  ✓ 达标!")
                else:
                    print(f"  ✗ 未达标")
                print(f"{'='*60}")
            else:
                print("\n  分数尚未生成，请稍后手动查看")

        except Exception as e:
            print(f"\n[错误] {e}")
            if self.page:
                self.page.screenshot(path="error_screenshot.png")
        finally:
            # 保持浏览器打开以便用户查看
            print("\n浏览器保持打开，按回车关闭...")
            try:
                input()
            except EOFError:
                pass
            self.stop()


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    automator = PigaiAutomator(CONFIG)
    automator.run()
