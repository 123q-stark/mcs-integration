// app/static/js/strategy.js
/**
 * 策略配置页面交互逻辑
 */

// ============ 工具函数 ============

function getApiBase() {
    return '/api/strategies';
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast ' + type + ' show';
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    });
    return response;
}

// ============ 配置管理 ============

async function loadCurrentConfig() {
    const statusEl = document.getElementById('config-status');
    try {
        const response = await fetchJson(`${getApiBase()}/config`);
        if (!response.ok) {
            if (response.status === 404) {
                statusEl.textContent = '⚠️ 未找到配置，请创建默认配置';
                return null;
            }
            throw new Error(`HTTP ${response.status}`);
        }
        const config = await response.json();
        statusEl.innerHTML = `✅ 当前配置：<span class="active">${config.config_name}</span> (ID: ${config.id})`;
        return config;
    } catch (error) {
        console.error('加载配置失败:', error);
        statusEl.textContent = '❌ 加载配置失败';
        return null;
    }
}

async function saveConfig(configData) {
    const btn = document.getElementById('save-btn');
    btn.disabled = true;
    btn.textContent = '保存中...';

    try {
        const response = await fetchJson(`${getApiBase()}/config`, {
            method: 'PUT',
            body: JSON.stringify(configData),
        });

        if (!response.ok) {
            let errorMsg = `保存失败 (HTTP ${response.status})`;
            try {
                const err = await response.json();
                if (err.detail) errorMsg = err.detail;
            } catch (e) {}
            throw new Error(errorMsg);
        }

        const result = await response.json();
        showToast(`✅ 配置 "${result.config_name}" 保存成功！`, 'success');
        await loadCurrentConfig();
        fillFormData(result);
        return result;
    } catch (error) {
        showToast('❌ ' + error.message, 'error');
        console.error('保存配置失败:', error);
        throw error;
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 保存配置';
    }
}

function fillFormData(config) {
    document.getElementById('config-name').value = config.config_name || '';
    document.getElementById('soc-min').value = config.soc_min || '';
    document.getElementById('soc-max').value = config.soc_max || '';
    document.getElementById('charge-power').value = config.charge_power_kw || '';
    document.getElementById('discharge-power').value = config.discharge_power_kw || '';
}

function getFormData() {
    return {
        config_name: document.getElementById('config-name').value.trim(),
        soc_min: parseFloat(document.getElementById('soc-min').value),
        soc_max: parseFloat(document.getElementById('soc-max').value),
        charge_power_kw: parseFloat(document.getElementById('charge-power').value),
        discharge_power_kw: parseFloat(document.getElementById('discharge-power').value),
    };
}

// ============ 预览功能 ============

async function previewDecision(previewData) {
    const btn = document.getElementById('preview-btn');
    btn.disabled = true;
    btn.textContent = '预览中...';

    const resultDiv = document.getElementById('preview-result');
    resultDiv.style.display = 'none';

    try {
        const response = await fetchJson(`${getApiBase()}/preview`, {
            method: 'POST',
            body: JSON.stringify(previewData),
        });

        if (!response.ok) {
            let errorMsg = `预览失败 (HTTP ${response.status})`;
            try {
                const err = await response.json();
                if (err.detail) errorMsg = err.detail;
            } catch (e) {}
            throw new Error(errorMsg);
        }

        const result = await response.json();
        displayPreviewResult(result);
        showToast('✅ 预览完成', 'success');
        return result;
    } catch (error) {
        showToast('❌ ' + error.message, 'error');
        console.error('预览失败:', error);
        throw error;
    } finally {
        btn.disabled = false;
        btn.textContent = '▶️ 预览决策';
    }
}

function displayPreviewResult(result) {
    const resultDiv = document.getElementById('preview-result');
    const actionEl = document.getElementById('preview-action');
    const powerEl = document.getElementById('preview-power');
    const messageEl = document.getElementById('preview-message');
    const timeEl = document.getElementById('preview-time');

    // 动作标签样式
    const actionMap = {
        'charge': { label: '🔋 充电', class: 'charge' },
        'discharge': { label: '⚡ 放电', class: 'discharge' },
        'idle': { label: '⏸️ 待机', class: 'idle' },
    };
    const info = actionMap[result.action] || { label: result.action, class: '' };
    actionEl.textContent = info.label;
    actionEl.className = 'action-tag ' + info.class;

    const powerValue = result.storage_power_target;
    const powerDisplay = powerValue < 0 ? `${powerValue} (充电)` : (powerValue > 0 ? `${powerValue} (放电)` : '0 (待机)');
    powerEl.textContent = powerDisplay;

    messageEl.textContent = result.message || '无说明';
    timeEl.textContent = new Date(result.created_at).toLocaleString();

    resultDiv.style.display = 'block';
}

function getPreviewData() {
    return {
        pv_power: parseFloat(document.getElementById('pv-power').value) || 0,
        load_power: parseFloat(document.getElementById('load-power').value) || 0,
        storage_power: parseFloat(document.getElementById('storage-power').value) || 0,
        storage_soc: parseFloat(document.getElementById('storage-soc').value) || 50,
    };
}

// ============ 页面初始化 ============

document.addEventListener('DOMContentLoaded', async function() {
    // 加载当前配置
    const config = await loadCurrentConfig();
    if (config) {
        fillFormData(config);
    }

    // 保存配置
    document.getElementById('strategy-form').addEventListener('submit', async function(e) {
        e.preventDefault();
        try {
            const data = getFormData();
            // 基本校验
            if (!data.config_name) {
                showToast('请输入配置名称', 'error');
                return;
            }
            if (data.soc_min >= data.soc_max) {
                showToast('SOC 下限必须小于上限', 'error');
                return;
            }
            if (data.soc_min < 0 || data.soc_max > 100) {
                showToast('SOC 必须在 0-100 范围内', 'error');
                return;
            }
            if (data.charge_power_kw <= 0 || data.charge_power_kw > 10) {
                showToast('充电功率必须在 0 到 10 kW 之间', 'error');
                return;
            }
            if (data.discharge_power_kw <= 0 || data.discharge_power_kw > 10) {
                showToast('放电功率必须在 0 到 10 kW 之间', 'error');
                return;
            }
            await saveConfig(data);
        } catch (error) {
            // 已在 saveConfig 中处理
        }
    });

    // 加载当前配置按钮
    document.getElementById('load-btn').addEventListener('click', async function() {
        const config = await loadCurrentConfig();
        if (config) {
            fillFormData(config);
            showToast('✅ 已加载当前配置', 'success');
        } else {
            showToast('❌ 未找到配置', 'error');
        }
    });

    // 预览决策
    document.getElementById('preview-form').addEventListener('submit', async function(e) {
        e.preventDefault();
        try {
            const data = getPreviewData();
            if (data.storage_soc < 0 || data.storage_soc > 100) {
                showToast('SOC 必须在 0-100 范围内', 'error');
                return;
            }
            await previewDecision(data);
        } catch (error) {
            // 已在 previewDecision 中处理
        }
    });

    // 自动预览（初始加载时）
    setTimeout(async function() {
        try {
            const data = getPreviewData();
            await previewDecision(data);
        } catch (e) {
            // 静默失败
        }
    }, 500);
});