#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import json
import requests
from urllib.parse import urlparse, parse_qs

INFO_URL = "https://drive-m.quark.cn/1/clouddrive/capacity/growth/info"
SIGN_URL = "https://drive-m.quark.cn/1/clouddrive/capacity/growth/sign"

UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Mobile Safari/537.36"
)

def _strip_value(v: str) -> str:
    # 去掉首尾空白 + 末尾多余分号
    return v.strip().rstrip(";").strip()

def parse_cookie_quark_env() -> list[dict]:
    raw = os.getenv("COOKIE_QUARK", "")

    if not raw.strip():
        print("❌ 未检测到环境变量 COOKIE_QUARK")
        return []

    # 用“空行”切账号（兼容 GitHub Secrets 里的 CRLF/空格空行）
    blocks = re.split(r"\r?\n\s*\r?\n", raw.strip())
    users: list[dict] = []

    for block in blocks:
        param: dict = {}
        for line in block.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            param[_strip_value(k)] = _strip_value(v)

        # 兼容：有人把 cookie;kps=...&sign=...&vcode=... 这种塞到 cookie 里
        # 如果存在 cookie 且 cookie 后面附带 kps/sign/vcode，用它补齐参数
        cookie = param.get("cookie") or param.get("Cookie")
        if cookie and ";" in cookie and ("kps=" in cookie or "sign=" in cookie or "vcode=" in cookie):
            # cookie; kps=...&sign=...&vcode=...
            parts = cookie.split(";", 1)
            param["cookie"] = parts[0].strip()
            tail = parts[1].strip()
            # tail 可能是 kps=...&sign=...&vcode=...
            for kv in tail.split("&"):
                if "=" in kv:
                    kk, vv = kv.split("=", 1)
                    param.setdefault(kk.strip(), vv.strip())

        # 如果给了 url，从 url 里提取 kps/sign/vcode
        url = param.get("url")
        if url:
            qs = parse_qs(urlparse(url).query)
            for k in ("kps", "sign", "vcode"):
                if k in qs and qs[k]:
                    param[k] = qs[k][0]

        # user 默认值
        param["user"] = _strip_value(param.get("user", f"账号{len(users)+1}"))

        users.append(param)

    return users

def _request_params(param: dict) -> dict:
    # 按社区常用写法带上 pr/fr，并补 sign_cyclic
    return {
        "pr": "ucpro",
        "fr": "android",
        "kps": param.get("kps", ""),
        "sign": param.get("sign", ""),
        "vcode": param.get("vcode", ""),
    }

def get_growth_info(session: requests.Session, param: dict) -> dict:
    qs = _request_params(param)
    # 有些实现会加 __t 和 sign_cyclic=true（容错更好）
    qs["__t"] = str(int(time.time() * 1000))
    qs["sign_cyclic"] = "true"
    resp = session.get(INFO_URL, params=qs, timeout=20)
    try:
        data = resp.json()
    except Exception:
        data = {"status": resp.status_code, "raw": resp.text[:200]}
    return {"http": resp.status_code, "json": data}

def do_sign(session: requests.Session, param: dict) -> dict:
    qs = _request_params(param)
    payload = {"sign_cyclic": True}
    resp = session.post(SIGN_URL, params=qs, json=payload, timeout=20)
    try:
        data = resp.json()
    except Exception:
        data = {"status": resp.status_code, "raw": resp.text[:200]}
    return {"http": resp.status_code, "json": data}

def main():
    print("---------- 夸克网盘开始签到 ----------")

    users = parse_cookie_quark_env()
    print(f"✅ 检测到共 {len(users)} 个夸克账号")

    failed = []   # [(user, reason)]
    skipped = []  # [(user, reason)]

    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://drive-m.quark.cn/",
    })

    for idx, u in enumerate(users, start=1):
        user = u.get("user", f"账号{idx}")

        print(f"\n👉 开始处理第 {idx} 个账号：{user}")

        # 校验必要参数
        if not u.get("kps") or not u.get("sign") or not u.get("vcode"):
            reason = "缺少 kps/sign/vcode（请从 /capacity/growth/info 抓包获取）"
            print(f"❌ [{user}] {reason}，跳过")
            skipped.append((user, reason))
            continue

        # 可选：cookie
        cookie = u.get("cookie")
        if cookie:
            session.headers["Cookie"] = cookie

        # 1) 拉成长/签到信息
        info = get_growth_info(session, u)
        print(f"ℹ️ [{user}] info HTTP 状态码: {info['http']}")
        print(f"🔍 [{user}] info 返回: {info['json']}")

        if info["http"] != 200:
            reason = f"info 接口 HTTP={info['http']}"
            print(f"❌ [{user}] {reason}")
            failed.append((user, reason))
            continue

        j = info["json"]
        code = j.get("code")
        msg = j.get("message") if j.get("message") is not None else (j.get("msg") or "")
        data = j.get("data") or {}

        if code not in (0, None):
            reason = f"info code={code} msg={msg}"
            print(f"❌ [{user}] {reason}")
            failed.append((user, reason))
            continue
            
        if not isinstance(data, dict):
            reason = f"info 接口返回异常 data={data}"
            print(f"❌ [{user}] {reason}")
            failed.append((user, reason))
            continue

        # 2) 判断是否已签到（按常见字段容错）
        cap_sign = data.get("cap_sign") or {}
        already = bool(cap_sign.get("sign_daily"))  # 常见字段
        vip = "88VIP" if data.get("88VIP") else "普通用户"

        if already:
            print(f"✅ [{user}] 身份: {vip} | 今日已签到")
            continue

        # 3) 未签到则执行签到
        sign_ret = do_sign(session, u)
        print(f"ℹ️ [{user}] sign HTTP 状态码: {sign_ret['http']}")
        print(f"🔍 [{user}] sign 返回: {sign_ret['json']}")

        if sign_ret["http"] != 200:
            reason = f"sign 接口 HTTP={sign_ret['http']}"
            print(f"❌ [{user}] {reason}")
            failed.append((user, reason))
            continue

        sj = sign_ret["json"]
        scode = sj.get("code")
        smsg = sj.get("message") if sj.get("message") is not None else (sj.get("msg") or "")
        if scode != 0:
            reason = f"sign code={scode} msg={smsg}"
            print(f"❌ [{user}] {reason}")
            failed.append((user, reason))
            continue

        print(f"✅ [{user}] 身份: {vip} | 签到成功")

    print("\n---------- 夸克网盘签到结束 ----------")

    # 统一在最后抛异常，触发 GitHub Actions 失败邮件
    if skipped or failed:
        lines = []
        if skipped:
            lines.append("跳过账号：")
            lines += [f"- {u}: {r}" for u, r in skipped]
        if failed:
            lines.append("失败账号：")
            lines += [f"- {u}: {r}" for u, r in failed]
        raise Exception("检测到异常账号，请检查参数：\n" + "\n".join(lines))

if __name__ == "__main__":
    main()
