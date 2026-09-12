from django.db import models
from apps.common.choices import MarketTypeChoices


class RuleMarketTypeChoices(models.TextChoices):
    INDEX_FO = MarketTypeChoices.INDEX_FO.value, MarketTypeChoices.INDEX_FO.label
    FOREX_FUTURES = MarketTypeChoices.FOREX_FUTURES.value, MarketTypeChoices.FOREX_FUTURES.label
    ALL = 'ALL', 'All Markets (Shared)'


class BacktestRuleTypeChoices(models.TextChoices):
    INTRADAY = 'intraday', 'Intraday Only'
    GAMMA_BLAST = 'gamma_blast', 'Gamma Blast (0DTE Expiry)'
    MORNING_TREND = 'morning_trend', 'Morning Trend Capture'
    GAP_OPENINGS = 'gap_openings', 'Overnight Gap Prediction (BTST / STBT)'
    RISK_MANAGEMENT = 'risk_management', 'Strict SL & TP Placement'
    RETEST_LIMIT = 'retest_limit', 'Retest Limit Entry (No Market Orders)'
    TRENDLINE_RETEST = 'trendline_retest', 'Trendline Breakout & Retest'
    INDIA_VIX = 'india_vix', 'India VIX Volatility Regime'
    LOSS_RCA = 'loss_rca', 'Stop-Loss RCA & Learning Engine'
    ATR_NOISE_FILTER = 'atr_noise_filter', 'Dynamic ATR Volatility Buffer (Anti-Noise)'
    CANDLE_CLOSE_SL = 'candle_close_sl', 'Candle Close SL & Anti-Wick Guardrail'
    LIQUIDITY_SWEEP = 'liquidity_sweep', 'Liquidity Sweep & False Breakout Filter (SMC)'
    PDH_PDL = 'pdh_pdl', 'PDH & PDL Breakout / Liquidity Sweep Filter'
    ICT_SMC = 'ict_smc_matrix', 'ICT Institutional Smart Money (Killzone, MSS, FVG & OTE)'
    ICT_SMC_V2 = 'ict_smc_v2', 'ICT v2: Confirmed OTE Retest & Mitigation (Zero Drawdown)'
    ICT_SMC_V3 = 'ict_smc_v3', 'ICT v3: Institutional Displacement, HTF Bias & Liquidity Sweep Engine'
    ICT_SMC_V4_LAYERING = 'ict_smc_v4_layering', 'ICT v4: Multi-Timeframe CHoCH & 0.5/0.705 Dual Layering OTE'
    MORNING_MACD_RETEST = 'morning_macd_retest', 'Morning 3-Min HTF & Option MACD Retest'
    FOREX_CVD_DIVERGENCE = 'forex_cvd_divergence', 'Forex CVD (Cumulative Volume Delta) Divergence'
    FOREX_DOM_ABSORPTION = 'forex_dom_absorption', 'Forex Level-10 DOM Depth & Iceberg Absorption'
    FOREX_KILLZONE_DELTA = 'forex_killzone_delta', 'Forex London & NY Killzone Order Flow Surge'
    FOREX_SMC_DISPLACEMENT = 'forex_smc_displacement', 'Forex SMC Displacement & FVG Retest'
    CUSTOM_PROMPT = 'custom_prompt', 'AI Prompt Directive'
    TECHNICAL = 'technical', 'Technical / Indicator'
    MOMENTUM_GUARDRAIL = 'momentum_guardrail', 'Professional Intraday Trend & Momentum Guardrails'
    ALGO_MICRO_SCALP = 'algo_micro_scalp', 'Institutional Micro-Scalp & Dynamic Risk Guard'

