# -*- coding: utf-8 -*-
"""
SQL 模块运行器：跑 sql/ 下所有 .sql，打印结果摘要，并导出 CSV 到 output/
用法:
    python run_sql.py            # 跑全部模块
    python run_sql.py 01 04      # 只跑指定编号
"""
import os
import re
import sys
import sqlite3
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "olist.db")
SQL_DIR = os.path.join(BASE, "sql")
OUT = os.path.join(BASE, "output")


def strip_comment_lines(sql: str) -> str:
    """去掉整行注释和行内注释（本项目的 SQL 字符串里不含 '--'，可安全移除）"""
    no_inline = re.sub(r"--[^\n]*", "", sql)
    return "\n".join(line for line in no_inline.splitlines() if line.strip())


def run_file(conn, path: str, export: bool = True):
    name = os.path.basename(path)
    raw = open(path, encoding="utf-8").read()
    code = strip_comment_lines(raw)
    stmts = [s.strip() for s in code.split(";") if s.strip()]
    print(f"\n{'='*60}\n▶ {name}")
    for i, stmt in enumerate(stmts, 1):
        up = stmt.lstrip().upper()
        is_select = up.startswith("SELECT") or up.startswith("WITH")
        try:
            if is_select:
                df = pd.read_sql_query(stmt, conn)
            else:
                conn.execute(stmt)          # DDL/DML（如 TEMP TABLE + INDEX）
                conn.commit()
                continue                    # 非查询语句不出结果
        except Exception as e:
            print(f"  ❌ 语句 {i} 报错: {e}")
            return False
        head = f"  语句{i}: {len(df)} 行 x {len(df.columns)} 列"
        if export and len(df) and not df.empty:
            stem = re.sub(r"\.sql$", "", name)
            out_path = os.path.join(OUT, f"{stem}_{i}.csv")
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            head += f"  → output/{os.path.basename(out_path)}"
        print(head)
        if not df.empty:
            print("  " + df.head(3).to_string(index=False).replace("\n", "\n  "))
    return True


def main():
    os.makedirs(OUT, exist_ok=True)
    conn = sqlite3.connect(DB)
    wanted = [a.zfill(2) for a in sys.argv[1:]]
    files = sorted(f for f in os.listdir(SQL_DIR) if f.endswith(".sql"))
    ok = 0
    for f in files:
        if wanted and not any(f.startswith(w) for w in wanted):
            continue
        if run_file(conn, os.path.join(SQL_DIR, f)):
            ok += 1
    conn.close()
    total = len(files) if not wanted else len(wanted)
    print(f"\n{'='*60}\n完成: {ok}/{total} 个模块跑通 ✅" if ok == total
          else f"\n{'='*60}\n⚠️ {ok}/{total} 通过，有报错请检查")


if __name__ == "__main__":
    main()
