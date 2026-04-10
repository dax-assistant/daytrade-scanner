const HOW_IT_WORKS = `This scanner implements the Ross Cameron / Warrior Trading day trading methodology. It continuously scans the entire market for stocks meeting 5 critical criteria: up at least 10% on the day, priced between $2-$20, at least 5× normal trading volume, a public float under 20 million shares, and a breaking news catalyst. Stocks meeting all 5 "pillars" represent A-quality setups with the highest probability of producing large percentage moves. The scanner runs during market hours with its primary focus on the 7:00-10:00 AM ET window when volume and volatility are highest.`;

const GLOSSARY = {
  "Gap %": "The percentage a stock's current price is above its previous day's closing price. A gap of 10%+ signals unusual momentum.",
  "Relative Volume": "Today's trading volume divided by the stock's average daily volume over the past 50 days.",
  "Float": "The number of shares available for public trading. Lower float can accelerate moves.",
  "MACD (12, 26, 9)": "When MACD line is above signal line, momentum is positive.",
  "VWAP": "Volume weighted average price. Price above VWAP is generally bullish intraday.",
  "9 EMA": "Short-term support during strong trends.",
  "20 EMA": "Secondary support and trend context.",
  "Pillar Score": "How many of the 5 setup pillars passed.",
  "Entry Signal": "MACD+, above VWAP, above EMA9, and bullish volume profile.",
  "Risk:Reward Ratio": "Potential reward divided by risk.",
  "Primary Window": "7:00 AM – 10:00 AM ET."
};

const els = {
  scannerState: document.getElementById('scannerState'),
  sessionBadge: document.getElementById('sessionBadge'),
  primaryCountdown: document.getElementById('primaryCountdown'),
  telegramToggle: document.getElementById('telegramToggle'),
  watchlist: document.getElementById('watchlist'),
  watchlistLoading: document.getElementById('watchlistLoading'),
  watchlistEmpty: document.getElementById('watchlistEmpty'),
  alerts: document.getElementById('alerts'),
  chartSymbol: document.getElementById('chartSymbol'),
  chartPrice: document.getElementById('chartPrice'),
  positionsBody: document.getElementById('positionsBody'),
  historyBody: document.getElementById('historyBody'),
  historyStats: document.getElementById('historyStats'),
  dailyPnl: document.getElementById('dailyPnl'),
  winRate: document.getElementById('winRate'),
  accountBalance: document.getElementById('accountBalance'),
  openCount: document.getElementById('openCount'),
  lossUsage: document.getElementById('lossUsage'),
  lossMeterBar: document.getElementById('lossMeterBar'),
  setupInfo: document.getElementById('setupInfo'),
  alltimePnl: document.getElementById('alltimePnl'),
  settingsBtn: document.getElementById('settingsBtn'),
  settingsPanel: document.getElementById('settingsPanel'),
  settingsClose: document.getElementById('settingsClose'),
  saveSettings: document.getElementById('saveSettings'),
  saveStatus: document.getElementById('saveStatus'),
  viewTrading: document.getElementById('view-trading'),
  viewChart: document.getElementById('view-chart'),
  viewAnalytics: document.getElementById('view-analytics'),
  tabTrading: document.getElementById('tabTrading'),
  tabChart: document.getElementById('tabChart'),
  tabAnalytics: document.getElementById('tabAnalytics'),
  backToTrading: document.getElementById('backToTrading'),
  chartPageTicker: document.getElementById('chartPageTicker'),
  chartTradeForm: document.getElementById('chartTradeForm'),
  chartTradeTicker: document.getElementById('chartTradeTicker'),
  chartTradeEntry: document.getElementById('chartTradeEntry'),
  chartTradeShares: document.getElementById('chartTradeShares'),
  chartArea: document.getElementById('chartArea'),
  chartContainer: document.getElementById('chartContainer'),
  macdContainer: document.getElementById('macdContainer'),
  analyticsStreak: document.getElementById('analyticsStreak'),
  aWinRate: document.getElementById('aWinRate'),
  aProfitFactor: document.getElementById('aProfitFactor'),
  aExpectancy: document.getElementById('aExpectancy'),
  aAvgWinner: document.getElementById('aAvgWinner'),
  aAvgLoser: document.getElementById('aAvgLoser'),
  aAvgHold: document.getElementById('aAvgHold'),
  aMaxWin: document.getElementById('aMaxWin'),
  aMaxLoss: document.getElementById('aMaxLoss'),
  aStreakCard: document.getElementById('aStreakCard'),
  aByReason: document.getElementById('aByReason'),
  aByHour: document.getElementById('aByHour'),
  aByDay: document.getElementById('aByDay'),
  aByGrade: document.getElementById('aByGrade'),
  tradeLogBody: document.getElementById('tradeLogBody'),
  tradeLogFilter: document.getElementById('tradeLogFilter'),
  preTradeModal: document.getElementById('preTradeModal'),
  preTradeModalClose: document.getElementById('preTradeModalClose'),
  preTradeTicker: document.getElementById('preTradeTicker'),
  preTradePrice: document.getElementById('preTradePrice'),
  preTradeDbId: document.getElementById('preTradeDbId'),
  preTradeSymbolBadge: document.getElementById('preTradeSymbolBadge'),
  preTradePriceText: document.getElementById('preTradePriceText'),
  preTradeCancel: document.getElementById('preTradeCancel'),
  preTradeConfirm: document.getElementById('preTradeConfirm'),
};

const state = {
  activeView: 'trading',
  pendingTradeEntry: null,
  analyticsRange: 'alltime',
  analyticsBreakdown: 'byReason',
  tradeLogFilter: 'all',
  allTrades: [],
  journalEntries: [],
  gradeAnalytics: [],
  previousTradeStatus: {},
};

let ws;
let watchlistItems = [];
let selectedSymbol = null;
let currentTf = '1m';
let thresholds = {};
let journalEntryMap = {}; // trade_id -> true if journaled
let currentJournalGrade = null;
const PRE_TRADE_STORAGE_KEY = 'preTradeChecklist';

const chart = LightweightCharts.createChart(els.chartContainer, {
  layout: { background: { type: 'solid', color: '#0e162a' }, textColor: '#d1d5db' },
  grid: { vertLines: { color: '#1f2b49' }, horzLines: { color: '#1f2b49' } },
  timeScale: { timeVisible: true, secondsVisible: false },
});
const candleSeries = chart.addCandlestickSeries({
  upColor: '#22c55e', downColor: '#ef4444', borderUpColor: '#22c55e', borderDownColor: '#ef4444', wickUpColor: '#22c55e', wickDownColor: '#ef4444'
});
const volumeSeries = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '', scaleMargins: { top: 0.8, bottom: 0 } });
const vwapSeries = chart.addLineSeries({ color: '#f59e0b', lineWidth: 2 });
const ema9Series = chart.addLineSeries({ color: '#9ca3af', lineWidth: 2 });
const ema20Series = chart.addLineSeries({ color: '#14b8a6', lineWidth: 2 });

