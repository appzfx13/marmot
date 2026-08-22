from django.db import models


class BacktestRuleTypeChoices(models.TextChoices):
    INTRADAY = 'intraday', 'Intraday Only'
    GAMMA_BLAST = 'gamma_blast', 'Gamma Blast (0DTE Expiry)'
    MORNING_TREND = 'morning_trend', 'Morning Trend Capture'
    GAP_OPENINGS = 'gap_openings', 'Overnight Gap Prediction (BTST / STBT)'
    RISK_MANAGEMENT = 'risk_management', 'Strict SL & TP Placement'
    RETEST_LIMIT = 'retest_limit', 'Retest Limit Entry (No Market Orders)'
    TRENDLINE_RETEST = 'trendline_retest', 'Trendline Breakout & Retest'
    CUSTOM_PROMPT = 'custom_prompt', 'AI Prompt Directive'
    TECHNICAL = 'technical', 'Technical / Indicator'
