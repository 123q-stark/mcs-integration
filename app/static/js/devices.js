// ==================== 设备管理页面 JavaScript ====================

const API_BASE = '/api/devices';
const REFRESH_INTERVAL = 5000; // 5秒自动刷新
let currentDeviceId = null;

// DOM 元素
const deviceListEl = document.getElementById('deviceList');
const deviceCountEl = document.getElementById('deviceCount');
const onlineCountEl = document.getElementById('onlineCount');
const offlineCountEl = document.getElementById('offlineCount');
const statusPanel = document.getElementById('statusPanel');
const statusDeviceName = document.getElementById('statusDeviceName');
const statusDeviceType = document.getElementById('statusDeviceType');
const statusDeviceCode = document.getElementById('statusDeviceCode');
const statusOnline = document.getElementById('statusOnline');
const statusPower = document.getElementById('statusPower');
const statusSoc = document.getElementById('statusSoc');
const statusSocRow = document.getElementById('statusSocRow');
const statusUpdatedAt = document.getElementById('statusUpdatedAt');
const closeStatusBtn = document.getElementById('closeStatusBtn');
const refreshButton = document.getElementById('refreshButton');

// ==================== 工具函数 ====================

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

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN');
}

// 获取设备图标
function getDeviceIcon(deviceType) {
    const icons = {
        'pv': '☀️',
        'storage': '🔋',
        'charger': '⚡'
    };
    return icons[deviceType] || '🔌';
}

// ==================== 设备列表渲染 ====================

function renderDevices(devices) {
    if (!devices || devices.length === 0) {
        deviceListEl.innerHTML = `<p class="empty-text">暂无设备数据</p>`;
        deviceCountEl.textContent = '0';
        onlineCountEl.textContent = '0';
        offlineCountEl.textContent = '0';
        return;
    }

    const online = devices.filter(d => d.is_online).length;
    const offline = devices.length - online;

    deviceCountEl.textContent = devices.length;
    onlineCountEl.textContent = online;
    offlineCountEl.textContent = offline;

    let html = '';
    devices.forEach(device => {
        const isOnline = device.is_online;
        const statusText = isOnline ? '在线' : '离线';
        const statusClass = isOnline ? '' : 'offline';
        const ratedPower = device.rated_power_kw !== null ? `${device.rated_power_kw} kW` : '--';
        const icon = getDeviceIcon(device.device_type);

        html += `
            <div class="device-card" data-device-id="${device.id}">
                <div class="card-top">
                    <span class="device-icon">${icon}</span>
                    <span class="status-tag ${statusClass}">● ${statusText}</span>
                </div>
                <div class="device-title">
                    <span class="device-name">${device.device_name}</span>
                    <span class="device-code">${device.device_code}</span>
                </div>
                <span class="type-tag">${device.device_type}</span>
                <div class="detail-row">
                    <span class="label">额定功率</span>
                    <span class="value">${ratedPower}</span>
                </div>
                <div class="detail-row">
                    <span class="label">最后更新</span>
                    <span class="value">${formatDate(device.updated_at)}</span>
                </div>
                <div style="display:flex; gap:8px; margin-top:14px;">
                    <button class="status-btn" data-device-id="${device.id}" style="flex:1; margin:0;">📊 查看状态</button>
                   <a href="/devices/${device.id}" class="detail-btn" style="flex:1; text-align:center; padding:10px 0; background:#4f8cf7; border-radius:8px; color:white; text-decoration:none; font-weight:600; font-size:14px; display:inline-block; border:none; cursor:pointer;">🔍 查看详情</a>
                </div>
            </div>
        `;
    });
    deviceListEl.innerHTML = html;

    document.querySelectorAll('.status-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const id = this.dataset.deviceId;
            fetchDeviceStatus(id);
        });
    });
}
// ==================== API 调用 ====================