const macdChart = LightweightCharts.createChart(els.macdContainer, {
  layout: { background: { type: 'solid', color: '#0e162a' }, textColor: '#94a3b8' },
  grid: { vertLines: { color: '#1f2b49' }, horzLines: { color: '#1f2b49' } },
  timeScale: { timeVisible: true, secondsVisible: false },
});
const macdSeries = macdChart.addLineSeries({ color: '#3b82f6', lineWidth: 2 });
const macdSignalSeries = macdChart.addLineSeries({ color: '#f59e0b', lineWidth: 2 });
const macdHistSeries = macdChart.addHistogramSeries({ lineWidth: 1 });

let setupLines = [];
function clearSetupLines() { setupLines.forEach(l => candleSeries.removePriceLine(l)); setupLines = []; }
function drawSetup(setup) {
  clearSetupLines();
  if (!setup || setup.entry == null || setup.stop == null) {
    els.setupInfo.textContent = 'Setup: waiting…';
    return;
  }
  const mk = (p, c, t) => candleSeries.createPriceLine({ price: Number(p), color: c, lineStyle: 2, lineWidth: 2, axisLabelVisible: true, title: t });
  setupLines.push(mk(setup.entry, '#22c55e', `Entry ${Number(setup.entry).toFixed(2)}`));
  setupLines.push(mk(setup.stop, '#ef4444', `Stop ${Number(setup.stop).toFixed(2)}`));
  if (setup.target != null) setupLines.push(mk(setup.target, '#38bdf8', `Target ${Number(setup.target).toFixed(2)}`));
  if (setup.trailing_stop != null) setupLines.push(mk(setup.trailing_stop, '#a855f7', `Trail ${Number(setup.trailing_stop).toFixed(2)}`));
  els.setupInfo.textContent = `Setup: Entry ${Number(setup.entry).toFixed(2)} | Stop ${Number(setup.stop).toFixed(2)} | Target ${setup.target != null ? Number(setup.target).toFixed(2) : 'trailing'}`;
}

function applyChartSizes() {
  if (!els.chartContainer || !els.macdContainer) return;
  const chartWidth = els.chartContainer.clientWidth || els.chartContainer.offsetWidth || 0;
  const chartHeight = els.chartContainer.clientHeight || els.chartContainer.offsetHeight || 0;
  const macdWidth = els.macdContainer.clientWidth || els.macdContainer.offsetWidth || 0;
  const macdHeight = els.macdContainer.clientHeight || els.macdContainer.offsetHeight || 0;
  if (chartWidth > 0 && chartHeight > 0) chart.applyOptions({ width: chartWidth, height: chartHeight });
  if (macdWidth > 0 && macdHeight > 0) macdChart.applyOptions({ width: macdWidth, height: macdHeight });
}

new ResizeObserver(() => {
  applyChartSizes();
}).observe(document.body);

function statusPill(stateValue) {
  els.scannerState.textContent = stateValue;
  els.scannerState.className = 'pill ' + (stateValue === 'scanning' ? 'pill-green' : stateValue === 'error' ? 'pill-red' : stateValue === 'waiting' ? 'pill-yellow' : 'pill-gray');
}

function setSessionBadge(session) {
  const s = (session || '').toUpperCase();
  els.sessionBadge.textContent = s;
  els.sessionBadge.className = 'pill ' + (session === 'primary_window' || session === 'open' ? 'pill-green' : session === 'pre_scan' || session === 'premarket' ? 'pill-yellow' : 'pill-gray');
}

function fmtMoney(v) { return `$${Number(v || 0).toFixed(2)}`; }

function getStoredPreTradeChecklist() {
  try {
    const saved = JSON.parse(localStorage.getItem(PRE_TRADE_STORAGE_KEY) || '{}');
    return {
      setup: Boolean(saved.setup),
      stop: Boolean(saved.stop),
      size: Boolean(saved.size),
      dailyLoss: Boolean(saved.dailyLoss),
    };
  } catch (err) {
    return { setup: false, stop: false, size: false, dailyLoss: false };
  }
}

function savePreTradeChecklist(stateValue) {
  localStorage.setItem(PRE_TRADE_STORAGE_KEY, JSON.stringify(stateValue));
}

function isClosedTradeStatus(status) {
  return String(status || '').startsWith('closed');
}

function getJournalEntryByTradeId(tradeId) {
  return (state.journalEntries || []).find(entry => Number(entry.trade_id) === Number(tradeId)) || null;
}

function getGradeBadgeClass(grade) {
  return grade ? `grade-pill grade-pill-${grade}` : 'grade-pill';
}

function renderGradeCell(tradeId, grade, status) {
  if (!isClosedTradeStatus(status)) return '<span class="muted">—</span>';
  if (grade) return `<span class="${getGradeBadgeClass(grade)}">${grade}</span>`;
  return `
    <div class="grade-inline" data-trade-grade="${tradeId}">
      <button class="grade-inline-btn" data-grade-tradeid="${tradeId}" data-grade-value="A">A</button>
      <button class="grade-inline-btn" data-grade-tradeid="${tradeId}" data-grade-value="B">B</button>
      <button class="grade-inline-btn" data-grade-tradeid="${tradeId}" data-grade-value="C">C</button>
      <button class="grade-inline-btn" data-grade-tradeid="${tradeId}" data-grade-value="D">D</button>
    </div>
  `;
}

