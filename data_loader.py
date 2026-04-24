"""
数据库specialty字段分析工具
用于查找门禁相关设备在数据库中的真实名称
"""

import oracledb
import pandas as pd

# 数据库配置
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "10.97.4.7:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# 初始化Oracle客户端
oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)

print("=" * 80)
print("数据库specialty字段分析工具")
print("=" * 80)

# 连接数据库
conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
print("✅ 数据库连接成功\n")

# ============================================
# 查询1：所有specialty字段的值（去重）
# ============================================
print("【查询1】所有specialty字段的值（去重）")
print("-" * 80)

sql1 = """
SELECT DISTINCT SPECIALTY, COUNT(*) AS CNT
FROM MAXIMO.SR
WHERE SPECIALTY IS NOT NULL
GROUP BY SPECIALTY
ORDER BY CNT DESC
"""

df1 = pd.read_sql(sql1, conn)
print(f"共找到 {len(df1)} 种不同的specialty")
print("\n前20个高频specialty：")
print(df1.head(20).to_string(index=False))

# ============================================
# 查询2：包含"门禁"关键词的记录
# ============================================
print("\n\n【查询2】包含'门禁'关键词的工单")
print("-" * 80)

sql2 = """
SELECT SPECIALTY, COUNT(*) AS CNT
FROM MAXIMO.SR
WHERE UPPER(DESCRIPTION) LIKE '%门禁%'
   OR UPPER(LONGDESCRIPTION) LIKE '%门禁%'
GROUP BY SPECIALTY
ORDER BY CNT DESC
"""

df2 = pd.read_sql(sql2, conn)
if df2.empty:
    print("❌ 未找到包含'门禁'的工单")
else:
    print(f"✅ 找到 {df2['CNT'].sum()} 条包含'门禁'的工单，分布在以下specialty：")
    print(df2.to_string(index=False))

# ============================================
# 查询3：包含"通道"关键词的记录
# ============================================
print("\n\n【查询3】包含'通道'关键词的工单")
print("-" * 80)

sql3 = """
SELECT SPECIALTY, COUNT(*) AS CNT
FROM MAXIMO.SR
WHERE UPPER(DESCRIPTION) LIKE '%通道%'
   OR UPPER(LONGDESCRIPTION) LIKE '%通道%'
GROUP BY SPECIALTY
ORDER BY CNT DESC
"""

df3 = pd.read_sql(sql3, conn)
if df3.empty:
    print("❌ 未找到包含'通道'的工单")
else:
    print(f"✅ 找到 {df3['CNT'].sum()} 条包含'通道'的工单，分布在以下specialty：")
    print(df3.head(10).to_string(index=False))

# ============================================
# 查询4：包含"闸机"关键词的记录
# ============================================
print("\n\n【查询4】包含'闸机'关键词的工单")
print("-" * 80)

sql4 = """
SELECT SPECIALTY, COUNT(*) AS CNT
FROM MAXIMO.SR
WHERE UPPER(DESCRIPTION) LIKE '%闸机%'
   OR UPPER(LONGDESCRIPTION) LIKE '%闸机%'
GROUP BY SPECIALTY
ORDER BY CNT DESC
"""

df4 = pd.read_sql(sql4, conn)
if df4.empty:
    print("❌ 未找到包含'闸机'的工单")
else:
    print(f"✅ 找到 {df4['CNT'].sum()} 条包含'闸机'的工单，分布在以下specialty：")
    print(df4.to_string(index=False))

# ============================================
# 查询5：包含"AFC"关键词的记录（可能是付费区设备）
# ============================================
print("\n\n【查询5】包含'AFC'关键词的specialty")
print("-" * 80)

sql5 = """
SELECT SPECIALTY, COUNT(*) AS CNT
FROM MAXIMO.SR
WHERE UPPER(SPECIALTY) LIKE '%AFC%'
GROUP BY SPECIALTY
ORDER BY CNT DESC
"""

df5 = pd.read_sql(sql5, conn)
if df5.empty:
    print("❌ 未找到包含'AFC'的specialty")
else:
    print(f"✅ 找到以下AFC相关的specialty：")
    print(df5.to_string(index=False))

# ============================================
# 查询6：包含"安防"关键词的记录
# ============================================
print("\n\n【查询6】包含'安防'关键词的specialty")
print("-" * 80)

sql6 = """
SELECT SPECIALTY, COUNT(*) AS CNT
FROM MAXIMO.SR
WHERE UPPER(SPECIALTY) LIKE '%安防%'
   OR UPPER(SPECIALTY) LIKE '%门禁%'
GROUP BY SPECIALTY
ORDER BY CNT DESC
"""

df6 = pd.read_sql(sql6, conn)
if df6.empty:
    print("❌ 未找到包含'安防'或'门禁'的specialty")
else:
    print(f"✅ 找到以下安防相关的specialty：")
    print(df6.to_string(index=False))

# ============================================
# 查询7：具体查看"门禁"相关工单的示例
# ============================================
print("\n\n【查询7】门禁相关工单示例（前5条）")
print("-" * 80)

sql7 = """
SELECT TICKETID, LINENUM, STATIONNAME, SPECIALTY, DESCRIPTION
FROM MAXIMO.SR
WHERE UPPER(DESCRIPTION) LIKE '%门禁%'
   OR UPPER(LONGDESCRIPTION) LIKE '%门禁%'
ORDER BY REPORTDATE DESC
FETCH FIRST 5 ROWS ONLY
"""

df7 = pd.read_sql(sql7, conn)
if df7.empty:
    print("❌ 未找到门禁相关工单示例")
else:
    print("✅ 门禁相关工单示例：")
    for idx, row in df7.iterrows():
        print(f"\n工单 {idx+1}:")
        print(f"  工单号: {row['TICKETID']}")
        print(f"  线路: {row['LINENUM']}")
        print(f"  车站: {row['STATIONNAME']}")
        print(f"  专业: {row['SPECIALTY']}")
        print(f"  描述: {row['DESCRIPTION'][:100]}")

# 关闭连接
conn.close()

print("\n" + "=" * 80)
print("分析完成！")
print("=" * 80)

print("\n\n【建议】")
print("根据以上查询结果，你需要：")
print("1. 看查询2-7的结果，找出'门禁'在specialty字段中的真实名称")
print("2. 将这些名称添加到SPECIALTY_SYNONYMS字典中")
print("3. 如果specialty字段本身就包含'门禁'，说明同义词映射有问题")
print("4. 如果specialty是其他名称（如AFC、安防等），需要建立映射关系")