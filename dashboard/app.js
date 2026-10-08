/* ============================================================
   app.js — Chhattisgarh Power Grid Dashboard
   ============================================================ */

const API = 'http://127.0.0.1:8000/api';

/* ── State ── */
const state = {
  currentPage: 'live',
  forecastHorizon: '5min',
  liveData: null,
  charts: {},
  refreshTimer: null,
  lastUpdate: null,
};

/* ── Utils ── */
const fmt  = (n, d=1) => n != null ? n.toLocaleString('en-IN', {minimumFractionDigits:d,maximumFractionDigits:d}) : '—';
const fmtN = (n)      => n != null ? Math.round(n).toLocaleString('en-IN') : '—';
const el   = (id)     => document.getElementById(id);

function showToast(msg, type='success') {
  const c = document.querySelector('.toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

function updateClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-IN', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const dateStr = now.toLocaleDateString('en-IN', {weekday:'short',day:'numeric',month:'short',year:'numeric'});
  if(el('clock')) el('clock').textContent = `${dateStr} ${timeStr}`;
  if(state.lastUpdate) {
    const diff = Math.round((now - state.lastUpdate) / 1000);
    if(el('last-update')) el('last-update').textContent = `Updated ${diff}s ago`;
  }
}

function animateCounter(element, target, duration=1200, decimals=0) {
  const start    = 0;
  const startTs  = performance.now();
  const update   = (ts) => {
    const prog = Math.min((ts - startTs) / duration, 1);
    const ease = 1 - Math.pow(1 - prog, 3);
    const val  = start + (target - start) * ease;
    element.textContent = decimals > 0 ? fmt(val, decimals) : fmtN(val);
    if (prog < 1) requestAnimationFrame(update);
  };
  requestAnimationFrame(update);
}

/* ── Navigation ── */
function navigate(page) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.page === page));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === `page-${page}`));
  state.currentPage = page;
  if (page === 'live')       loadLivePage();
  if (page === 'forecast')   loadForecastPage();
  if (page === 'historical') loadHistoricalPage();
  if (page === 'models')     loadModelsPage();
}

/* ============================================================
   CHART DEFAULTS
   ============================================================ */
function chartDefaults() {
  Chart.defaults.color = '#94a3b8';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
  Chart.defaults.font.family = 'Inter';
}

function destroyChart(key) {
  if (state.charts[key]) { state.charts[key].destroy(); delete state.charts[key]; }
}

/* ============================================================
   LIVE PAGE
   ============================================================ */
async function loadLivePage() {
  try {
    const data = await fetch(`${API}/chhattisgarh/latest`).then(r=>r.json());
    state.liveData  = data;
    state.lastUpdate = new Date();

    const latest = data.demand_points?.at(-1);
    const latestW = data.weather_points?.at(-1);

    // Stat cards
    const curEl = el('stat-current');
    if (curEl) animateCounter(curEl, latest?.demand_mw ?? 0);
    const peakEl = el('stat-peak');
    if (peakEl) animateCounter(peakEl, data.peak_demand_mw ?? 0);
    const avgEl = el('stat-avg');
    if (avgEl) animateCounter(avgEl, data.avg_demand_mw ?? 0);

    // Weather
    if (latestW) {
      if(el('w-temp'))  el('w-temp').textContent  = fmt(latestW.temperature_c, 1) + '°C';
      if(el('w-hum'))   el('w-hum').textContent   = fmt(latestW.humidity_pct, 0) + '%';
      if(el('w-rain'))  el('w-rain').textContent  = fmt(latestW.rain_mm, 2) + ' mm';
      if(el('w-wind'))  el('w-wind').textContent  = fmt(latestW.wind_speed_ms, 1) + ' m/s';
    }

    // Live demand chart
    renderLiveChart(data.demand_points ?? [], data.weather_points ?? []);

    showToast('Live data refreshed ✓', 'success');
  } catch(e) {
    showToast('API error — is server running?', 'error');
    console.error(e);
  }
}