async function saveTradeGrade(tradeId, grade) {
  const existing = getJournalEntryByTradeId(tradeId) || {};
  const payload = {
    setup_type: existing.setup_type || null,
    emotional_state: existing.emotional_state || null,
    grade: grade || null,
    notes: existing.notes || null,
    mistakes: existing.mistakes || null,
  };

  const res = await fetch(`/api/journal/${tradeId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) throw new Error('grade_save_failed');
  const data = await res.json();
  const savedEntry = data.entry || payload;
  journalEntryMap[tradeId] = true;
  state.journalEntries = (state.journalEntries || []).filter(entry => Number(entry.trade_id) !== Number(tradeId));
  state.journalEntries.unshift(savedEntry);
  return savedEntry;
}

function bindGradeButtons(scope = document) {
  scope.querySelectorAll('[data-grade-tradeid]').forEach(btn => {
    btn.onclick = async (event) => {
      event.stopPropagation();
      const tradeId = Number(btn.dataset.gradeTradeid);
      const grade = btn.dataset.gradeValue;
      const group = btn.closest('[data-trade-grade]');
      if (group) group.querySelectorAll('.grade-inline-btn').forEach(x => x.disabled = true);
      try {
        await saveTradeGrade(tradeId, grade);
        await refreshData();
      } catch (err) {
        console.error('Grade save failed', err);
        if (group) group.querySelectorAll('.grade-inline-btn').forEach(x => x.disabled = false);
      }
    };
  });
}

function getSelectedWatchlistItem() {
  return watchlistItems.find(item => (item.ticker || '').toUpperCase() === (selectedSymbol || '').toUpperCase()) || null;
}

function syncChartTradeForm(item = getSelectedWatchlistItem()) {
  const ticker = (item?.ticker || selectedSymbol || '').toUpperCase();
  const price = Number(item?.price || 0);
  let changed = false;
  if (els.chartPageTicker) els.chartPageTicker.textContent = ticker || '—';
  if (els.chartTradeTicker) els.chartTradeTicker.value = ticker;
  if (els.chartTradeEntry) {
    const active = document.activeElement === els.chartTradeEntry;
    if (!active || !els.chartTradeEntry.value) {
      els.chartTradeEntry.value = price ? price.toFixed(2) : '';
      changed = true;
    }
  }
  if (document.getElementById('calcEntry')) {
    const calcEntry = document.getElementById('calcEntry');
    const active = document.activeElement === calcEntry;
    if ((!active || !calcEntry.value) && price) {
      calcEntry.value = price.toFixed(2);
      changed = true;
    }
  }
  if (changed) calcPositionSize();
}

async function submitPreTradeEntry() {
  const payload = {
    ticker: els.preTradeTicker.value,
    price: Number(els.preTradePrice.value || 0),
    db_id: els.preTradeDbId.value ? Number(els.preTradeDbId.value) : null,
    ...(watchlistItems.find(item => (item.ticker || '').toUpperCase() === (els.preTradeTicker.value || '').toUpperCase()) || {}),
  };

  const res = await fetch('/api/simulator/enter', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    throw new Error(data.error || 'trade_entry_failed');
  }
  return data;
}

function updatePreTradeConfirmState() {
  const checklistState = {};
  document.querySelectorAll('#preTradeChecklist input[type=checkbox]').forEach(cb => {
    checklistState[cb.dataset.checklistItem] = cb.checked;
  });
  savePreTradeChecklist(checklistState);
  const ready = Object.values(checklistState).length === 4 && Object.values(checklistState).every(Boolean);
  els.preTradeConfirm.disabled = !ready;
}

function closePreTradeModal() {
  els.preTradeModal.classList.remove('active');
  els.preTradeConfirm.disabled = true;
  state.pendingTradeEntry = null;
}

function openPreTradeModal(item) {
  const checklistState = getStoredPreTradeChecklist();
  const tradeItem = item || getSelectedWatchlistItem() || {};
  const manualEntry = state.pendingTradeEntry || {};
  const entryPrice = Number(manualEntry.price ?? tradeItem.price ?? 0);
  els.preTradeTicker.value = manualEntry.ticker || tradeItem.ticker || '';
  els.preTradePrice.value = entryPrice || '';
  els.preTradeDbId.value = tradeItem.db_id || '';
  els.preTradeSymbolBadge.textContent = manualEntry.ticker || tradeItem.ticker || '—';
  els.preTradePriceText.textContent = `Entry: ${fmtMoney(entryPrice || 0)}`;
  document.querySelectorAll('#preTradeChecklist input[type=checkbox]').forEach(cb => {
    cb.checked = Boolean(checklistState[cb.dataset.checklistItem]);
  });
  updatePreTradeConfirmState();
  els.preTradeModal.classList.add('active');
}

function initPreTradeModal() {
  if (!els.preTradeModal) return;
  els.preTradeModalClose.onclick = closePreTradeModal;
  els.preTradeCancel.onclick = closePreTradeModal;
  els.preTradeModal.onclick = (event) => {
    if (event.target === els.preTradeModal) closePreTradeModal();
  };

  document.querySelectorAll('#preTradeChecklist input[type=checkbox]').forEach(cb => {
    cb.addEventListener('change', updatePreTradeConfirmState);
  });

  els.preTradeConfirm.onclick = async () => {
    els.preTradeConfirm.disabled = true;
    const original = els.preTradeConfirm.textContent;
    els.preTradeConfirm.textContent = 'Entering...';
    try {
      await submitPreTradeEntry();
      closePreTradeModal();
      await refreshData();
    } catch (err) {
      console.error('Trade entry failed', err);
      alertLine(`Trade entry failed: ${err.message}`);
      updatePreTradeConfirmState();
    } finally {
      els.preTradeConfirm.textContent = original;
    }
  };
}

function promptForNewlyClosedTrades(trades) {
  const nextStatus = {};
  const hasBaseline = Object.keys(state.previousTradeStatus || {}).length > 0;
  (trades || []).forEach(trade => {
    const tradeId = Number(trade.id);
    const status = String(trade.status || '');
    const previous = state.previousTradeStatus[tradeId];
    nextStatus[tradeId] = status;
    if (!hasBaseline) return;
    if (previous && !isClosedTradeStatus(previous) && isClosedTradeStatus(status) && !getJournalEntryByTradeId(tradeId)?.grade) {
      alertLine(`${trade.ticker} closed — grade the trade A/B/C/D in history.`);
    }
  });
  state.previousTradeStatus = nextStatus;
}

function alertLine(text) {
  const li = document.createElement('li');
  li.textContent = `${new Date().toLocaleTimeString()} ${text}`;
  els.alerts.prepend(li);
  while (els.alerts.children.length > 200) els.alerts.removeChild(els.alerts.lastChild);
}

function floatClass(tier) {
  return tier === 'ideal' ? 'float-ideal' : tier === 'great' ? 'float-great' : tier === 'good' ? 'float-good' : tier === 'acceptable' ? 'float-acceptable' : 'float-poor';
}

function renderWatchlist(items) {
  els.watchlist.innerHTML = '';

  if (!items || !items.length) {
    els.watchlistEmpty.classList.remove('hidden');
    return;
  }

  els.watchlistEmpty.classList.add('hidden');
  items.sort((a, b) => Number(b.gap_percent || 0) - Number(a.gap_percent || 0));
  items.forEach(item => {
    const card = document.createElement('div');
    card.className = 'watch-card' + ((item.ticker || '').toUpperCase() === selectedSymbol ? ' active' : '');
    const p = item.pillars || {};
    const sig = item.entry_signals || {};
    card.innerHTML = `
      <div class="watch-main"><strong>${item.ticker}</strong><span class="float-badge ${floatClass(item.float_tier)}">${item.float_tier || 'n/a'}</span></div>
      <div>$${Number(item.price || 0).toFixed(2)} | ${Number(item.gap_percent || 0).toFixed(1)}%</div>
      <div class="muted">RelVol ${Number(item.relative_volume || 0).toFixed(1)}x | Float ${item.float_shares ? (item.float_shares / 1_000_000).toFixed(1) + 'M' : '-'}</div>
      <div class="pillar-row">Pillars ${item.score || 0}/5: <span class="${p.price ? 'pass':'fail'}">P</span> <span class="${p.gap_percent ? 'pass':'fail'}">G</span> <span class="${p.relative_volume ? 'pass':'fail'}">RV</span> <span class="${p.float_shares ? 'pass':'fail'}">F</span> <span class="${p.news_catalyst ? 'pass':'fail'}">N</span></div>
      <div class="signal-row">Entry: <span class="${sig.macd_positive ? 'pass':'fail'}">MACD</span> <span class="${sig.above_vwap ? 'pass':'fail'}">VWAP</span> <span class="${sig.above_ema9 ? 'pass':'fail'}">EMA</span> <span class="${sig.volume_bullish ? 'pass':'fail'}">VOL</span></div>
      <div class="muted">${(item.news && item.news.headline) ? item.news.headline.slice(0, 68) : 'No recent headline'}</div>
      <div class="watch-actions">
        <button class="watch-buy-btn" data-buy-ticker="${item.ticker}">Buy</button>
      </div>
    `;
    card.onclick = () => selectSymbol(item.ticker, { switchView: true });
    card.querySelector('.watch-buy-btn').onclick = (event) => {
      event.stopPropagation();
      openPreTradeModal(item);
    };
    els.watchlist.appendChild(card);
  });
}

function fmtTimeET(isoStr) {
  if (!isoStr) return '-';
  try {
    return new Date(isoStr).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/New_York' });
  } catch (e) { return '-'; }
}

function fmtDateTimeET(isoStr) {
  if (!isoStr) return '-';
  try {
    const d = new Date(isoStr);
    const mo = String(d.toLocaleDateString('en-US', { month: '2-digit', timeZone: 'America/New_York' })).padStart(2, '0');
    const day = String(d.toLocaleDateString('en-US', { day: '2-digit', timeZone: 'America/New_York' })).padStart(2, '0');
    const hhmm = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/New_York' });
    return `${mo}/${day} ${hhmm}`;
  } catch (e) { return '-'; }
}

function renderPositions(data) {
  const items = data.items || [];
  els.positionsBody.innerHTML = '';
  items.forEach(t => {
    const pnl = Number(t.unrealized_pnl || 0);
    const entryTime = fmtTimeET(t.entry_time);
    const hold = t.hold_minutes != null ? `${t.hold_minutes}m` : '-';
    const target = (t.take_profit ?? t.target_price) != null ? Number(t.take_profit ?? t.target_price).toFixed(2) : '-';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${t.ticker}</td><td>${Number(t.entry_price || 0).toFixed(2)}</td><td>${Number(t.current_price || 0).toFixed(2)}</td><td>${target}</td><td>${t.quantity || 0}</td><td class="${pnl >= 0 ? 'green' : 'red'}">${pnl.toFixed(2)}</td><td>${Number(t.stop_loss || 0).toFixed(2)}</td><td>${entryTime}</td><td>${hold}</td>`;
    els.positionsBody.appendChild(tr);
  });
  els.openCount.textContent = items.length;
  els.accountBalance.textContent = fmtMoney(data.current_balance || 0);
  els.dailyPnl.textContent = fmtMoney(data.daily_pnl || 0);
}

