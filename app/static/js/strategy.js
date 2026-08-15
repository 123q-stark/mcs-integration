// ============================================================
// v1.5 策略页面 - 唯一 JavaScript 事实源
// 整合自 strategy.html 内联 + 原 strategy.js
// ============================================================

// ============ 工具函数 ============
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = 'toast ' + type + ' show';
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function getApiBase() {
    return '/api/strategies';
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

// ============ 配置加载 ============
async function loadDefaultConfigs() {
    try {
        // 加载电价
        const priceData = await fetchJson('/api/strategies/price-config');
        document.getElementById('price-valley').value = priceData.valley_price;
        document.getElementById('price-flat').value = priceData.flat_price;
        document.getElementById('price-peak').value = priceData.peak_price;

        // 加载 Grid
        const gridData = await fetchJson('/api/strategies/grid-config');
        document.getElementById('grid-max-import').value = gridData.max_import_power_kw;
        document.getElementById('grid-allow-export').checked = gridData.allow_export;
        document.getElementById('grid-max-export').value = gridData.max_export_power_kw;

        // 加载策略配置
        const configData = await fetchJson('/api/strategies/config');
        document.getElementById('batt-soc-min').value = configData.soc_min;
        document.getElementById('batt-soc-max').value = configData.soc_max;
        document.getElementById('batt-charge-power').value = configData.charge_power_kw;
        document.getElementById('batt-discharge-power').value = configData.discharge_power_kw;
        document.getElementById('batt-backup-soc').value = configData.backup_soc_target || 50;
        document.getElementById('requested-mode').value = configData.requested_mode || 'AUTO';
        document.getElementById('effective-mode-display').textContent = configData.requested_mode || 'AUTO';
        document.getElementById('header-mode').textContent = configData.requested_mode || 'AUTO';

        // 加载设备策略配置
        await loadDeviceConfigs();
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

async function loadDeviceConfigs() {
    try {
        const data = await fetchJson('/api/strategies/device-configs');
        // PV 配置 (前5条)
        const pvConfigs = data.filter(c => c.device_code.startsWith('PV'));
        const pvRows = document.querySelectorAll('#pv-config-table tr');
        pvRows.forEach((row, index) => {
            if (index < pvConfigs.length) {
                const config = pvConfigs[index];
                row.cells[1].querySelector('input').checked = config.participate_in_strategy;
                row.cells[2].querySelector('input').checked = config.allow_strategy_control;
                row.cells[3].querySelector('input').value = config.priority;
            }
        });

        // Charger 配置 (后5条)
        const chargerConfigs = data.filter(c => c.device_code.startsWith('CHG'));
        const chargerRows = document.querySelectorAll('#charger-config-table tr');
        chargerRows.forEach((row, index) => {
            if (index < chargerConfigs.length) {
                const config = chargerConfigs[index];
                row.cells[1].querySelector('input').checked = config.participate_in_strategy;
                row.cells[2].querySelector('input').checked = config.allow_strategy_control;
                row.cells[3].querySelector('input').value = config.strategy_power_limit_kw || 50;
                row.cells[4].querySelector('input').value = config.priority;
            }
        });
    } catch (error) {
        console.error('加载设备配置失败:', error);
    }
}

// ============ 配置保存 ============
function getFormData() {
    return {
        config_name: 'default',
        soc_min: parseFloat(document.getElementById('batt-soc-min').value),
        soc_max: parseFloat(document.getElementById('batt-soc-max').value),
        charge_power_kw: parseFloat(document.getElementById('batt-charge-power').value),
        discharge_power_kw: parseFloat(document.getElementById('batt-discharge-power').value),
        backup_soc_target: parseFloat(document.getElementById('batt-backup-soc').value),
        requested_mode: document.getElementById('requested-mode').value,
    };
}

async function saveConfig() {
    try {
        const data = getFormData();
        await fetchJson('/api/strategies/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        showToast('配置已保存');
    } catch (error) {
        console.error('保存配置失败:', error);
        showToast('保存失败', 'error');
    }
}

async function saveMode() {
    const mode = document.getElementById('requested-mode').value;
    try {
        const data = await fetchJson('/api/strategies/mode', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requested_mode: mode }),
        });
        document.getElementById('effective-mode-display').textContent = data.effective_mode || mode;
        document.getElementById('header-mode').textContent = data.effective_mode || mode;
        showToast('模式已保存: ' + mode);
    } catch (error) {
        showToast('保存失败', 'error');
    }
}

async function saveBatteryConfig() {
    await saveConfig();
}

async function saveGridConfig() {
    const data = {
        max_import_power_kw: parseFloat(document.getElementById('grid-max-import').value),
        allow_export: document.getElementById('grid-allow-export').checked,
        max_export_power_kw: parseFloat(document.getElementById('grid-max-export').value),
    };
    try {
        await fetchJson('/api/strategies/grid-config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        showToast('Grid 配置已保存');
    } catch (error) {
        showToast('保存失败', 'error');
    }
}

async function savePriceConfig() {
    const data = {
        valley_price: parseFloat(document.getElementById('price-valley').value),
        flat_price: parseFloat(document.getElementById('price-flat').value),
        peak_price: parseFloat(document.getElementById('price-peak').value),
    };
    try {
        await fetchJson('/api/strategies/price-config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        showToast('电价配置已保存');
    } catch (error) {
        showToast('保存失败', 'error');
    }
}

// ============ 策略运行 ============
async function runStrategy() {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '运行中...';
    try {
        const data = await fetchJson('/api/strategies/run', { method: 'POST' });
        document.getElementById('result-storage-target').textContent = (data.decision?.storage_power_target || 0) + ' kW';
        document.getElementById('result-message').textContent = data.decision?.message || data.message || '无消息';
        document.getElementById('result-last-run').textContent = new Date().toLocaleString();

        if (data.decision?.source) {
            document.getElementById('result-algorithm').textContent = data.decision.source;
        }
        if (data.effective_mode) {
            document.getElementById('result-effective-mode').textContent = data.effective_mode;
            document.getElementById('header-mode').textContent = data.effective_mode;
        }
        if (data.fallback_used !== undefined) {
            document.getElementById('result-fallback').textContent = data.fallback_used ? '是' : '否';
        }
        document.getElementById('header-status-text').textContent = '运行成功';
        document.getElementById('header-status-dot').className = 'stat-dot online';
        showToast('策略运行完成');
        setTimeout(fetchSchedule, 500);
        setTimeout(fetchForecast, 600);
    } catch (error) {
        showToast('运行失败', 'error');
        document.getElementById('header-status-text').textContent = '运行失败';
        document.getElementById('header-status-dot').className = 'stat-dot offline';
    } finally {
        btn.disabled = false;
        btn.textContent = '▶️ 运行一次策略';
    }
}

async function refreshResult() {
    try {
        const data = await fetchJson('/api/strategies/runtime');
        document.getElementById('result-algorithm').textContent = data.source || 'FixedRule';
        document.getElementById('result-requested-mode').textContent = data.requested_mode || 'AUTO';
        document.getElementById('result-effective-mode').textContent = data.effective_mode || 'AUTO';
        document.getElementById('result-fallback').textContent = data.fallback ? '是' : '否';
        document.getElementById('result-storage-target').textContent = (data.storage_power_target || 0) + ' kW';
        document.getElementById('result-message').textContent = data.message || '-';
        document.getElementById('header-mode').textContent = data.effective_mode || 'AUTO';
        if (data.executed_at) {
            document.getElementById('result-last-run').textContent = new Date(data.executed_at).toLocaleString();
        }
        document.getElementById('header-status-text').textContent = '已刷新';
        document.getElementById('header-status-dot').className = 'stat-dot online';
    } catch (error) {
        document.getElementById('header-status-text').textContent = '刷新失败';
        document.getElementById('header-status-dot').className = 'stat-dot offline';
    }
}

// ============ v1.3 预测曲线 ============
let loadChart = null;
let pvChart = null;

async function fetchForecast() {
    try {
        const loadData = await fetchJson('/api/strategies/forecast/load');
        const pvData = await fetchJson('/api/strategies/forecast/pv');

        const labels = loadData.points.map(p => {
            const dt = new Date(p.timestamp);
            return dt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        });
        const loadValues = loadData.points.map(p => p.value_kw);
        const pvValues = pvData.points.map(p => p.value_kw);

        updateChart('loadForecastChart', '负荷预测 (kW)', labels, loadValues, loadChart, '#4f8cf7');
        updateChart('pvForecastChart', 'PV 预测 (kW)', labels, pvValues, pvChart, '#f59e0b');
        document.getElementById('forecastTime').textContent = '更新于: ' + new Date().toLocaleString();
    } catch (error) {
        console.error('获取预测失败:', error);
        document.getElementById('forecastTime').textContent = '加载失败';
    }
}

function updateChart(canvasId, label, labels, values, chartInstance, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (chartInstance) {
        chartInstance.destroy();
    }
    const newChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: values,
                borderColor: color,
                backgroundColor: color + '33',
                fill: true,
                tension: 0.3,
                pointRadius: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { maxTicksLimit: 24, autoSkip: true } },
                y: { beginAtZero: true }
            }
        }
    });
    if (canvasId === 'loadForecastChart') {
        loadChart = newChart;
    } else if (canvasId === 'pvForecastChart') {
        pvChart = newChart;
    }
}

