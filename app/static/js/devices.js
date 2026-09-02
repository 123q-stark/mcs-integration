// ==================== 设备管理页面 JavaScript ====================

const API_BASE = '/api/devices';
const REFRESH_INTERVAL = 5000;
let currentDevices = [];

const deviceListEl = document.getElementById('deviceList');
const deviceCountEl = document.getElementById('deviceCount');
const onlineCountEl = document.getElementById('onlineCount');
const offlineCountEl = document.getElementById('offlineCount');
const refreshButton = document.getElementById('refreshButton');

// ==================== 模式名称映射 ====================

const MODE_DISPLAY = {
    'AUTO': '自动模式',
    'PV_PRIORITY': '光伏优先',
    'ECONOMIC_SCHEDULE': '经济调度',
    'GRID_BACKUP': '电网备用',
    'SAFE': '安全模式'
};

function getModeDisplay(mode) {
    return MODE_DISPLAY[mode] || mode || '--';
}

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

function getDeviceIcon(deviceType) {
    const icons = {
        'pv': '☀️',
        'battery': '🔋',
        'storage': '🔋',
        'charger': '⚡',
        'grid': '🔌'
    };
    return icons[deviceType] || '🔌';
}

// ==================== 设备列表渲染 ====================

function renderDevices(devices, realtimeStatusMap) {
    if (!devices || devices.length === 0) {
        deviceListEl.innerHTML = `<p class="empty-text">暂无设备数据</p>`;
        deviceCountEl.textContent = '0';
        onlineCountEl.textContent = '0';
        offlineCountEl.textContent = '0';
        return;
    }

    let onlineCount = 0;
    let offlineCount = 0;

    devices.forEach(device => {
        const realtime = realtimeStatusMap ? realtimeStatusMap[device.device_code] : null;
        const isOnline = realtime ? realtime.is_online : device.is_online;
        if (isOnline) onlineCount++;
        else offlineCount++;
    });

    deviceCountEl.textContent = devices.length;
    onlineCountEl.textContent = onlineCount;
    offlineCountEl.textContent = offlineCount;

    let html = '';
    devices.forEach(device => {
        const realtime = realtimeStatusMap ? realtimeStatusMap[device.device_code] : null;
        const isOnline = realtime ? realtime.is_online : device.is_online;
        const quality = realtime ? realtime.quality : 'good';
        const powerKw = realtime ? realtime.power_kw : 0;
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
                    <span class="label">实时功率</span>
                    <span class="value">${powerKw.toFixed(2)} kW</span>
                </div>
                <div class="detail-row">
                    <span class="label">额定功率</span>
                    <span class="value">${ratedPower}</span>
                </div>
                <div class="detail-row">
                    <span class="label">质量状态</span>
                    <span class="value">${quality}</span>
                </div>
                <a href="/devices/${device.id}" class="detail-btn">🔍 查看详情</a>
            </div>
        `;
    });
    deviceListEl.innerHTML = html;
}

// ==================== 获取实时状态映射 ====================

async function fetchRealtimeStatusMap() {
    try {
        const response = await fetch(`${API_BASE}/runtime/system-state`, {
            cache: 'no-store'
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const state = await response.json();
        const map = {};

        if (state.pv_units) {
            state.pv_units.forEach(dev => {
                map[dev.device_code] = {
                    is_online: dev.is_online,
                    quality: dev.quality,
                    power_kw: dev.power_kw,
                    timestamp: dev.timestamp
                };
            });
        }
        if (state.chargers) {
            state.chargers.forEach(dev => {
                map[dev.device_code] = {
                    is_online: dev.is_online,
                    quality: dev.quality,
                    power_kw: dev.power_kw,
                    timestamp: dev.timestamp
                };
            });
        }
        if (state.battery) {
            map[state.battery.device_code] = {
                is_online: state.battery.is_online,
                quality: state.battery.quality,
                power_kw: state.battery.power_kw,
                timestamp: state.battery.timestamp
            };
        }
        if (state.grid) {
            map[state.grid.device_code] = {
                is_online: state.grid.is_online,
                quality: state.grid.quality,
                power_kw: state.grid.power_kw,
                timestamp: state.grid.timestamp
            };
        }
        return map;
    } catch (error) {
        console.warn('获取实时状态映射失败:', error);
        return null;
    }
}

// ==================== 加载设备列表 ====================

async function fetchDevices() {
    try {
        const response = await fetch(API_BASE, {
            cache: 'no-store'
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const devices = await response.json();
        currentDevices = devices;

        const realtimeMap = await fetchRealtimeStatusMap();
        renderDevices(devices, realtimeMap);
    } catch (error) {
        console.error('获取设备列表失败:', error);
        deviceListEl.innerHTML = `<p class="empty-text">加载失败: ${error.message}</p>`;
        deviceCountEl.textContent = '0';
        onlineCountEl.textContent = '0';
        offlineCountEl.textContent = '0';
        showToast('获取设备列表失败，请刷新重试', 'error');
    }
}

// ==================== 系统口摘要卡 ====================

async function fetchSystemSummary() {
    try {
        const runtimeResp = await fetch('/api/strategies/runtime');
        if (runtimeResp.ok) {
            const runtime = await runtimeResp.json();
            // ✅ 修改：使用中文显示模式名称
            document.getElementById('requestedMode').textContent = getModeDisplay(runtime.requested_mode);
            document.getElementById('effectiveMode').textContent = `生效: ${getModeDisplay(runtime.effective_mode)}`;
        }
    } catch (e) {
        console.warn('获取策略状态失败:', e);
    }

    try {
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

// ==================== 事件绑定 ====================

refreshButton.addEventListener('click', function() {
    fetchDevices();
    fetchSystemSummary();
    showToast('刷新中...', 'info');
});

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', function() {
    fetchDevices();
    fetchSystemSummary();
    setInterval(fetchDevices, REFRESH_INTERVAL);
});