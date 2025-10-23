# Dashboard 专业仪表盘布局升级总结

## 概述
本次升级实现了专业仪表盘布局（方案二），包含以下核心功能：

1. **70-30 栅格布局** - 创建视觉焦点的专业布局
2. **SLA 对比图** - 替换状态时长分布，显示多时间窗口可用率
3. **P95/P99 增强** - 响应时间图添加性能百分位线
4. **联动交互** - Uptime 历史图与告警历史的智能联动

## 详细改动

### 1. 布局重构 (70-30 栅格)

#### HTML 结构 (`app/templates/dashboard.html`)
- 引入 `dashboard-grid` 容器，实现响应式栅格布局
- 左侧主区域 (`dashboard-main`，70% 宽度)：
  - 实时状态墙
  - 站点选择器
  - Uptime 历史状态图
  - 响应时间对比图
  - 日志告警历史表格
- 右侧次级信息栏 (`dashboard-sidebar`，30% 宽度)：
  - 4 个摘要卡片（已选站点、平均可用率、平均响应时间、异常事件）
  - SLA 对比图（新增）

#### CSS 样式 (`app/static/css/dashboard.css`)
```css
.dashboard-grid {
    display: grid;
    grid-template-columns: 1fr;  /* 移动端单列 */
}

@media (min-width: 1200px) {
    .dashboard-grid {
        grid-template-columns: 70fr 30fr;  /* 桌面端 70-30 布局 */
    }
    .dashboard-sidebar {
        position: sticky;
        top: 80px;  /* 粘性定位，保持可见 */
    }
}
```

### 2. SLA 对比图

#### 后端 API 增强 (`app/routes.py`)
在 `/api/history` 端点中添加 SLA 统计计算：

```python
# 计算不同时间窗口的可用率
now_utc = datetime.datetime.now(timezone.utc)
today_start = datetime.datetime.combine(now_utc.date(), datetime.time.min, tzinfo=timezone.utc)
week_start = now_utc - datetime.timedelta(days=7)
month_start = now_utc - datetime.timedelta(days=30)

sla_today = calc_availability_for_period(today_start, now_utc)
sla_week = calc_availability_for_period(week_start, now_utc)
sla_month = calc_availability_for_period(month_start, now_utc)

results[site]["sla_stats"] = {
    "today": sla_today,
    "week": sla_week,
    "month": sla_month
}
```

#### 前端渲染 (`app/static/js/dashboard.js`)
- 创建 `renderSLAComparison()` 函数
- 使用 ECharts 横向条形图（bar chart）
- 每个站点显示 3 个条形（今日、近7天、近30天）
- 根据可用率自动着色：
  - ≥ 99.99% → 绿色系
  - ≥ 99.9% → 浅绿色
  - ≥ 99% → 黄绿色
  - ≥ 95% → 橙色
  - < 95% → 红色
- Tooltip 显示可用率和"几个9"标签

### 3. P95/P99 增强

#### 后端计算 (`app/routes.py`)
```python
# 计算 P95 和 P99
p95_response_time = 0
p99_response_time = 0
if valid_times:
    sorted_times = sorted(valid_times)
    p95_index = int(len(sorted_times) * 0.95)
    p99_index = int(len(sorted_times) * 0.99)
    p95_response_time = sorted_times[min(p95_index, len(sorted_times) - 1)]
    p99_response_time = sorted_times[min(p99_index, len(sorted_times) - 1)]

results[site]["overall_stats"]["p95_response_time"] = p95_response_time
results[site]["overall_stats"]["p99_response_time"] = p99_response_time
```

#### 前端渲染 (`app/static/js/dashboard.js`)
- 在 `renderComparisonCharts()` 中增强响应时间图
- 为每个站点添加 P95 和 P99 参考线：
  - P95 使用虚线（dashed）
  - P99 使用点线（dotted）
  - 透明度 0.7，不响应鼠标事件（silent: true）
- 在图例中显示 P95/P99 线

