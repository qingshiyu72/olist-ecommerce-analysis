# -*- coding: utf-8 -*-
"""
Agent 核心循环：DeepSeek function calling，LLM 自主决定调用哪些分析工具。
用法:
    python agent_core.py "2018年GMV为什么停止增长？"     # 单次提问（CLI 冒烟测试）
    python agent_core.py                               # 交互式命令行
"""
import json
import os
import sys
import requests

import agent_prompts
from agent_tools import TOOL_SPECS, dispatch

BASE = os.path.dirname(os.path.abspath(__file__))
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
MAX_TURNS = 8          # 单次提问最多工具调用轮数（防失控）
MAX_TOOL_CALLS = 5     # system prompt 里约定的工具调用上限


def load_key() -> str:
    key_path = os.path.join(BASE, ".api_key")
    if not os.path.exists(key_path):
        raise FileNotFoundError("未找到 .api_key，请在项目根目录创建并填入 DeepSeek API Key")
    return open(key_path, encoding="utf-8").read().strip()


def chat(user_question: str, key: str, history: list = None) -> tuple:
    """执行一次完整的 Agent 推理。返回 (最终回答, 工具调用轨迹)"""
    messages = [{"role": "system", "content": agent_prompts.SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-6:])           # 只带最近 3 轮，控制 token
    messages.append({"role": "user", "content": user_question})

    trace = []                                   # [(工具名, 参数, 结果摘要), ...]
    tool_calls_used = 0
    for turn in range(MAX_TURNS):
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": messages,
                "tools": TOOL_SPECS,
                "temperature": 0.1,
            },
            timeout=120,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]

        tool_calls = msg.get("tool_calls")
        if tool_calls and tool_calls_used < MAX_TOOL_CALLS:
            messages.append({"role": "assistant",
                             "content": msg.get("content"),
                             "tool_calls": tool_calls})
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = dispatch(name, args)
                tool_calls_used += 1
                trace.append({"tool": name, "args": args,
                              "preview": result[:150]})
                messages.append({"role": "tool",
                                 "tool_call_id": tc["id"],
                                 "content": result[:4000]})   # 截断防 token 爆炸
            continue

        # 无工具调用（或达到上限）→ 生成最终回答
        content = msg.get("content")
        if content is None and tool_calls_used >= MAX_TOOL_CALLS:
            messages.append({"role": "assistant", "content": "请基于以上工具结果直接回答。",
                             "tool_calls": None})
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "temperature": 0.1},
                timeout=120,
            )
            content = resp.json()["choices"][0]["message"]["content"]
        return content, trace

    return "（已达到最大推理轮数，请缩小问题范围重试）", trace


def main():
    key = load_key()
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        answer, trace = chat(question, key)
        if trace:
            print("── 工具调用轨迹 ──")
            for i, t in enumerate(trace, 1):
                print(f"  [{i}] {t['tool']}  参数={t['args']}")
        print("\n── 回答 ──")
        print(answer)
        return

    print("AI 经营分析助手（输入 q 退出）")
    history = []
    while True:
        try:
            q = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in {"q", "quit", "exit"}:
            break
        answer, trace = chat(q, key, history)
        for t in trace:
            print(f"  ⚙ {t['tool']}({t['args']})")
        print(f"\n助手> {answer}")
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
