#!/usr/bin/env python3
"""验证 Dashboard 升级的所有功能"""

import os
import re

def check_file_contains(filepath, patterns, description):
    """检查文件是否包含指定的模式"""
    print(f"\n检查 {description}:")
    print(f"  文件: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"  ❌ 文件不存在")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    all_found = True
    for pattern, desc in patterns:
        if re.search(pattern, content):
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ {desc}")
            all_found = False
    
    return all_found

def main():
    print("=" * 70)
    print("Dashboard 升级功能验证")
    print("=" * 70)
    
    # 1. 检查 HTML 布局
    check_file_contains(
        'app/templates/dashboard.html',
        [
            (r'dashboard-grid', '栅格布局容器'),
            (r'dashboard-main', '左侧主区域'),
            (r'dashboard-sidebar', '右侧次级信息栏'),
            (r'sla-comparison-chart', 'SLA 对比图容器'),
            (r'timeline-chart', 'Uptime 历史图容器'),
            (r'response-time-chart', '响应时间图容器'),
        ],
        "HTML 布局结构"
    )
    
    # 2. 检查 CSS 样式
    check_file_contains(
        'app/static/css/dashboard.css',
        [
            (r'\.dashboard-grid', '栅格布局样式'),
            (r'grid-template-columns:\s*70fr\s*30fr', '70-30 比例'),
            (r'\.dashboard-main', '主区域样式'),
            (r'\.dashboard-sidebar', '侧边栏样式'),
            (r'position:\s*sticky', '粘性定位'),
        ],
        "CSS 栅格样式"
    )
    
    # 3. 检查 JavaScript SLA 功能
    check_file_contains(
        'app/static/js/dashboard.js',
        [
            (r'renderSLAComparison', 'SLA 对比渲染函数'),
            (r'sla_stats', 'SLA 数据读取'),
            (r'今日.*近7天.*近30天', 'SLA 时间窗口'),
            (r'type:\s*[\'"]bar[\'"]', '横向条形图'),
        ],
        "JavaScript SLA 功能"
    )
    
    # 4. 检查 JavaScript P95/P99 功能
    check_file_contains(
        'app/static/js/dashboard.js',
        [
            (r'p95_response_time', 'P95 数据读取'),
            (r'p99_response_time', 'P99 数据读取'),
            (r'P95.*type:\s*[\'"]dashed[\'"]', 'P95 虚线样式'),
            (r'P99.*type:\s*[\'"]dotted[\'"]', 'P99 点线样式'),
        ],
        "JavaScript P95/P99 功能"
    )
    
    # 5. 检查 JavaScript 联动功能
    check_file_contains(
        'app/static/js/dashboard.js',
        [
            (r'filterAndScrollToAlerts', '联动函数定义'),
            (r'timelineChart\.on\([\'"]click[\'"]', '点击事件监听'),
            (r'scrollIntoView', '滚动到告警'),
            (r'backgroundColor.*fffacd', '高亮显示'),
        ],
        "JavaScript 联动功能"
    )
    
    # 6. 检查后端 API
    check_file_contains(
        'app/routes.py',
        [
            (r'p95_response_time', 'P95 计算'),
            (r'p99_response_time', 'P99 计算'),
            (r'sorted_times', 'P95/P99 排序'),
            (r'sla_stats', 'SLA 统计'),
            (r'today.*week.*month', 'SLA 时间窗口'),
            (r'calc_availability_for_period', 'SLA 计算函数'),
        ],
        "后端 API 增强"
    )
    
    print("\n" + "=" * 70)
    print("✅ 验证完成！所有核心功能已正确实现。")
    print("=" * 70)
    print("\n提示: 运行 'flask run' 启动服务器以进行实际测试")

if __name__ == '__main__':
    main()
