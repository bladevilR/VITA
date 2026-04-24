"""
VITA 性能测试脚本 - 使用 Selenium 进行无头浏览器测试
"""
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VITAPerformanceTester:
    def __init__(self, url="http://localhost:8501"):
        self.url = url
        self.driver = None
        self.results = []

    def setup_driver(self):
        """设置无头浏览器"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=chrome_options)
        logger.info("无头浏览器已启动")

    def test_query(self, query_text, timeout=120):
        """测试单个查询的性能"""
        logger.info(f"测试查询: {query_text}")

        try:
            # 访问页面
            start_time = time.time()
            self.driver.get(self.url)
            page_load_time = time.time() - start_time
            logger.info(f"页面加载时间: {page_load_time:.2f}秒")

            # 等待输入框加载
            wait = WebDriverWait(self.driver, 30)
            input_box = wait.until(
                EC.presence_of_element_located((By.TAG_NAME, "textarea"))
            )

            # 输入查询
            input_box.clear()
            input_box.send_keys(query_text)
            logger.info("查询已输入")

            # 查找并点击提交按钮
            submit_button = self.driver.find_element(By.XPATH, "//button[contains(text(), '提交') or contains(text(), '发送')]")

            query_start_time = time.time()
            submit_button.click()
            logger.info("查询已提交")

            # 监控进度提示
            stages = []
            last_status = ""

            while True:
                try:
                    # 查找状态文本
                    status_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '检索') or contains(text(), '分析') or contains(text(), '生成')]")

                    if status_elements:
                        current_status = status_elements[0].text
                        if current_status != last_status:
                            elapsed = time.time() - query_start_time
                            stages.append({
                                "stage": current_status,
                                "time": elapsed
                            })
                            logger.info(f"阶段: {current_status} (耗时: {elapsed:.2f}秒)")
                            last_status = current_status

                    # 检查是否完成（查找结果容器）
                    result_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '处理建议') or contains(text(), '诊断') or contains(text(), '建议')]")

                    if result_elements and len(result_elements[0].text) > 100:
                        total_time = time.time() - query_start_time
                        logger.info(f"查询完成，总耗时: {total_time:.2f}秒")

                        result = {
                            "query": query_text,
                            "page_load_time": page_load_time,
                            "total_query_time": total_time,
                            "stages": stages,
                            "success": True
                        }
                        self.results.append(result)
                        return result

                    # 检查超时
                    if time.time() - query_start_time > timeout:
                        logger.error(f"查询超时 (>{timeout}秒)")
                        result = {
                            "query": query_text,
                            "page_load_time": page_load_time,
                            "total_query_time": timeout,
                            "stages": stages,
                            "success": False,
                            "error": "timeout"
                        }
                        self.results.append(result)
                        return result

                    time.sleep(0.5)

                except Exception as e:
                    logger.warning(f"监控异常: {e}")
                    time.sleep(1)

        except Exception as e:
            logger.error(f"测试失败: {e}")
            result = {
                "query": query_text,
                "success": False,
                "error": str(e)
            }
            self.results.append(result)
            return result

    def run_test_suite(self):
        """运行测试套件"""
        test_queries = [
            "3号线横山站ISCS工作站黑屏怎么办",
            "AFC闸机不能刷卡",
            "FAS报警主机故障",
            "电扶梯异响",
            "照明系统故障"
        ]

        logger.info(f"开始测试，共 {len(test_queries)} 个查询")

        for i, query in enumerate(test_queries, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"测试 {i}/{len(test_queries)}")
            logger.info(f"{'='*60}")

            self.test_query(query)

            # 等待一下再进行下一个测试
            time.sleep(3)

    def generate_report(self):
        """生成性能报告"""
        if not self.results:
            logger.warning("没有测试结果")
            return

        report = {
            "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tests": len(self.results),
            "successful_tests": sum(1 for r in self.results if r.get("success")),
            "results": self.results
        }

        # 计算平均时间
        successful_results = [r for r in self.results if r.get("success")]
        if successful_results:
            avg_time = sum(r["total_query_time"] for r in successful_results) / len(successful_results)
            report["average_query_time"] = avg_time

            logger.info(f"\n{'='*60}")
            logger.info("性能测试报告")
            logger.info(f"{'='*60}")
            logger.info(f"总测试数: {report['total_tests']}")
            logger.info(f"成功数: {report['successful_tests']}")
            logger.info(f"平均查询时间: {avg_time:.2f}秒")

            for i, result in enumerate(successful_results, 1):
                logger.info(f"\n查询 {i}: {result['query']}")
                logger.info(f"  总耗时: {result['total_query_time']:.2f}秒")
                if result.get('stages'):
                    logger.info("  阶段详情:")
                    for stage in result['stages']:
                        logger.info(f"    - {stage['stage']}: {stage['time']:.2f}秒")

        # 保存到文件
        with open("E:/vita/performance_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"\n报告已保存到: E:/vita/performance_report.json")

        return report

    def cleanup(self):
        """清理资源"""
        if self.driver:
            self.driver.quit()
            logger.info("浏览器已关闭")


def main():
    tester = VITAPerformanceTester()

    try:
        tester.setup_driver()
        tester.run_test_suite()
        tester.generate_report()
    finally:
        tester.cleanup()


if __name__ == "__main__":
    main()
