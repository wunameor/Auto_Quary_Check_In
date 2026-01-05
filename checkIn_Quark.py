# -*- coding: utf-8 -*-
"""
Quark Auto Check-In (Stable Version for 2026)
Author: ChatGPT (based on community scripts)
Feature:
- Multi-account support
- Never crash on API changes
- GitHub Actions friendly (no exit 1 for business failure)
"""

import os
import time
import requests


class Quark:
    def __init__(self, param: dict):
        self.param = param
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 Chrome/120",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://drive-m.quark.cn/",
        })

    def do_sign(self):
        user = self.param.get("user", "未知用户")
        url = self.param.get("url")

        if not url:
            print(f"❌ [{user}] 未提供签到 URL，跳过")
            return

        try:
            resp = self.session.get(url, timeout=15)
        except Exception as e:
            print(f"❌ [{user}] 请求失败: {e}")
            return

        print(f"ℹ️ [{user}] HTTP 状态码: {resp.status_code}")

        try:
            data = resp.json()
        except Exception:
            print(f"❌ [{user}] 返回非 JSON 数据，内容如下：")
            print(resp.text[:200])
            return

        # 打印原始返回，方便以后排查接口变更
        print(f"🔍 [{user}] 返回数据: {data}")

        # ====== 尝试解析成长信息（接口经常变，这里必须非常宽容） ======
        growth_info = None
        if isinstance(data, dict):
            growth_info = data.get("data") or data.get("result") or data

        is_vip = False
        if isinstance(growth_info, dict):
            is_vip = growth_info.get("88VIP", False)

        # ====== 解析签到结果 ======
        msg = data.get("msg") or data.get("message") or "未知返回"
        code = data.get("code")

        print(
            f"✅ [{user}] 身份: {'88VIP' if is_vip else '普通用户'} | "
            f"结果码: {code} | 信息: {msg}"
        )


def parse_env():
    """
    解析 COOKIE_QUARK 环境变量
    支持：
    - 单账号
    - 多账号（&& 分隔）
    """
    env = os.getenv("COOKIE_QUARK")
    if not env:
        print("❌ 未检测到 COOKIE_QUARK 环境变量")
        return []

    accounts = []
    parts = env.split("&&")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        param = {}
        if "url=" in part:
            # url=xxx; kps=xxx; sign=xxx
            for seg in part.split(";"):
                if "=" in seg:
                    k, v = seg.split("=", 1)
                    param[k.strip()] = v.strip()
        else:
            # 兼容旧格式：kps=xxx; sign=xxx
            for seg in part.split(";"):
                if "=" in seg:
                    k, v = seg.split("=", 1)
                    param[k.strip()] = v.strip()

        # user 字段可选
        if "user" not in param:
            param["user"] = f"账号{len(accounts)+1}"

        accounts.append(param)

    return accounts


def main():
    print("---------- 夸克网盘开始签到 ----------")

    users = parse_env()
    print(f"✅ 检测到共 {len(users)} 个夸克账号")

    for idx, user_data in enumerate(users, start=1):
        print(f"\n👉 开始处理第 {idx} 个账号：{user_data.get('user')}")
        try:
            Quark(user_data).do_sign()
        except Exception as e:
            # 兜底保护：任何异常都不影响其他账号 & 不影响 Actions
            print(f"❌ [{user_data.get('user')}] 发生未捕获异常: {e}")

        time.sleep(2)

    print("\n---------- 夸克网盘签到结束 ----------")


if __name__ == "__main__":
    main()
