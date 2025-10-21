// web-monitor/app/static/js/dashboard.js (最终自定义系列版 - 已修复)

document.addEventListener('DOMContentLoaded', () => {

    // --- 变量初始化 ---
    const timelineChartContainer = document.getElementById('timeline-chart');
    let timelineChart = echarts.init(timelineChartContainer);
    const uptimeChart = echarts.init(document.getElementById('uptime-chart'));
    const responseTimeChart = echarts.init(document.getElementById('response-time-chart'));


    const initialStatuses = window.INITIAL_STATUSES;
    const dataRetentionDays = window.DATA_RETENTION_DAYS;
    let currentParams = {};
    let flatpickrInstance;

    const STATUS_COLORS = {
        0: '#f0f0f0', 1: '#91cc75', 2: '#fac858', 3: '#ee6666'
    };

    // --- 【修复】重新添加回 toLocalISOString 函数 ---
    const toLocalISOString = dt =>
        `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}T${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;


    // --- 核心功能函数 ---

    function renderItem(params, api) {
        const categoryIndex = api.value(0);
        const start = api.coord([api.value(1), categoryIndex]);
        const end = api.coord([api.value(2), categoryIndex]);
        const height = api.size([0, 1])[1] * 0.8;

        const rectShape = echarts.graphic.clipRectByRect(
            { x: start[0], y: start[1] - height / 2, width: end[0] - start[0], height: height },
            { x: params.coordSys.x, y: params.coordSys.y, width: params.coordSys.width, height: params.coordSys.height }
        );

        return rectShape && { type: 'rect', shape: rectShape, style: { fill: STATUS_COLORS[api.value(3)] } };
    }

    function renderUptimeHistory(data) {
        if (!data || Object.keys(data).length === 0) {
            timelineChart.clear();
            timelineChartContainer.innerHTML = '<p>没有选中任何网站或当前时间范围无数据。</p>';
            return;
        }

        const siteNames = Object.keys(data);
        const series = [];
        const chartHeight = Math.max(150, siteNames.length * 40 + 80); // 动态高度，增加最小值
        timelineChartContainer.style.height = `${chartHeight}px`;
        if (timelineChart.isDisposed()) {
            timelineChart = echarts.init(timelineChartContainer);
        }
        timelineChart.resize();

        siteNames.forEach((siteName, index) => {
            const siteData = data[siteName].timeline_data.map(item => [index, item[0], item[1], item[2], item[3]]);
            series.push({
                name: siteName, type: 'custom', renderItem: renderItem, itemStyle: { opacity: 0.8 },
                encode: { x: [1, 2], y: 0 }, data: siteData
            });
        });

        const option = {
            tooltip: {
                // 【核心修复】将 trigger 从 'axis' 改为 'item'
                trigger: 'item',
                axisPointer: {
                    type: 'shadow'
                },
                formatter: function (params) {
                    if (!params || params.seriesType !== 'custom') {
                        return '';
                    }

                    const seriesName = params.seriesName;
                    const details = params.value[4];

                    // 【新增】从数据中获取起止时间，并格式化
                    const startTime = new Date(params.value[1]);
                    const endTime = new Date(params.value[2]);
                    const timeFormat = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
                    const timeRangeStr = `${startTime.toLocaleTimeString('zh-CN', timeFormat)} - ${endTime.toLocaleTimeString('zh-CN', timeFormat)}`;
                    return `<strong>${seriesName}</strong><br/>
                            时间: ${timeRangeStr}<br/>
                            ${details}`;
                }
            },

dataZoom: [
    {
        type: 'slider', filterMode: 'weakFilter', showDataShadow: false,
        bottom: 10, height: 24, borderColor: 'transparent', backgroundColor: '#e2e2e2',
        handleIcon: 'path://M10.7,11.9H9.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4h1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,22H6.7v-1.4h6.6V22z',
        handleSize: 20, handleStyle: { color: '#fff', shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.3)' }
    },
    { type: 'inside', filterMode: 'weakFilter' }
],
grid: { top: 10, left: 100, right: 20, bottom: 60 },
            xAxis: {
                type: 'time',
                min: new Date(currentParams.start_iso),
                max: new Date(currentParams.end_iso),
                axisLabel: {
                    formatter: function (value) {
                        return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
                    }
                }
            },
            yAxis: { type: 'category', data: siteNames, axisLabel: { interval: 0 } },
            series: series
        };
        timelineChart.setOption(option, true);
    }
    // --- 【新增】恢复 renderComparisonCharts 函数 ---
    function renderComparisonCharts(data) {
        const uptimeCategories = [];
        const uptimeData = [];
        const responseTimeLegends = [];
        const responseTimeSeries = [];
        let allTimestamps = new Set();
        Object.keys(data).forEach(siteName => {
            if (data[siteName].response_times.timestamps.length > 0) {
                data[siteName].response_times.timestamps.forEach(t => allTimestamps.add(t));
            }
        });
        const sortedTimestamps = Array.from(allTimestamps).sort();
        for (const siteName in data) {
            const siteData = data[siteName];
            // 可用率图表数据
            if (siteData.overall_stats) {
                uptimeCategories.push(siteName);
                uptimeData.push(siteData.overall_stats.availability.toFixed(2));
            }
            // 响应时间图表数据
            if (siteData.response_times.timestamps.length > 0) {
                responseTimeLegends.push(siteName);
                const rtData = siteData.response_times;
                const seriesData = sortedTimestamps.map(ts => {
                    const index = rtData.timestamps.indexOf(ts);
                    return index > -1 ? rtData.times[index] : null;
                });
                responseTimeSeries.push({ name: siteName, type: 'line', smooth: true, data: seriesData, connectNulls: true });
            }
        }

        // 渲染可用率图表 (代码和之前一样)
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
        // 渲染响应时间图表 (代码和之前一样)
        responseTimeChart.setOption({
            tooltip: { trigger: 'axis' }, legend: { data: responseTimeLegends, top: 10 },
            grid: { top: 60, left: 50, right: 50, bottom: 60 },
            xAxis: { type: 'category', boundaryGap: false, data: sortedTimestamps },
            yAxis: { type: 'value', name: '响应时间 (秒)' },
            dataZoom: [{ type: 'inside' }, { type: 'slider' }],
            series: responseTimeSeries
        }, true);
    }
    async function updateDashboard() {
        const selectedSites = Array.from(document.querySelectorAll('#site-selector input:checked')).map(el => el.value);
        if (selectedSites.length === 0) {
            if (timelineChart && !timelineChart.isDisposed()) timelineChart.clear();
            if (uptimeChart && !uptimeChart.isDisposed()) uptimeChart.clear();
            if (responseTimeChart && !responseTimeChart.isDisposed()) responseTimeChart.clear();
            return;
        }

        // 简化 loading
        if (timelineChart && !timelineChart.isDisposed()) timelineChart.showLoading();

        const siteParams = selectedSites.map(s => `sites=${encodeURIComponent(s)}`).join('&');
        const timeParams = `start_time=${currentParams.start_iso}&end_time=${currentParams.end_iso}`;

        try {
            const response = await fetch(`/api/history?${siteParams}&${timeParams}`);
            if (!response.ok) throw new Error(`API 请求失败: ${response.status}`);
            const data = await response.json();

            // 【修改】同时调用两个渲染函数
            renderUptimeHistory(data);
            renderComparisonCharts(data);

        } catch (error) {
            console.error(error);
        } finally {
            if (timelineChart && !timelineChart.isDisposed()) timelineChart.hideLoading();
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
            end_iso: toLocalISOString(endDate)
        };
        updateDashboard();
    }

    function initializeControls() {
        const minDate = new Date();
        minDate.setDate(minDate.getDate() - dataRetentionDays);
        flatpickrInstance = flatpickr("#custom-time-range", {
            mode: "range", dateFormat: "Y-m-d H:i", enableTime: true, time_24hr: true,
            minDate: minDate, maxDate: "today",
            onChange: (selectedDates) => {
                if (selectedDates.length === 2) {
                    document.querySelector('#time-range-selector .active')?.classList.remove('active');
                    setAndTriggerUpdate(selectedDates[0], selectedDates[1]);
                }
            }
        });

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
    document.querySelector('#time-range-selector button.active').click();
    updateStatusWall(initialStatuses);
    setInterval(() => updateStatusWall(), 15000);
});
