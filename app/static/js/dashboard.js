import { determinePickerLocale, toLocalISOString, setChartEmptyState } from './utils.js';
import { renderAlertHistory, renderAlertHistoryError, updateSummaryCards, updateStatusWall, filterAndScrollToAlerts } from './ui.js';
import { renderUptimeHistory, renderComparisonCharts, renderSLAComparison } from './charts.js';

document.addEventListener('DOMContentLoaded', () => {
    const timelineChartContainer = document.getElementById('timeline-chart');
    let timelineChart = echarts.init(timelineChartContainer);
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

    const summaryElements = {
        siteCount: document.getElementById('summary-site-count'),
        avgUptime: document.getElementById('summary-avg-uptime'),
        avgResponse: document.getElementById('summary-avg-response'),
        incidents: document.getElementById('summary-incident-count'),
        incidentHint: document.getElementById('summary-incident-hint')
    };

    const alertFilters = {
        status: 'unresolved',
        type: 'all'
    };
    const alertStatusFilter = document.getElementById('alert-status-filter');
    const alertTypeFilter = document.getElementById('alert-type-filter');

    const initialStatuses = window.INITIAL_STATUSES;
    const dataRetentionDays = 30;
    let currentParams = {};
    let rangePicker;

    const uiContext = {
        elements: {
            body: alertHistoryBody,
            table: alertHistoryTable,
            emptyState: alertHistoryEmptyState,
            footnote: alertHistoryFootnote
        },
        controls: {
            typeSelect: alertTypeFilter,
            statusSelect: alertStatusFilter
        },
        filters: alertFilters,
        state: {
            latestHistoryData: null
        },
        defaultEmptyMessage: defaultAlertHistoryMessage
    };

    const charts = {
        timelineChart,
        timelineChartContainer,
        responseTimeChart,
        responseTimeChartContainer,
        slaComparisonChart,
        slaComparisonChartContainer
    };

    const pickerLocale = determinePickerLocale();
    if (pickerLocale !== 'default' && flatpickr.l10ns[pickerLocale]) {
        flatpickr.localize(flatpickr.l10ns[pickerLocale]);
    }

    const refreshAlertHistory = () => {
        if (uiContext.state.latestHistoryData) {
            renderAlertHistory(uiContext.state.latestHistoryData, {}, uiContext);
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

    async function updateDashboard() {
        const selectedSites = Array.from(document.querySelectorAll('.status-card.selected'))
            .map(card => card.dataset.siteName);
        updateSummaryCards(null, selectedSites, summaryElements);
        if (selectedSites.length === 0) {
            setChartEmptyState(timelineChart, timelineChartContainer, '请选择至少一个网站以查看历史数据');
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '请选择至少一个网站以查看响应时间');
            if (slaComparisonChart && slaComparisonChartContainer) {
                setChartEmptyState(slaComparisonChart, slaComparisonChartContainer, '请选择至少一个网站以查看 SLA 对比');
            }
            renderAlertHistory(null, { emptyMessage: '请选择站点以查看告警' }, uiContext);
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
            uiContext.state.latestHistoryData = data;
            updateSummaryCards(data, selectedSites, summaryElements);
            renderUptimeHistory(data, charts, currentParams, (siteName, startTime, endTime, status) => {
                filterAndScrollToAlerts({ siteName, startTime, endTime, status }, uiContext);
            });
            renderComparisonCharts(data, charts, currentParams);
            renderSLAComparison(data, charts);
            renderAlertHistory(data, {}, uiContext);
        } catch (error) {
            console.error(error);
            setChartEmptyState(timelineChart, timelineChartContainer, '数据加载失败，请稍后重试');
            setChartEmptyState(responseTimeChart, responseTimeChartContainer, '数据加载失败');
            if (slaComparisonChart) {
                setChartEmptyState(slaComparisonChart, slaComparisonChartContainer, '数据加载失败');
            }
            renderAlertHistoryError('数据加载失败', uiContext);
        } finally {
            timelineChart.hideLoading();
        }
    }

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
        document.getElementById('status-wall').addEventListener('click', (e) => {
            const card = e.target.closest('.status-card');
            if (card) {
                card.classList.toggle('selected');
                updateDashboard();
            }
        });
        document.getElementById('select-all-status').addEventListener('click', () => {
            document.querySelectorAll('.status-card').forEach(card => card.classList.add('selected'));
            updateDashboard();
        });
        document.getElementById('deselect-all-status').addEventListener('click', () => {
            document.querySelectorAll('.status-card').forEach(card => card.classList.remove('selected'));
            updateDashboard();
        });
    }

    initializeControls();
    
    const statusWall = document.getElementById('status-wall');
    updateStatusWall({ wallElement: statusWall, initialData: initialStatuses })
        .then(() => {
            const activeButton = document.querySelector('#time-range-selector button.active');
            if (activeButton) {
                activeButton.click();
            } else {
                console.warn('No active time button found, defaulting to 12 hours.');
                const end = new Date();
                const start = new Date(end.getTime() - 12 * 60 * 60 * 1000);
                setAndTriggerUpdate(start, end);
            }
        })
        .catch(error => console.error('Failed to initialize status wall:', error));
    
    setInterval(() => {
        updateStatusWall({ wallElement: statusWall }).catch(error => console.error('Failed to refresh status wall:', error));
    }, 15000);
    
    window.addEventListener('resize', () => {
        if (timelineChart && !timelineChart.isDisposed()) timelineChart.resize();
        if (responseTimeChart && !responseTimeChart.isDisposed()) responseTimeChart.resize();
        if (slaComparisonChart && !slaComparisonChart.isDisposed()) slaComparisonChart.resize();
    });
});
