// ============================================================
// v1.5 策略页面 - 唯一 JavaScript 事实源
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

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

// ============ 设备配置暂存 ============
const deviceConfigChanges = {};

// ============ 加载所有配置 ============
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

        // 加载设备配置
        await loadDeviceConfigs();
    } catch (error) {
        console.error('加载配置失败:', error);
        showToast('加载配置失败', 'error');
    }
}

// ============ 加载设备配置（动态渲染表格） ============
async function loadDeviceConfigs() {
    try {
        const data = await fetchJson('/api/strategies/device-configs');
        
        // 渲染 PV 表格
        const pvConfigs = data.filter(c => c.device_code.startsWith('PV'));
        const pvTbody = document.getElementById('pv-config-table');
        if (pvTbody) {
            pvTbody.innerHTML = pvConfigs.map(c => `
                <tr>
                    <td><strong>${c.device_code}</strong></td>
                    <td><input type="checkbox" ${c.participate_in_strategy ? 'checked' : ''} 
                               onchange="updateDeviceConfig('${c.device_code}', 'participate_in_strategy', this.checked)"></td>
                    <td><input type="checkbox" ${c.allow_strategy_control ? 'checked' : ''} disabled></td>
                    <td><input type="number" value="${c.priority}" min="1" max="5" 
                               onchange="updateDeviceConfig('${c.device_code}', 'priority', parseInt(this.value))"></td>
                    <td><button class="btn btn-sm btn-primary" onclick="saveDeviceConfig('${c.device_code}')">💾 保存</button></td>
                </tr>
            `).join('');
        }

        // 渲染 Charger 表格
        const chargerConfigs = data.filter(c => c.device_code.startsWith('CHG'));
        const chargerTbody = document.getElementById('charger-config-table');
        if (chargerTbody) {
            chargerTbody.innerHTML = chargerConfigs.map(c => `
                <tr>
                    <td><strong>${c.device_code}</strong></td>
                    <td><input type="checkbox" ${c.participate_in_strategy ? 'checked' : ''} 
                               onchange="updateDeviceConfig('${c.device_code}', 'participate_in_strategy', this.checked)"></td>
                    <td><input type="checkbox" ${c.allow_strategy_control ? 'checked' : ''} 
                               onchange="updateDeviceConfig('${c.device_code}', 'allow_strategy_control', this.checked)"></td>
                    <td><input type="number" value="${c.strategy_power_limit_kw || 50}" min="0" max="200" 
                               onchange="updateDeviceConfig('${c.device_code}', 'strategy_power_limit_kw', parseFloat(this.value))"></td>
                    <td><input type="number" value="${c.priority}" min="1" max="5" 
                               onchange="updateDeviceConfig('${c.device_code}', 'priority', parseInt(this.value))"></td>
                    <td><button class="btn btn-sm btn-primary" onclick="saveDeviceConfig('${c.device_code}')">💾 保存</button></td>
                </tr>
            `).join('');
        }
    } catch (error) {
        console.error('加载设备配置失败:', error);
        showToast('加载设备配置失败', 'error');
    }
}

// ============ 暂存设备配置修改 ============
function updateDeviceConfig(deviceCode, field, value) {
    if (!deviceConfigChanges[deviceCode]) {
        deviceConfigChanges[deviceCode] = {};
    }
    deviceConfigChanges[deviceCode][field] = value;
}

