const REFRESH_MS = 3000;

const elements = {
    pvPower: document.getElementById("pvPower"),
    loadPower: document.getElementById("loadPower"),
    storagePower: document.getElementById("storagePower"),
    storageSoc: document.getElementById("storageSoc"),
    strategyMessage: document.getElementById("strategyMessage"),
    updatedAt: document.getElementById("updatedAt"),
    actionBadge: document.getElementById("actionBadge"),
    socText: document.getElementById("socText"),
    socBar: document.getElementById("socBar"),
    commandBody: document.getElementById("commandBody"),
    resetButton: document.getElementById("resetButton"),
    toast: document.getElementById("toast"),
    chart: document.getElementById("historyChart")
};

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options
    });

    if (!response.ok) {
        throw new Error(`请求失败：${response.status}`);
    }
    return response.json();
}

function formatNumber(value) {
    return Number(value).toFixed(1);
}

function formatTime(value) {
    return new Date(value).toLocaleTimeString("zh-CN", { hour12: false });
}

function actionLabel(action) {
    const labels = {
        charge: "储能充电",
        discharge: "储能放电",
        idle: "储能待机"
    };
    return labels[action] || action;
}

function updateStatus(status) {
    elements.pvPower.textContent = formatNumber(status.pv_power);
    elements.loadPower.textContent = formatNumber(status.load_power);
    elements.storagePower.textContent = formatNumber(status.storage_power);
    elements.storageSoc.textContent = formatNumber(status.storage_soc);

    elements.strategyMessage.textContent = status.strategy_message;
    elements.updatedAt.textContent = `更新时间：${formatTime(status.updated_at)}`;
    elements.actionBadge.textContent = actionLabel(status.action);
    elements.actionBadge.className = `badge ${status.action}`;

    const soc = Math.max(0, Math.min(100, Number(status.storage_soc)));
    elements.socText.textContent = `${soc.toFixed(1)}%`;
    elements.socBar.style.width = `${soc}%`;
}

function updateCommands(commands) {
    if (!commands.length) {
        elements.commandBody.innerHTML = `<tr><td colspan="5">暂无记录</td></tr>`;
        return;
    }

    elements.commandBody.innerHTML = commands.map(item => `
        <tr>
            <td>${formatTime(item.created_at)}</td>
            <td>${actionLabel(item.action)}</td>
            <td>${formatNumber(item.command_value)} kW</td>
            <td>${item.strategy_message}</td>
            <td>${item.execute_result}</td>
        </tr>
    `).join("");
}

function drawChart(history) {
    const canvas = elements.chart;
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = 290;

    canvas.width = width * dpr;
    canvas.height = height * dpr;

    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const padding = { left: 48, right: 18, top: 20, bottom: 34 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;

    ctx.font = "12px Microsoft YaHei";
    ctx.fillStyle = "#7b8798";
    ctx.strokeStyle = "#e4eaf2";
    ctx.lineWidth = 1;

    const allValues = history.flatMap(item => [
        item.pv_power,
        item.load_power,
        item.storage_power
    ]);
    const minValue = Math.min(-15, ...allValues);
    const maxValue = Math.max(100, ...allValues);
    const range = maxValue - minValue || 1;

    for (let i = 0; i <= 5; i++) {
        const y = padding.top + (plotHeight / 5) * i;
        const value = maxValue - (range / 5) * i;

        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();

        ctx.fillText(value.toFixed(0), 8, y + 4);
    }

    if (history.length < 2) {
        ctx.fillText("等待更多历史数据……", padding.left + 20, padding.top + 40);
        return;
    }

    const xOf = index =>
        padding.left + (plotWidth * index) / (history.length - 1);
    const yOf = value =>
        padding.top + ((maxValue - value) / range) * plotHeight;

    function drawSeries(field, color) {
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.4;

        history.forEach((item, index) => {
            const x = xOf(index);
            const y = yOf(item[field]);
            if (index === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });

        ctx.stroke();
    }

    drawSeries("pv_power", "#2f6fed");
    drawSeries("load_power", "#e8902f");
    drawSeries("storage_power", "#23a36d");

    const first = history[0];
    const last = history[history.length - 1];
    ctx.fillStyle = "#7b8798";
    ctx.fillText(formatTime(first.created_at), padding.left, height - 10);
    const lastLabel = formatTime(last.created_at);
    const labelWidth = ctx.measureText(lastLabel).width;
    ctx.fillText(lastLabel, width - padding.right - labelWidth, height - 10);
}

function showToast(message) {
    elements.toast.textContent = message;
    elements.toast.classList.add("show");
    window.setTimeout(() => elements.toast.classList.remove("show"), 2200);
}

async function refreshAll() {
    try {
        const [status, history, commands] = await Promise.all([
            requestJson("/api/status"),
            requestJson("/api/history"),
            requestJson("/api/commands")
        ]);

        updateStatus(status);
        drawChart(history);
        updateCommands(commands);
    } catch (error) {
        console.error(error);
        showToast("读取后端数据失败");
    }
}

elements.resetButton.addEventListener("click", async () => {
    elements.resetButton.disabled = true;
    try {
        const result = await requestJson("/api/reset", { method: "POST" });
        showToast(result.message);
        await refreshAll();
    } catch (error) {
        console.error(error);
        showToast("重置失败");
    } finally {
        elements.resetButton.disabled = false;
    }
});

window.addEventListener("resize", () => {
    requestJson("/api/history")
        .then(drawChart)
        .catch(console.error);
});

refreshAll();
window.setInterval(refreshAll, REFRESH_MS);
