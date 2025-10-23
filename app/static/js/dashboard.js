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
    const alertHistoryTable = document.getElementById('alert-history-table');
    const alertHistoryBody = document.getElementById('alert-history-body');
    const alertHistoryEmptyState = document.getElementById('alert-history-empty');
    const alertHistoryFootnote = document.getElementById('alert-history-footnote');
    const defaultAlertHistoryMessage = alertHistoryEmptyState
        ? (alertHistoryEmptyState.dataset.defaultText || alertHistoryEmptyState.textContent || '选定范围内暂无告警')
        : '选定范围内暂无告警';
    const ALERT_HISTORY_LIMIT = 30;

    const summaryElements = {
        siteCount: document.getElementById('summary-site-count'),
        avgUptime: document.getElementById('summary-avg-uptime'),
        avgResponse: document.getElementById('summary-avg-response'),
        incidents: document.getElementById('summary-incident-count'),
        incidentHint: document.getElementById('summary-incident-hint')
    };

    let latestHistoryData = null;
    const alertFilters = {
        status: 'unresolved',
        type: 'all'
    };
    const alertStatusFilter = document.getElementById('alert-status-filter');
    const alertTypeFilter = document.getElementById('alert-type-filter');

    const initialStatuses = window.INITIAL_STATUSES;
    const dataRetentionDays = 30; // 固定为30天
    let currentParams = {};
    let rangePicker;

    const STATUS_COLORS = {
        0: '#f0f0f0',
        1: '#91cc75',
        2: '#fac858',
        3: '#ee6666'
    };

    const calculateNineCount = (availability) => {
        if (!Number.isFinite(availability)) {
            return null;
        }
        if (availability >= 100) {
            return Infinity;
        }
        const downtimeRatio = 1 - availability / 100;
        if (downtimeRatio <= 0) {
            return Infinity;
        }
        const nineCount = Math.floor(-Math.log10(downtimeRatio));
        return Math.max(0, nineCount);
    };

    const describeAvailability = (availability) => {
        if (!Number.isFinite(availability)) {
            return {
                valueText: '--',
                combined: '--',
                ninesLabel: '',
                nineCount: null,
            };
        }
        const valueText = `${availability.toFixed(2)}%`;
        const nineCount = calculateNineCount(availability);
        let ninesLabel = '';
        if (nineCount === null) {
            ninesLabel = '';
        } else if (!Number.isFinite(nineCount)) {
            ninesLabel = '∞个9';
        } else if (nineCount <= 0) {
            ninesLabel = '不足1个9';
        } else {
            ninesLabel = `${nineCount}个9`;
        }
        const combined = ninesLabel ? `${valueText} · ${ninesLabel}` : valueText;
        return {
            valueText,
            combined,
            ninesLabel,
            nineCount,
        };
    };

    const parseDate = (value) => {
        if (!value) {
            return null;
        }
        const direct = new Date(value);
        if (!Number.isNaN(direct.getTime())) {
            return direct;
        }
        const fallback = new Date(String(value).replace(' ', 'T'));
        if (!Number.isNaN(fallback.getTime())) {
            return fallback;
        }
        return null;
    };

    const getTimeRangeSpanMs = () => {
        const start = parseDate(currentParams.start_iso);
        const end = parseDate(currentParams.end_iso);
        if (!start || !end) {
            return null;
        }
        const diff = end.getTime() - start.getTime();
        return Number.isFinite(diff) ? Math.abs(diff) : null;
    };

    const formatChartAxisTime = (value) => {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return '';
        }
        const span = getTimeRangeSpanMs();
        const ONE_DAY = 24 * 60 * 60 * 1000;
        const ONE_WEEK = 7 * ONE_DAY;
        if (!span || span <= ONE_DAY) {
            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
        }
        if (span <= ONE_WEEK) {
            return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
        }
        return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
    };

    const formatChartTooltipTime = (value) => {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return '--';
        }
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    };

    const buildAlertEmptyMessage = () => {
        const statusLabelMap = {
            unresolved: '未恢复',
            resolved: '已恢复',
            all: ''
        };
        const typeLabelMap = {
            down: '宕机',
            slow: '访问过慢',
            all: ''
        };
        const parts = [];
        const statusLabel = statusLabelMap[alertFilters.status];
        if (statusLabel) {
            parts.push(statusLabel);
        }
        const typeLabel = typeLabelMap[alertFilters.type];
        if (typeLabel) {
            parts.push(typeLabel);
        }
        if (parts.length === 0) {
            return '当前筛选条件下暂无告警';
        }
        return `当前筛选条件下暂无${parts.join(' · ')}告警`;
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

    const formatDateTime = (timestamp) => {
        if (timestamp === null || timestamp === undefined) {
            return '--';
        }
        const date = new Date(timestamp);
        if (Number.isNaN(date.getTime())) {
            return '--';
        }
        return date.toLocaleString('zh-CN', { hour12: false });
    };

    const escapeHtml = (value) => {
        if (value === null || value === undefined) {
            return '';
        }
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
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

        const startBoundary = parseDate(currentParams.start_iso);
        const endBoundary = parseDate(currentParams.end_iso);

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
                    const startLabel = formatChartTooltipTime(params.value[1]);
                    const endLabel = formatChartTooltipTime(params.value[2]);
                    return `<strong>${seriesName}</strong><br/>时间: ${startLabel} - ${endLabel}<br/>${details}`;
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
                    zoomLock: false,
                    moveOnMouseWheel: false,
                    zoomOnMouseWheel: false
                }
            ],
            grid: { top: 25, left: 120, right: 30, bottom: 90 },
            xAxis: {
                type: 'time',
                min: startBoundary,
                max: endBoundary,
                axisLabel: {
                    formatter: value => formatChartAxisTime(value)
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
        const uptimeSeriesData = [];
        const responseTimeLegends = [];
        const responseTimeSeries = [];
        const timestampSet = new Set();
        const timestampLabelMap = new Map();
        const siteResponseMaps = new Map();

        siteKeys.forEach(siteName => {
            const siteData = data[siteName] || {};

            if (siteData.overall_stats) {
                const availability = siteData.overall_stats.availability;
                if (Number.isFinite(availability)) {
                    const availabilityInfo = describeAvailability(availability);
                    uptimeCategories.push(siteName);
                    uptimeSeriesData.push({
                        value: Number(availability.toFixed(4)),
                        rawValue: availability,
                        combinedLabel: availabilityInfo.combined,
                        ninesLabel: availabilityInfo.ninesLabel,
                    });
                }
            }

            const rtData = siteData.response_times || {};
            const timestampsMs = Array.isArray(rtData.timestamps_ms) ? rtData.timestamps_ms : [];
            const timestampLabels = Array.isArray(rtData.timestamps) ? rtData.timestamps : [];
            const responseTimes = Array.isArray(rtData.times) ? rtData.times : [];
            const siteTimestampMap = new Map();

            if (timestampsMs.length > 0) {
                timestampsMs.forEach((ts, idx) => {
                    if (!Number.isFinite(ts)) {
                        return;
                    }
                    timestampSet.add(ts);
                    const label = timestampLabels[idx] || formatChartTooltipTime(ts);
                    if (label && !timestampLabelMap.has(ts)) {
                        timestampLabelMap.set(ts, label);
                    }
                    const value = idx < responseTimes.length ? responseTimes[idx] : null;
                    siteTimestampMap.set(ts, value === null || value === undefined ? null : Number(value));
                });
            }

            if (siteTimestampMap.size === 0 && timestampLabels.length > 0) {
                timestampLabels.forEach((label, idx) => {
                    if (!label) {
                        return;
                    }
                    const parsed = Date.parse(label.replace(' ', 'T'));
                    if (Number.isNaN(parsed)) {
                        return;
                    }
                    timestampSet.add(parsed);
                    if (!timestampLabelMap.has(parsed)) {
                        timestampLabelMap.set(parsed, label);
                    }
                    const value = idx < responseTimes.length ? responseTimes[idx] : null;
                    siteTimestampMap.set(parsed, value === null || value === undefined ? null : Number(value));
                });
            }

            siteResponseMaps.set(siteName, siteTimestampMap);
        });

        const sortedTimestamps = Array.from(timestampSet).sort((a, b) => a - b);

        siteKeys.forEach(siteName => {
            const siteTimestampMap = siteResponseMaps.get(siteName);
            if (siteTimestampMap && siteTimestampMap.size > 0) {
                responseTimeLegends.push(siteName);
                const seriesData = sortedTimestamps.map(ts => {
                    const value = siteTimestampMap.has(ts) ? siteTimestampMap.get(ts) : null;
                    return [ts, value];
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
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'shadow' },
                    formatter: params => {
                        if (!params || !params.length) {
                            return '';
                        }
                        const item = params[0];
                        const dataItem = item.data || {};
                        const combined = dataItem.combinedLabel || `${Number(item.value).toFixed(2)}%`;
                        return `${item.marker}${item.name}<br/>可用率：${combined}`;
                    }
                },
                grid: { top: 40, left: 60, right: 30, bottom: 70 },
                xAxis: { type: 'category', data: uptimeCategories, axisLabel: { interval: 0 } },
                yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
                series: [{
                    type: 'bar',
                    barWidth: '45%',
                    data: uptimeSeriesData,
                    label: {
                        show: true,
                        position: 'top',
                        formatter: params => {
                            const dataItem = params.data || {};
                            if (dataItem.combinedLabel) {
                                return dataItem.combinedLabel;
                            }
                            return `${Number(params.value).toFixed(2)}%`;
                        },
                        color: '#333'
                    },
                    itemStyle: {
                        color: function (params) {
                            const dataItem = params.data || {};
                            const value = Number.isFinite(dataItem.rawValue) ? dataItem.rawValue : Number(params.value);
                            if (value >= 99.99) return '#2ecc71';
                            if (value >= 99.9) return '#67C23A';
                            if (value >= 99) return '#91cc75';
                            if (value >= 95) return '#E6A23C';
                            return '#F56C6C';
                        }
                    }
                }]
            }, true);
        }

        const startBoundary = parseDate(currentParams.start_iso);
        const endBoundary = parseDate(currentParams.end_iso);

        if (responseTimeSeries.length === 0 || sortedTimestamps.length === 0) {
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '暂无响应时间数据');
        } else {
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, null);

            responseTimeChart.setOption({
                tooltip: {
                    trigger: 'axis',
                    formatter: params => {
                        if (!params || !params.length) {
                            return '';
                        }
                        const first = params[0];
                        const value = Array.isArray(first.value) ? first.value[0] : first.axisValue;
                        const numericValue = Number(value);
                        const label = timestampLabelMap.get(numericValue) || formatChartTooltipTime(numericValue);
                        const lines = [`<strong>${label}</strong>`];
                        params.forEach(item => {
                            const val = Array.isArray(item.value) ? item.value[1] : item.data;
                            const valueText = Number.isFinite(val) ? `${Number(val).toFixed(2)} 秒` : '--';
                            lines.push(`${item.marker}${item.seriesName}：${valueText}`);
                        });
                        return lines.join('<br/>');
                    }
                },
                legend: { data: responseTimeLegends, top: 10, type: 'scroll' },
                grid: { top: 70, left: 60, right: 50, bottom: 120 },
                xAxis: {
                    type: 'time',
                    boundaryGap: false,
                    min: startBoundary,
                    max: endBoundary,
                    axisLabel: {
                        formatter: value => formatChartAxisTime(value)
                    }
                },
                yAxis: { type: 'value', name: '响应时间 (秒)', nameGap: 30 },
                dataZoom: [
                    {
                        type: 'slider',
                        bottom: 20,
                        height: 20,
                        start: 0,
                        end: 100,
                        zoomLock: false,
                        moveOnMouseWheel: false,
                        zoomOnMouseWheel: false,
                        brushSelect: false
                    },
                    {
                        type: 'inside',
                        disabled: true
                    }
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
    const allSiteTotals = [];

    siteKeys.forEach(siteName => {
        const siteTotals = { up: 0, slow: 0, down: 0, nodata: 0 };
        const segments = data[siteName].timeline_data || [];

        segments.forEach(segment => {
            const start = segment[0] || 0;
            const end = segment[1] || 0;
            const status = segment[2];
            const duration = Math.max(0, end - start);
            if (!duration) return;

            if (status === 1) siteTotals.up += duration;
            else if (status === 2) siteTotals.slow += duration;
            else if (status === 3) siteTotals.down += duration;
            else siteTotals.nodata += duration;
        });

        allSiteTotals.push(siteTotals);
    });
    // 计算平均时长
    const avgTotals = { up: 0, slow: 0, down: 0, nodata: 0 };
    allSiteTotals.forEach(totals => {
        avgTotals.up += totals.up;
        avgTotals.slow += totals.slow;
        avgTotals.down += totals.down;
        avgTotals.nodata += totals.nodata;
    });

    // 取平均值
    const siteCount = allSiteTotals.length;
    if (siteCount > 0) {
        avgTotals.up /= siteCount;
        avgTotals.slow /= siteCount;
        avgTotals.down /= siteCount;
        avgTotals.nodata /= siteCount;
    }
    const totalDuration = Object.values(avgTotals).reduce((acc, value) => acc + value, 0);
    if (totalDuration <= 0) {
        setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, '暂无状态分布数据');
        return;
    }
    setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, null);
    const pieData = [];
    if (avgTotals.up > 0) pieData.push({ name: '正常', value: avgTotals.up, itemStyle: { color: '#67C23A' } });
    if (avgTotals.slow > 0) pieData.push({ name: '访问过慢', value: avgTotals.slow, itemStyle: { color: '#E6A23C' } });
    if (avgTotals.down > 0) pieData.push({ name: '无法访问', value: avgTotals.down, itemStyle: { color: '#F56C6C' } });
    if (avgTotals.nodata > 0) pieData.push({ name: '无数据', value: avgTotals.nodata, itemStyle: { color: '#C0CCDA' } });
    statusDistributionChart.setOption({
        title: {
            text: siteCount > 1 ? `状态时长分布（${siteCount}个站点平均）` : '状态时长分布',
            left: 'center',
            top: 10,
            textStyle: {
                fontSize: 16,
                fontWeight: 'normal'
            }
        },
        tooltip: {
            trigger: 'item',
            formatter: params => {
                const percent = Number.isFinite(params.percent) ? params.percent.toFixed(1) : '0.0';
                return `${params.marker}${params.name}<br/>占比：${percent}%<br/>平均时长：${formatDuration(params.value)}`;
            }
        },
        legend: {
            orient: 'horizontal',
            bottom: 10,
            left: 'center'
        },
        series: [{
            name: '状态时长分布',
            type: 'pie',
            radius: ['40%', '65%'],
            center: ['50%', '50%'],
            data: pieData,
            label: {
                formatter: info => `${info.name}\n${Number(info.percent).toFixed(1)}%`
            },
            emphasis: {
                scale: true,
                scaleSize: 8
            }
        }]
    }, true);
}

    function renderAlertHistory(data, options = {}) {
        if (!alertHistoryBody || !alertHistoryEmptyState || !alertHistoryTable) {
            return;
        }

        if (data === null) {
            alertHistoryBody.innerHTML = '';
            alertHistoryTable.style.display = 'none';
            alertHistoryEmptyState.textContent = options.emptyMessage || defaultAlertHistoryMessage;
            alertHistoryEmptyState.style.display = 'block';
            if (alertHistoryFootnote) {
                alertHistoryFootnote.style.display = 'none';
            }
            return;
        }

        if (data && typeof data === 'object') {
            latestHistoryData = data;
        }

        const sourceData = data && typeof data === 'object' ? data : latestHistoryData;
        const incidents = [];

        if (sourceData && typeof sourceData === 'object') {
            Object.entries(sourceData).forEach(([siteName, siteData]) => {
                (siteData.incidents || []).forEach(incident => {
                    incidents.push({
                        site_name: siteName,
                        ...incident
                    });
                });
            });
        }

        incidents.sort((a, b) => {
            const aValue = a.start_ts || 0;
            const bValue = b.start_ts || 0;
            return bValue - aValue;
        });

        const filteredIncidents = incidents.filter(incident => {
            const statusFilter = alertFilters.status;
            let statusMatch = true;
            if (statusFilter === 'resolved') {
                statusMatch = incident.resolved === true;
            } else if (statusFilter === 'unresolved') {
                statusMatch = incident.resolved === false || incident.resolved === undefined || incident.resolved === null;
            }

            const typeFilter = alertFilters.type;
            let typeMatch = true;
            if (typeFilter !== 'all') {
                typeMatch = incident.status_key === typeFilter;
            }
            return statusMatch && typeMatch;
        });

        if (filteredIncidents.length === 0) {
            alertHistoryBody.innerHTML = '';
            alertHistoryTable.style.display = 'none';
            const message = options.emptyMessage
                || (incidents.length === 0 ? defaultAlertHistoryMessage : buildAlertEmptyMessage());
            alertHistoryEmptyState.textContent = message;
            alertHistoryEmptyState.style.display = 'block';
            if (alertHistoryFootnote) {
                alertHistoryFootnote.style.display = 'none';
            }
            return;
        }

        alertHistoryEmptyState.style.display = 'none';
        alertHistoryTable.style.display = '';

        const limitedIncidents = filteredIncidents.slice(0, ALERT_HISTORY_LIMIT);
        const rowsHtml = limitedIncidents.map(incident => {
            const badgeClass = incident.status_key === 'down'
                ? 'alert-badge--down'
                : incident.status_key === 'slow'
                    ? 'alert-badge--slow'
                    : '';
            const typeLabel = incident.status_label || incident.status_key || '告警';
            const startText = formatDateTime(incident.start_ts);
            const endText = incident.resolved ? formatDateTime(incident.end_ts) : null;
            const durationText = formatDuration(incident.duration_ms);
            const reasonParts = [];
            if (incident.reason) {
                reasonParts.push(incident.reason);
            }
            const httpCode = Number(incident.http_status_code);
            if (Number.isFinite(httpCode) && httpCode >= 400) {
                const reasonText = incident.reason ? String(incident.reason) : '';
                if (!reasonText.includes(String(httpCode))) {
                    reasonParts.push(`HTTP ${httpCode}`);
                }
            }
            const detailText = reasonParts.length ? reasonParts.join(' / ') : '—';
            const endCellContent = incident.resolved
                ? escapeHtml(endText)
                : '<span class="alert-status-pending">未恢复</span>';
            return `<tr>
                <td>${escapeHtml(incident.site_name)}</td>
                <td><span class="alert-badge ${badgeClass}">${escapeHtml(typeLabel)}</span></td>
                <td>${escapeHtml(startText)}</td>
                <td>${endCellContent}</td>
                <td>${escapeHtml(durationText)}</td>
                <td>${escapeHtml(detailText)}</td>
            </tr>`;
        }).join('');

        alertHistoryBody.innerHTML = rowsHtml;
        if (alertHistoryFootnote) {
            alertHistoryFootnote.style.display = filteredIncidents.length > ALERT_HISTORY_LIMIT ? 'block' : 'none';
        }
    }

    function renderAlertHistoryError(message) {
        if (!alertHistoryBody || !alertHistoryEmptyState || !alertHistoryTable) {
            return;
        }
        latestHistoryData = null;
        alertHistoryBody.innerHTML = '';
        alertHistoryTable.style.display = 'none';
        alertHistoryEmptyState.textContent = message || '数据加载失败';
        alertHistoryEmptyState.style.display = 'block';
        if (alertHistoryFootnote) {
            alertHistoryFootnote.style.display = 'none';
        }
    }

    const refreshAlertHistory = () => {
        if (latestHistoryData) {
            renderAlertHistory(latestHistoryData);
        }
    };

    if (alertStatusFilter) {
        if (alertStatusFilter.value) {
            alertFilters.status = alertStatusFilter.value;
        }
        alertStatusFilter.addEventListener('change', event => {
            alertFilters.status = event.target.value;
            refreshAlertHistory();
        });
    }

    if (alertTypeFilter) {
        if (alertTypeFilter.value) {
            alertFilters.type = alertTypeFilter.value;
        }
        alertTypeFilter.addEventListener('change', event => {
            alertFilters.type = event.target.value;
            refreshAlertHistory();
        });
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

        if (summaryElements.avgUptime) {
            if (avgAvailability !== null) {
                const availabilityInfo = describeAvailability(avgAvailability);
                summaryElements.avgUptime.textContent = availabilityInfo.combined;
                if (availabilityInfo.valueText && availabilityInfo.valueText !== '--') {
                    summaryElements.avgUptime.title = availabilityInfo.ninesLabel
                        ? `${availabilityInfo.valueText}（${availabilityInfo.ninesLabel}）`
                        : availabilityInfo.valueText;
                } else {
                    summaryElements.avgUptime.removeAttribute('title');
                }
            } else {
                summaryElements.avgUptime.textContent = '--';
                summaryElements.avgUptime.removeAttribute('title');
            }
        }

        if (summaryElements.avgResponse) {
            summaryElements.avgResponse.textContent = avgResponse !== null ? avgResponse.toFixed(2) : '--';
        }

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
            latestHistoryData = null;
            renderAlertHistory(null, { emptyMessage: '请选择站点以查看告警' });
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
            latestHistoryData = data;
            updateSummaryCards(data, selectedSites);
            renderUptimeHistory(data);
            renderComparisonCharts(data);
            renderStatusDistribution(data);
            renderAlertHistory(data);
        } catch (error) {
            console.error(error);
            setChartEmptyState(timelineChart, timelineChartContainer, '数据加载失败，请稍后重试');
            setChartEmptyState(uptimeChart, uptimeChartContainer, '数据加载失败');
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '数据加载失败');
            if (statusDistributionChart) {
                setChartEmptyState(statusDistributionChart, statusDistributionChartContainer, '数据加载失败');
            }
            renderAlertHistoryError('数据加载失败');
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
                if (selectedDates.length === 2) {
                    const [start, end] = selectedDates;
                    const diffDays = (end - start) / (1000 * 60 * 60 * 24);

                    if (diffDays > dataRetentionDays) {
                        alert(`自定义时间范围不能超过${dataRetentionDays}天，请重新选择`);
                        rangePicker.clear();
                        applyCustomRangeBtn.disabled = true;
                    } else {
                        applyCustomRangeBtn.disabled = false;
                    }
                } else {
                    applyCustomRangeBtn.disabled = true;
                }
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

                const diffDays = (end - start) / (1000 * 60 * 60 * 24);
                if (diffDays > dataRetentionDays) {
                    alert(`自定义时间范围不能超过${dataRetentionDays}天`);
                    return;
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