// ============ v1.4 调度计划 ============
let schedulePowerChart = null;
let scheduleSocChart = null;

async function fetchSchedule() {
    try {
        const data = await fetchJson('/api/strategies/schedule');
        if (data.schedule && data.schedule.length > 0) {
            const labels = data.schedule.map(item => {
                const dt = new Date(item.timestamp);
                return dt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            });
            const powerValues = data.schedule.map(item => item.power);
            const socValues = data.schedule.map(item => item.soc);

            updateScheduleChart('schedulePowerChart', '储能功率 (kW)', labels, powerValues, schedulePowerChart, '#10b981', '#10b98133');
            updateScheduleChart('scheduleSocChart', 'SOC (%)', labels, socValues, scheduleSocChart, '#6366f1', '#6366f133');
            document.getElementById('scheduleTime').textContent = '更新于: ' + new Date(data.created_at).toLocaleString();
        } else {
            document.getElementById('scheduleTime').textContent = '暂无调度数据';
        }
    } catch (error) {
        console.error('获取调度计划失败:', error);
        document.getElementById('scheduleTime').textContent = '加载失败';
    }
}

function updateScheduleChart(canvasId, label, labels, values, chartInstance, color, fillColor) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (chartInstance) {
        chartInstance.destroy();
    }
    const newChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: values,
                borderColor: color,
                backgroundColor: fillColor || color + '33',
                fill: true,
                tension: 0.3,
                pointRadius: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { maxTicksLimit: 24, autoSkip: true } },
                y: { beginAtZero: true }
            }
        }
    });
    if (canvasId === 'schedulePowerChart') {
        schedulePowerChart = newChart;
    } else if (canvasId === 'scheduleSocChart') {
        scheduleSocChart = newChart;
    }
}

