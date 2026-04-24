import oracledb
import pandas as pd
import re

# ============================================
# 配置区域
# ============================================
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "10.97.4.7:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# 阈值：一个专业至少出现多少次才被采纳为规则
MIN_COUNT_THRESHOLD = 100


# ============================================
# 主逻辑 (最终版)
# ============================================

def generate_final_rules():
    """
    【最终版】连接数据库，从SPECIALTY字段中提取关键词，生成规则字典。
    """
    print("=" * 60)
    print("🚀 开始生成VITA关键词规则字典... (最终正确版)")
    print("=" * 60)

    try:
        oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
        print("✅ Oracle客户端初始化成功。")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return

    # 核心改变：我们现在只关心 SPECIALTY
    query = f"""
        SELECT 
            SPECIALTY, 
            COUNT(*) as RECORD_COUNT
        FROM MAXIMO.SR
        WHERE 
            SPECIALTY IS NOT NULL
            AND REPORTDATE >= TO_DATE('2020-01-01', 'YYYY-MM-DD')
        GROUP BY 
            SPECIALTY
        HAVING 
            COUNT(*) >= {MIN_COUNT_THRESHOLD}
        ORDER BY 
            RECORD_COUNT DESC
    """

    try:
        print(f"\n🔗 正在连接数据库并按'SPECIALTY'分析 (阈值 > {MIN_COUNT_THRESHOLD} 条)...")
        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
            # 忽略Pandas的DBAPI2警告，不影响功能
            df = pd.read_sql(query, conn)
        print(f"✅ 查询完成，找到 {len(df)} 条符合条件的专业。")
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")
        return

    # 生成字典
    keyword_rules = {}

    # 定义需要被清理掉的常见后缀
    suffixes_to_remove = ['设备', '（综合维修）', '（维修）']

    print("\n" + "=" * 60)
    print("🤖 正在从'SPECIALTY'中智能提取关键词...")
    print("=" * 60)

    for _, row in df.iterrows():
        specialty_name = row['SPECIALTY']

        # 智能提取关键词
        keyword = specialty_name
        for suffix in suffixes_to_remove:
            keyword = keyword.replace(suffix, '')
        keyword = keyword.strip()  # 去除前后空格

        # 应用过滤器，确保关键词质量
        if keyword and not keyword.isnumeric() and len(keyword) > 1:
            # 避免重复添加
            if keyword not in keyword_rules:
                keyword_rules[keyword] = {
                    "专业": specialty_name,  # 保留原始的、完整的专业名称
                    "设备": keyword  # 使用清理后的核心词作为设备名
                }
                print(f"  - ✅ 提取成功: '{specialty_name}' -> '{keyword}'")

    print("\n" + "=" * 60)
    print("📋 生成的 KEYWORD_RULES 字典如下：")
    print("=" * 60)
    print(f"\n(从 {len(df)} 个专业中成功提炼出 {len(keyword_rules)} 条高质量规则)\n")
    print("请将下面的所有内容，完整复制到 'vita_web_ai.py' 文件中对应的位置：\n")

    # 格式化输出，按关键词长度倒序排列，优先匹配长关键词
    print("KEYWORD_RULES = {")
    sorted_rules = sorted(keyword_rules.items(), key=lambda item: len(item[0]), reverse=True)
    for keyword, info in sorted_rules:
        # 为了美观，对齐输出
        print(f'    "{keyword}":'.ljust(25) + f' {info},')
    print("}")
    print("\n" + "=" * 60)


if __name__ == '__main__':
    generate_final_rules()