from django.db import models


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
    MORNING_MACD_RETEST = 'morning_macd_retest', 'Morning 3-Min HTF & Option MACD Retest'
    CUSTOM_PROMPT = 'custom_prompt', 'AI Prompt Directive'
    TECHNICAL = 'technical', 'Technical / Indicator'
