import {
    escapeHtml,
    formatDateTime,
    formatDuration,
    describeAvailability,
    ALERT_HISTORY_LIMIT
} from './utils.js';

export const buildAlertEmptyMessage = (filters) => {
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
    const statusLabel = statusLabelMap[filters.status];
    if (statusLabel) {
        parts.push(statusLabel);
    }
    const typeLabel = typeLabelMap[filters.type];
    if (typeLabel) {
        parts.push(typeLabel);
    }
    if (parts.length === 0) {
        return '当前筛选条件下暂无告警';
    }
    return `当前筛选条件下暂无${parts.join(' · ')}告警`;
};

export const renderAlertHistory = (data, options = {}, context) => {
    const {
        elements,
        filters,
        state,
        defaultEmptyMessage
    } = context;
    const {
        body,
        table,
        emptyState,
        footnote
    } = elements;

    if (!body || !table || !emptyState) {
        return;
    }

    const fallbackMessage = defaultEmptyMessage || '选定范围内暂无告警';

    if (data === null) {
        state.latestHistoryData = null;
        body.innerHTML = '';
        table.style.display = 'none';
        emptyState.textContent = options.emptyMessage || fallbackMessage;
        emptyState.style.display = 'block';
        if (footnote) {
            footnote.style.display = 'none';
        }
        return;
    }

    if (data && typeof data === 'object') {
        state.latestHistoryData = data;
    }

    const sourceData = data && typeof data === 'object' ? data : state.latestHistoryData;
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
        const statusFilter = filters.status;
        let statusMatch = true;
        if (statusFilter === 'resolved') {
            statusMatch = incident.resolved === true;
        } else if (statusFilter === 'unresolved') {
            statusMatch = incident.resolved === false || incident.resolved === undefined || incident.resolved === null;
        }

        const typeFilter = filters.type;
        let typeMatch = true;
        if (typeFilter !== 'all') {
            typeMatch = incident.status_key === typeFilter;
        }
        return statusMatch && typeMatch;
    });

    if (filteredIncidents.length === 0) {
        body.innerHTML = '';
        table.style.display = 'none';
        const message = options.emptyMessage
            || (incidents.length === 0 ? fallbackMessage : buildAlertEmptyMessage(filters));
        emptyState.textContent = message;
        emptyState.style.display = 'block';
        if (footnote) {
            footnote.style.display = 'none';
        }
        return;
    }

    emptyState.style.display = 'none';
    table.style.display = '';

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

    body.innerHTML = rowsHtml;
    if (footnote) {
        footnote.style.display = filteredIncidents.length > ALERT_HISTORY_LIMIT ? 'block' : 'none';
    }
};

export const renderAlertHistoryError = (message, context) => {
    const { elements, state } = context;
    const { body, table, emptyState, footnote } = elements;

    if (!body || !table || !emptyState) {
        return;
    }
    state.latestHistoryData = null;
    body.innerHTML = '';
    table.style.display = 'none';
    emptyState.textContent = message || '数据加载失败';
    emptyState.style.display = 'block';
    if (footnote) {
        footnote.style.display = 'none';
    }
};

export const updateSummaryCards = (data, selectedSites, summaryElements) => {
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
};

export const updateStatusWall = async ({ wallElement, initialData } = {}) => {
    if (!wallElement) {
        return;
    }

    const previouslySelected = new Set(
        Array.from(wallElement.querySelectorAll('.status-card.selected')).map(card => card.dataset.siteName)
    );
    const isFirstRun = wallElement.children.length === 0;

    let data = initialData;
    if (!data) {
        const response = await fetch('/health');
        data = await response.json();
    }

    const allSiteNames = Object.keys(data);

    wallElement.innerHTML = allSiteNames.map(siteName => {
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
            <div class="status-card ${statusClass}" data-site-name="${escapeHtml(siteName)}">
                <h3>${escapeHtml(siteName)}</h3>
                <p><strong>状态:</strong> ${site.status}</p>
                ${statusSpecificLine}
                <p><strong>响应时间:</strong> ${responseTimeText}</p>
                ${totalChecksLine}
                <p><strong>上次检查:</strong> ${site.last_checked}</p>
            </div>`;
    }).join('');

    wallElement.querySelectorAll('.status-card').forEach(card => {
        const siteName = card.dataset.siteName;
        if (isFirstRun || previouslySelected.has(siteName)) {
            card.classList.add('selected');
        }
    });
};

export const filterAndScrollToAlerts = ({ siteName, startTime, endTime, status }, context) => {
    const { elements, controls, filters, state } = context;
    const { body } = elements;
    const { typeSelect, statusSelect } = controls || {};

    if (!body || !state.latestHistoryData) {
        return;
    }

    const alertsContainer = document.querySelector('.alerts-container');
    if (alertsContainer) {
        alertsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    if (typeSelect) {
        if (status === 3) {
            typeSelect.value = 'down';
        } else if (status === 2) {
            typeSelect.value = 'slow';
        }
        filters.type = typeSelect.value;
    }

    if (statusSelect) {
        statusSelect.value = 'all';
        filters.status = 'all';
    }

    renderAlertHistory(state.latestHistoryData, {}, context);

    setTimeout(() => {
        const rows = body.querySelectorAll('tr');
        let foundMatch = false;
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 3) {
                const rowSiteName = cells[0].textContent.trim();
                const triggerTimeText = cells[2].textContent.trim();

                if (rowSiteName === siteName) {
                    const triggerTime = Date.parse(triggerTimeText.replace(' ', 'T'));
                    if (triggerTime >= startTime && triggerTime <= endTime) {
                        row.style.backgroundColor = '#fffacd';
                        row.style.transition = 'background-color 0.3s';
                        if (!foundMatch) {
                            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            foundMatch = true;
                        }
                        setTimeout(() => {
                            row.style.backgroundColor = '';
                        }, 3000);
                    }
                }
            }
        });
    }, 300);
};
