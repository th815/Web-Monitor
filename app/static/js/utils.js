export const STATUS_COLORS = {
    0: '#f0f0f0',
    1: '#91cc75',
    2: '#fac858',
    3: '#ee6666'
};

export const LINE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#84cc16', '#ec4899'];

export const ALERT_HISTORY_LIMIT = 30;

export const calculateNineCount = (availability) => {
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

export const describeAvailability = (availability) => {
    if (!Number.isFinite(availability)) {
        return {
            valueText: '--',
            combined: '--',
            ninesLabel: '',
            nineCount: null
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
        nineCount
    };
};

export const parseDate = (value) => {
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

export const getTimeRangeSpanMs = (startIso, endIso) => {
    const start = parseDate(startIso);
    const end = parseDate(endIso);
    if (!start || !end) {
        return null;
    }
    const diff = end.getTime() - start.getTime();
    return Number.isFinite(diff) ? Math.abs(diff) : null;
};

export const formatChartAxisTime = (value, rangeSpanMs) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return '';
    }
    const span = rangeSpanMs;
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

export const formatChartTooltipTime = (value) => {
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

export const formatDuration = (ms) => {
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

export const formatDateTime = (timestamp) => {
    if (timestamp === null || timestamp === undefined) {
        return '--';
    }
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
        return '--';
    }
    return date.toLocaleString('zh-CN', { hour12: false });
};

export const escapeHtml = (value) => {
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

export const setChartEmptyState = (chart, domElement, message) => {
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

export const determinePickerLocale = () => {
    const htmlLang = (document.documentElement.lang || '').toLowerCase();
    if (htmlLang.startsWith('zh') && flatpickr.l10ns.zh) {
        return 'zh';
    }
    return 'default';
};

export const toLocalISOString = (dt) => {
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}T${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
};