function renderHistory(data) {
  const items = data.items || [];
  const stats = data.stats || {};
  els.historyBody.innerHTML = '';
  items.forEach(t => {
    const pnl = Number(t.pnl || 0);
    const entryDT = fmtDateTimeET(t.entry_time);
    const exitDT = t.exit_time ? fmtDateTimeET(t.exit_time) : '-';
    const journal = getJournalEntryByTradeId(t.id);
    const gradeCell = renderGradeCell(t.id, journal?.grade, t.status);
    const hasJournal = journalEntryMap[t.id];
    const journalCell = `<td><div class="grade-cell">${gradeCell}</div><button class="journal-btn" data-tradeid="${t.id}" title="Journal this trade">${hasJournal ? '✅' : '📝'}</button></td>`;
    const tr = document.createElement('tr');
    if (isClosedTradeStatus(t.status) && !journal?.grade) tr.classList.add('needs-grade');
    const histTarget = (t.take_profit ?? t.target_price) != null ? Number(t.take_profit ?? t.target_price).toFixed(2) : '-';
    tr.innerHTML = `<td>${t.id || ''}</td><td>${t.ticker}</td><td>${Number(t.entry_price || 0).toFixed(2)}</td><td>${t.exit_price != null ? Number(t.exit_price).toFixed(2) : '-'}</td><td>${histTarget}</td><td class="${pnl >= 0 ? 'green':'red'}">${pnl.toFixed(2)}</td><td>${t.status || ''}</td><td>${entryDT}</td><td>${exitDT}</td>${journalCell}`;
    els.historyBody.appendChild(tr);
  });
  document.querySelectorAll('#historyBody .journal-btn').forEach(btn => {
    btn.onclick = () => openJournalModal(Number(btn.dataset.tradeid));
  });
  bindGradeButtons(els.historyBody);
  els.winRate.textContent = `${Number(stats.win_rate || 0).toFixed(1)}%`;
  els.historyStats.textContent = `Trades: ${stats.total_trades || 0} | AvgW: ${fmtMoney(stats.avg_winner || 0)} | AvgL: ${fmtMoney(stats.avg_loser || 0)} | PF: ${Number(stats.profit_factor || 0).toFixed(2)}`;
}

function updateLossMeter(simStatus) {
  const used = Number(simStatus?.stats?.daily_loss_used || 0);
  const limit = Number(simStatus?.stats?.daily_loss_limit || 0);
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  els.lossUsage.textContent = `${fmtMoney(used)} / ${fmtMoney(limit)}`;
  els.lossMeterBar.style.width = `${pct}%`;
  els.lossMeterBar.style.background = pct > 90 ? '#ef4444' : pct > 70 ? '#f59e0b' : '#22c55e';
}

function renderChartSnapshot(data) {
  if (!data || (data.symbol || '').toUpperCase() !== selectedSymbol) return;
  const candles = data.candles || [];
  const overlays = data.overlays || {};

  candleSeries.setData(candles.map(c => ({ time: Number(c.time), open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close) })));
  volumeSeries.setData(candles.map(c => ({ time: Number(c.time), value: Number(c.volume || 0), color: Number(c.close) >= Number(c.open) ? '#22c55e77' : '#ef444477' })));

  vwapSeries.setData((overlays.vwap || []).map(x => ({ time: Number(x.time), value: Number(x.value) })));
  ema9Series.setData((overlays.ema9 || []).map(x => ({ time: Number(x.time), value: Number(x.value) })));
  ema20Series.setData((overlays.ema20 || []).map(x => ({ time: Number(x.time), value: Number(x.value) })));

  macdSeries.setData((overlays.macd || []).map(x => ({ time: Number(x.time), value: Number(x.macd) })));
  macdSignalSeries.setData((overlays.macd || []).map(x => ({ time: Number(x.time), value: Number(x.signal) })));
  macdHistSeries.setData((overlays.macd || []).map(x => ({ time: Number(x.time), value: Number(x.histogram), color: Number(x.histogram) >= 0 ? '#22c55e88' : '#ef444488' })));

  if (candles.length) {
    const latestClose = Number(candles[candles.length - 1].close || 0);
    els.chartPrice.textContent = fmtMoney(latestClose);
    if (els.chartTradeEntry && document.activeElement !== els.chartTradeEntry) els.chartTradeEntry.value = latestClose ? latestClose.toFixed(2) : '';
    const calcEntry = document.getElementById('calcEntry');
    if (calcEntry && document.activeElement !== calcEntry) calcEntry.value = latestClose ? latestClose.toFixed(2) : '';
    calcPositionSize();
  }
}


