// ============================================================
// v1.5 策略页面 - 唯一 JavaScript 事实源
// ============================================================

// ============ 工具函数 ============
function showToast(message, type) {
    if (type === undefined) type = 'success';
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = 'toast ' + type + ' show';
    setTimeout(function() {
        toast.classList.remove('show');
    }, 3000);
}

async function fetchJson(url, options) {
    if (options === undefined) options = {};
    const response = await fetch(url, options);
    if (!response.ok) {
        throw new Error('HTTP ' + response.status + ': ' + response.statusText);
    }
    return response.json();
}

// ============ 配置加载 ============
async function loadDefaultConfigs() {
    try {
        var priceData = await fetchJson('/api/strategies/price-config');
        document.getElementById('price-valley').value = priceData.valley_price;
        document.getElementById('price-flat').value = priceData.flat_price;
        document.getElementById('price-peak').value = priceData.peak_price;

        var gridData = await fetchJson('/api/strategies/grid-config');
        document.getElementById('grid-max-import').value = gridData.max_import_power_kw;
        document.getElementById('grid-allow-export').checked = gridData.allow_export;
        document.getElementById('grid-max-export').value = gridData.max_export_power_kw;

        var configData = await fetchJson('/api/strategies/config');
        document.getElementById('batt-soc-min').value = configData.soc_min;
        document.getElementById('batt-soc-max').value = configData.soc_max;
        document.getElementById('batt-charge-power').value = configData.charge_power_kw;
        document.getElementById('batt-discharge-power').value = configData.discharge_power_kw;
        document.getElementById('batt-backup-soc').value = configData.backup_soc_target || 50;
        document.getElementById('requested-mode').value = configData.requested_mode || 'AUTO';
        document.getElementById('effective-mode-display').textContent = configData.requested_mode || 'AUTO';
        document.getElementById('header-mode').textContent = configData.requested_mode || 'AUTO';

        await loadDeviceConfigs();
    } catch (error) {
        console.error('加载配置失败:', error);
        showToast('加载配置失败', 'error');
    }
}

// ============ 设备配置暂存 ============
var deviceConfigChanges = {};

async function loadDeviceConfigs() {
    try {
        var data = await fetchJson('/api/strategies/device-configs');
        
        var pvConfigs = data.filter(function(c) { return c.device_code.startsWith('PV'); });
        var pvTbody = document.getElementById('pv-config-table');
        if (pvTbody) {
            var pvHtml = '';
            for (var i = 0; i < pvConfigs.length; i++) {
                var c = pvConfigs[i];
                var checked = c.participate_in_strategy ? 'checked' : '';
                pvHtml += '<tr>';
                pvHtml += '<td><strong>' + c.device_code + '</strong></td>';
                pvHtml += '<td><input type="checkbox" ' + checked + ' onchange="updateDeviceConfig(\'' + c.device_code + '\', \'participate_in_strategy\', this.checked)"></td>';
                pvHtml += '<td><input type="checkbox" ' + (c.allow_strategy_control ? 'checked' : '') + ' disabled></td>';
                pvHtml += '<td><input type="number" value="' + c.priority + '" min="1" max="5" onchange="updateDeviceConfig(\'' + c.device_code + '\', \'priority\', parseInt(this.value))"></td>';
                pvHtml += '<td><button class="btn btn-sm btn-primary" onclick="saveDeviceConfig(\'' + c.device_code + '\')">💾 保存</button></td>';
                pvHtml += '</tr>';
            }
            pvTbody.innerHTML = pvHtml;
        }

        var chargerConfigs = data.filter(function(c) { return c.device_code.startsWith('CHG'); });
        var chargerTbody = document.getElementById('charger-config-table');
        if (chargerTbody) {
            var chargerHtml = '';
            for (var j = 0; j < chargerConfigs.length; j++) {
                var c2 = chargerConfigs[j];
                var checked1 = c2.participate_in_strategy ? 'checked' : '';
                var checked2 = c2.allow_strategy_control ? 'checked' : '';
                var limitVal = c2.strategy_power_limit_kw || 50;
                chargerHtml += '<tr>';
                chargerHtml += '<td><strong>' + c2.device_code + '</strong></td>';
                chargerHtml += '<td><input type="checkbox" ' + checked1 + ' onchange="updateDeviceConfig(\'' + c2.device_code + '\', \'participate_in_strategy\', this.checked)"></td>';
                chargerHtml += '<td><input type="checkbox" ' + checked2 + ' onchange="updateDeviceConfig(\'' + c2.device_code + '\', \'allow_strategy_control\', this.checked)"></td>';
                chargerHtml += '<td><input type="number" value="' + limitVal + '" min="0" max="200" onchange="updateDeviceConfig(\'' + c2.device_code + '\', \'strategy_power_limit_kw\', parseFloat(this.value))"></td>';
                chargerHtml += '<td><input type="number" value="' + c2.priority + '" min="1" max="5" onchange="updateDeviceConfig(\'' + c2.device_code + '\', \'priority\', parseInt(this.value))"></td>';
                chargerHtml += '<td><button class="btn btn-sm btn-primary" onclick="saveDeviceConfig(\'' + c2.device_code + '\')">💾 保存</button></td>';
                chargerHtml += '</tr>';
            }
            chargerTbody.innerHTML = chargerHtml;
        }
    } catch (error) {
        console.error('加载设备配置失败:', error);
        showToast('加载设备配置失败', 'error');
    }
}

