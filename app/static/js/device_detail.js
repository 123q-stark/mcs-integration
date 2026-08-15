// ==================== 设备详情页 ====================

const API_BASE = '/api/devices';
const STRATEGY_API_BASE = '/api/strategies';

const pathParts = window.location.pathname.split('/');
const deviceId = pathParts[pathParts.length - 1];

let chartInstance = null;
let currentDeviceType = null;  // A-P1-04: 存储当前设备类型

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN');
}

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.style.display = 'block';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}

async function loadDeviceDetail() {
    try {
        const response = await fetch(`${API_BASE}/${deviceId}`);
        if (!response.ok) {
            if (response.status === 404) {
                document.getElementById('detailDeviceName').textContent = '设备不存在';
                document.getElementById('realtimeGrid').innerHTML = `
                    <div style="grid-column:1/-1;text-align:center;color:#8c9aab;padding:40px 0;">
                        ❌ 设备 ID ${deviceId} 不存在
                    </div>
                `;
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }
        const device = await response.json();
        // A-P1-04: 保存设备类型供历史图表使用
        currentDeviceType = device.device_type;
        renderDeviceDetail(device);
        loadDeviceStatus(deviceId);
        loadDeviceHistory(deviceId);
        // A-P1-03: 所有设备类型都加载策略参数
        loadStrategyParams(device);
    } catch (error) {
        console.error('加载设备详情失败:', error);
        document.getElementById('realtimeGrid').innerHTML = `
            <div style="grid-column:1/-1;text-align:center;color:#ef4444;padding:40px 0;">
                ❌ 加载失败: ${error.message}
            </div>
        `;
    }
}

function renderDeviceDetail(device) {
    document.getElementById('detailDeviceName').textContent = device.device_name || '设备详情';
    document.getElementById('detailDeviceCode').textContent = `编码: ${device.device_code || '--'}`;
    document.getElementById('detailDeviceType').textContent = device.device_type || '--';

    const statusEl = document.getElementById('detailOnlineStatus');
    if (device.is_online) {
        statusEl.textContent = '🟢 在线';
        statusEl.className = 'status-badge online';
    } else {
        statusEl.textContent = '🔴 离线';
        statusEl.className = 'status-badge offline';
    }

    const controlSection = document.getElementById('controlSection');
    if (device.device_type === 'charger') {
        controlSection.style.display = 'flex';
    } else {
        controlSection.style.display = 'none';
    }

    // A-P1-03: 所有设备类型都显示策略参数区域
    document.getElementById('strategyParams').style.display = 'block';
}

async function loadDeviceStatus(deviceId) {
    try {
        const response = await fetch(`${API_BASE}/${deviceId}/status`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const status = await response.json();
        renderDeviceStatus(status);
    } catch (error) {
        console.error('获取设备状态失败:', error);
    }
}

function renderDeviceStatus(status) {
    const grid = document.getElementById('realtimeGrid');
    const items = [
        { label: '当前功率', value: `${status.power_kw?.toFixed(2) || '--'} kW` },
        { label: '在线状态', value: status.is_online ? '在线' : '离线' },
        { label: '更新时间', value: formatDate(status.updated_at) },
    ];

    if (status.device_type === 'pv') {
        items.push(
            { label: '电压', value: status.voltage_v ? `${status.voltage_v.toFixed(1)} V` : '--' },
            { label: '电流', value: status.current_a ? `${status.current_a.toFixed(1)} A` : '--' },
            { label: '温度', value: status.temperature_c ? `${status.temperature_c.toFixed(1)} °C` : '--' },
            { label: '日发电量', value: status.energy_kwh ? `${status.energy_kwh.toFixed(1)} kWh` : '--' }
        );
    } else if (status.device_type === 'battery' || status.device_type === 'storage') {
        items.push(
            { label: 'SOC', value: status.storage_soc !== null ? `${status.storage_soc.toFixed(1)} %` : '--' },
            { label: '温度', value: status.temperature_c ? `${status.temperature_c.toFixed(1)} °C` : '--' },
            { label: '容量', value: status.energy_kwh ? `${status.energy_kwh.toFixed(0)} kWh` : '--' }
        );
    } else if (status.device_type === 'charger') {
        items.push(
            { label: '充电状态', value: status.status || '--' },
            { label: '电压', value: status.voltage_v ? `${status.voltage_v.toFixed(1)} V` : '--' },
            { label: '电流', value: status.current_a ? `${status.current_a.toFixed(1)} A` : '--' },
            { label: '会话电量', value: status.energy_kwh ? `${status.energy_kwh.toFixed(1)} kWh` : '--' }
        );
    } else if (status.device_type === 'grid') {
        items.push(
            { label: '电压', value: status.voltage_v ? `${status.voltage_v.toFixed(1)} V` : '--' },
            { label: '电流', value: status.current_a ? `${status.current_a.toFixed(1)} A` : '--' },
            { label: '频率', value: '50.0 Hz' }
        );
    }

    grid.innerHTML = items.map(item => `
        <div class="realtime-item">
            <span class="label">${item.label}</span>
            <span class="value">${item.value}</span>
        </div>
    `).join('');

    const ctrlStatus = document.getElementById('ctrlStatus');
    if (status.device_type === 'charger') {
        ctrlStatus.textContent = `当前状态: ${status.status || 'idle'}`;
    }
}

// ==================== A-P1-03: 根据设备类型加载对应的策略参数 ====================

async function loadStrategyParams(device) {
    const grid = document.getElementById('strategyParamGrid');
    const deviceCode = device.device_code;
    const deviceType = device.device_type;

    try {
        let params = [];

        if (deviceType === 'pv') {
            // PV: 获取设备策略配置（是否参与策略）
            const response = await fetch(`${STRATEGY_API_BASE}/device-configs`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const configs = await response.json();
            const config = configs.find(c => c.device_code === deviceCode);
            params = [
                { label: '参与策略', value: config ? (config.participate_in_strategy ? '✅ 是' : '❌ 否') : '--' }
            ];
        } else if (deviceType === 'charger') {
            // Charger: 获取设备策略配置
            const response = await fetch(`${STRATEGY_API_BASE}/device-configs`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const configs = await response.json();
            const config = configs.find(c => c.device_code === deviceCode);
            params = [
                { label: '参与策略', value: config ? (config.participate_in_strategy ? '✅ 是' : '❌ 否') : '--' },
                { label: '允许策略控制', value: config ? (config.allow_strategy_control ? '✅ 是' : '❌ 否') : '--' },
                { label: '策略功率上限', value: config?.strategy_power_limit_kw ? `${config.strategy_power_limit_kw} kW` : '--' },
                { label: '优先级', value: config?.priority || '--' }
            ];
        } else if (deviceType === 'battery' || deviceType === 'storage') {
            // Battery: 获取全局策略配置
            const response = await fetch(`${STRATEGY_API_BASE}/config`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const config = await response.json();
            params = [
                { label: 'SOC 下限', value: config.soc_min !== undefined ? `${config.soc_min}%` : '--' },
                { label: 'SOC 上限', value: config.soc_max !== undefined ? `${config.soc_max}%` : '--' },
                { label: '充电功率上限', value: config.charge_power_kw !== undefined ? `${config.charge_power_kw} kW` : '--' },
                { label: '放电功率上限', value: config.discharge_power_kw !== undefined ? `${config.discharge_power_kw} kW` : '--' }
            ];
        } else if (deviceType === 'grid') {
            // Grid: 获取电网策略配置
            const response = await fetch(`${STRATEGY_API_BASE}/grid-config`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const config = await response.json();
            params = [
                { label: '最大购电功率', value: config.max_import_power_kw !== undefined ? `${config.max_import_power_kw} kW` : '--' },
                { label: '是否允许上网', value: config.allow_export !== undefined ? (config.allow_export ? '✅ 是' : '❌ 否') : '--' },
                { label: '最大上网功率', value: config.max_export_power_kw !== undefined ? `${config.max_export_power_kw} kW` : '--' }
            ];
        } else {
            // 未知类型
            params = [{ label: '策略配置', value: '--' }];
        }

        // 渲染
        grid.innerHTML = params.map(p => `
            <div class="param-item">
                <span class="plabel">${p.label}</span>
                <span class="pvalue">${p.value}</span>
            </div>
        `).join('');

    } catch (error) {
        console.warn('获取策略参数失败:', error);
        grid.innerHTML = `<div class="param-item"><span class="plabel">加载失败</span><span class="pvalue">--</span></div>`;
    }
}

async function controlCharger(command) {
    const startBtn = document.getElementById('ctrlStartBtn');
    const stopBtn = document.getElementById('ctrlStopBtn');
    startBtn.disabled = true;
    stopBtn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/${deviceId}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: command })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || `HTTP ${response.status}`);
        }
        const result = await response.json();
        showToast(result.message || `命令 ${command} 执行成功`, 'success');
        await loadDeviceStatus(deviceId);
    } catch (error) {
        showToast(`控制失败: ${error.message}`, 'error');
    } finally {
        startBtn.disabled = false;
        stopBtn.disabled = false;
    }
}

async function loadDeviceHistory(deviceId) {
    try {
        const response = await fetch(`${API_BASE}/${deviceId}/history?hours=24`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        // A-P1-04: 传入设备类型用于判断是否显示 SOC
        renderHistory(data, currentDeviceType);
    } catch (error) {
        console.error('获取历史数据失败:', error);
        document.getElementById('historyNoData').style.display = 'block';
        document.getElementById('historyNoData').textContent = '加载历史数据失败';
    }
}

// ==================== A-P1-04: Battery 同时画 SOC 与功率 ====================

function renderHistory(data, deviceType) {
    const canvas = document.getElementById('historyChart');
    const noData = document.getElementById('historyNoData');

    if (!data.data || data.data.length === 0) {
        canvas.style.display = 'none';
        noData.style.display = 'block';
        noData.textContent = '暂无历史数据';
        return;
    }

    canvas.style.display = 'block';
    noData.style.display = 'none';

    const labels = data.data.map(d => {
        const date = new Date(d.time);
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    });
    const powers = data.data.map(d => d.power_kw);

    if (chartInstance) {
        chartInstance.destroy();
    }

    const ctx = canvas.getContext('2d');
    const isBattery = (deviceType === 'battery' || deviceType === 'storage');

    if (isBattery) {
        // A-P1-04: Battery 设备同时显示功率和 SOC（双 Y 轴）
        const socs = data.data.map(d => d.storage_soc);

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: '功率 (kW)',
                        data: powers,
                        borderColor: '#4f8cf7',
                        backgroundColor: 'rgba(79, 140, 247, 0.08)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 1.5,
                        borderWidth: 2,
                        yAxisID: 'y'
                    },
                    {
                        label: 'SOC (%)',
                        data: socs,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.08)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 1.5,
                        borderWidth: 2,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        labels: { boxWidth: 12, padding: 8, font: { size: 11 } }
                    }
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.04)' },
                        ticks: { font: { size: 10 } },
                        title: {
                            display: true,
                            text: '功率 (kW)',
                            font: { size: 10 }
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        beginAtZero: true,
                        max: 100,
                        grid: { drawOnChartArea: false },
                        ticks: { font: { size: 10 } },
                        title: {
                            display: true,
                            text: 'SOC (%)',
                            font: { size: 10 }
                        }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { font: { size: 9 }, maxTicksLimit: 12 }
                    }
                },
                interaction: { intersect: false, mode: 'index' }
            }
        });
    } else {
        // 非 Battery 设备：只显示功率
        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: '功率 (kW)',
                    data: powers,
                    borderColor: '#4f8cf7',
                    backgroundColor: 'rgba(79, 140, 247, 0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 1.5,
                    borderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, labels: { boxWidth: 12, padding: 8, font: { size: 11 } } }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 120,
                        grid: { color: 'rgba(0,0,0,0.04)' },
                        ticks: { font: { size: 10 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { font: { size: 9 }, maxTicksLimit: 12 }
                    }
                },
                interaction: { intersect: false, mode: 'index' }
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', function() {
    loadDeviceDetail();

    document.getElementById('ctrlStartBtn').addEventListener('click', function() {
        controlCharger('start');
    });
    document.getElementById('ctrlStopBtn').addEventListener('click', function() {
        controlCharger('stop');
    });
});