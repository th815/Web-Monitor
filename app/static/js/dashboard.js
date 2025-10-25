// web-monitor/app/static/js/dashboard.js

document.addEventListener('DOMContentLoaded', () => {

    // --- 图表实例与 DOM 引用 ---
    const timelineChartContainer = document.getElementById('timeline-chart');
    let timelineChart = echarts.init(timelineChartContainer);
    // const uptimeChartContainer = document.getElementById('uptime-chart');
    // const uptimeChart = echarts.init(uptimeChartContainer);
    const responseTimeChartContainer = document.getElementById('response-time-chart');
    const responseTimeChart = echarts.init(responseTimeChartContainer);
    const slaComparisonChartContainer = document.getElementById('sla-comparison-chart');
    const slaComparisonChart = slaComparisonChartContainer ? echarts.init(slaComparisonChartContainer) : null;
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
    // 统一调色板（可按需调整）
    const LINE_COLORS = ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#84cc16','#ec4899'];

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
            ninesLabel = '无限个9';
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
        // params.context.dataIndex 是当前数据项的索引
        // api.value(n) 用于获取当前数据项 value 数组的第 n 个值
        const categoryIndex = api.value(0); // Y 轴索引
        const startTime = api.value(1);     // 开始时间戳
        const endTime = api.value(2);       // 结束时间戳
        // 将数据坐标转换为画布上的物理坐标
        const startPoint = api.coord([startTime, categoryIndex]);
        const endPoint = api.coord([endTime, categoryIndex]);
        // 如果坐标无效（例如数据点在当前视图范围之外），则不渲染
        if (!startPoint || !endPoint) {
            return;
        }
        const height = api.size([0, 1])[1] * 0.8; // 计算条块的高度
        const width = endPoint[0] - startPoint[0];
        // 定义矩形的形状
        const rectShape = {
            x: startPoint[0],
            y: startPoint[1] - height / 2,
            width: width,
            height: height
        };
        // 使用 ECharts 内置的裁剪函数，确保条块不会画出图表区域
        const clippedRect = echarts.graphic.clipRectByRect(rectShape, {
            x: params.coordSys.x,
            y: params.coordSys.y,
            width: params.coordSys.width,
            height: params.coordSys.height
        });
        // 返回最终的图形元素定义
        return clippedRect && {
            type: 'rect',
            shape: clippedRect,
            style: {
                fill: STATUS_COLORS[api.value(3)] // 从 value[3] 获取颜色
            }
        };
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
        const chartHeight = Math.max(160, siteNames.length * 42 + 80);
        timelineChartContainer.style.height = `${chartHeight}px`;
        timelineChart.resize();
        const allSiteData = [];
        siteNames.forEach((siteName, index) => {
            const siteData = data[siteName].timeline_data.map(item => {
                // 准备 custom series 需要的数据格式
                // value: [Y轴索引, X开始, X结束, 状态ID, 详情]
                return {
                    name: siteName, // 把网站名存在 name 里，方便 tooltip
                    value: [index, item[0], item[1], item[2], item[3]]
                };
            });
            allSiteData.push(...siteData);
        });
        const option = {
            tooltip: {
                trigger: 'item',
                formatter: function (params) {
                    if (params.seriesType !== 'custom') {
                        return '';
                    }
                    const siteName = params.name;
                    const value = params.value;
                    const startLabel = formatChartTooltipTime(value[1]);
                    const endLabel = formatChartTooltipTime(value[2]);
                    const status = value[3];
                    const details = value[4];
                    let tip = `<strong>${siteName}</strong><br/>时间: ${startLabel} - ${endLabel}<br/>${details}`;
                    if (status === 3 || status === 2) {
                        tip += '<br/><span style="color: #3498db; font-size: 11px;">💡 点击查看相关告警</span>';
                    }
                    return tip;
                }
            },
            dataZoom: [ /* dataZoom 配置保持不变 */ {
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
            }],
            grid: { top: 25, left: 120, right: 30, bottom: 90 },
            xAxis: {
                type: 'time',
                axisLabel: { formatter: value => formatChartAxisTime(value) }
            },
            yAxis: {
                type: 'category',
                data: siteNames,
                axisLabel: { interval: 0 }
            },
            series: [{
                type: 'custom',
                renderItem: renderItem, // 关键：指定我们的渲染函数
                data: allSiteData,
                encode: {
                    // 告诉 ECharts value 数组的哪个索引对应哪个轴
                    x: [1, 2], // value[1] 和 value[2] 对应 X 轴
                    y: 0       // value[0] 对应 Y 轴
                }
            }]
        };
        timelineChart.setOption(option, true);

        timelineChart.off('click');
        timelineChart.on('click', function (params) {
            if (params.seriesType === 'custom' && Array.isArray(params.value)) {
                const siteName = params.name;
                const value = params.value;
                const startTime = value[1];
                const endTime = value[2];
                const status = value[3];
                if (status === 3 || status === 2) {
                    filterAndScrollToAlerts(siteName, startTime, endTime, status);
                }
            }
        });
    }
    // 联动函数：筛选并滚动到告警
    function filterAndScrollToAlerts(siteName, startTime, endTime, status) {
        if (!alertHistoryBody || !latestHistoryData) {
            return;
        }
        
        // 滚动到告警历史区域
        const alertsContainer = document.querySelector('.alerts-container');
        if (alertsContainer) {
            alertsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        
        // 更新筛选器以显示相关告警
        if (alertTypeFilter) {
            if (status === 3) {
                alertTypeFilter.value = 'down';
            } else if (status === 2) {
                alertTypeFilter.value = 'slow';
            }
            alertFilters.type = alertTypeFilter.value;
        }
        
        if (alertStatusFilter) {
            alertStatusFilter.value = 'all';
            alertFilters.status = 'all';
        }
        
        // 重新渲染告警历史
        renderAlertHistory(latestHistoryData);
        
        // 高亮匹配的行
        setTimeout(() => {
            const rows = alertHistoryBody.querySelectorAll('tr');
            let foundMatch = false;
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 3) {
                    const rowSiteName = cells[0].textContent.trim();
                    const triggerTimeText = cells[2].textContent.trim();
                    
                    // 简单的时间范围匹配
                    if (rowSiteName === siteName) {
                        // 解析触发时间
                        const triggerTime = Date.parse(triggerTimeText.replace(' ', 'T'));
                        if (triggerTime >= startTime && triggerTime <= endTime) {
                            row.style.backgroundColor = '#fffacd';
                            row.style.transition = 'background-color 0.3s';
                            if (!foundMatch) {
                                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                foundMatch = true;
                            }
                            // 3秒后恢复原色
                            setTimeout(() => {
                                row.style.backgroundColor = '';
                            }, 3000);
                        }
                    }
                }
            });
        }, 300);
    }

        function renderComparisonCharts(data) {
    const siteKeys = Object.keys(data || {});
    if (siteKeys.length === 0) {
        // 只保留 responseTimeChart 的空状态设置
        setChartEmptyState(responseTimeChart, responseTimeChartContainer, '暂无响应时间数据');
        return;
    }
    const responseTimeLegends = [];
    const responseTimeSeries = [];
    const timestampSet = new Set();
    const timestampLabelMap = new Map();
    const siteResponseMaps = new Map();
    siteKeys.forEach(siteName => {
        const siteData = data[siteName] || {};
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
                data: seriesData
            });
        }
    });
    const startBoundary = parseDate(currentParams.start_iso);
    const endBoundary = parseDate(currentParams.end_iso);
    if (responseTimeSeries.length === 0 || sortedTimestamps.length === 0) {
        setChartEmptyState(responseTimeChart, responseTimeChartContainer, '暂无响应时间数据');
    } else {
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, null);

            // 添加 P95 和 P99 线
            const allSeries = [...responseTimeSeries];
            const p95Series = [];
            const p99Series = [];
            
            siteKeys.forEach(siteName => {
                const siteData = data[siteName] || {};
                const p95 = siteData.overall_stats?.p95_response_time;
                const p99 = siteData.overall_stats?.p99_response_time;
                
                if (Number.isFinite(p95) && p95 > 0) {
                    p95Series.push({
                        name: `${siteName} P95`,
                        type: 'line',
                        data: sortedTimestamps.map(ts => [ts, p95]),
                        lineStyle: { type: 'dashed', width: 1.5, opacity: 0.7 },
                        symbol: 'none',
                        silent: true
                    });
                }
                
                if (Number.isFinite(p99) && p99 > 0) {
                    p99Series.push({
                        name: `${siteName} P99`,
                        type: 'line',
                        data: sortedTimestamps.map(ts => [ts, p99]),
                        lineStyle: { type: 'dotted', width: 1.5, opacity: 0.7 },
                        symbol: 'none',
                        silent: true
                    });
                }
            });

            allSeries.push(...p95Series, ...p99Series);
            const allLegends = [...responseTimeLegends, ...p95Series.map(s => s.name), ...p99Series.map(s => s.name)];

            responseTimeChart.setOption({
                color: LINE_COLORS,
                tooltip: {
                    trigger: 'axis',
                    formatter: params => {
                        if (!params || !params.length) return '';
                        const first = params[0];
                        const value = Array.isArray(first.value) ? first.value[0] : first.axisValue;
                        const numericValue = Number(value);
                        const label = (timestampLabelMap && timestampLabelMap.get && timestampLabelMap.get(numericValue))
                            || (typeof formatChartTooltipTime === 'function' ? formatChartTooltipTime(numericValue) : new Date(numericValue).toLocaleString());
                        const lines = [`<strong>${label}</strong>`];
                        params.forEach(item => {
                            const val = Array.isArray(item.value) ? item.value[1] : item.data;
                            const valueText = Number.isFinite(val) ? `${Number(val).toFixed(2)} 秒` : '--';
                            lines.push(`${item.marker}${item.seriesName}：${valueText}`);
                        });
                        return lines.join('<br/>');
                    }
                },
                legend: { data: allLegends, top: 10, type: 'scroll' },
                grid: { top: 70, left: 60, right: 50, bottom: 120 },
                xAxis: {
                    type: 'time',
                    boundaryGap: false,
                    axisLabel: { formatter: value => formatChartAxisTime(value) }
                },
                yAxis: {
                        type: 'log', // 从 'value' 改为 'log'
                        name: '响应时间 (秒)',
                        nameGap: 30,
                        // 对数轴的标签可以自定义格式，防止出现 0.0001 这样的小数
                        axisLabel: {
                            formatter: function (value) {
                                if (value < 1) {
                                    return value.toFixed(2); // 小于1秒时，显示两位小数
                                }
                                return value.toFixed(1); // 大于等于1秒时，显示一位小数
                            }
                        }
                    },
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
                    { type: 'inside', disabled: true }
                ],
                series: allSeries.map((s, idx) => {
                    // 如果是 P95/P99 线，保持原样
                    if (s.name.includes('P95') || s.name.includes('P99')) {
                        return {
                            ...s,
                            connectNulls: true
                        };
                    }
                    // 否则应用平滑和样式
                    return {
                        ...s,
                        connectNulls: true,
                        smooth: 0.25,
                        symbol: 'circle',
                        symbolSize: 4,
                        showSymbol: false,
                        lineStyle: { width: 2, opacity: 0.95 },
                        areaStyle: { opacity: 0.06 },
                        emphasis: { focus: 'series' }
                    };
                })
            }, true);
        }
    }


    function renderSLAComparison(data) {
        if (!slaComparisonChart || !slaComparisonChartContainer) {
            return;
        }
        const siteKeys = Object.keys(data || {});
        if (siteKeys.length === 0) {
            setChartEmptyState(slaComparisonChart, slaComparisonChartContainer, '暂无 SLA 对比数据');
            return;
        }

        // 计算每个站点在不同时间窗口的可用率
        const slaData = [];
        const now = new Date();
        
        siteKeys.forEach(siteName => {
            const siteData = data[siteName] || {};
            const overallAvailability = siteData.overall_stats?.availability || 0;
            
            // 从 overall_stats 中获取或计算可用率
            // 这里简化处理，使用当前选定时段的可用率作为参考
            // 实际应该从后端获取不同时间窗口的数据
            const sla = {
                name: siteName,
                today: overallAvailability,
                week: overallAvailability,
                month: overallAvailability
            };
            
            // 如果有 sla_stats，则使用它
            if (siteData.sla_stats) {
                sla.today = siteData.sla_stats.today || overallAvailability;
                sla.week = siteData.sla_stats.week || overallAvailability;
                sla.month = siteData.sla_stats.month || overallAvailability;
            }
            
            slaData.push(sla);
        });

        const chartHeight = Math.max(400, siteKeys.length * 80 + 120);
        slaComparisonChartContainer.style.height = `${chartHeight}px`;
        slaComparisonChart.resize();

        setChartEmptyState(slaComparisonChart, slaComparisonChartContainer, null);

        const option = {
            title: {
                text: '可用率对比 (今日/近7天/近30天)',
                left: 'center',
                top: 10,
                textStyle: {
                    fontSize: 14,
                    fontWeight: 'normal'
                }
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'shadow'
                },
                formatter: params => {
                    if (!params || !params.length) return '';
                    const siteName = params[0].axisValue;
                    let result = `<strong>${siteName}</strong><br/>`;
                    params.forEach(item => {
                        const value = Number.isFinite(item.value) ? item.value.toFixed(2) : '--';
                        const nineCount = calculateNineCount(item.value);
                        let ninesLabel = '';
                        if (nineCount !== null) {
                            if (!Number.isFinite(nineCount)) {
                                ninesLabel = ' (无限个9)';
                            } else if (nineCount > 0) {
                                ninesLabel = ` (${nineCount}个9)`;
                            }
                        }
                        result += `${item.marker}${item.seriesName}: ${value}%${ninesLabel}<br/>`;
                    });
                    return result;
                }
            },
            legend: {
                data: ['今日', '近7天', '近30天'],
                top: 40,
                left: 'center'
            },
            grid: {
                left: 100,
                right: 60,
                top: 80,
                bottom: 30,
                containLabel: false
            },
            xAxis: {
                type: 'value',
                max: 100,
                axisLabel: {
                    formatter: '{value}%'
                }
            },
            yAxis: {
                type: 'category',
                data: slaData.map(item => item.name),
                axisLabel: {
                    interval: 0
                }
            },
            series: [
                {
                    name: '今日',
                    type: 'bar',
                    data: slaData.map(item => Number(item.today.toFixed(4))),
                    itemStyle: {
                        color: function(params) {
                            const value = params.value;
                            if (value >= 99.99) return '#2ecc71';
                            if (value >= 99.9) return '#67C23A';
                            if (value >= 99) return '#91cc75';
                            if (value >= 95) return '#E6A23C';
                            return '#F56C6C';
                        }
                    },
                    label: {
                        show: true,
                        position: 'right',
                        formatter: params => `${Number(params.value).toFixed(2)}%`,
                        fontSize: 11
                    }
                },
                {
                    name: '近7天',
                    type: 'bar',
                    data: slaData.map(item => Number(item.week.toFixed(4))),
                    itemStyle: {
                        color: function(params) {
                            const value = params.value;
                            if (value >= 99.99) return '#3498db';
                            if (value >= 99.9) return '#5dade2';
                            if (value >= 99) return '#85c1e9';
                            if (value >= 95) return '#f39c12';
                            return '#e74c3c';
                        }
                    },
                    label: {
                        show: true,
                        position: 'right',
                        formatter: params => `${Number(params.value).toFixed(2)}%`,
                        fontSize: 11
                    }
                },
                {
                    name: '近30天',
                    type: 'bar',
                    data: slaData.map(item => Number(item.month.toFixed(4))),
                    itemStyle: {
                        color: function(params) {
                            const value = params.value;
                            if (value >= 99.99) return '#8e44ad';
                            if (value >= 99.9) return '#9b59b6';
                            if (value >= 99) return '#af7ac5';
                            if (value >= 95) return '#e67e22';
                            return '#c0392b';
                        }
                    },
                    label: {
                        show: true,
                        position: 'right',
                        formatter: params => `${Number(params.value).toFixed(2)}%`,
                        fontSize: 11
                    }
                }
            ]
        };

        slaComparisonChart.setOption(option, true);
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
        const selectedSites = Array.from(document.querySelectorAll('.status-card.selected'))
                             .map(card => card.dataset.siteName);
        updateSummaryCards(null, selectedSites);
        if (selectedSites.length === 0) {
            setChartEmptyState(timelineChart, timelineChartContainer, '请选择至少一个网站以查看历史数据');
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '请选择至少一个网站以查看响应时间');
            if (slaComparisonChart && slaComparisonChartContainer) {
                setChartEmptyState(slaComparisonChart, slaComparisonChartContainer, '请选择至少一个网站以查看 SLA 对比');
            }
            latestHistoryData = null;
            renderAlertHistory(null, { emptyMessage: '请选择站点以查看告警' });
            return;
        }
        setChartEmptyState(timelineChart, timelineChartContainer, null);
        timelineChart.showLoading();
        if (slaComparisonChart && slaComparisonChartContainer) {
            setChartEmptyState(slaComparisonChart, slaComparisonChartContainer, null);
            slaComparisonChart.showLoading('');
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
            renderSLAComparison(data);
            renderAlertHistory(data);
        } catch (error) {
            console.error(error);
            setChartEmptyState(timelineChart, timelineChartContainer, '数据加载失败，请稍后重试');
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '数据加载失败');
            if (slaComparisonChart) {
                setChartEmptyState(slaComparisonChart, slaComparisonChartContainer, '数据加载失败');
            }
            renderAlertHistoryError('数据加载失败');
        } finally {
            timelineChart.hideLoading();
            // if (statusDistributionChart) {
            //     statusDistributionChart.hideLoading();
            // }
        }
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
    async function updateStatusWall(initialData = null) {
    const wall = document.getElementById('status-wall');

    // 在重新渲染前，记录当前已选择的站点
    const previouslySelected = new Set(
        Array.from(wall.querySelectorAll('.status-card.selected')).map(card => card.dataset.siteName)
    );
    // 判断是否是首次加载（此时墙内没有卡片）
    const isFirstRun = wall.children.length === 0;

    const data = initialData || await (await fetch('/health')).json();
    // const siteOrder = Array.from(document.querySelectorAll('#site-selector input')).map(el => el.value);

    // 新的获取站点顺序的方式
    const allSiteNames = Object.keys(data);

    wall.innerHTML = allSiteNames.map(siteName => {
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

        // **关键**: 添加 data-site-name 属性，并确保 siteName 被正确转义
        return `
            <div class="status-card ${statusClass}" data-site-name="${escapeHtml(siteName)}">
                <h3>${escapeHtml(siteName)}</h3>
                <p><strong>状态:</strong> ${site.status}</p>
                ${statusSpecificLine}
                <p><strong>响应时间:</strong> ${responseTimeText}</p>
                ${totalChecksLine}
                <p><strong>上次检查:</strong> ${site.last_checked}</p>
            </div>`;
    }).join('');

    // 重新应用选择状态
    wall.querySelectorAll('.status-card').forEach(card => {
        const siteName = card.dataset.siteName;
        // 如果是首次加载，默认全选。否则，恢复之前的选择。
        if (isFirstRun || previouslySelected.has(siteName)) {
            card.classList.add('selected');
        }
    });
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
            document.getElementById('status-wall').addEventListener('click', (e) => {
                const card = e.target.closest('.status-card');
                if (card) {
                    card.classList.toggle('selected');
                    updateDashboard(); // 点击后立即更新图表
                }
            });
            // 2. "全选" 按钮
            document.getElementById('select-all-status').addEventListener('click', () => {
                document.querySelectorAll('.status-card').forEach(card => card.classList.add('selected'));
                updateDashboard();
            });
            // 3. "全不选" 按钮
            document.getElementById('deselect-all-status').addEventListener('click', () => {
                document.querySelectorAll('.status-card').forEach(card => card.classList.remove('selected'));
                updateDashboard();
            });
    }