### 4. Uptime 历史图与告警历史联动

#### 点击事件处理 (`app/static/js/dashboard.js`)
```javascript
timelineChart.on('click', function (params) {
    if (params.seriesType === 'custom' && params.value) {
        const status = params.value[3];
        const startTime = params.value[1];
        const endTime = params.value[2];
        const siteName = params.seriesName;
        
        // 只有宕机或慢响应才联动
        if (status === 3 || status === 2) {
            filterAndScrollToAlerts(siteName, startTime, endTime, status);
        }
    }
});
```

#### 联动功能 (`filterAndScrollToAlerts()`)
1. **滚动到告警历史区域** - 使用 `scrollIntoView()`
2. **自动筛选告警类型**：
   - 宕机（status === 3）→ 筛选 "宕机"
   - 慢响应（status === 2）→ 筛选 "访问过慢"
3. **高亮匹配的告警记录**：
   - 根据站点名称和时间范围匹配
   - 背景色变为淡黄色 (#fffacd)
   - 3秒后自动恢复
4. **Tooltip 提示** - 在宕机/慢响应分段的 tooltip 中显示 "💡 点击查看相关告警"

## 用户体验提升

### 布局优化
- **视觉焦点明确**：主图表占据 70% 宽度，一目了然
- **信息分层**：核心数据在主区域，概览数据在侧边栏
- **减少滚动**：关键信息在一屏内可见
- **响应式设计**：移动端自动切换为单列布局

### 数据洞察
- **SLA 对比**：快速对比不同时间窗口的稳定性
- **性能百分位**：P95/P99 线更能反映用户体验的"天花板"
- **联动分析**：从宏观（Uptime 图）到微观（告警详情）的流畅分析路径

### 交互反馈
- **可点击提示**：Tooltip 中明确提示可点击
- **视觉高亮**：高亮显示匹配的告警记录
- **平滑滚动**：使用 smooth scrolling 提升体验

## 技术亮点

1. **响应式栅格布局** - 使用 CSS Grid，支持多种屏幕尺寸
2. **粘性定位** - 侧边栏使用 sticky positioning，保持可见
3. **数据聚合计算** - 后端高效计算 P95/P99 和多时间窗口 SLA
4. **ECharts 高级特性** - 使用自定义渲染、事件监听、动态着色
5. **时间范围匹配** - 精准匹配告警记录的时间范围

## 测试验证

所有功能已通过测试：
- ✅ 布局在桌面端和移动端正常显示
- ✅ SLA 对比图正确显示不同时间窗口数据
- ✅ P95/P99 线正确渲染在响应时间图中
- ✅ 点击 Uptime 图的宕机/慢响应分段能正确联动
- ✅ API 返回完整的 sla_stats 和 p95/p99 数据

## 文件清单

修改的文件：
1. `app/templates/dashboard.html` - HTML 结构重构
2. `app/static/css/dashboard.css` - 栅格布局样式
3. `app/static/js/dashboard.js` - 前端逻辑增强
4. `app/routes.py` - 后端 API 数据增强

新增的文件：
1. `test_dashboard.html` - 功能测试页面
2. `DASHBOARD_UPGRADE_SUMMARY.md` - 本文档

## 部署说明

无需特殊部署步骤，更改即生效。建议：
1. 清除浏览器缓存以加载新的 CSS/JS
2. 确保有足够的历史数据以显示完整的 SLA 对比
3. 在不同屏幕尺寸下测试响应式布局

## 未来优化建议

1. **异常点标记** - 在响应时间图上高亮显示超过阈值的点
2. **平均线** - 为每个站点添加贯穿始终的平均响应时间虚线
3. **告警时间轴** - 在 Uptime 图下方添加告警事件标记
4. **导出功能** - 支持导出 SLA 报告和图表
5. **对比模式** - 支持选择不同时间段进行 SLA 对比

---

**升级完成时间**: 2025-01-23  
**版本**: v2.0 - 专业仪表盘布局
