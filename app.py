# -*- coding: utf-8 -*-
"""AI 经营分析助手 · Streamlit 界面
启动: streamlit run app.py
"""
import os
import streamlit as st

from agent_core import chat, load_key, basis_line

st.set_page_config(page_title="AI 经营分析助手", page_icon="🛒", layout="wide")
st.title("🛒 AI 经营分析助手")
st.caption("Olist 10 万订单 · SQL 工具库 × DeepSeek 归因推理 · 数据截止 2018-10-17")

# ---------- 侧边栏 ----------
with st.sidebar:
    st.header("设置")
    key_input = st.text_input("DeepSeek API Key",
                              value=st.session_state.get("_key", ""),
                              type="password",
                              help="仅存于本次会话内存，不写入任何文件")
    if not key_input:
        try:
            key_input = load_key()
            st.info("已自动加载项目根目录的 .api_key")
        except FileNotFoundError:
            st.warning("未找到 .api_key，请在上方输入 DeepSeek API Key")
    st.divider()
    st.subheader("试试这些问题")
    examples = [
        "2018 年 GMV 为什么停止增长？",
        "哪些品类贡献了最多的销售额？",
        "复购率是多少？这说明什么？",
        "差评的主要原因是什么？",
        "各地区的销售分布怎么样？",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["pending_question"] = ex

# ---------- 会话状态 ----------
if "messages" not in st.session_state:
    st.session_state.messages = []      # [{"role", "content", "trace"}]

# ---------- 历史渲染 ----------
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            st.caption(basis_line(m.get("trace")))
        if m.get("trace"):
            with st.expander(f"🔍 推理过程（调用 {len(m['trace'])} 次工具）"):
                for i, t in enumerate(m["trace"], 1):
                    st.markdown(f"**{i}. `{t['tool']}`**  参数: `{t['args']}`")
                    st.text(t["preview"])

# ---------- 输入处理 ----------
user_q = st.chat_input("问我任何关于这家电商的经营问题…")
pending = st.session_state.pop("pending_question", None)
if pending:
    user_q = pending

if user_q and key_input:
    # 先取历史再追加当前提问：chat() 内部会 append 当前提问，
    # 若把当前提问也放进 history 会导致同一句话被发两遍
    history = [{"role": m["role"], "content": m["content"]}
               for m in st.session_state.messages]
    st.session_state.messages.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)

    with st.chat_message("assistant"):
        with st.spinner("思考中…（取数 → 归因 → 结论）"):
            try:
                answer, trace = chat(user_q, key_input, history)
            except Exception as e:
                answer = f"出错了：{e}\n\n请检查 API Key 是否有效（上方侧边栏可更新）。"
                trace = []
        st.markdown(answer)
        st.caption(basis_line(trace))
        if trace:
            with st.expander(f"🔍 推理过程（调用 {len(trace)} 次工具）"):
                for i, t in enumerate(trace, 1):
                    st.markdown(f"**{i}. `{t['tool']}`**  参数: `{t['args']}`")
                    st.text(t["preview"])

    st.session_state.messages.append({"role": "assistant",
                                      "content": answer, "trace": trace})
elif user_q and not key_input:
    st.error("请先在侧边栏输入 DeepSeek API Key")