function renderLiveChart(demand, weather) {
  destroyChart('live');
  const ctx = el('chart-live');
  if (!ctx) return;

  const labels = demand.map(d => {
    const dt = new Date(d.datetime);
    return dt.toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit'});
  });
  const dmw  = demand.map(d => d.demand_mw);
  const temps = weather.map(w => w.temperature_c);

  state.charts.live = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Demand (MW)',
          data: dmw,
          borderColor: '#00d4ff',
          backgroundColor: (ctx) => {
            const g = ctx.chart.ctx.createLinearGradient(0,0,0,ctx.chart.height);
            g.addColorStop(0, 'rgba(0,212,255,0.25)');
            g.addColorStop(1, 'rgba(0,212,255,0)');
            return g;
          },
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 5,
          borderWidth: 2.5,
          yAxisID: 'y',
        },
        {
          label: 'Temperature (°C)',
          data: temps,
          borderColor: '#f59e0b',
          backgroundColor: 'transparent',
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 5,
          borderWidth: 2,
          borderDash: [6, 3],
          yAxisID: 'y1',
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 800 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(8,13,26,0.95)',
          borderColor: 'rgba(0,212,255,0.3)',
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: (ctx) => ctx.dataset.label === 'Demand (MW)'
              ? ` ${fmtN(ctx.parsed.y)} MW`
              : ` ${fmt(ctx.parsed.y, 1)} °C`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { maxTicksLimit: 12, font: { size: 11 } },
        },
        y: {
          position: 'left',
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { callback: v => fmtN(v) + ' MW', font: { size: 11 } },
        },
        y1: {
          position: 'right',
          grid: { display: false },
          ticks: { callback: v => v + '°C', font: { size: 11 } },
        },
      },
    },
  });
}

/* ============================================================
   FORECAST PAGE
   ============================================================ */
async function loadForecastPage(horizon) {
  horizon = horizon || state.forecastHorizon || '5min';
  state.forecastHorizon = horizon;

  // Update tab styles
  document.querySelectorAll('.fc-tab').forEach(b => b.classList.toggle('active', b.dataset.h === horizon));

  let dateStr = el('fc-date') ? el('fc-date').value : '';
  if (!dateStr) {
    const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
    dateStr = tomorrow.toISOString().slice(0, 10);
    if (el('fc-date')) el('fc-date').value = dateStr;
  }

  try {
    let url, slots;

    if (horizon === '5min') {
      url     = `${API}/chhattisgarh/forecast?date=${dateStr}`;
      const r = await fetch(url).then(r => r.json());
      slots   = r.slots ?? [];
      renderForecastChart(slots, 'datetime', '5-Min Forecast', '#7c3aed'); // Purple for forecast
      updateForecastStats(r);
    } else if (horizon === '1hour') {
      url     = `${API}/chhattisgarh/forecast/1hour?date=${dateStr}`;
      const r = await fetch(url).then(r => r.json());
      slots   = r.slots ?? [];
      renderForecastChart(slots, 'datetime', '1-Hour Forecast', '#7c3aed');
      updateForecastStats(r);
    } else if (horizon === '3hour') {
      url     = `${API}/chhattisgarh/forecast/3hour?date=${dateStr}`;
      const r = await fetch(url).then(r => r.json());
      slots   = r.slots ?? [];
      renderForecastChart(slots, 'datetime', '3-Hour Forecast', '#10b981');
      updateForecastStats(r);
    } else if (horizon === '24hour') {
      url     = `${API}/chhattisgarh/forecast/24hour?days=30`;
      const r = await fetch(url).then(r => r.json());
      slots   = (r.days ?? []).map(d => ({datetime: d.date, predicted_mw: d.predicted_mw, actual_mw: d.actual_mw, temperature_c: d.temperature_c}));
      renderForecastChart(slots, 'datetime', '30-Day Forecast', '#f59e0b', true);
      updateForecastStats(r);
    }
  } catch(e) {
    showToast('Forecast API error', 'error');
    console.error(e);
  }
}

