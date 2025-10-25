import {
    STATUS_COLORS,
    LINE_COLORS,
    parseDate,
    formatChartAxisTime,
    formatChartTooltipTime,
    calculateNineCount,
    setChartEmptyState,
    getTimeRangeSpanMs
} from './utils.js';

function renderItem(params, api) {
    const categoryIndex = api.value(0);
    const start = api.coord([api.value(1), categoryIndex]);
    const end = api.coord([api.value(2), categoryIndex]);
    const height = api.size([0, 1])[1] * 0.8;

    const width = end[0] - start[0];
    if (width <= 0) {
        return null;
    }

    const rectShape = echarts.graphic.clipRectByRect(
        { x: start[0], y: start[1] - height / 2, width: width, height: height },
        { x: params.coordSys.x, y: params.coordSys.y, width: params.coordSys.width, height: params.coordSys.height }
    );

    return rectShape && { 
        type: 'rect', 
        shape: rectShape, 
        style: { fill: STATUS_COLORS[api.value(3)] },
        z2: 10
    };
}

export const renderUptimeHistory = (data, charts, currentParams, onClickCallback) => {
    const { timelineChart, timelineChartContainer } = charts;
    if (!timelineChart || !timelineChartContainer) {
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
    // --- 【核心修改 1】: 创建一个数组来存放所有网站的数据 ---
    const allSiteData = [];
    siteNames.forEach((siteName, index) => {
        const timelineData = Array.isArray(data?.[siteName]?.timeline_data) ? data[siteName].timeline_data : [];
        const siteData = timelineData.map(item => {
            // 准备 custom series 需要的数据格式
            // value: [Y轴索引, X开始, X结束, 状态ID, 详情]
            return {
                name: siteName, // 把网站名存在 name 里，方便 tooltip
                value: [index, item[0], item[1], item[2], item[3]]
            };
        });
        // 将当前网站的数据合并到总数组中
        allSiteData.push(...siteData);
    });
    const rangeSpan = currentParams ? getTimeRangeSpanMs(currentParams.start_iso, currentParams.end_iso) : null;
    const option = {
        animation: false,
        tooltip: {
            trigger: 'item',
            formatter: function (params) {
                if (!params || params.seriesType !== 'custom') {
                    return '';
                }
                // --- 【核心修改 2】: 从 params.name 获取网站名 ---
                const siteName = params.name;
                const value = params.value;
                const details = value[4];
                const startLabel = formatChartTooltipTime(value[1]);
                const endLabel = formatChartTooltipTime(value[2]);
                const status = value[3];
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
            axisLabel: {
                formatter: value => formatChartAxisTime(value, rangeSpan)
            }
        },
        yAxis: { type: 'category', data: siteNames, axisLabel: { interval: 0 } },
        // --- 【核心修改 3】: 只使用一个 series ---
        series: [{
            type: 'custom',
            renderItem: renderItem,
            itemStyle: { opacity: 0.85 },
            encode: { x: [1, 2], y: 0 },
            data: allSiteData, // 使用包含所有数据的数组
            progressive: 400,
            progressiveThreshold: 2000,
            progressiveChunkMode: 'mod'
        }]
    };
    timelineChart.setOption(option, true);
    timelineChart.off('click');
    timelineChart.on('click', function (params) {
        if (params.seriesType === 'custom' && params.value) {
            // --- 【核心修改 4】: 从 params.name 获取网站名 ---
            const siteName = params.name;
            const value = params.value;
            const status = value[3];
            const startTime = value[1];
            const endTime = value[2];
            if (status === 3 || status === 2) {
                onClickCallback(siteName, startTime, endTime, status);
            }
        }
    });
};

export const renderComparisonCharts = (data, charts, currentParams) => {
    const { responseTimeChart, responseTimeChartContainer } = charts;

    if (!responseTimeChart || !responseTimeChartContainer) {
        return;
    }

    const siteKeys = Object.keys(data || {});
    if (siteKeys.length === 0) {
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

    const rangeSpan = currentParams ? getTimeRangeSpanMs(currentParams.start_iso, currentParams.end_iso) : null;

    if (responseTimeSeries.length === 0 || sortedTimestamps.length === 0) {
        setChartEmptyState(responseTimeChart, responseTimeChartContainer, '暂无响应时间数据');
    } else {
        setChartEmptyState(responseTimeChart, responseTimeChartContainer, null);

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
                axisLabel: { formatter: value => formatChartAxisTime(value, rangeSpan) }
            },
            yAxis: {
                type: 'log',
                name: '响应时间 (秒)',
                nameGap: 30,
                axisLabel: {
                    formatter: function (value) {
                        if (value < 1) {
                            return value.toFixed(2);
                        }
                        return value.toFixed(1);
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
                if (s.name.includes('P95') || s.name.includes('P99')) {
                    return {
                        ...s,
                        connectNulls: true
                    };
                }
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
};

export const renderSLAComparison = (data, charts) => {
    const { slaComparisonChart, slaComparisonChartContainer } = charts;
    
    if (!slaComparisonChart || !slaComparisonChartContainer) {
        return;
    }
    const siteKeys = Object.keys(data || {});
    if (siteKeys.length === 0) {
        setChartEmptyState(slaComparisonChart, slaComparisonChartContainer, '暂无 SLA 对比数据');
        return;
    }

    const slaData = [];

    siteKeys.forEach(siteName => {
        const siteData = data[siteName] || {};
        const overallAvailability = siteData.overall_stats?.availability || 0;

        const sla = {
            name: siteName,
            today: overallAvailability,
            week: overallAvailability,
            month: overallAvailability
        };

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
                    color: function (params) {
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
                    color: function (params) {
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
                    color: function (params) {
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
};
