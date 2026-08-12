// ==================== 设备详情页 ====================

const API_BASE = '/api/devices';
const STRATEGY_API_BASE = '/api/strategies';

const pathParts = window.location.pathname.split('/');
const deviceId = pathParts[pathParts.length - 1];

let chartInstance = null;

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
        renderDeviceDetail(device);
        loadDeviceStatus(deviceId);
        loadDeviceHistory(deviceId);
        if (device.device_type === 'charger') {
            loadStrategyParams(device.device_code);
        }
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

    const strategyParams = document.getElementById('strategyParams');
    if (device.device_type === 'charger') {
        strategyParams.style.display = 'block';
    } else {
        strategyParams.style.display = 'none';
    }
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

async function loadStrategyParams(deviceCode) {
    try {
        const response = await fetch(`${STRATEGY_API_BASE}/device-configs`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const configs = await response.json();
        const config = configs.find(c => c.device_code === deviceCode);
        if (config) {
            document.getElementById('spParticipate').textContent = config.participate_in_strategy ? '是' : '否';
            document.getElementById('spAllowControl').textContent = config.allow_strategy_control ? '是' : '否';
            document.getElementById('spPowerLimit').textContent = config.strategy_power_limit_kw ? `${config.strategy_power_limit_kw} kW` : '--';
            document.getElementById('spPriority').textContent = config.priority || '--';
        }
    } catch (error) {
        console.warn('获取策略参数失败:', error);
        document.getElementById('spParticipate').textContent = '--';
        document.getElementById('spAllowControl').textContent = '--';
        document.getElementById('spPowerLimit').textContent = '--';
        document.getElementById('spPriority').textContent = '--';
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
        renderHistory(data);
    } catch (error) {
        console.error('获取历史数据失败:', error);
        document.getElementById('historyNoData').style.display = 'block';
        document.getElementById('historyNoData').textContent = '加载历史数据失败';
    }
}

function renderHistory(data) {
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

document.addEventListener('DOMContentLoaded', function() {
    loadDeviceDetail();

    document.getElementById('ctrlStartBtn').addEventListener('click', function() {
        controlCharger('start');
    });
    document.getElementById('ctrlStopBtn').addEventListener('click', function() {
        controlCharger('stop');
    });
});