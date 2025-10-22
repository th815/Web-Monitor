// web-monitor/app/static/js/dashboard.js

document.addEventListener('DOMContentLoaded', () => {

    // --- 图表实例与 DOM 引用 ---
    const timelineChartContainer = document.getElementById('timeline-chart');
    let timelineChart = echarts.init(timelineChartContainer);
    const uptimeChartContainer = document.getElementById('uptime-chart');
    const uptimeChart = echarts.init(uptimeChartContainer);
    const responseTimeChartContainer = document.getElementById('response-time-chart');
    const responseTimeChart = echarts.init(responseTimeChartContainer);
    const statusDistributionChartContainer = document.getElementById('status-distribution-chart');
    const statusDistributionChart = statusDistributionChartContainer ? echarts.init(statusDistributionChartContainer) : null;

    const summaryElements = {
        siteCount: document.getElementById('summary-site-count'),
        avgUptime: document.getElementById('summary-avg-uptime'),
        avgResponse: document.getElementById('summary-avg-response'),
        incidents: document.getElementById('summary-incident-count'),
        incidentHint: document.getElementById('summary-incident-hint')
    };

    const initialStatuses = window.INITIAL_STATUSES;
    const dataRetentionDays = window.DATA_RETENTION_DAYS;
    let currentParams = {};
    let rangePicker;

    const STATUS_COLORS = {
        0: '#f0f0f0',
        1: '#91cc75',
        2: '#fac858',
        3: '#ee6666'
    };


    const formatDuration = (ms) => {
        if (!ms || ms <= 0) {
            return '0秒';
        }
        let seconds = Math.round(ms / 1000);
        const days = Math.floor(seconds / 86400);
        seconds -= days * 86400;
        const hours = Math.floor(seconds / 3600);
        seconds -= hours * 3600;
        const minutes = Math.floor(seconds / 60);
        seconds -= minutes * 60;

        const parts = [];
        if (days) parts.push(`${days}天`);
        if (hours) parts.push(`${hours}小时`);
        if (minutes) parts.push(`${minutes}分钟`);
        if (seconds || parts.length === 0) parts.push(`${seconds}秒`);
        return parts.join('');
    };

    const setChartEmptyState = (chart, domElement, message) => {
        if (!chart || !domElement) {
            return;
        }
        chart.hideLoading();
        if (message) {
            chart.clear();
            domElement.classList.add('chart-empty');
            domElement.setAttribute('data-empty-message', message);
        } else {
            domElement.classList.remove('chart-empty');
            domElement.removeAttribute('data-empty-message');
        }
    };

    const determinePickerLocale = () => {
        const htmlLang = (document.documentElement.lang || '').toLowerCase();
        if (htmlLang.startsWith('zh') && flatpickr.l10ns.zh) {
            return 'zh';
        }
        return 'default';
    };

    const pickerLocale = determinePickerLocale();
    if (pickerLocale !== 'default' && flatpickr.l10ns[pickerLocale]) {
        flatpickr.localize(flatpickr.l10ns[pickerLocale]);
    }

    // --- ECharts 自定义渲染函数 ---
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
        if (!timelineChartContainer) {
            return;
        }
        if (!data || Object.keys(data).length === 0) {
            timelineChartContainer.style.height = '250px';
            setChartEmptyState(timelineChart, timelineChartContainer, '没有选中任何网站或当前时间范围无数据。');
            return;
        }

        setChartEmptyState(timelineChart, timelineChartContainer, null);

        const siteNames = Object.keys(data);
        const series = [];
        const chartHeight = Math.max(160, siteNames.length * 42 + 80);
        timelineChartContainer.style.height = `${chartHeight}px`;
        timelineChart.resize();

        siteNames.forEach((siteName, index) => {
            const siteData = data[siteName].timeline_data.map(item => [index, item[0], item[1], item[2], item[3]]);
            series.push({
                name: siteName,
                type: 'custom',
                renderItem,
                itemStyle: { opacity: 0.85 },
                encode: { x: [1, 2], y: 0 },
                data: siteData
            });
        });

        const option = {
            tooltip: {
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
                    const startTime = new Date(params.value[1]);
                    const endTime = new Date(params.value[2]);
                    const timeFormat = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
                    const timeRangeStr = `${startTime.toLocaleTimeString('zh-CN', timeFormat)} - ${endTime.toLocaleTimeString('zh-CN', timeFormat)}`;
                    return `<strong>${seriesName}</strong><br/>时间: ${timeRangeStr}<br/>${details}`;
                }
            },
            dataZoom: [
                {
                    type: 'slider',
                    filterMode: 'weakFilter',
                    showDataShadow: false,
                    bottom: 6,
                    height: 24,
                    borderColor: 'transparent',
                    backgroundColor: '#e2e2e2',
                    handleIcon: 'path://M10.7,11.9H9.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4h1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,22H6.7v-1.4h6.6V22z',
                    handleSize: 20,
                    handleStyle: { color: '#fff', shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.3)' },
                    zoomOnMouseWheel: false,
                    moveOnMouseWheel: false,
                    moveOnMouseMove: false
                }
            ],
            grid: { top: 25, left: 120, right: 30, bottom: 90 },
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
            series
        };
        timelineChart.setOption(option, true);
    }

    function renderComparisonCharts(data) {
        const siteKeys = Object.keys(data || {});
        if (siteKeys.length === 0) {
            setChartEmptyState(uptimeChart, uptimeChartContainer, '暂无可用率数据');
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '暂无响应时间数据');
            return;
        }

        const uptimeCategories = [];
        const uptimeData = [];
        const responseTimeLegends = [];
        const responseTimeSeries = [];
        let allTimestamps = new Set();

        siteKeys.forEach(siteName => {
            const siteData = data[siteName];
            if (siteData.response_times.timestamps.length > 0) {
                siteData.response_times.timestamps.forEach(t => allTimestamps.add(t));
            }
        });

        const sortedTimestamps = Array.from(allTimestamps).sort();

        siteKeys.forEach(siteName => {
            const siteData = data[siteName];
            if (siteData.overall_stats) {
                const availability = siteData.overall_stats.availability;
                if (Number.isFinite(availability)) {
                    uptimeCategories.push(siteName);
                    uptimeData.push(parseFloat(availability.toFixed(2)));
                }
            }

            const rtData = siteData.response_times;
            if (rtData.timestamps.length > 0) {
                responseTimeLegends.push(siteName);
                const seriesData = sortedTimestamps.map(ts => {
                    const index = rtData.timestamps.indexOf(ts);
                    return index > -1 ? rtData.times[index] : null;
                });
                responseTimeSeries.push({
                    name: siteName,
                    type: 'line',
                    smooth: true,
                    symbol: 'circle',
                    symbolSize: 6,
                    connectNulls: true,
                    data: seriesData
                });
            }
        });

        if (uptimeCategories.length === 0) {
            setChartEmptyState(uptimeChart, uptimeChartContainer, '暂无可用率数据');
        } else {
            setChartEmptyState(uptimeChart, uptimeChartContainer, null);
            uptimeChart.setOption({
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
                grid: { top: 40, left: 60, right: 30, bottom: 70 },
                xAxis: { type: 'category', data: uptimeCategories, axisLabel: { interval: 0 } },
                yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
                series: [{
                    type: 'bar',
                    barWidth: '45%',
                    data: uptimeData,
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

        if (responseTimeSeries.length === 0 || sortedTimestamps.length === 0) {
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '暂无响应时间数据');
        } else {
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, null);
            const rotateLabels = sortedTimestamps.length > 10 ? -35 : 0;
            responseTimeChart.setOption({
                tooltip: { trigger: 'axis' },
                legend: { data: responseTimeLegends, top: 10, type: 'scroll' },
                grid: { top: 70, left: 60, right: 50, bottom: 100 },
                xAxis: {
                    type: 'category',
                    boundaryGap: false,
                    data: sortedTimestamps,
                    axisLabel: { rotate: rotateLabels, hideOverlap: true }
                },
                yAxis: { type: 'value', name: '响应时间 (秒)', nameGap: 30 },
                dataZoom: [
                    {
                        type: 'slider',
                        bottom: 16,
                        height: 24,
                        zoomOnMouseWheel: false,
                        moveOnMouseWheel: false,
                        moveOnMouseMove: false
                    },
                    { type: 'inside' }
                ],
                series: responseTimeSeries
            }, true);
        }
    }

    function renderStatusDistribution(data) {
        if (!statusDistributionChart || !statusDistributionChartContainer) {
            return;
        }

        const siteKeys = Object.keys(data || {});
        if (siteKeys.length === 0) {
            setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, '暂无状态分布数据');
            return;
        }

        const totals = { up: 0, slow: 0, down: 0, nodata: 0 };
        siteKeys.forEach(siteName => {
            const segments = data[siteName].timeline_data || [];
            segments.forEach(segment => {
                const start = segment[0] || 0;
                const end = segment[1] || 0;
                const status = segment[2];
                const duration = Math.max(0, end - start);
                if (!duration) return;
                if (status === 1) totals.up += duration;
                else if (status === 2) totals.slow += duration;
                else if (status === 3) totals.down += duration;
                else totals.nodata += duration;
            });
        });

        const totalDuration = Object.values(totals).reduce((acc, value) => acc + value, 0);
        if (totalDuration <= 0) {
            setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, '暂无状态分布数据');
            return;
        }

        setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, null);

        const pieData = [];
        if (totals.up > 0) pieData.push({ name: '正常', value: totals.up, itemStyle: { color: '#67C23A' } });
        if (totals.slow > 0) pieData.push({ name: '访问过慢', value: totals.slow, itemStyle: { color: '#E6A23C' } });
        if (totals.down > 0) pieData.push({ name: '无法访问', value: totals.down, itemStyle: { color: '#F56C6C' } });
        if (totals.nodata > 0) pieData.push({ name: '无数据', value: totals.nodata, itemStyle: { color: '#C0CCDA' } });

        statusDistributionChart.setOption({
            tooltip: {
                trigger: 'item',
                formatter: params => {
                    const percent = Number.isFinite(params.percent) ? params.percent.toFixed(1) : '0.0';
                    return `${params.marker}${params.name}<br/>占比：${percent}%<br/>时长：${formatDuration(params.value)}`;
                }
            },
            legend: {
                orient: 'vertical',
                right: 10,
                top: 'middle'
            },
            series: [{
                name: '状态时长分布',
                type: 'pie',
                radius: ['45%', '70%'],
                center: ['40%', '50%'],
                data: pieData,
                label: {
                    formatter: info => `${info.name}\n${Number(info.percent).toFixed(1)}%`
                },
                emphasis: {
                    scale: true,
                    scaleSize: 6
                }
            }]
        }, true);
    }

    function updateSummaryCards(data, selectedSites) {
        if (!summaryElements.siteCount) {
            return;
        }
        const selectedCount = selectedSites.length;
        summaryElements.siteCount.textContent = String(selectedCount);

        if (!data || Object.keys(data).length === 0) {
            summaryElements.avgUptime.textContent = '--';
            summaryElements.avgResponse.textContent = '--';
            summaryElements.incidents.textContent = selectedCount > 0 ? '0' : '--';
            if (summaryElements.incidentHint) {
                summaryElements.incidentHint.textContent = '宕机 + 性能告警';
            }
            return;
        }

        let availabilitySum = 0;
        let availabilityCount = 0;
        let responseSum = 0;
        let responseCount = 0;
        let downSegments = 0;
        let slowSegments = 0;

        Object.values(data).forEach(siteData => {
            const availability = siteData.overall_stats?.availability;
            if (Number.isFinite(availability)) {
                availabilitySum += availability;
                availabilityCount += 1;
            }
            const avgResponse = siteData.overall_stats?.avg_response_time;
            if (Number.isFinite(avgResponse) && avgResponse > 0) {
                responseSum += avgResponse;
                responseCount += 1;
            }
            (siteData.timeline_data || []).forEach(segment => {
                if (segment[2] === 3) downSegments += 1;
                if (segment[2] === 2) slowSegments += 1;
            });
        });

        const avgAvailability = availabilityCount ? (availabilitySum / availabilityCount) : null;
        const avgResponse = responseCount ? (responseSum / responseCount) : null;
        const totalIncidents = downSegments + slowSegments;

        summaryElements.avgUptime.textContent = avgAvailability !== null ? `${avgAvailability.toFixed(2)}%` : '--';
        summaryElements.avgResponse.textContent = avgResponse !== null ? avgResponse.toFixed(2) : '0.00';
        summaryElements.incidents.textContent = String(totalIncidents);

        if (summaryElements.incidentHint) {
            summaryElements.incidentHint.textContent = totalIncidents > 0 ? `宕机：${downSegments} · 慢：${slowSegments}` : '宕机 + 性能告警';
        }
    }

    async function updateDashboard() {
        const selectedSites = Array.from(document.querySelectorAll('#site-selector input:checked')).map(el => el.value);
        updateSummaryCards(null, selectedSites);

        if (selectedSites.length === 0) {
            setChartEmptyState(timelineChart, timelineChartContainer, '请选择至少一个网站以查看历史数据');
            setChartEmptyState(uptimeChart, uptimeChartContainer, '请选择至少一个网站以查看可用率');
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '请选择至少一个网站以查看响应时间');
            if (statusDistributionChart && statusDistributionChartContainer) {
                setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, '请选择至少一个网站以查看状态分布');
            }
            return;
        }

        setChartEmptyState(timelineChart, timelineChartContainer, null);
        timelineChart.showLoading();
        if (statusDistributionChart && statusDistributionChartContainer) {
            setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, null);
            statusDistributionChart.showLoading('');
        }

        const siteParams = selectedSites.map(s => `sites=${encodeURIComponent(s)}`).join('&');
        const timeParams = `start_time=${currentParams.start_iso}&end_time=${currentParams.end_iso}`;

        try {
            const response = await fetch(`/api/history?${siteParams}&${timeParams}`);
            if (!response.ok) {
                throw new Error(`API 请求失败: ${response.status}`);
            }
            const data = await response.json();
            updateSummaryCards(data, selectedSites);
            renderUptimeHistory(data);
            renderComparisonCharts(data);
            renderStatusDistribution(data);
        } catch (error) {
            console.error(error);
            setChartEmptyState(timelineChart, timelineChartContainer, '数据加载失败，请稍后重试');
            setChartEmptyState(uptimeChart, uptimeChartContainer, '数据加载失败');
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '数据加载失败');
            if (statusDistributionChart) {
                setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, '数据加载失败');
            }
        } finally {
            timelineChart.hideLoading();
            if (statusDistributionChart) {
                statusDistributionChart.hideLoading();
            }
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
            const statusSpecificLine =
                site.status === '无法访问' && site.down_since
                    ? `<p><strong>故障开始:</strong> ${site.down_since}</p>`
                    : site.status === '访问过慢' && site.slow_since
                        ? `<p><strong>减速开始:</strong> ${site.slow_since}</p>`
                        : '';
            const totalChecksLine = site.total_checks ? `<p><strong>累计检查:</strong> ${site.total_checks}</p>` : '';
            const responseTimeText = typeof site.response_time_seconds === 'number'
                ? `${site.response_time_seconds.toFixed(2)}秒`
                : 'N/A';
            return `
                <div class="status-card ${statusClass}">
                    <h3>${siteName}</h3>
                    <p><strong>状态:</strong> ${site.status}</p>
                    ${statusSpecificLine}
                    <p><strong>响应时间:</strong> ${responseTimeText}</p>
                    ${totalChecksLine}
                    <p><strong>上次检查:</strong> ${site.last_checked}</p>
                </div>`;
        }).join('');
    }

    const toLocalISOString = dt =>
        `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}T${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;

    function setAndTriggerUpdate(startDate, endDate) {
        currentParams = {
            start_iso: toLocalISOString(startDate),
            end_iso: toLocalISOString(endDate)
        };
        updateDashboard();
    }

    function initializeControls() {
        const earliestDate = new Date();
        earliestDate.setDate(earliestDate.getDate() - dataRetentionDays);

        const customRangeStartInput = document.getElementById('custom-range-start');
        const customRangeEndInput = document.getElementById('custom-range-end');
        const applyCustomRangeBtn = document.getElementById('apply-custom-range');
        const clearCustomRangeBtn = document.getElementById('clear-custom-range');

        const pickerOptions = {
            enableTime: true,
            time_24hr: true,
            dateFormat: 'Y-m-d H:i',
            minDate: earliestDate,
            maxDate: 'today',
            minuteIncrement: 5,
            plugins: [new rangePlugin({ input: '#custom-range-end' })],
            onChange: (selectedDates) => {
                applyCustomRangeBtn.disabled = selectedDates.length !== 2;
            }
        };

        if (pickerLocale !== 'default') {
            pickerOptions.locale = pickerLocale;
        }

        rangePicker = flatpickr(customRangeStartInput, pickerOptions);

        applyCustomRangeBtn.addEventListener('click', () => {
            const selectedDates = rangePicker.selectedDates;
            if (selectedDates.length === 2) {
                let [start, end] = selectedDates;
                if (start > end) {
                    [start, end] = [end, start];
                }
                if (start < earliestDate) {
                    start = new Date(earliestDate.getTime());
                }
                document.querySelector('#time-range-selector .active')?.classList.remove('active');
                setAndTriggerUpdate(start, end);
            }
        });

        clearCustomRangeBtn.addEventListener('click', () => {
            rangePicker.clear();
            customRangeEndInput.value = '';
            applyCustomRangeBtn.disabled = true;
        });

        document.getElementById('time-range-selector').addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON') return;
            const range = e.target.dataset.range;
            if (!range) return;
            const end = new Date();
            let start = new Date(end.getTime());
            const match = range.match(/^(\d+)([mhdwM])$/);
            if (!match) return;
            const value = parseInt(match[1], 10);
            const unit = match[2];

            switch (unit) {
                case 'm':
                    start.setMinutes(start.getMinutes() - value);
                    break;
                case 'h':
                    start.setHours(start.getHours() - value);
                    break;
                case 'd':
                    start.setDate(start.getDate() - value);
                    break;
                case 'w':
                    start.setDate(start.getDate() - value * 7);
                    break;
                case 'M':
                    start.setMonth(start.getMonth() - value);
                    break;
                default:
                    break;
            }

            if (start < earliestDate) {
                start = new Date(earliestDate.getTime());
            }

            document.querySelector('#time-range-selector .active')?.classList.remove('active');
            e.target.classList.add('active');
            rangePicker.clear();
            customRangeEndInput.value = '';
            applyCustomRangeBtn.disabled = true;
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

    window.addEventListener('resize', () => {
        if (timelineChart && !timelineChart.isDisposed()) timelineChart.resize();
        if (uptimeChart && !uptimeChart.isDisposed()) uptimeChart.resize();
        if (responseTimeChart && !responseTimeChart.isDisposed()) responseTimeChart.resize();
        if (statusDistributionChart && !statusDistributionChart.isDisposed()) statusDistributionChart.resize();
    });
});