function renderForecastChart(slots, labelKey, title, color, isBar=false) {
  destroyChart('forecast');
  const ctx = el('chart-forecast');
  if (!ctx) return;

  const labels = slots.map(s => {
    const dt = new Date(s[labelKey]);
    return dt.toLocaleDateString('en-IN', {month:'short', day:'numeric'}) + (state.forecastHorizon !== '24hour' ? ' ' + dt.toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit'}) : '');
  });
  const values  = slots.map(s => s.predicted_mw);
  const actuals = slots.map(s => s.actual_mw);
  const temps   = slots.map(s => s.temperature_c);

  const hasActual = slots.some(s => s.actual_mw !== null && s.actual_mw !== undefined);

  const datasets = [
    {
      label: 'Predicted Demand (MW)',
      data: values,
      borderColor: color,
      borderDash: hasActual ? [6, 4] : [], // Dashed for predicted when actual is present
      backgroundColor: isBar ? `${color}33` : 'transparent',
      fill: false,
      tension: 0.4,
      pointRadius: isBar ? 0 : 2,
      pointHoverRadius: 6,
      borderWidth: 2.5,
      yAxisID: 'y',
      borderRadius: isBar ? 4 : 0,
    }
  ];

  if (hasActual) {
    datasets.push({
      label: 'Actual Demand (MW)',
      data: actuals,
      borderColor: '#00d4ff', // Cyan for actual
      backgroundColor: (ctx) => {
        const g = ctx.chart.ctx.createLinearGradient(0,0,0,ctx.chart.height);
        g.addColorStop(0, 'rgba(0,212,255,0.22)');
        g.addColorStop(1, 'rgba(0,212,255,0)');
        return g;
      },
      fill: true,
      tension: 0.4,
      pointRadius: 0,
      pointHoverRadius: 6,
      borderWidth: 3,
      yAxisID: 'y',
    });
  }

  // Always keep temperature as the secondary line
  datasets.push({
    label: 'Temperature (°C)',
    data: temps,
    borderColor: '#f59e0b',
    backgroundColor: 'transparent',
    type: 'line',
    tension: 0.4,
    pointRadius: 0,
    borderWidth: 1.5,
    borderDash: [4,3],
    yAxisID: 'y1',
  });

  state.charts.forecast = new Chart(ctx, {
    type: isBar ? 'bar' : 'line',
    data: {
      labels,
      datasets,
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 600 },
      plugins: {
        legend: {
          display: true,
          labels: { boxWidth:12, font:{size:12}, color:'#94a3b8', usePointStyle:true, padding:12 }
        },
        tooltip: {
          backgroundColor: 'rgba(8,13,26,0.95)',
          borderColor: `${color}55`,
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: (ctx) => ctx.dataset.label.includes('Demand')
              ? ` ${ctx.dataset.label.split(' ')[0]}: ${fmtN(ctx.parsed.y)} MW`
              : ` ${ctx.dataset.label}: ${fmt(ctx.parsed.y,1)} °C`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { maxTicksLimit: 12, font:{size:11} },
        },
        y: {
          position: 'left',
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { callback: v => fmtN(v) + ' MW', font:{size:11} },
        },
        y1: {
          position: 'right',
          grid: { display: false },
          ticks: { callback: v => v + '°C', font:{size:11} },
        },
      },
    },
  });
}

function updateForecastStats(r) {
  if(el('fc-peak')) el('fc-peak').textContent = fmtN(r.peak_demand_mw) + ' MW';
  if(el('fc-avg'))  el('fc-avg').textContent  = fmtN(r.avg_demand_mw)  + ' MW';
  if(el('fc-min'))  el('fc-min').textContent  = fmtN(r.min_demand_mw)  + ' MW';
}

/* ============================================================
   HISTORICAL PAGE
   ============================================================ */
async function loadHistoricalPage() {
  const end   = new Date().toISOString().slice(0, 10);
  const start = new Date(Date.now() - 365*24*60*60*1000).toISOString().slice(0, 10);
  await fetchHistorical(start, end);
}

async function fetchHistorical(start, end) {
  try {
    const r = await fetch(`${API}/chhattisgarh/daily-summary?start_date=${start}&end_date=${end}`).then(r=>r.json());
    const days = r.days ?? [];
    renderHistoricalChart(days);
    renderYoYChart(days);

    // Stats
    const peaks = days.map(d => d.peak_demand_mw);
    const avgs  = days.map(d => d.avg_demand_mw);
    if(el('hist-peak')) animateCounter(el('hist-peak'), Math.max(...peaks));
    if(el('hist-avg'))  animateCounter(el('hist-avg'),  avgs.reduce((a,b)=>a+b,0)/avgs.length);
    if(el('hist-days')) el('hist-days').textContent = days.length + ' days';
    showToast('Historical data loaded ✓', 'success');
  } catch(e) {
    showToast('Error loading historical data', 'error');
  }
}