function updateDeviceConfig(deviceCode, field, value) {
    if (!deviceConfigChanges[deviceCode]) {
        deviceConfigChanges[deviceCode] = {};
    }
    deviceConfigChanges[deviceCode][field] = value;
}

async function saveDeviceConfig(deviceCode) {
    var changes = deviceConfigChanges[deviceCode] || {};
    var keys = Object.keys(changes);
    if (keys.length === 0) {
        showToast('没有需要保存的修改', 'warning');
        return;
    }
    
    var btn = event ? event.target : null;
    if (btn) {
        btn.disabled = true;
        btn.textContent = '保存中...';
    }
    
    try {
        await fetchJson('/api/strategies/device-configs/' + deviceCode, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(changes)
        });
        delete deviceConfigChanges[deviceCode];
        showToast(deviceCode + ' 配置已保存');
        await loadDeviceConfigs();
    } catch (error) {
        console.error('保存失败:', error);
        showToast('保存失败: ' + error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '💾 保存';
        }
    }
}

async function saveAllDeviceConfigs() {
    var allChanges = Object.keys(deviceConfigChanges);
    if (allChanges.length === 0) {
        showToast('没有需要保存的修改', 'warning');
        return;
    }
    
    try {
        for (var i = 0; i < allChanges.length; i++) {
            var deviceCode = allChanges[i];
            var changes = deviceConfigChanges[deviceCode];
            await fetchJson('/api/strategies/device-configs/' + deviceCode, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(changes)
            });
        }
        for (var j = 0; j < allChanges.length; j++) {
            delete deviceConfigChanges[allChanges[j]];
        }
        showToast('所有配置已保存');
        await loadDeviceConfigs();
    } catch (error) {
        console.error('保存所有配置失败:', error);
        showToast('保存失败: ' + error.message, 'error');
    }
}

// ============ 模式保存 ============
async function saveMode() {
    var mode = document.getElementById('requested-mode').value;
    try {
        var data = await fetchJson('/api/strategies/mode', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requested_mode: mode })
        });
        document.getElementById('effective-mode-display').textContent = data.effective_mode || mode;
        document.getElementById('header-mode').textContent = data.effective_mode || mode;
        showToast('模式已保存: ' + mode);
    } catch (error) {
        showToast('保存失败', 'error');
    }
}

function saveBatteryConfig() {
    var data = {
        soc_min: parseFloat(document.getElementById('batt-soc-min').value),
        soc_max: parseFloat(document.getElementById('batt-soc-max').value),
        charge_power_kw: parseFloat(document.getElementById('batt-charge-power').value),
        discharge_power_kw: parseFloat(document.getElementById('batt-discharge-power').value),
        backup_soc_target: parseFloat(document.getElementById('batt-backup-soc').value)
    };
    fetch('/api/strategies/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config_name: 'default', 'soc_min': data.soc_min, 'soc_max': data.soc_max, 'charge_power_kw': data.charge_power_kw, 'discharge_power_kw': data.discharge_power_kw, 'backup_soc_target': data.backup_soc_target })
    })
    .then(function() { showToast('Battery 配置已保存'); })
    .catch(function() { showToast('保存失败', 'error'); });
}