function renderChartUpdate(data) {
  if (!data) return;
  if ((data.symbol || '').toUpperCase() !== selectedSymbol || (data.timeframe || '1m') !== currentTf) return;
  const c = data.candle || {};
  candleSeries.update({ time: Number(c.time), open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close) });
  volumeSeries.update({ time: Number(c.time), value: Number(c.volume || 0), color: Number(c.close) >= Number(c.open) ? '#22c55e77' : '#ef444477' });
  const ind = data.indicators || {};
  if (ind.vwap != null) vwapSeries.update({ time: Number(c.time), value: Number(ind.vwap) });
  if (ind.ema9 != null) ema9Series.update({ time: Number(c.time), value: Number(ind.ema9) });
  if (ind.ema20 != null) ema20Series.update({ time: Number(c.time), value: Number(ind.ema20) });
  if (ind.macd) {
    macdSeries.update({ time: Number(c.time), value: Number(ind.macd.macd || 0) });
    macdSignalSeries.update({ time: Number(c.time), value: Number(ind.macd.signal || 0) });
    macdHistSeries.update({ time: Number(c.time), value: Number(ind.macd.histogram || 0), color: Number(ind.macd.histogram || 0) >= 0 ? '#22c55e88' : '#ef444488' });
  }
  const latestClose = Number(c.close || 0);
  els.chartPrice.textContent = fmtMoney(latestClose);
  if (els.chartTradeEntry && document.activeElement !== els.chartTradeEntry) els.chartTradeEntry.value = latestClose ? latestClose.toFixed(2) : '';
  const calcEntry = document.getElementById('calcEntry');
  if (calcEntry && document.activeElement !== calcEntry) calcEntry.value = latestClose ? latestClose.toFixed(2) : '';
  calcPositionSize();
}

function connectWs() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${scheme}://${location.host}/ws`);
  ws.onopen = () => { if (selectedSymbol) subscribeChart(selectedSymbol, currentTf); };
  ws.onclose = () => setTimeout(connectWs, 1500);
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const { event: ev, data } = msg;
    if (ev === 'alert_history') (data || []).forEach(a => alertLine(a.message || 'alert'));
    if (ev === 'web_alert') alertLine(data.message || 'alert');
    if (ev === 'scanner_hit') upsertWatchlist(data);
    if (ev === 'scanner_status') {
      statusPill(data.state || 'unknown');
      setSessionBadge(data.session || 'closed');
      updatePrimaryCountdown(data.primary_window);
    }
    if (ev === 'entry_rejected') alertLine(`${data.ticker} entry rejected`);
    if (ev === 'chart_snapshot') renderChartSnapshot(data);
    if (ev === 'chart_candle_update') renderChartUpdate(data);
    if (ev === 'chart_setup' && (data.symbol || '').toUpperCase() === selectedSymbol) drawSetup(data.setup || {});
    if (['trade_opened', 'trade_closed', 'trade_updated', 'position_update', 'config_updated'].includes(ev)) refreshData();
  };
}

function subscribeChart(symbol, timeframe) {
  if (!ws || ws.readyState !== WebSocket.OPEN || !symbol) return;
  ws.send(JSON.stringify({ action: 'subscribe_chart', symbol, timeframe }));
}

function selectSymbol(sym, { switchView = false } = {}) {
  selectedSymbol = (sym || '').toUpperCase();
  els.chartSymbol.textContent = selectedSymbol;
  syncChartTradeForm();
  renderWatchlist(watchlistItems);
  if (switchView) setActiveView('chart');
  subscribeChart(selectedSymbol, currentTf);
  requestAnimationFrame(() => applyChartSizes());
}

function upsertWatchlist(item) {
  if (!item || !item.ticker) return;
  const idx = watchlistItems.findIndex(x => x.ticker === item.ticker);
  if (idx >= 0) watchlistItems[idx] = item;
  else watchlistItems.push(item);
  renderWatchlist(watchlistItems);
  if ((item.ticker || '').toUpperCase() === selectedSymbol) syncChartTradeForm(item);
}

function updatePrimaryCountdown(pw) {
  if (!pw) { els.primaryCountdown.textContent = 'Primary window: --'; return; }
  const secs = Number(pw.countdown_seconds || 0);
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = secs % 60;
  els.primaryCountdown.textContent = pw.is_active
    ? `Primary window ends in ${h}h ${m}m ${s}s`
    : `Primary window starts in ${h}h ${m}m ${s}s`;
}

function normalizeHashView(hash) {
  if (hash === '#analytics') return 'analytics';
  if (hash === '#chart') return 'chart';
  return 'trading';
}

function setActiveView(view, { updateHash = true } = {}) {
  const normalized = view === 'analytics' ? 'analytics' : view === 'chart' ? 'chart' : 'trading';
  state.activeView = normalized;

  els.viewTrading.classList.toggle('hidden', normalized !== 'trading');
  els.viewChart.classList.toggle('hidden', normalized !== 'chart');
  els.viewAnalytics.classList.toggle('hidden', normalized !== 'analytics');
  els.tabTrading.classList.toggle('active', normalized === 'trading');
  els.tabChart.classList.toggle('active', normalized === 'chart');
  els.tabAnalytics.classList.toggle('active', normalized === 'analytics');
  els.tabTrading.setAttribute('aria-selected', String(normalized === 'trading'));
  els.tabChart.setAttribute('aria-selected', String(normalized === 'chart'));
  els.tabAnalytics.setAttribute('aria-selected', String(normalized === 'analytics'));
  document.body.classList.toggle('trading-active', normalized === 'trading');
  document.body.classList.toggle('chart-active', normalized === 'chart');
  document.body.classList.toggle('analytics-active', normalized === 'analytics');

  if (updateHash) {
    const nextHash = normalized === 'analytics' ? '#analytics' : normalized === 'chart' ? '#chart' : '#trading';
    if (window.location.hash !== nextHash) history.replaceState(null, '', nextHash);
  }

  if (normalized === 'chart') {
    requestAnimationFrame(() => {
      applyChartSizes();
    });
  }
}

function initViewTabs() {
  els.tabTrading.onclick = () => setActiveView('trading');
  els.tabChart.onclick = () => setActiveView('chart');
  els.tabAnalytics.onclick = () => setActiveView('analytics');
  if (els.backToTrading) els.backToTrading.onclick = () => setActiveView('trading');

  window.addEventListener('hashchange', () => {
    setActiveView(normalizeHashView(window.location.hash), { updateHash: false });
  });

  document.addEventListener('keydown', (event) => {
    const tag = (event.target?.tagName || '').toLowerCase();
    const isTyping = ['input', 'textarea', 'select'].includes(tag) || event.target?.isContentEditable;
    if (isTyping || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === '1') setActiveView('trading');
    if (event.key === '2') setActiveView('chart');
    if (event.key === '3') setActiveView('analytics');
  });

  setActiveView(normalizeHashView(window.location.hash), { updateHash: !window.location.hash });
}


