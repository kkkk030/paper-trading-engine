# Paper Trading Engine (v1)

코인실장 x 코딩실장 협업용 페이퍼 트레이딩 프로젝트.

## 목적
- 실주문 없이 신호 생성/가상체결/성과평가를 1주간 수행
- 전략 파라미터 튜닝 후 실거래 엔진으로 확장

## v1 고정 조건
- Universe: BTC, ETH, SOL, XRP (KRW 마켓)
- Main TF: 15m (보조: 1h, 5m)
- Max concurrent positions: 4
- Paper capital: 10,000,000 KRW
- Risk per trade: 0.6% of equity
- Daily stop: -5%
- 24h 운영
- 체결 이벤트 즉시 알림

## 폴더 구조
- `docs/` 설계 문서
- `config/` 파라미터
- `src/` 엔진 코드
- `data/` 로우/가공 데이터
- `logs/` 실행 로그
- `reports/` 일일/주간 리포트
- `scripts/` 실행 스크립트

## 실행(초기)
```bash
cd projects/paper-trading-engine
# 15분 진입 판단 사이클
python3 scripts/run_hybrid_cycle.py --mode entry
# 1~5분 리스크 감시 사이클
python3 scripts/run_hybrid_cycle.py --mode risk
```

- `run_hybrid_cycle.py --mode entry`: 시그널 계산 + 가상체결(신규진입 포함)
- `run_hybrid_cycle.py --mode risk`: 포지션 리스크 관리만(신규진입 없음)
- 상태 파일: `data/paper_state.json` (equity/cash/positions/fees 포함)
- 체결 로그: `logs/trades.jsonl`
- 최신 리포트: `reports/latest_cycle.json`
- 수수료: `config/strategy_v1.json`의 `fee_rate` 적용 (기본 0.0005 = 0.05%)

## 대시보드
- 경로: `dashboard/index.html`
- 구조: 실시간 스트리밍이 아닌 수동 새로고침 버튼 방식

## 주의
- 본 프로젝트는 페이퍼 트레이딩 전용이며, 업비트 주문 API 호출을 포함하지 않음.
