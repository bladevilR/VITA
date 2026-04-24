import pandas as pd
import oracledb

# --- 配置信息 ---
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "10.97.4.7:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# --- 初始化 ---
try:
    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
except Exception as e:
    print(f"Oracle Client 初始化失败: {e}")
    exit()

if __name__ == '__main__':
    print("--- VITA SR视图侦察工具 ---")
    try:
        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as connection:
            print("\n" + "="*50)
            print("--- 任务一：正在侦察 SR 视图的结构和样本数据 ---")
            print("="*50)
            try:
                # 设置pandas以显示所有列
                pd.set_option('display.max_columns', None)
                df_sample = pd.read_sql("SELECT * FROM MAXIMO.SR FETCH FIRST 5 ROWS ONLY", connection)
                print("SR 视图的列名和前5条数据样本如下：")
                print(df_sample)
            except Exception as e:
                print(f"查询样本数据失败: {e}")

            print("\n" + "="*50)
            print("--- 任务二：正在侦察 SR 视图的数据时间范围 ---")
            print("="*50)
            try:
                df_range = pd.read_sql("SELECT MIN(REPORTDATE) AS EARLIEST_DATE, MAX(REPORTDATE) AS LATEST_DATE FROM MAXIMO.SR", connection)
                print("SR 视图的数据时间范围如下：")
                print(df_range)
            except Exception as e:
                print(f"查询时间范围失败: {e}")

    except Exception as e:
        print(f"数据库连接失败: {e}")