async function loadThresholds() {
  thresholds = await fetch('/api/scanner/thresholds').then(r => r.json()).catch(() => ({}));
  document.getElementById('setMinGap').value = thresholds.min_gap_percent ?? '';
  document.getElementById('setMinPrice').value = thresholds.min_price ?? '';
  document.getElementById('setMaxPrice').value = thresholds.max_price ?? '';
  document.getElementById('setMinRelVol').value = thresholds.min_relative_volume ?? '';
  document.getElementById('setMaxFloat').value = thresholds.max_float_shares ?? '';
  document.getElementById('setMinPillars').value = thresholds.min_pillars_for_alert ?? '';
  document.getElementById('setStartHour').value = thresholds.start_hour_et ?? '';
  document.getElementById('setEndHour').value = thresholds.end_hour_et ?? '';
  document.getElementById('setPrimaryStart').value = thresholds.primary_window_start_hour_et ?? '';
  document.getElementById('setPrimaryEnd').value = thresholds.primary_window_end_hour_et ?? '';

  const pillars = document.getElementById('pillarsLive');
  pillars.innerHTML = `
    <li>1) Gap % ≥ ${thresholds.min_gap_percent ?? 10}</li>
    <li>2) Price $${thresholds.min_price ?? 2} - $${thresholds.max_price ?? 20}</li>
    <li>3) RelVol ≥ ${thresholds.min_relative_volume ?? 5}x</li>
    <li>4) Float ≤ ${(Number(thresholds.max_float_shares || 20000000) / 1_000_000).toFixed(0)}M</li>
    <li>5) News catalyst required</li>
  `;
}

function renderAlltimePnl(data) {
  const el = els.alltimePnl;
  if (!el) return;
  const pnl = Number(data.total_pnl || 0);
  const trades = Number(data.total_trades || 0);
  const sign = pnl >= 0 ? '+' : '';
  el.textContent = `All-Time: $${sign}${pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${trades} trades)`;
  el.className = pnl >= 0 ? 'green' : 'red';
}

function fmtPnl(v) {
  const n = Number(v || 0);
  return `<span class="${n >= 0 ? 'green' : 'red'}">${n >= 0 ? '+' : '-'}$${Math.abs(n).toFixed(2)}</span>`;
}

function renderAnalyticsEmpty() {
  els.analyticsStreak.textContent = 'No trades in this range.';
  [els.aWinRate, els.aProfitFactor, els.aExpectancy, els.aAvgWinner, els.aAvgLoser, els.aAvgHold, els.aMaxWin, els.aMaxLoss, els.aStreakCard].forEach(el => el.textContent = '—');
  els.aByReason.innerHTML = '';
  els.aByHour.innerHTML = '';
  els.aByDay.innerHTML = '';
  els.aByGrade.innerHTML = '';
}

function renderAnalytics(data, gradeAnalytics = []) {
  if (!data || !data.total_trades) {
    renderAnalyticsEmpty();
    return;
  }

  const streak = data.streak || {};
  els.analyticsStreak.innerHTML = `
    Current streak: <strong>${streak.current || 0} ${streak.type === 'win' ? '🟢 wins' : '🔴 losses'}</strong>
    &nbsp;|&nbsp; Best win streak: <strong>${streak.best_win_streak || 0}</strong>
    &nbsp;|&nbsp; Best loss streak: <strong>${streak.best_loss_streak || 0}</strong>
    &nbsp;|&nbsp; Total trades: <strong>${data.total_trades}</strong>
  `;

  els.aWinRate.textContent = `${Number(data.win_rate || 0).toFixed(1)}%`;
  els.aProfitFactor.textContent = Number(data.profit_factor || 0).toFixed(2);
  const exp = Number(data.expectancy || 0);
  els.aExpectancy.innerHTML = `<span class="${exp >= 0 ? 'green' : 'red'}">${exp >= 0 ? '+' : '-'}$${Math.abs(exp).toFixed(2)}</span>`;
  els.aAvgWinner.textContent = `$${Number(data.avg_winner || 0).toFixed(2)}`;
  els.aAvgLoser.textContent = `$${Math.abs(Number(data.avg_loser || 0)).toFixed(2)}`;
  els.aAvgHold.textContent = `${Number(data.avg_hold_minutes || 0).toFixed(1)}m`;
  els.aMaxWin.textContent = `$${Number(data.max_win || 0).toFixed(2)}`;
  els.aMaxLoss.textContent = `-$${Math.abs(Number(data.max_loss || 0)).toFixed(2)}`;
  els.aStreakCard.textContent = `${streak.current || 0} ${streak.type === 'win' ? 'W' : 'L'}`;

  const reasonLabels = { closed_target: 'Target', closed_stop: 'Stop', closed_time: 'Time', closed_eod: 'EOD' };
  els.aByReason.innerHTML = '';
  Object.entries(data.by_close_reason || {}).forEach(([reason, v]) => {
    const label = reasonLabels[reason] || reason;
    els.aByReason.innerHTML += `<tr><td>${label}</td><td>${v.count}</td><td>${fmtPnl(v.total_pnl)}</td><td>${fmtPnl(v.avg_pnl)}</td></tr>`;
  });

  els.aByHour.innerHTML = '';
  Object.entries(data.by_hour || {}).forEach(([hour, v]) => {
    const h = parseInt(hour, 10);
    const label = isNaN(h) ? hour : (h % 12 || 12) + (h < 12 ? 'am' : 'pm');
    els.aByHour.innerHTML += `<tr><td>${label}</td><td>${v.count}</td><td>${fmtPnl(v.total_pnl)}</td><td>${v.win_rate}%</td></tr>`;
  });

  els.aByDay.innerHTML = '';
  Object.entries(data.by_day_of_week || {}).forEach(([day, v]) => {
    els.aByDay.innerHTML += `<tr><td>${day.slice(0, 3)}</td><td>${v.count}</td><td>${fmtPnl(v.total_pnl)}</td><td>${v.win_rate}%</td></tr>`;
  });

  els.aByGrade.innerHTML = '';
  (gradeAnalytics || []).forEach(item => {
    const label = item.grade === 'ungraded' ? 'Ungraded' : item.grade;
    els.aByGrade.innerHTML += `<tr><td>${label}</td><td>${item.count}</td><td>${fmtPnl(item.avg_pnl)}</td><td>${item.win_rate}%</td></tr>`;
  });
}

