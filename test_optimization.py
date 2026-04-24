"""
直接测试 VITA 核心函数的性能
不依赖 Streamlit，直接调用函数
"""
import sys
import time
import os

# 添加当前目录到路径
sys.path.insert(0, 'E:/vita')

def test_imports():
    """测试导入"""
    print("=" * 60)
    print("测试 1: 导入模块")
    print("=" * 60)

    try:
        import vita
        print("✅ vita.py 导入成功")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_database_connection():
    """测试数据库连接"""
    print("\n" + "=" * 60)
    print("测试 2: 数据库连接")
    print("=" * 60)

    try:
        from vita import DatabaseManager
        start = time.time()
        db = DatabaseManager()
        elapsed = time.time() - start
        print(f"✅ 数据库连接成功 ({elapsed:.2f}秒)")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False

def test_faiss_loading():
    """测试 FAISS 索引加载"""
    print("\n" + "=" * 60)
    print("测试 3: FAISS 索引加载")
    print("=" * 60)

    try:
        import faiss
        start = time.time()

        index_path = "E:/vita/faiss_index_curated_v15.index"
        if os.path.exists(index_path):
            index = faiss.read_index(index_path)
            elapsed = time.time() - start
            print(f"✅ FAISS 索引加载成功 ({elapsed:.2f}秒)")
            print(f"   索引大小: {index.ntotal} 条")
            return True
        else:
            print(f"❌ 索引文件不存在: {index_path}")
            return False
    except Exception as e:
        print(f"❌ FAISS 加载失败: {e}")
        return False

def test_optimization_applied():
    """验证优化是否已应用"""
    print("\n" + "=" * 60)
    print("测试 4: 验证优化参数")
    print("=" * 60)

    try:
        with open('E:/vita/vita.py', 'r', encoding='utf-8') as f:
            content = f.read()

        checks = {
            'max_tokens=1200': 'max_tokens=1200' in content,
            'k=50 (FAISS)': 'k=50' in content and '# 优化' in content,
            'head(30) (Rerank)': 'head(30)' in content and '# 优化' in content,
        }

        all_passed = True
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"{status} {check}: {'已应用' if passed else '未应用'}")
            if not passed:
                all_passed = False

        return all_passed
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False

def main():
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "VITA 性能优化验证测试" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = []

    # 测试 1: 导入
    results.append(("导入模块", test_imports()))

    # 测试 2: 数据库
    results.append(("数据库连接", test_database_connection()))

    # 测试 3: FAISS
    results.append(("FAISS索引", test_faiss_loading()))

    # 测试 4: 优化验证
    results.append(("优化参数", test_optimization_applied()))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")

    print()
    print(f"通过率: {passed}/{total} ({passed/total*100:.0f}%)")

    if passed == total:
        print("\n🎉 所有测试通过！优化已成功应用。")
        print("\n下一步:")
        print("  1. 手动运行: D:\\python\\python.exe -m streamlit run vita.py")
        print("  2. 在浏览器中测试查询")
        print("  3. 查看终端日志中的性能数据")
    else:
        print("\n⚠️ 部分测试失败，请检查环境配置。")

    print()

if __name__ == "__main__":
    main()