function renderHistoricalChart(days) {
  destroyChart('historical');
  const ctx = el('chart-historical');
  if (!ctx) return;

  const labels = days.map(d => {
    const dt = new Date(d.date);
    return dt.toLocaleDateString('en-IN', {month:'short', day:'numeric'});
  });

  state.charts.historical = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Peak Demand',
          data: days.map(d => d.peak_demand_mw),
          borderColor: '#f43f5e',
          backgroundColor: 'rgba(244,63,94,0.08)',
          fill: false,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 1.5,
        },
        {
          label: 'Avg Demand',
          data: days.map(d => d.avg_demand_mw),
          borderColor: '#00d4ff',
          backgroundColor: (ctx) => {
            const g = ctx.chart.ctx.createLinearGradient(0,0,0,ctx.chart.height);
            g.addColorStop(0, 'rgba(0,212,255,0.2)');
            g.addColorStop(1, 'rgba(0,212,255,0)');
            return g;
          },
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        },
        {
          label: 'Min Demand',
          data: days.map(d => d.min_demand_mw),
          borderColor: '#10b981',
          backgroundColor: 'transparent',
          fill: false,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 1.5,
          borderDash: [4,3],
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 600 },
      plugins: {
        legend: {
          display: true,
          labels: { boxWidth:12, font:{size:12}, color:'#94a3b8', usePointStyle:true, pointStyleWidth:10 },
        },
        tooltip: {
          backgroundColor:'rgba(8,13,26,0.95)',
          borderColor:'rgba(0,212,255,0.2)',
          borderWidth:1, padding:12,
          callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmtN(ctx.parsed.y)} MW` },
        },
      },
      scales: {
        x: { grid:{color:'rgba(255,255,255,0.04)'}, ticks:{maxTicksLimit:12, font:{size:11}} },
        y: { grid:{color:'rgba(255,255,255,0.05)'}, ticks:{callback:v=>fmtN(v)+' MW', font:{size:11}} },
      },
    },
  });
}

function renderYoYChart(days) {
  destroyChart('yoy');
  const ctx = el('chart-yoy');
  if (!ctx) return;

  const byMonth = {};
  days.forEach(d => {
    const dt  = new Date(d.date);
    const yr  = dt.getFullYear();
    const mon = dt.toLocaleString('default', { month: 'short' });
    const key = `${yr}-${String(dt.getMonth()+1).padStart(2,'0')}`;
    if (!byMonth[key]) byMonth[key] = { label: `${mon} '${String(yr).slice(2)}`, year: yr, vals: [] };
    byMonth[key].vals.push(d.avg_demand_mw);
  });

  const months = Object.values(byMonth).sort((a,b) => a.label.localeCompare(b.label));
  const avgsByMonth = months.map(m => m.vals.reduce((a,b)=>a+b,0)/m.vals.length);

  const years  = [...new Set(months.map(m => m.year))].sort();
  const colors = ['#00d4ff','#7c3aed','#10b981','#f59e0b'];
  const datasets = years.map((yr, i) => ({
    label: String(yr),
    data: months.filter(m=>m.year===yr).map(m => m.vals.reduce((a,b)=>a+b,0)/m.vals.length),
    backgroundColor: `${colors[i % colors.length]}66`,
    borderColor: colors[i % colors.length],
    borderWidth: 2,
    borderRadius: 4,
  }));

  state.charts.yoy = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: [...new Set(months.map(m => m.label.split(' ')[0]))],
      datasets,
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { boxWidth:12, font:{size:12}, color:'#94a3b8', usePointStyle:true } },
        tooltip: {
          backgroundColor:'rgba(8,13,26,0.95)',
          borderColor:'rgba(255,255,255,0.1)',
          borderWidth:1, padding:12,
          callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmtN(ctx.parsed.y)} MW` },
        },
      },
      scales: {
        x: { grid:{color:'rgba(255,255,255,0.04)'}, ticks:{font:{size:11}} },
        y: { grid:{color:'rgba(255,255,255,0.05)'}, ticks:{callback:v=>fmtN(v)+' MW', font:{size:11}} },
      },
    },
  });
}

/* ============================================================
   MODELS PAGE
   ============================================================ */
function loadModelsPage() {
  const models = [
    { name: '5-Min Forecast',   file:'state_5min_CG.pkl',   mae:'5.39 MW',  mape:'0.11%', r2:'99.99%', rows:'3,39,552', badge:'excellent', use:'Real-time dashboard' },
    { name: '1-Hour Forecast',  file:'state_CG_1hour.pkl',  mae:'46.02 MW', mape:'0.96%', r2:'98.97%', rows:'28,296',   badge:'good',      use:'Operations planning' },
    { name: '3-Hour Forecast',  file:'state_CG_3hour.pkl',  mae:'56.79 MW', mape:'1.19%', r2:'97.99%', rows:'9,432',    badge:'good',      use:'Load dispatch' },
    { name: '24-Hour Forecast', file:'state_CG_24hour.pkl', mae:'5.74 MW',  mape:'0.12%', r2:'99.92%', rows:'1,156',    badge:'excellent', use:'Day-ahead planning' },
  ];

  const tbody = el('models-table-body');
  if (!tbody) return;
  tbody.innerHTML = models.map(m => `
    <tr>
      <td><strong>${m.name}</strong><br><small style="color:var(--text-muted);font-family:'JetBrains Mono',monospace;font-size:11px">${m.file}</small></td>
      <td style="font-family:'JetBrains Mono',monospace">${m.mae}</td>
      <td style="font-family:'JetBrains Mono',monospace">${m.mape}</td>
      <td>
        <span style="font-family:'JetBrains Mono',monospace">${m.r2}</span>
        <div style="margin-top:6px">
          <div class="progress-bar"><div class="progress-fill" style="width:${parseFloat(m.r2)}%"></div></div>
        </div>
      </td>
      <td style="font-family:'JetBrains Mono',monospace">${m.rows}</td>
      <td><span class="badge badge-${m.badge}">${m.badge === 'excellent' ? '🏆 Excellent' : '✅ Very Good'}</span></td>
      <td style="color:var(--text-secondary);font-size:12px">${m.use}</td>
    </tr>
  `).join('');

  renderModelR2Chart(models);
}

function renderModelR2Chart(models) {
  destroyChart('r2');
  const ctx = el('chart-r2');
  if (!ctx) return;

  state.charts.r2 = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: models.map(m => m.name),
      datasets: [{
        data: models.map(m => parseFloat(m.r2)),
        backgroundColor: ['rgba(0,212,255,0.7)','rgba(124,58,237,0.7)','rgba(16,185,129,0.7)','rgba(245,158,11,0.7)'],
        borderColor: ['#00d4ff','#7c3aed','#10b981','#f59e0b'],
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      cutout: '72%',
      plugins: {
        legend: { position:'bottom', labels:{ boxWidth:12, font:{size:12}, color:'#94a3b8', usePointStyle:true, padding:16 } },
        tooltip: { callbacks: { label: ctx => ` R² = ${ctx.parsed}%` } },
      },
    },
  });
}

/* ============================================================
   AUTO REFRESH
   ============================================================ */
function startAutoRefresh() {
  if (state.refreshTimer) clearInterval(state.refreshTimer);
  state.refreshTimer = setInterval(() => {
    if (state.currentPage === 'live') loadLivePage();
  }, 30000);
}

/* ============================================================
   INIT
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  chartDefaults();

  // Nav
  document.querySelectorAll('.nav-item[data-page]').forEach(n => {
    n.addEventListener('click', () => navigate(n.dataset.page));
  });

  // Forecast tabs
  document.querySelectorAll('.fc-tab').forEach(b => {
    b.addEventListener('click', () => loadForecastPage(b.dataset.h));
  });

  // Forecast date control
  const btnFcLoad = el('btn-load-forecast');
  if (btnFcLoad) {
    btnFcLoad.addEventListener('click', () => {
      loadForecastPage();
    });
  }

  // Set default date for forecast picker (today)
  if (el('fc-date')) {
    el('fc-date').value = new Date().toISOString().slice(0, 10);
  }

  // Historical date range
  const btnLoad = el('btn-load-hist');
  if (btnLoad) {
    btnLoad.addEventListener('click', () => {
      const start = el('hist-start').value;
      const end   = el('hist-end').value;
      if (start && end) fetchHistorical(start, end);
    });
  }

  // Clock
  setInterval(updateClock, 1000);
  updateClock();

  // Set default dates for historical
  const today = new Date();
  const oneYearAgo = new Date(today); oneYearAgo.setFullYear(today.getFullYear()-1);
  if(el('hist-end'))   el('hist-end').value   = today.toISOString().slice(0,10);
  if(el('hist-start')) el('hist-start').value  = oneYearAgo.toISOString().slice(0,10);

  // Initial page
  navigate('live');
  startAutoRefresh();
});