// ============ 保存单个设备配置 ============
async function saveDeviceConfig(deviceCode) {
    const changes = deviceConfigChanges[deviceCode] || {};
    if (Object.keys(changes).length === 0) {
        showToast('没有需要保存的修改', 'warning');
        return;
    }
    
    const btn = event?.target;
    if (btn) { btn.disabled = true; btn.textContent = '保存中...'; }
    
    try {
        await fetchJson(`/api/strategies/device-configs/${deviceCode}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(changes)
        });
        
        delete deviceConfigChanges[deviceCode];
        showToast(`${deviceCode} 配置已保存`);
        await loadDeviceConfigs();
    } catch (error) {
        console.error('保存失败:', error);
        showToast('保存失败: ' + error.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '💾 保存'; }
    }
}

// ============ 保存所有设备配置 ============
async function saveAllDeviceConfigs() {
    const allChanges = Object.keys(deviceConfigChanges);
    if (allChanges.length === 0) {
        showToast('没有需要保存的修改', 'warning');
        return;
    }
    
    try {
        for (const deviceCode of allChanges) {
            const changes = deviceConfigChanges[deviceCode];
            await fetchJson(`/api/strategies/device-configs/${deviceCode}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(changes)
            });
        }
        // 清空暂存
        for (const key of allChanges) {
            delete deviceConfigChanges[key];
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
    const mode = document.getElementById('requested-mode').value;
    try {
        const data = await fetchJson('/api/strategies/mode', {
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

// ============ Battery 配置保存 ============
function saveBatteryConfig() {
    const data = {
        soc_min: parseFloat(document.getElementById('batt-soc-min').value),
        soc_max: parseFloat(document.getElementById('batt-soc-max').value),
        charge_power_kw: parseFloat(document.getElementById('batt-charge-power').value),
        discharge_power_kw: parseFloat(document.getElementById('batt-discharge-power').value),
        backup_soc_target: parseFloat(document.getElementById('batt-backup-soc').value)
    };
    fetch('/api/strategies/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config_name: 'default', ...data })
    })
    .then(res => res.json())
    .then(() => showToast('Battery 配置已保存'))
    .catch(() => showToast('保存失败', 'error'));
}

// ============ Grid 配置保存 ============
function saveGridConfig() {
    const data = {
        max_import_power_kw: parseFloat(document.getElementById('grid-max-import').value),
        allow_export: document.getElementById('grid-allow-export').checked,
        max_export_power_kw: parseFloat(document.getElementById('grid-max-export').value)
    };
    fetch('/api/strategies/grid-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => showToast('Grid 配置已保存'))
    .catch(() => showToast('保存失败', 'error'));
}

// ============ Price 配置保存 ============
function savePriceConfig() {
    const data = {
        valley_price: parseFloat(document.getElementById('price-valley').value),
        flat_price: parseFloat(document.getElementById('price-flat').value),
        peak_price: parseFloat(document.getElementById('price-peak').value)
    };
    fetch('/api/strategies/price-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => showToast('电价配置已保存'))
    .catch(() => showToast('保存失败', 'error'));
}

// ============ 运行策略 ============
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

// ============ 刷新结果 ============
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

// ============ 预览决策 ============
document.getElementById('preview-form')?.addEventListener('submit', function(e) {
    e.preventDefault();
    const data = {
        pv_power: parseFloat(document.getElementById('pv-power').value),
        load_power: parseFloat(document.getElementById('load-power').value),
        storage_power: parseFloat(document.getElementById('storage-power').value),
        storage_soc: parseFloat(document.getElementById('storage-soc').value)
    };
    fetch('/api/strategies/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(result => {
        const actionEl = document.getElementById('preview-action');
        actionEl.textContent = result.action;
        actionEl.className = 'action-tag ' + result.action;
        document.getElementById('preview-power').textContent = result.storage_power_target;
        document.getElementById('preview-message').textContent = result.message;
        document.getElementById('preview-time').textContent = new Date(result.created_at).toLocaleString();
        document.getElementById('preview-result').style.display = 'block';
    })
    .catch(() => {
        document.getElementById('preview-result').style.display = 'block';
        document.getElementById('preview-message').textContent = '预览失败，请检查输入';
    });
});

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
    if (chartInstance) chartInstance.destroy();
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
    if (canvasId === 'loadForecastChart') loadChart = newChart;
    else if (canvasId === 'pvForecastChart') pvChart = newChart;
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
    if (chartInstance) chartInstance.destroy();
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
    if (canvasId === 'schedulePowerChart') schedulePowerChart = newChart;
    else if (canvasId === 'scheduleSocChart') scheduleSocChart = newChart;
}

// ============ 页面初始化 ============
document.addEventListener('DOMContentLoaded', function() {
    loadDefaultConfigs();
    setTimeout(fetchForecast, 300);
    setTimeout(fetchSchedule, 600);
});
