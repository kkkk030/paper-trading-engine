async function loadData() {
  const res = await fetch('./latest_cycle.json?ts=' + Date.now());
  if (!res.ok) throw new Error('latest_cycle.json load failed');
  return await res.json();
}

function won(n){return Number(n||0).toLocaleString('ko-KR')}

function render(d){
  document.getElementById('updatedAt').textContent = `updated: ${d.generatedAt} (${d.mode})`;
  const s = d.state;
  const positions = s.positions || {};
  const invested = Object.entries(positions).reduce((acc,[sym,p])=>acc + (p.qty * (d.prices?.[sym] || p.entry)),0);
  const dailyPct = ((s.daily.realized / s.daily.start_equity) * 100) || 0;
  document.getElementById('summary').innerHTML = `
    <h2>Summary</h2>
    <div class='item'>Equity: <b>${won(s.equity)}</b> KRW</div>
    <div class='item'>Cash: <b>${won(s.cash)}</b> KRW</div>
    <div class='item'>Invested (MTM): <b>${won(invested)}</b> KRW</div>
    <div class='item'>Open Positions: <b>${Object.keys(positions).length}</b></div>
    <div class='item'>Daily Realized: <b class='${dailyPct>=0?'good':'bad'}'>${won(s.daily.realized)} KRW (${dailyPct.toFixed(2)}%)</b></div>
    <div class='item'>Daily Fees: <b>${won(s.daily?.fees || 0)}</b> KRW / Total Fees: <b>${won(s.fee_total || 0)}</b> KRW</div>
  `;

  const sig = d.signals||[];
  document.getElementById('signals').innerHTML = sig.length ? sig.map(x=>`<div class='item'>${x.symbol} score=<b>${x.score}</b> regime=${x.regime} action=<b>${x.action}</b><div class='muted'>${x.reason}</div></div>`).join('') : `<div class='muted'>risk mode cycle (signals skipped)</div>`;

  const alerts = d.alerts||[];
  document.getElementById('alerts').innerHTML = alerts.length ? alerts.map(a=>`<div class='item'>${a}</div>`).join('') : `<div class='muted'>no alerts</div>`;

  const pos = s.positions || {};
  const keys = Object.keys(pos);
  document.getElementById('positions').innerHTML = keys.length ? keys.map(k=>{
    const p=pos[k];
    const now = d.prices?.[k] || p.entry;
    const u = (now - p.entry) * p.qty;
    return `<div class='item'>${k} qty=${p.qty.toFixed(6)} entry=${won(p.entry)} now=${won(now)} stop=${won(p.stop)} uPnL=<span class='${u>=0?'good':'bad'}'>${won(u)}</span> tp1=${p.tp1_done?'Y':'N'} tp2=${p.tp2_done?'Y':'N'}</div>`;
  }).join('') : `<div class='muted'>no open positions</div>`;

  const trades = d.recentTrades || [];
  document.getElementById('trades').innerHTML = trades.length ? trades.slice().reverse().map(t=>{
    const pnl = Number(t.pnl || 0);
    const fee = Number(t.fee || 0);
    return `<div class='item'>${t.ts} | ${t.symbol} ${t.kind} ${t.side} qty=${Number(t.qty||0).toFixed(6)} price=${won(t.price)} fee=${won(fee)} pnl=<span class='${pnl>=0?'good':'bad'}'>${won(pnl)}</span></div>`;
  }).join('') : `<div class='muted'>no trade history yet</div>`;
}

async function refresh(){
  try{ render(await loadData()); }
  catch(e){
    document.getElementById('summary').innerHTML = `<div class='bad'>${e.message}</div>`;
  }
}

document.getElementById('refreshBtn').addEventListener('click', refresh);
refresh();
