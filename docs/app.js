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
