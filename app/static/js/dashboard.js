// 使用 document.addEventListener 确保 DOM 完全加载后再执行脚本
document.addEventListener('DOMContentLoaded', () => {
    // --- 变量初始化 ---
    const uptimeChart = echarts.init(document.getElementById('uptime-chart'));
    const responseTimeChart = echarts.init(document.getElementById('response-time-chart'));
    const uptimeHistoryContainer = document.getElementById('uptime-history-charts');
    const tooltip = document.getElementById('uptime-tooltip');
    // 直接从 window 对象获取已经解析好的数据，不再需要 JSON.parse
    const initialStatuses = window.INITIAL_STATUSES;
    const dataRetentionDays = window.DATA_RETENTION_DAYS;
    let currentParams = {};
    let flatpickrInstance;
    // --- 核心功能函数 ---
    const toLocalISOString = dt =>
        `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}T${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
    function showLoading() {
        uptimeChart.showLoading();
        responseTimeChart.showLoading();
        uptimeHistoryContainer.innerHTML = '<p>加载中...</p>';
    }
    function hideLoading() {
        uptimeChart.hideLoading();
        responseTimeChart.hideLoading();
    }
    function renderUptimeHistory(data) {
        uptimeHistoryContainer.innerHTML = '';
        if (!data || Object.keys(data).length === 0) {
            uptimeHistoryContainer.innerHTML = '<p>没有选中任何网站或当前时间范围无数据。</p>';
            return;
        }
        let content = '';
        const { start_date, end_date } = currentParams;
        for (const siteName in data) {
            const siteData = data[siteName];
            if (!siteData.uptime_intervals || siteData.uptime_intervals.length === 0) continue;
            // 1. 生成所有小分段的 HTML
            const segmentsHtml = siteData.uptime_intervals.map(interval => {
                // 将数据附加到 data-* 属性，供悬浮窗使用
                return `<div class="uptime-bar-segment bar-${interval.status}" 
                             data-time-range="${interval.time_range}" 
                             data-status="${interval.status}"
                             data-details="${interval.details}"></div>`;
            }).join('');
            // 2. 组装每个网站的完整模块
            content += `
                <div class="site-uptime-wrapper">
                    <div class="site-uptime-header">
                        <div class="site-uptime-title">${siteName}</div>
                        <div class="site-uptime-stats">
                            <span>平均响应: <span class="stat-value">${siteData.overall_stats.avg_response_time.toFixed(2)}s</span></span>
                            <span><span class="stat-value">${siteData.overall_stats.availability.toFixed(2)}%</span> 在线率</span>
                        </div>
                    </div>
                    <div class="uptime-bar-container">${segmentsHtml}</div>
                    <div class="uptime-timeline-labels">
                        <span>${start_date}</span>
                        <span>${end_date}</span>
                    </div>
                </div>`;
        }
        uptimeHistoryContainer.innerHTML = content || '<p>当前时间范围无数据。</p>';
    }
    // 【修改】渲染对比图表的函数
    function renderComparisonCharts(data) {
        const uptimeCategories = [];
        const uptimeData = [];
        for (const siteName in data) {
            const siteData = data[siteName];
            if (siteData.uptime_intervals.length > 0) {
                uptimeCategories.push(siteName);
                // 直接使用后端计算好的总体可用率
                uptimeData.push(siteData.overall_stats.availability.toFixed(2));
            }
        }

        // 可用率图表 (逻辑和之前一样)
        if (uptimeCategories.length === 0) {
            uptimeChart.setOption({ title: { text: '当前时间范围无可用率数据', left: 'center', top: 'center' } }, true);
        } else {
            uptimeChart.setOption({
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
                xAxis: { type: 'category', data: uptimeCategories },
                yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
                series: [{
                    type: 'bar', barWidth: '40%', data: uptimeData,
                    label: { show: true, position: 'top', formatter: '{c}%', color: '#333' },
                    itemStyle: {
                        color: function (params) {
                            const value = parseFloat(params.value);
                            if (value >= 99.9) return '#67C23A';
                            if (value >= 99) return '#91cc75';
                            if (value >= 95) return '#E6A23C';
                            return '#F56C6C';
                        }
                    }
                }]
            }, true);
        }
        // 响应时间图表 (逻辑和之前一样)
        const responseTimeLegends = [];
        const responseTimeSeries = [];
        let allTimestamps = new Set();
        Object.keys(data).forEach(siteName => {
            if (data[siteName].response_times.timestamps.length > 0) {
                data[siteName].response_times.timestamps.forEach(t => allTimestamps.add(t));
            }
        });
        const sortedTimestamps = Array.from(allTimestamps).sort();
        Object.keys(data).forEach(siteName => {
             if (data[siteName].response_times.timestamps.length > 0) {
                responseTimeLegends.push(siteName);
                const siteData = data[siteName].response_times;
                const seriesData = sortedTimestamps.map(ts => {
                    const index = siteData.timestamps.indexOf(ts);
                    return index > -1 ? siteData.times[index] : null;
                });
                responseTimeSeries.push({ name: siteName, type: 'line', smooth: true, data: seriesData, connectNulls: true });
            }
        });
        if (responseTimeLegends.length === 0) {
             responseTimeChart.setOption({ title: { text: '当前时间范围无响应时间数据', left: 'center', top: 'center' } }, true);
        } else {
             responseTimeChart.setOption({
                title: { text: '' }, tooltip: { trigger: 'axis' }, legend: { data: responseTimeLegends, top: 10 },
                grid: { top: 60, left: 50, right: 50, bottom: 60 }, xAxis: { type: 'category', boundaryGap: false, data: sortedTimestamps },
                yAxis: { type: 'value', name: '响应时间 (秒)' }, dataZoom: [{ type: 'inside' }, { type: 'slider' }], series: responseTimeSeries
             }, true);
        }
    }

    async function updateDashboard() {
        const selectedSites = Array.from(document.querySelectorAll('#site-selector input:checked')).map(el => el.value);

        if (selectedSites.length === 0) {
            uptimeHistoryContainer.innerHTML = '<p>请至少选择一个网站。</p>';
            uptimeChart.setOption({ title: { text: '请选择网站', left: 'center', top: 'center' } }, true);
            responseTimeChart.setOption({ title: { text: '请选择网站', left: 'center', top: 'center' } }, true);
            return;
        }
        showLoading();
        const siteParams = selectedSites.map(s => `sites=${encodeURIComponent(s)}`).join('&');
        const timeParams = `start_time=${currentParams.start_iso}&end_time=${currentParams.end_iso}`;

        try {
            const response = await fetch(`/api/history?${siteParams}&${timeParams}`);
            if (!response.ok) throw new Error(`API 请求失败: ${response.status}`);
            const data = await response.json();
            // 现在这两个函数都会使用新的数据结构
            renderUptimeHistory(data);
            renderComparisonCharts(data);
        } catch (error) {
            uptimeHistoryContainer.innerHTML = `<p style="color:red;">加载数据失败: ${error.message}</p>`;
            console.error(error);
        } finally {
            hideLoading();
        }
    }
    // 悬浮窗事件监听函数
    function setupTooltipEvents() {
        // 使用事件委托，将监听器绑定在外层容器上，提高性能
        uptimeHistoryContainer.addEventListener('mouseover', function(e) {
            // 只在悬浮到 .uptime-bar-segment 元素上时触发
            const segment = e.target.closest('.uptime-bar-segment');
            if (segment) {
                const timeRange = segment.dataset.timeRange;
                const status = segment.dataset.status;
                const details = segment.dataset.details;

                // 更新内容并显示
                tooltip.innerHTML = `<strong>${timeRange}</strong><br>状态: ${status}<br>${details}`;
                tooltip.style.display = 'block';
            }
        });
        // 核心修改：使用 mousemove 事件来实时更新位置
        uptimeHistoryContainer.addEventListener('mousemove', function(e) {
            // 只有当悬浮窗是可见状态时，才更新位置
            if (tooltip.style.display === 'block') {
                // pageX 和 pageY 提供了鼠标相对于整个文档的坐标
                // +15 的偏移量是为了避免鼠标指针直接覆盖在悬浮窗上，导致闪烁
                tooltip.style.left = e.clientX + 15 + 'px';
                tooltip.style.top = e.clientY + 15 + 'px';
            }
        });
        // 当鼠标离开整个历史记录容器时，隐藏悬浮窗
        uptimeHistoryContainer.addEventListener('mouseleave', function(e) {
            tooltip.style.display = 'none';
        });
    }
    async function updateStatusWall(initialData = null) {
        const data = initialData || await (await fetch('/health')).json();
        const wall = document.getElementById('status-wall');
        const siteOrder = Array.from(document.querySelectorAll('#site-selector input')).map(el => el.value);

        wall.innerHTML = siteOrder.map(siteName => {
            if (!data[siteName]) return '';
            const site = data[siteName];
            const statusClass = `status-${site.status === '正常' ? 'ok' : (site.status === '访问过慢' ? 'slow' : 'down')}`;
            return `
                <div class="status-card ${statusClass}">
                    <h3>${siteName}</h3>
                    <p><strong>状态:</strong> ${site.status}</p>
                    <p><strong>响应时间:</strong> ${site.response_time_seconds !== null ? site.response_time_seconds + 's' : 'N/A'}</p>
                    <p><strong>上次检查:</strong> ${site.last_checked}</p>
                </div>`;
        }).join('');
    }
    function setAndTriggerUpdate(startDate, endDate) {
        currentParams = {
            start_iso: toLocalISOString(startDate),
            end_iso: toLocalISOString(endDate),
            start_date: startDate.toLocaleDateString(),
            end_date: endDate.toLocaleDateString()
        };
        updateDashboard();
    }
    // --- 事件监听器设置 ---
    function initializeControls() {
        // Flatpickr (日期选择器)
        const minDate = new Date();
        minDate.setDate(minDate.getDate() - dataRetentionDays);
        flatpickrInstance = flatpickr("#custom-time-range", {
            mode: "range",
            dateFormat: "Y-m-d H:i",
            enableTime: true,
            time_24hr: true,
            minDate: minDate,
            maxDate: "today",
            onChange: (selectedDates) => {
                if (selectedDates.length === 2) {
                    document.querySelector('#time-range-selector .active')?.classList.remove('active');
                    setAndTriggerUpdate(selectedDates[0], selectedDates[1]);
                }
            }
        });
        // 时间范围按钮
        document.getElementById('time-range-selector').addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON') return;
            const range = e.target.dataset.range;
            const end = new Date();
            let start = new Date();
            const [num, unit] = [parseInt(range.slice(0, -1)), range.slice(-1)];

            if (unit === 'h') start.setHours(start.getHours() - num);
            if (unit === 'd') start.setDate(start.getDate() - num);
            if (unit === 'm') start.setMonth(start.getMonth() - num);
            document.querySelector('#time-range-selector .active')?.classList.remove('active');
            e.target.classList.add('active');
            flatpickrInstance.clear();
            setAndTriggerUpdate(start, end);
        });
        // 网站选择器
        document.getElementById('site-selector').addEventListener('change', updateDashboard);
        document.getElementById('select-all').addEventListener('click', () => {
            document.querySelectorAll('#site-selector input').forEach(el => el.checked = true);
            updateDashboard();
        });
        document.getElementById('deselect-all').addEventListener('click', () => {
            document.querySelectorAll('#site-selector input').forEach(el => el.checked = false);
            updateDashboard();
        });
    }
    // --- 初始加载 ---

    initializeControls();
    // 【新增】调用此函数来激活悬浮窗
    setupTooltipEvents();
    // 首次加载时，触发默认激活的时间按钮
    document.querySelector('#time-range-selector button.active').click();
    // 使用传入的初始数据首次渲染状态墙
    updateStatusWall(initialStatuses);
    // 设置定时更新状态墙
    setInterval(() => updateStatusWall(), 15000);
});
