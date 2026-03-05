# DESIGN_V1

## 1. 전략 개요
- Regime-aware swing strategy
- 돌파/눌림 진입 병행
- 분할익절 + 트레일링 잔량 운용

## 2. 확정 파라미터
- Universe: KRW-BTC, KRW-ETH, KRW-SOL, KRW-XRP
- Main timeframe: 15m
- Confirm timeframe: 1h
- Timing timeframe: 5m
- Max positions: 4
- Initial capital: 10,000,000 KRW
- Risk per trade: 0.6%
- Daily loss limit: -5%

## 3. 시그널 파이프라인
1) Data fetch (OHLCV)
2) Feature calc (EMA, RSI, ATR, volume z-score)
3) Regime classify (UP/RANGE/DOWN/SHOCK)
4) Signal score (0~100)
5) Risk filters
6) Entry/Exit decision
7) Paper fill
8) Logging/notification

## 4. 진입/청산 규칙(v1)
- Entry threshold: score >= 70
- TP: 30% @ 1.8R, 30% @ 3.0R, 40% trailing
- Stop: ATR-based (2~4% range equivalent)
- Re-entry cooldown: 45 min after stop

## 5. 성과 평가(1주)
- MDD <= 6%
- Profit Factor >= 1.25
- EV > 0
- Max consecutive losses <= 5
- Total trades >= 25