function renderTradeLog() {
  const journalByTradeId = Object.fromEntries((state.journalEntries || []).map(entry => [Number(entry.trade_id), entry]));
  const filtered = (state.allTrades || []).filter(trade => {
    if (state.tradeLogFilter === 'open') return trade.status === 'open';
    if (state.tradeLogFilter === 'winner') return trade.status !== 'open' && Number(trade.pnl || 0) > 0;
    if (state.tradeLogFilter === 'loser') return trade.status !== 'open' && Number(trade.pnl || 0) <= 0;
    return true;
  });

  els.tradeLogBody.innerHTML = '';
  filtered.forEach(trade => {
    const pnl = trade.status === 'open' ? Number(trade.unrealized_pnl || 0) : Number(trade.pnl || 0);
    const journal = journalByTradeId[Number(trade.id)];
    const tr = document.createElement('tr');
    tr.className = 'trade-log-row';
    tr.dataset.tradeId = String(trade.id);
    tr.innerHTML = `
      <td>${trade.id || ''}</td>
      <td>${trade.ticker || '-'}</td>
      <td>${Number(trade.entry_price || 0).toFixed(2)}</td>
      <td>${trade.exit_price != null ? Number(trade.exit_price).toFixed(2) : '-'}</td>
      <td class="${pnl >= 0 ? 'green' : 'red'}">${pnl.toFixed(2)}</td>
      <td>${trade.status || ''}</td>
      <td>${fmtDateTimeET(trade.entry_time)}</td>
      <td>${trade.exit_time ? fmtDateTimeET(trade.exit_time) : '-'}</td>
      <td><div class="grade-cell">${renderGradeCell(trade.id, journal?.grade, trade.status)}</div><button class="journal-btn" data-tradeid="${trade.id}" title="Journal this trade">${journal ? '✅' : '📝'}</button></td>
    `;

    const detail = document.createElement('tr');
    detail.className = 'trade-log-detail hidden';
    const detailCell = document.createElement('td');
    detailCell.colSpan = 9;
    if (isClosedTradeStatus(trade.status) && !journal?.grade) tr.classList.add('needs-grade');
    detailCell.innerHTML = journal ? `
      <div class="trade-log-meta">
        <span><strong>Setup:</strong> ${journal.setup_type || '—'}</span>
        <span><strong>Emotion:</strong> ${journal.emotional_state || '—'}</span>
        <span><strong>Grade:</strong> ${journal.grade || '—'}</span>
        <span><strong>Mistakes:</strong> ${journal.mistakes || '—'}</span>
        <span><strong>Close:</strong> ${trade.close_reason || '—'}</span>
      </div>
      <div class="trade-log-note">${journal.notes || 'No journal notes yet.'}</div>
    ` : `<div class="trade-log-note muted">No journal entry yet. Click 📝 to add one.</div>`;
    detail.appendChild(detailCell);

    tr.addEventListener('click', () => {
      const expanded = detail.classList.toggle('hidden') === false;
      tr.classList.toggle('expanded', expanded);
    });

    tr.querySelector('.journal-btn').addEventListener('click', (event) => {
      event.stopPropagation();
      openJournalModal(Number(event.currentTarget.dataset.tradeid));
    });

    els.tradeLogBody.appendChild(tr);
    els.tradeLogBody.appendChild(detail);
  });
  bindGradeButtons(els.tradeLogBody);
}

async function refreshData() {
  const [watchlist, scannerStatus, positions, history, simStatus, alltime, journalAll, analytics, gradeAnalytics, allTrades] = await Promise.all([
    fetch('/api/scanner/watchlist').then(r => r.json()).catch(() => ({ items: [] })),
    fetch('/api/scanner/status').then(r => r.json()).catch(() => ({})),
    fetch('/api/simulator/positions').then(r => r.json()).catch(() => ({ items: [] })),
    fetch('/api/simulator/history').then(r => r.json()).catch(() => ({ items: [], stats: {} })),
    fetch('/api/simulator/status').then(r => r.json()).catch(() => ({})),
    fetch('/api/simulator/alltime').then(r => r.json()).catch(() => ({ total_pnl: 0, total_trades: 0 })),
    fetch('/api/journal').then(r => r.json()).catch(() => ({ items: [] })),
    fetch(`/api/analytics/summary?range=${encodeURIComponent(state.analyticsRange)}`).then(r => r.json()).catch(() => ({})),
    fetch(`/api/analytics/grades?range=${encodeURIComponent(state.analyticsRange)}`).then(r => r.json()).catch(() => ({ items: [] })),
    fetch('/api/trades?limit=100000').then(r => r.json()).catch(() => ({ items: [] })),
  ]);

  journalEntryMap = {};
  (journalAll.items || []).forEach(e => { journalEntryMap[e.trade_id] = true; });
  state.journalEntries = journalAll.items || [];
  state.allTrades = allTrades.items || [];
  state.gradeAnalytics = gradeAnalytics.items || [];
  state.tradeLogFilter = els.tradeLogFilter?.value || state.tradeLogFilter;
  promptForNewlyClosedTrades(state.allTrades);

  watchlistItems = watchlist.items || [];
  renderWatchlist(watchlistItems);
  els.watchlistLoading.style.display = 'none';

  statusPill(scannerStatus.state || 'unknown');
  setSessionBadge(scannerStatus.session || 'closed');
  updatePrimaryCountdown(scannerStatus.primary_window);

  renderPositions(positions);
  renderHistory(history);
  renderTradeLog();
  updateLossMeter(simStatus);
  renderAlltimePnl(alltime);
  renderAnalytics(analytics, state.gradeAnalytics);

  if (!selectedSymbol && watchlistItems.length) selectSymbol(watchlistItems[0].ticker);
  else syncChartTradeForm();
}

function initGlossary() {
  document.getElementById('howItWorks').textContent = HOW_IT_WORKS;
  const defs = document.getElementById('glossaryDefs');
  defs.innerHTML = Object.entries(GLOSSARY).map(([k, v]) => `<p><strong>${k}:</strong> ${v}</p>`).join('');
  document.getElementById('glossaryToggle').onclick = () => {
    document.getElementById('glossaryContent').classList.toggle('hidden');
  };
}

function initSettings() {
  els.settingsBtn.onclick = () => els.settingsPanel.classList.remove('hidden');
  els.settingsClose.onclick = () => els.settingsPanel.classList.add('hidden');
  els.saveSettings.onclick = async () => {
    els.saveStatus.textContent = 'Saving...';
    const scannerPayload = {
      min_gap_percent: Number(document.getElementById('setMinGap').value),
      min_price: Number(document.getElementById('setMinPrice').value),
      max_price: Number(document.getElementById('setMaxPrice').value),
      min_relative_volume: Number(document.getElementById('setMinRelVol').value),
      max_float_shares: Number(document.getElementById('setMaxFloat').value),
      min_pillars_for_alert: Number(document.getElementById('setMinPillars').value),
      start_hour_et: Number(document.getElementById('setStartHour').value),
      end_hour_et: Number(document.getElementById('setEndHour').value),
      primary_window_start_hour_et: Number(document.getElementById('setPrimaryStart').value),
      primary_window_end_hour_et: Number(document.getElementById('setPrimaryEnd').value),
    };
    const accountPayload = { account_size: Number(document.getElementById('setAccountSize').value || 0) };

    await fetch('/api/scanner/thresholds', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(scannerPayload) });
    if (accountPayload.account_size > 0) {
      await fetch('/api/simulator/account', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(accountPayload) });
    }
    await fetch('/api/settings/telegram', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: els.telegramToggle.checked }) });

    els.saveStatus.textContent = '✓ Saved';
    setTimeout(() => { els.settingsPanel.classList.add('hidden'); els.saveStatus.textContent = ''; }, 800);
    await loadThresholds();
    await refreshData();
  };
}

function initTelegramToggle() {
  els.telegramToggle.onchange = async () => {
    await fetch('/api/settings/telegram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: els.telegramToggle.checked }),
    });
  };
}

async function openJournalModal(tradeId) {
  currentJournalGrade = null;
  document.getElementById('journalTradeId').value = tradeId;
  document.getElementById('journalSetup').value = '';
  document.getElementById('journalEmotion').value = '';
  document.getElementById('journalNotes').value = '';
  document.querySelectorAll('.grade-btn').forEach(b => b.className = 'grade-btn');
  document.querySelectorAll('.mistakes-grid input[type=checkbox]').forEach(cb => cb.checked = false);

  try {
    const res = await fetch(`/api/journal/${tradeId}`);
    const data = await res.json();
    if (data.entry) {
      const e = data.entry;
      if (e.setup_type) document.getElementById('journalSetup').value = e.setup_type;
      if (e.emotional_state) document.getElementById('journalEmotion').value = e.emotional_state;
      if (e.notes) document.getElementById('journalNotes').value = e.notes;
      if (e.grade) {
        currentJournalGrade = e.grade;
        document.querySelectorAll('.grade-btn').forEach(b => {
          b.className = 'grade-btn' + (b.dataset.grade === e.grade ? ` active-${e.grade}` : '');
        });
      }
      if (e.mistakes) {
        const mistakes = e.mistakes.split(',').map(m => m.trim()).filter(Boolean);
        document.querySelectorAll('.mistakes-grid input[type=checkbox]').forEach(cb => {
          cb.checked = mistakes.includes(cb.value);
        });
      }
    }
  } catch (err) {}

  document.getElementById('journalModal').classList.add('active');
}