// ============ 预览决策 ============
function getPreviewData() {
    return {
        pv_power: parseFloat(document.getElementById('pv-power').value),
        load_power: parseFloat(document.getElementById('load-power').value),
        storage_power: parseFloat(document.getElementById('storage-power').value),
        storage_soc: parseFloat(document.getElementById('storage-soc').value)
    };
}

function displayPreviewResult(result) {
    const actionEl = document.getElementById('preview-action');
    actionEl.textContent = result.action;
    actionEl.className = 'action-tag ' + result.action;
    document.getElementById('preview-power').textContent = result.storage_power_target;
    document.getElementById('preview-message').textContent = result.message;
    document.getElementById('preview-time').textContent = new Date(result.created_at).toLocaleString();
    document.getElementById('preview-result').style.display = 'block';
}

async function previewDecision() {
    try {
        const data = getPreviewData();
        const result = await fetchJson('/api/strategies/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        displayPreviewResult(result);
    } catch (error) {
        document.getElementById('preview-result').style.display = 'block';
        document.getElementById('preview-message').textContent = '预览失败，请检查输入';
    }
}

// ============ 页面初始化 ============
document.addEventListener('DOMContentLoaded', function() {
    loadDefaultConfigs();
    setTimeout(fetchForecast, 300);
    setTimeout(fetchSchedule, 600);

    // 预览表单提交
    document.getElementById('preview-form')?.addEventListener('submit', function(e) {
        e.preventDefault();
        previewDecision();
    });
});