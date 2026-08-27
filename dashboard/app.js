async function loadData() {
  const ts = Date.now();
  const candidates = [
    `./latest_cycle.json?ts=${ts}`,
    `https://raw.githubusercontent.com/kkkk030/paper-trading-engine/main/docs/latest_cycle.json?ts=${ts}`,
    `../reports/latest_cycle.json?ts=${ts}`,
    `./docs/latest_cycle.json?ts=${ts}`,
  ];

  let lastErr = null;
  for (const url of candidates) {
    try {
      const res = await fetch(url);
      if (!res.ok) {
        lastErr = new Error(`${url} (${res.status})`);
        continue;
      }
      return await res.json();
    } catch (e) {
      lastErr = e;
    }
  }
  throw new Error(`latest_cycle.json 로드 실패: ${lastErr?.message || 'unknown error'}`);
}

function won(n){return Number(n||0).toLocaleString('ko-KR')}
function pct(n){return `${(Number(n||0)*100).toFixed(2)}%`}

function render(d){
  document.getElementById('updatedAt').textContent = `업데이트: ${d.generatedAt} (${d.mode})`;
  const s = d.state;
  const positions = s.positions || {};
  const invested = Object.entries(positions).reduce((acc,[sym,p])=>acc + (p.qty * (d.prices?.[sym] || p.entry)),0);
  const dailyPct = ((s.daily.realized / s.daily.start_equity) * 100) || 0;
  document.getElementById('summary').innerHTML = `
    <h2>요약</h2>
    <div class='item'>총자산(Equity): <b>${won(s.equity)}</b> KRW</div>
    <div class='item'>현금 보유(Cash): <b>${won(s.cash)}</b> KRW</div>
    <div class='item'>보유 평가금액(MTM): <b>${won(invested)}</b> KRW</div>
    <div class='item'>보유 포지션 수: <b>${Object.keys(positions).length}</b></div>
    <div class='item'>금일 실현손익: <b class='${dailyPct>=0?'good':'bad'}'>${won(s.daily.realized)} KRW (${dailyPct.toFixed(2)}%)</b></div>
    <div class='item'>금일 수수료: <b>${won(s.daily?.fees || 0)}</b> KRW / 누적 수수료: <b>${won(s.fee_total || 0)}</b> KRW</div>
  `;

  const rc = d.riskControls || {};
  document.getElementById('riskControls').innerHTML = `
    <div class='item'>1회 거래 리스크: <b>${pct(rc.risk_per_trade)}</b> / 일 손실 중지: <b>${pct(rc.daily_loss_limit)}</b></div>
    <div class='item'>최대 동시 포지션: <b>${rc.max_positions || '-'}</b> / 손절 확인: <b>${rc.stop_confirm_bars || '-'}회</b></div>
    <div class='item'>ATR 손절: <b>${rc.stop_atr_mult || '-'}배</b> / 범위 <b>${pct(rc.stop_pct_min)}~${pct(rc.stop_pct_max)}</b></div>
    <div class='item'>하드스탑: <b>${pct(rc.hard_stop_pct)}</b> / TP2 이후 트레일링: <b>${pct(rc.trailing_stop_pct)}</b></div>
  `;

  const sh = d.shadow?.shadow || {};
  const diff = Number(sh.equity || 0) - Number(s.equity || 0);
  document.getElementById('shadow').innerHTML = Object.keys(sh).length ? `
    <div class='item'>Shadow Equity: <b>${won(sh.equity)}</b> KRW / Live 대비 <b class='${diff>=0?'good':'bad'}'>${diff>=0?'+':''}${won(diff)}</b> KRW</div>
    <div class='item'>Shadow 현금: <b>${won(sh.cash)}</b> KRW / 포지션: <b>${sh.positions || 0}</b>개</div>
    <div class='item'>Shadow 당일실현: <b class='${Number(sh.daily_realized || 0)>=0?'good':'bad'}'>${won(sh.daily_realized)}</b> KRW / 알림: <b>${sh.alerts || 0}</b>건</div>
  ` : `<div class='muted'>섀도우 비교 데이터 없음</div>`;

  const sig = d.signals||[];
  document.getElementById('signals').innerHTML = sig.length ? sig.map(x=>`<div class='item'>${x.symbol} 점수=<b>${x.score}</b> 장세=${x.regime} 액션=<b>${x.action}</b><div class='muted'>${x.reason}</div></div>`).join('') : `<div class='muted'>리스크 모드 사이클 (신호 계산 생략)</div>`;

  const alerts = d.alerts||[];
  document.getElementById('alerts').innerHTML = alerts.length ? alerts.map(a=>`<div class='item'>${a}</div>`).join('') : `<div class='muted'>알림 없음</div>`;

  const pos = s.positions || {};
  const keys = Object.keys(pos);
  document.getElementById('positions').innerHTML = keys.length ? keys.map(k=>{
    const p=pos[k];
    const now = d.prices?.[k] || p.entry;
    const u = (now - p.entry) * p.qty;
    return `<div class='item'>${k} 수량=${p.qty.toFixed(6)} 진입가=${won(p.entry)} 현재가=${won(now)} 손절가=${won(p.stop)} 미실현손익=<span class='${u>=0?'good':'bad'}'>${won(u)}</span> 1차익절=${p.tp1_done?'Y':'N'} 2차익절=${p.tp2_done?'Y':'N'}</div>`;
  }).join('') : `<div class='muted'>보유 포지션 없음</div>`;

  const trades = d.recentTrades || [];
  document.getElementById('trades').innerHTML = trades.length ? trades.slice().reverse().map(t=>{
    const pnl = Number(t.pnl || 0);
    const fee = Number(t.fee || 0);
    return `<div class='item'>${t.ts} | ${t.symbol} ${t.kind} ${t.side} 수량=${Number(t.qty||0).toFixed(6)} 가격=${won(t.price)} 수수료=${won(fee)} 손익=<span class='${pnl>=0?'good':'bad'}'>${won(pnl)}</span></div>`;
  }).join('') : `<div class='muted'>체결 내역 없음</div>`;
}

async function refresh(){
  try{ render(await loadData()); }
  catch(e){
    document.getElementById('summary').innerHTML = `<div class='bad'>${e.message}</div>`;
  }
}

document.getElementById('refreshBtn').addEventListener('click', refresh);
refresh();