function initJournalModal() {
  document.getElementById('journalModalClose').onclick = () => {
    document.getElementById('journalModal').classList.remove('active');
  };
  document.getElementById('journalModal').onclick = (e) => {
    if (e.target === document.getElementById('journalModal')) {
      document.getElementById('journalModal').classList.remove('active');
    }
  };

  document.querySelectorAll('.grade-btn').forEach(btn => {
    btn.onclick = () => {
      currentJournalGrade = btn.dataset.grade;
      document.querySelectorAll('.grade-btn').forEach(b => b.className = 'grade-btn');
      btn.className = `grade-btn active-${btn.dataset.grade}`;
    };
  });

  document.getElementById('journalSave').onclick = async () => {
    const tradeId = Number(document.getElementById('journalTradeId').value);
    const mistakes = Array.from(document.querySelectorAll('.mistakes-grid input[type=checkbox]:checked'))
      .map(cb => cb.value).join(',');
    const payload = {
      setup_type: document.getElementById('journalSetup').value || null,
      emotional_state: document.getElementById('journalEmotion').value || null,
      grade: currentJournalGrade || null,
      notes: document.getElementById('journalNotes').value || null,
      mistakes: mistakes || null,
    };
    try {
      const res = await fetch(`/api/journal/${tradeId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        journalEntryMap[tradeId] = true;
        document.getElementById('journalModal').classList.remove('active');
        await refreshData();
      }
    } catch (err) {
      console.error('Journal save failed', err);
    }
  };
}

function initAnalyticsControls() {
  document.querySelectorAll('.date-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.date-btn').forEach(x => x.classList.remove('active'));
      btn.classList.add('active');
      state.analyticsRange = btn.dataset.range || 'alltime';
      await refreshData();
    });
  });

  document.querySelectorAll('.breakdown-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      state.analyticsBreakdown = btn.dataset.table || 'byReason';
      document.querySelectorAll('.breakdown-tab').forEach(x => x.classList.toggle('active', x === btn));
      document.getElementById('breakdownByReason').classList.toggle('hidden', state.analyticsBreakdown !== 'byReason');
      document.getElementById('breakdownByHour').classList.toggle('hidden', state.analyticsBreakdown !== 'byHour');
      document.getElementById('breakdownByDay').classList.toggle('hidden', state.analyticsBreakdown !== 'byDay');
      document.getElementById('breakdownByGrade').classList.toggle('hidden', state.analyticsBreakdown !== 'byGrade');
    });
  });

  els.tradeLogFilter.addEventListener('change', () => {
    state.tradeLogFilter = els.tradeLogFilter.value;
    renderTradeLog();
  });
}

function calcPositionSize() {
  const account = parseFloat(document.getElementById('calcAccount').value) || 0;
  const riskPct = parseFloat(document.getElementById('calcRisk').value) || 0;
  const entry = parseFloat(document.getElementById('calcEntry').value) || 0;
  const stop = parseFloat(document.getElementById('calcStop').value) || 0;
  const target = parseFloat(document.getElementById('calcTarget').value) || 0;

  const riskDollars = account * riskPct / 100;
  document.getElementById('calcRiskDollars').textContent = `Risk: $${riskDollars.toFixed(2)}`;

  const stopDist = Math.abs(entry - stop);
  if (!stopDist || !entry || !stop || entry === stop) {
    document.getElementById('calcShares').textContent = '—';
    if (els.chartTradeShares && document.activeElement !== els.chartTradeShares) els.chartTradeShares.value = '';
    document.getElementById('calcDollarRisk').textContent = '—';
    document.getElementById('calcRR').textContent = '—';
    return;
  }

  const shares = Math.floor(riskDollars / stopDist);
  const dollarRisk = shares * stopDist;
  document.getElementById('calcShares').textContent = shares.toLocaleString();
  if (els.chartTradeShares && document.activeElement !== els.chartTradeShares) {
    els.chartTradeShares.value = shares > 0 ? String(shares) : '';
  }
  document.getElementById('calcDollarRisk').textContent = `$${dollarRisk.toFixed(2)}`;

  if (target && target !== entry) {
    const reward = Math.abs(target - entry);
    const rr = reward / stopDist;
    document.getElementById('calcRR').textContent = `${rr.toFixed(2)}:1`;
  } else {
    document.getElementById('calcRR').textContent = '—';
  }
}

function initChartTradeForm() {
  if (!els.chartTradeForm) return;
  els.chartTradeForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const ticker = (els.chartTradeTicker?.value || selectedSymbol || '').toUpperCase();
    const price = Number(els.chartTradeEntry?.value || 0);
    if (!ticker || !price) return;
    state.pendingTradeEntry = {
      ticker,
      price,
      shares: Number(els.chartTradeShares?.value || 0) || null,
    };
    const item = getSelectedWatchlistItem() || { ticker, price };
    openPreTradeModal(item);
  });
}

function initPositionCalculator() {
  const savedAccount = localStorage.getItem('calcAccount');
  const savedRisk = localStorage.getItem('calcRisk');
  if (savedAccount) document.getElementById('calcAccount').value = savedAccount;
  if (savedRisk) document.getElementById('calcRisk').value = savedRisk;

  ['calcAccount', 'calcRisk', 'calcEntry', 'calcStop', 'calcTarget'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
      calcPositionSize();
      localStorage.setItem('calcAccount', document.getElementById('calcAccount').value);
      localStorage.setItem('calcRisk', document.getElementById('calcRisk').value);
    });
  });

  calcPositionSize();
}

async function init() {
  initGlossary();
  initSettings();
  initTelegramToggle();
  initJournalModal();
  initPreTradeModal();
  initPositionCalculator();
  initChartTradeForm();
  initViewTabs();
  initAnalyticsControls();

  const settings = await fetch('/api/settings').then(r => r.json()).catch(() => ({ telegram_enabled: true }));
  els.telegramToggle.checked = settings.telegram_enabled !== false;

  const sim = await fetch('/api/simulator/status').then(r => r.json()).catch(() => ({}));
  document.getElementById('setAccountSize').value = sim?.run_controls?.account_size || 25000;

  document.querySelectorAll('.tf-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.tf-btn').forEach(x => x.classList.remove('active'));
      btn.classList.add('active');
      currentTf = btn.dataset.tf;
      subscribeChart(selectedSymbol, currentTf);
    };
  });

  await loadThresholds();
  await refreshData();
  connectWs();

  setInterval(refreshData, 10000);
}

init();