function saveGridConfig() {
    var data = {
        max_import_power_kw: parseFloat(document.getElementById('grid-max-import').value),
        allow_export: document.getElementById('grid-allow-export').checked,
        max_export_power_kw: parseFloat(document.getElementById('grid-max-export').value)
    };
    fetch('/api/strategies/grid-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(function() { showToast('Grid 配置已保存'); })
    .catch(function() { showToast('保存失败', 'error'); });
}

function savePriceConfig() {
    var data = {
        valley_price: parseFloat(document.getElementById('price-valley').value),
        flat_price: parseFloat(document.getElementById('price-flat').value),
        peak_price: parseFloat(document.getElementById('price-peak').value)
    };
    fetch('/api/strategies/price-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(function() { showToast('电价配置已保存'); })
    .catch(function() { showToast('保存失败', 'error'); });
}

// ============ 策略运行 ============
async function runStrategy() {
    var btn = event ? event.target : null;
    if (btn) {
        btn.disabled = true;
        btn.textContent = '运行中...';
    }
    try {
        var data = await fetchJson('/api/strategies/run', { method: 'POST' });
        document.getElementById('result-storage-target').textContent = (data.decision ? data.decision.storage_power_target : 0) + ' kW';
        document.getElementById('result-message').textContent = (data.decision ? data.decision.message : data.message) || '无消息';
        document.getElementById('result-last-run').textContent = new Date().toLocaleString();
        if (data.decision && data.decision.source) {
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
        if (btn) {
            btn.disabled = false;
            btn.textContent = '▶️ 运行一次策略';
        }
    }
}

async function refreshResult() {
    try {
        var data = await fetchJson('/api/strategies/runtime');
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

// ============ 预测曲线 ============
var loadChart = null;
var pvChart = null;

async function fetchForecast() {
    try {
        var loadData = await fetchJson('/api/strategies/forecast/load');
        var pvData = await fetchJson('/api/strategies/forecast/pv');
        var labels = loadData.points.map(function(p) {
            var dt = new Date(p.timestamp);
            return dt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        });
        var loadValues = loadData.points.map(function(p) { return p.value_kw; });
        var pvValues = pvData.points.map(function(p) { return p.value_kw; });
        updateChart('loadForecastChart', '负荷预测 (kW)', labels, loadValues, loadChart, '#4f8cf7');
        updateChart('pvForecastChart', 'PV 预测 (kW)', labels, pvValues, pvChart, '#f59e0b');
        document.getElementById('forecastTime').textContent = '更新于: ' + new Date().toLocaleString();
    } catch (error) {
        console.error('获取预测失败:', error);
        document.getElementById('forecastTime').textContent = '加载失败';
    }
}

function updateChart(canvasId, label, labels, values, chartInstance, color) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    if (chartInstance) {
        chartInstance.destroy();
    }
    var newChart = new Chart(ctx, {
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

var schedulePowerChart = null;
var scheduleSocChart = null;

async function fetchSchedule() {
    try {
        var data = await fetchJson('/api/strategies/schedule');
        if (data.schedule && data.schedule.length > 0) {
            var labels = data.schedule.map(function(item) {
                var dt = new Date(item.timestamp);
                return dt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            });
            var powerValues = data.schedule.map(function(item) { return item.power; });
            var socValues = data.schedule.map(function(item) { return item.soc; });
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
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    if (chartInstance) {
        chartInstance.destroy();
    }
    var newChart = new Chart(ctx, {
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
    var actionEl = document.getElementById('preview-action');
    actionEl.textContent = result.action;
    actionEl.className = 'action-tag ' + result.action;
    document.getElementById('preview-power').textContent = result.storage_power_target;
    document.getElementById('preview-message').textContent = result.message;
    document.getElementById('preview-time').textContent = new Date(result.created_at).toLocaleString();
    document.getElementById('preview-result').style.display = 'block';
}

async function previewDecision() {
    try {
        var data = getPreviewData();
        var result = await fetchJson('/api/strategies/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
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

    var form = document.getElementById('preview-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            previewDecision();
        });
    }
});