// --- 初始加载 ---
initializeControls();
// 1. 使用初始数据渲染状态墙。
//    updateStatusWall 是 async 函数，返回一个 Promise。
updateStatusWall(initialStatuses).then(() => {
    // 2. 状态墙渲染完毕并且卡片已默认选中后，
    //    再模拟点击时间按钮来触发第一次数据加载。
    //    这个 .click() 会调用 setAndTriggerUpdate，从而设置好时间并调用 updateDashboard。
    const activeButton = document.querySelector('#time-range-selector button.active');
    if (activeButton) {
        activeButton.click();
    } else {
        // 如果没有默认激活的按钮，手动触发一个默认范围
        console.warn("No active time button found, defaulting to 12 hours.");
        const end = new Date();
        const start = new Date(end.getTime() - 12 * 60 * 60 * 1000);
        setAndTriggerUpdate(start, end);
    }
});
// 3. 设置状态墙的周期性刷新。
setInterval(() => updateStatusWall(), 15000);
// 4. 窗口大小调整监听器。
window.addEventListener('resize', () => {
    if (timelineChart && !timelineChart.isDisposed()) timelineChart.resize();
    if (responseTimeChart && !responseTimeChart.isDisposed()) responseTimeChart.resize();
    if (slaComparisonChart && !slaComparisonChart.isDisposed()) slaComparisonChart.resize();
});

});