async function fetchDevices() {
    try {
        const response = await fetch(API_BASE);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        renderDevices(data);
    } catch (error) {
        console.error('获取设备列表失败:', error);
        deviceListEl.innerHTML = `<p class="empty-text">加载失败: ${error.message}</p>`;
        deviceCountEl.textContent = '0';
        onlineCountEl.textContent = '0';
        offlineCountEl.textContent = '0';
        showToast('获取设备列表失败，请刷新重试', 'error');
    }
}

async function fetchDeviceStatus(deviceId) {
    try {
        const response = await fetch(`${API_BASE}/${deviceId}/status`);
        if (!response.ok) {
            if (response.status === 404) {
                showToast('设备不存在', 'error');
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        showDeviceStatus(data);
    } catch (error) {
        console.error('获取设备状态失败:', error);
        showToast('获取设备状态失败', 'error');
    }
}

// ==================== 状态面板渲染 ====================

function showDeviceStatus(status) {
    currentDeviceId = status.device_id;
    statusDeviceName.textContent = `📊 ${status.device_code} 状态`;
    statusDeviceType.textContent = status.device_type;
    statusDeviceCode.textContent = status.device_code;

    const isOnline = status.is_online;
    statusOnline.textContent = isOnline ? '🟢 在线' : '🔴 离线';
    statusOnline.style.color = isOnline ? '#2e7d32' : '#c62828';

    statusPower.innerHTML = `${status.power_kw.toFixed(2)} <span class="unit">kW</span>`;

    if (status.storage_soc !== null && status.storage_soc !== undefined) {
        statusSocRow.style.display = 'flex';
        statusSoc.innerHTML = `${status.storage_soc.toFixed(1)} <span class="unit">%</span>`;
    } else {
        statusSocRow.style.display = 'none';
    }

    statusUpdatedAt.textContent = formatDate(status.updated_at);
    statusPanel.style.display = 'block';
    statusPanel.scrollIntoView({ behavior: 'smooth' });
}

// ==================== 事件绑定 ====================

closeStatusBtn.addEventListener('click', function() {
    statusPanel.style.display = 'none';
});

refreshButton.addEventListener('click', function() {
    fetchDevices();
    showToast('刷新中...', 'info');
});

// ==================== 自动刷新 ====================

document.addEventListener('DOMContentLoaded', function() {
    fetchDevices();
    fetchSystemSummary();
    setInterval(fetchDevices, REFRESH_INTERVAL);
});

// ==================== A-09: 系统口摘要卡（PRICE + STRATEGY） ====================

async function fetchSystemSummary() {
    try {
        // 获取策略运行时状态
        const runtimeResp = await fetch('/api/strategies/runtime');
        if (runtimeResp.ok) {
            const runtime = await runtimeResp.json();
            document.getElementById('requestedMode').textContent = runtime.requested_mode || '--';
            document.getElementById('effectiveMode').textContent = `生效: ${runtime.effective_mode || '--'}`;
        }
    } catch (e) {
        console.warn('获取策略状态失败:', e);
    }

    try {
        // 获取当前电价配置
        const priceResp = await fetch('/api/strategies/price-config');
        if (priceResp.ok) {
            const price = await priceResp.json();
            const hour = new Date().getHours();
            let period = '平段';
            let priceVal = price.flat_price || 0.55;
            if (hour >= 0 && hour < 7) { period = '谷段'; priceVal = price.valley_price || 0.35; }
            else if (hour >= 7 && hour < 10) { period = '平段'; priceVal = price.flat_price || 0.55; }
            else if (hour >= 10 && hour < 15) { period = '峰段'; priceVal = price.peak_price || 0.85; }
            else if (hour >= 15 && hour < 18) { period = '平段'; priceVal = price.flat_price || 0.55; }
            else if (hour >= 18 && hour < 21) { period = '峰段'; priceVal = price.peak_price || 0.85; }
            else { period = '平段'; priceVal = price.flat_price || 0.55; }
            document.getElementById('currentPrice').textContent = priceVal.toFixed(2);
            document.getElementById('pricePeriod').textContent = period;
        }
    } catch (e) {
        console.warn('获取电价配置失败:', e);
    }
}