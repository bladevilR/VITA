import oracledb
import pandas as pd
import sys
import os

# ============================================
# 配置
# ============================================
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "10.97.4.7:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# ============================================
# 【请在这里修改】 - 放入1-3个你想查的工单号
# ============================================
TICKET_IDS_TO_CHECK = [
    "SD8870423",
    # "请在这里添加另一个工单号",
    # "再添加一个工单号"
]
# ============================================

# 我们只查询最关心的、之前“未捕获”的关键字段
COLUMNS_WE_NEED = [
    "TICKETID",
    "DESCRIPTION",
    "STATIONNAME",
    "SPECIALTY",
    "SOLUTION",
    "PROCREMEDY",
    "OWNER",
    "OWNERGROUP",
    "STATUS"
]


def safe_print_series(series):
    """安全地打印pandas Series"""
    for index, value in series.items():
        # 为了对齐，手动格式化输出
        print(f"{str(index):<20} : {str(value)}")


def get_specific_data():
    """
    精准捕获指定工单的关键字段数据，验证数据完整性。
    """
    try:
        os.environ['NLS_LANG'] = 'AMERICAN_AMERICA.AL32UTF8'
        oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
    except Exception as e:
        print(f"Oracle Client 初始化失败: {e}")
        sys.exit(1)

    print("正在连接到 Maximo 数据库...")

    try:
        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
            print("✅ 连接成功！")

            # 将我们要查询的列名列表转换为SQL字符串
            sql_columns = ", ".join(COLUMNS_WE_NEED)

            # 使用参数化查询来安全地处理多个ID
            placeholders = ", ".join([f":id_{i}" for i in range(len(TICKET_IDS_TO_CHECK))])
            params = {f"id_{i}": ticket_id for i, ticket_id in enumerate(TICKET_IDS_TO_CHECK)}

            sql_query = f"SELECT {sql_columns} FROM MAXIMO.SR WHERE TICKETID IN ({placeholders})"

            print("正在执行精准查询...")
            df_results = pd.read_sql(sql_query, conn, params=params)

            if df_results.empty:
                print("错误：未找到任何指定的工单。请检查工单号是否正确。")
                return

            print("\n" + "=" * 50)
            print("🎉 精准捕获成功！以下是完整的关键数据：")
            print("=" * 50)

            # 逐一打印每个工单的结果
            for index, row in df_results.iterrows():
                print(f"\n--- 案例: {row['TICKETID']} ---")
                safe_print_series(row)
                print("-" * (len(row['TICKETID']) + 8))

    except oracledb.DatabaseError as e:
        error_obj, = e.args
        print(f"数据库错误: {error_obj.message}")
    except Exception as e:
        print(f"发生未知错误: {e}")


if __name__ == "__main__":
    import warnings

    warnings.filterwarnings('ignore', category=UserWarning, module='pandas')
    get_specific_data()