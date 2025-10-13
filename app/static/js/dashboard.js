// 使用 document.addEventListener 确保 DOM 完全加载后再执行脚本
document.addEventListener('DOMContentLoaded', () => {
    // --- 变量初始化 ---
    const uptimeChart = echarts.init(document.getElementById('uptime-chart'));
    const responseTimeChart = echarts.init(document.getElementById('response-time-chart'));
    const uptimeHistoryContainer = document.getElementById('uptime-history-charts');
    // 【关键修复】直接从 window 对象获取已经解析好的数据，不再需要 JSON.parse
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
        const { start_date, end_date } = currentParams;
        let content = '';
        for (const siteName in data) {
            const siteData = data[siteName];
            const total = siteData.availability.up_count + siteData.availability.down_count;
            const availability = total > 0 ? (siteData.availability.up_count / total * 100).toFixed(2) : 'N/A';
            const avgTime = siteData.avg_response_time ? siteData.avg_response_time.toFixed(2) + 's' : 'N/A';

            const barsHtml = siteData.uptime_bars.map(bar => {
                const barClass = `bar-${bar}`; // Simplified class mapping
                return `<div class="uptime-bar ${barClass}" title="${bar}"></div>`;
            }).join('');
            content += `
                <div class="uptime-history-item">
                    <div class="uptime-header">
                        <div class="uptime-title">${siteName}</div>
                        <div class="uptime-stats">
                            <span class="response-time">平均响应: ${avgTime}</span>
                            <span class="availability">${availability}% 在线率</span>
                        </div>
                    </div>
                    <div class="uptime-bars-container">${barsHtml}</div>
                    <div class="uptime-labels"><span>${start_date}</span><span>${end_date}</span></div>
                </div>`;
        }
        uptimeHistoryContainer.innerHTML = content;
    }
    function renderComparisonCharts(data) {
        const uptimeCategories = [];
        const uptimeData = [];
        const responseTimeLegends = [];
        const responseTimeSeries = [];
        let allTimestamps = new Set();
        for (const siteName in data) {
            const { availability, response_times } = data[siteName];
            const total = availability.up_count + availability.down_count;
            if (total > 0) {
                uptimeCategories.push(siteName);
                uptimeData.push((availability.up_count / total * 100).toFixed(2));
                response_times.timestamps.forEach(t => allTimestamps.add(t));
            }
        }
        const sortedTimestamps = Array.from(allTimestamps).sort();
        for (const siteName in data) {
            const total = data[siteName].availability.up_count + data[siteName].availability.down_count;
            if (total > 0) {
                responseTimeLegends.push(siteName);
                const { timestamps, times } = data[siteName].response_times;
                const seriesData = sortedTimestamps.map(ts => {
                    const index = timestamps.indexOf(ts);
                    return index > -1 ? times[index] : null;
                });
                responseTimeSeries.push({
                    name: siteName,
                    type: 'line',
                    smooth: true,
                    data: seriesData,
                    connectNulls: true
                });
            }
        }
        // 更新可用率图表
        if (uptimeCategories.length === 0) {
            uptimeChart.setOption({ title: { text: '当前时间范围无可用率数据', left: 'center', top: 'center' } }, true);
        } else {
            uptimeChart.setOption({
                title: { text: '' },
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}: {c}% 可用' },
                xAxis: { type: 'category', data: uptimeCategories },
                yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
                series: [{ data: uptimeData, type: 'bar', barWidth: '40%' }]
            }, true);
        }
        // 更新响应时间图表
        if (responseTimeLegends.length === 0) {
            responseTimeChart.setOption({ title: { text: '当前时间范围无响应时间数据', left: 'center', top: 'center' } }, true);
        } else {
            responseTimeChart.setOption({
                title: { text: '' },
                tooltip: { trigger: 'axis' },
                legend: { data: responseTimeLegends, top: 10 },
                grid: { top: 60, left: 50, right: 50, bottom: 60 },
                xAxis: { type: 'category', boundaryGap: false, data: sortedTimestamps },
                yAxis: { type: 'value', name: '响应时间 (秒)' },
                dataZoom: [{ type: 'inside' }, { type: 'slider' }],
                series: responseTimeSeries
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
            renderUptimeHistory(data);
            renderComparisonCharts(data);
        } catch (error) {
            uptimeHistoryContainer.innerHTML = `<p style="color:red;">加载数据失败: ${error.message}</p>`;
            console.error(error);
        } finally {
            hideLoading();
        }
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
    // 首次加载时，触发默认激活的时间按钮
    document.querySelector('#time-range-selector button.active').click();
    // 使用传入的初始数据首次渲染状态墙
    updateStatusWall(initialStatuses);
    // 设置定时更新状态墙
    setInterval(() => updateStatusWall(), 15000);
});
