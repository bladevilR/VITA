import pandas as pd
import oracledb

# --- 配置信息 ---
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "htdora-scan.sz-mtr.com:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# --- 初始化 ---
try:
    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
except Exception as e:
    print(f"Oracle Client 初始化失败: {e}")
    exit()

# --- 发现查询 ---
# 这个查询会获取 TICKET 表的第一行数据，从而让我们看到所有的列名
QUERY = "SELECT * FROM MAXIMO.TICKET FETCH FIRST 1 ROWS ONLY"

if __name__ == '__main__':
    print("--- VITA 表结构发现工具 ---")
    try:
        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as connection:
            print("--- ----------------------------------------------------")
            print("--- 正在查询 MAXIMO.TICKET 的第一行以获取所有列名...")
            print("--- ----------------------------------------------------")
            df = pd.read_sql(QUERY, connection)
            print("\n--- 发现完成！ ---")
            print("MAXIMO.TICKET 表中的列名如下：")

            # 打印所有列名
            for col in df.columns.tolist():
                print(col)

    except Exception as e:
        print(f"数据库查询失败: {e}")