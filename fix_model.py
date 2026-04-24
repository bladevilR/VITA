"""
一键修复本地Embedding模型配置

问题：sentence-transformers加载模型时需要完整的Pooling配置
解决：自动创建缺失的配置文件

运行：python fix_model.py
"""

import json
import os

MODEL_DIR = "models"

print("=" * 70)
print("🔧 修复本地模型配置")
print("=" * 70)

# 步骤1：读取模型主配置
print("\n📖 步骤1：读取模型配置...")
config_path = os.path.join(MODEL_DIR, "config.json")

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    hidden_size = config.get('hidden_size')
    print(f"✅ 找到模型配置")
    print(f"   模型名称: {config.get('_name_or_path', '未知')}")
    print(f"   向量维度: {hidden_size}")

except FileNotFoundError:
    print(f"❌ 找不到 {config_path}")
    print("   请确认模型文件已正确下载到 models/ 目录")
    exit(1)

# 步骤2：检查modules.json
print("\n📖 步骤2：检查模块配置...")
modules_path = os.path.join(MODEL_DIR, "modules.json")

try:
    with open(modules_path, 'r', encoding='utf-8') as f:
        modules = json.load(f)
    print(f"✅ 模型包含以下模块:")
    for i, module in enumerate(modules):
        print(f"   {i}. {module['type']} ({module['path']})")
except FileNotFoundError:
    print(f"⚠️  找不到 {modules_path}")
    print("   将使用默认配置")
    modules = []

# 步骤3：创建Pooling配置（如果不存在）
print("\n🔧 步骤3：修复Pooling配置...")

# 检查是否有Pooling模块
has_pooling = any(m.get('type') == 'sentence_transformers.models.Pooling' for m in modules)

if has_pooling:
    print("✓ 模型配置中包含Pooling模块")

    # 检查配置文件
    pooling_dir = os.path.join(MODEL_DIR, "1_Pooling")
    pooling_config_path = os.path.join(pooling_dir, "config.json")

    if os.path.exists(pooling_config_path):
        with open(pooling_config_path, 'r', encoding='utf-8') as f:
            existing_config = json.load(f)
        print(f"✓ Pooling配置已存在: {pooling_config_path}")
        print(f"   内容: {existing_config}")

        # 检查是否有必需的字段
        if 'word_embedding_dimension' not in existing_config:
            print("⚠️  配置不完整，正在修复...")
            existing_config['word_embedding_dimension'] = hidden_size
            with open(pooling_config_path, 'w', encoding='utf-8') as f:
                json.dump(existing_config, f, indent=2, ensure_ascii=False)
            print("✅ 已添加缺失的 word_embedding_dimension")
    else:
        print(f"❌ 找不到 {pooling_config_path}")
        print("   正在创建...")

        # 创建目录
        os.makedirs(pooling_dir, exist_ok=True)

        # 创建配置
        pooling_config = {
            "word_embedding_dimension": hidden_size,
            "pooling_mode_cls_token": False,
            "pooling_mode_mean_tokens": True,
            "pooling_mode_max_tokens": False,
            "pooling_mode_mean_sqrt_len_tokens": False
        }

        with open(pooling_config_path, 'w', encoding='utf-8') as f:
            json.dump(pooling_config, f, indent=2, ensure_ascii=False)

        print(f"✅ 已创建 Pooling 配置")
        print(f"   路径: {pooling_config_path}")
        print(f"   配置: {json.dumps(pooling_config, indent=2, ensure_ascii=False)}")
else:
    print("✓ 模型不使用Pooling模块，跳过")

# 步骤4：创建或修复modules.json（如果需要）
print("\n🔧 步骤4：确认modules.json配置...")

if not modules or len(modules) == 0:
    print("⚠️  modules.json为空或不存在，创建默认配置...")

    default_modules = [
        {
            "idx": 0,
            "name": "0",
            "path": "",
            "type": "sentence_transformers.models.Transformer"
        },
        {
            "idx": 1,
            "name": "1",
            "path": "1_Pooling",
            "type": "sentence_transformers.models.Pooling"
        }
    ]

    with open(modules_path, 'w', encoding='utf-8') as f:
        json.dump(default_modules, f, indent=2, ensure_ascii=False)

    print("✅ 已创建默认 modules.json")

    # 同时创建Pooling配置
    pooling_dir = os.path.join(MODEL_DIR, "1_Pooling")
    os.makedirs(pooling_dir, exist_ok=True)

    pooling_config = {
        "word_embedding_dimension": hidden_size,
        "pooling_mode_cls_token": False,
        "pooling_mode_mean_tokens": True,
        "pooling_mode_max_tokens": False,
        "pooling_mode_mean_sqrt_len_tokens": False
    }

    pooling_config_path = os.path.join(pooling_dir, "config.json")
    with open(pooling_config_path, 'w', encoding='utf-8') as f:
        json.dump(pooling_config, f, indent=2, ensure_ascii=False)

    print(f"✅ 已创建 {pooling_config_path}")
else:
    print("✓ modules.json配置正常")

# 步骤5：测试加载
print("\n🧪 步骤5：测试模型加载...")

try:
    from sentence_transformers import SentenceTransformer

    print("   正在加载模型...")
    model = SentenceTransformer(MODEL_DIR, device='cpu')

    print("✅ 模型加载成功！")
    print(f"   向量维度: {model.get_sentence_embedding_dimension()}")

    # 测试编码
    print("\n   测试向量生成...")
    test_text = "测试文本"
    embedding = model.encode([test_text])
    print(f"✅ 向量生成成功！")
    print(f"   输入: '{test_text}'")
    print(f"   输出维度: {embedding.shape}")

except Exception as e:
    print(f"❌ 模型加载失败: {e}")
    print("\n可能的原因:")
    print("  1. sentence-transformers 未安装：pip install sentence-transformers")
    print("  2. 模型文件不完整")
    print("  3. 模型格式不兼容")
    exit(1)

# 完成
print("\n" + "=" * 70)
print("🎉 模型修复完成！")
print("=" * 70)
print("\n✅ 现在可以运行 create_knowledge_base.py 了")
print("\n命令: python create_knowledge_base.py")
print("=" * 70)