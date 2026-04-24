"""
VITA 性能监控版本 - 添加详细的时间记录
在原有代码基础上添加性能监控
"""

import time
import json
from datetime import datetime

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.stages = []
        self.start_time = None

    def start(self):
        """开始监控"""
        self.start_time = time.time()
        self.stages = []

    def record(self, stage_name):
        """记录阶段"""
        if self.start_time is None:
            self.start_time = time.time()

        elapsed = time.time() - self.start_time
        self.stages.append({
            "stage": stage_name,
            "elapsed_time": round(elapsed, 2),
            "timestamp": datetime.now().isoformat()
        })
        print(f"[性能] {stage_name}: {elapsed:.2f}秒")

    def get_report(self):
        """获取报告"""
        if not self.stages:
            return {}

        total_time = self.stages[-1]["elapsed_time"] if self.stages else 0

        return {
            "total_time": total_time,
            "stages": self.stages,
            "stage_count": len(self.stages)
        }

    def save_report(self, filepath="performance_log.json"):
        """保存报告"""
        report = self.get_report()
        report["saved_at"] = datetime.now().isoformat()

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(report, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"保存性能报告失败: {e}")


# 使用示例：
# 在 diagnose_fault 函数开头添加：
# perf = PerformanceMonitor()
# perf.start()
#
# 在每个关键阶段后添加：
# perf.record("检索完成")
# perf.record("Rerank完成")
# perf.record("LLM生成完成")
#
# 最后：
# perf.save_report("E:/vita/performance_log.json")
