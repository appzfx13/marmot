from django.core.management.base import BaseCommand
from apps.backtest.models import BacktestRule
from apps.backtest.choices import BacktestRuleTypeChoices, RuleMarketTypeChoices


class Command(BaseCommand):
    """Seeds professional Backtest Strategy Rules for the RL trading engine."""

    help = "Seeds clean, institutional Backtest Strategy Rules for the RL trading engine."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            default=False,
            help='Removes legacy outdated micro-rules before seeding.'
        )

    def handle(self, *args, **options):
        clean_legacy = options.get('clean', False)

        if clean_legacy:
            deleted = BacktestRule.all_objects.all().hard_delete()
            self.stdout.write(self.style.WARNING(f"Removed legacy rules from database: {deleted}"))

        rules_data = [
            {
                "name": "ICT Smart Money: CHoCH & Liquidity Sweep Retest",
                "rule_type": BacktestRuleTypeChoices.ICT_SMC,
                "market_type": RuleMarketTypeChoices.ALL,
                "description": (
                    "Multi-Timeframe (15m HTF -> 1m LTF) institutional SMC strategy. Identifies Higher Timeframe "
                    "Market Structure & CHoCH, waits for Lower Timeframe liquidity sweep / Fair Value Gap (FVG) "
                    "pullback, and enters strictly via LIMIT ORDER at the retest level (Market chase prohibited). "
                    "Stop Loss anchored below swing low and Target at major external liquidity resistance."
                ),
                "prompt_directive": (
                    "Perform Multi-Timeframe analysis: Use 15m HTF for directional bias and 1m/3m LTF for precision entry. "
                    "Detect Change of Character (CHoCH) breakout. Wait for liquidity sweep retracement into Fair Value Gap (FVG) / "
                    "Order Block. Place strict LIMIT ORDER at the retest level (NO MARKET CHASE). Enforce SL below structural "
                    "swing low and target external liquidity resistance (1:2.5+ R:R). Auto-cancel if unfilled within 3 bars."
                ),
                "parameters": {
                    "htf_timeframe": "15m",
                    "ltf_timeframe": "1m",
                    "mtf_bias_filter": True,
                    "structure_signal": "CHOCH",
                    "entry_trigger": "LIQUIDITY_SWEEP_RETEST",
                    "fvg_detection": True,
                    "liquidity_sweep_detection": True,
                    "order_execution_type": "LIMIT_ONLY",
                    "limit_retest_anchor": "ORDERBLOCK_EQUILIBRIUM_FVG",
                    "cancel_unfilled_bars": 3,
                    "sl_anchor": "SWING_LOW",
                    "target_anchor": "EXTERNAL_LIQUIDITY_HIGH",
                    "min_risk_reward": 2.5,
                    "killzone_filter": True,
                },
                "is_system_preset": True,
                "is_active": True,
            },
            {
                "name": "ICT Smart Money v2: Confirmed OTE Retest & Mitigation (Zero Drawdown)",
                "rule_type": BacktestRuleTypeChoices.ICT_SMC_V2,
                "market_type": RuleMarketTypeChoices.ALL,
                "description": (
                    "Multi-Timeframe ICT v2 sniper execution. Stage 1 detects displacement CHoCH or sweep. "
                    "Stage 2 waits for confirmed retracement into the 50%-78.6% OTE equilibrium / FVG mitigation zone "
                    "before entering. Anchors tight SL behind invalidation swing level, eliminating adverse drawdown "
                    "and securing 1:3.5+ RR."
                ),
                "prompt_directive": (
                    "Detect initial CHoCH or liquidity sweep displacement. DO NOT enter on initial spike. "
                    "Establish OTE (50%-78.6%) and FVG mitigation zone. Place resting limit order and execute only upon "
                    "confirmed retest wick rejection. Anchor tight SL behind displacement swing and target external "
                    "liquidity resistance (1:3.5+ RR)."
                ),
                "parameters": {
                    "htf_timeframe": "15m",
                    "ltf_timeframe": "1m",
                    "ote_fib_min": 0.50,
                    "ote_fib_max": 0.786,
                    "fvg_mitigation_filter": True,
                    "zero_drawdown_limit": True,
                    "min_risk_reward": 3.5,
                    "sl_pts": 8.0,
                    "invalidation_buffer_pts": 2.0,
                    "killzone_filter": True,
                    "cancel_unfilled_bars": 12,
                },
                "is_system_preset": True,
                "is_active": True,
            },
            {
                "name": "ICT Smart Money v3: Institutional Displacement, HTF Bias & Liquidity Sweep",
                "rule_type": BacktestRuleTypeChoices.ICT_SMC_V3,
                "market_type": RuleMarketTypeChoices.ALL,
                "description": (
                    "Institutional-grade ICT v3 execution engine. Solves counter-trend traps by strictly enforcing "
                    "15m Opening Range & EMA 9/21 trend alignment, true multi-candle Displacement (candle body >= 65%), "
                    "and 61.8%-78.6% OTE limit mitigation. Eliminates knife-catching during runaway open drives."
                ),
                "prompt_directive": (
                    "Strictly align with Higher-Timeframe trend: Do NOT buy PE if Spot is above 15m ORB High or EMA 9 > 21; "
                    "do NOT buy CE if Spot is below 15m ORB Low or EMA 9 < 21. Require genuine Displacement with candle body >= 65% "
                    "closing beyond 3-bar swing fractal. Wait for 61.8%-78.6% OTE Retest limit entry with minimum 1:3.0 RR."
                ),
                "parameters": {
                    "htf_orb_filter": True,
                    "ema_trend_lock": True,
                    "displacement_body_min_pct": 0.65,
                    "mss_fractal_bars": 3,
                    "ote_fib_min": 0.618,
                    "ote_fib_max": 0.786,
                    "min_risk_reward": 3.0,
                    "sl_pts": 7.5,
                    "anti_knife_premium_filter": True,
                    "killzone_filter": True,
                    "cancel_unfilled_bars": 10,
                },
                "is_system_preset": True,
                "is_active": True,
            },
            {
                "name": "Professional Intraday Trend & Momentum Guardrails",
                "rule_type": BacktestRuleTypeChoices.MOMENTUM_GUARDRAIL,
                "market_type": RuleMarketTypeChoices.ALL,
                "description": (
                    "Eliminates blind 09:15 entries and 6-hour theta decay. Enforces 15-minute "
                    "Opening Range (09:15-09:30) discovery, EMA 9/21 trend confirmation, dynamic "
                    "1.5x ATR targets, and a 45-minute momentum time-stop."
                ),
                "prompt_directive": (
                    "Wait for 09:30 15-min Opening Range Breakout and EMA 9/21 trend confirmation. "
                    "Enforce 45-minute momentum time-stop and trailing stop loss to protect long options against theta decay."
                ),
                "parameters": {
                    "orb_minutes": 15,
                    "ema_fast": 9,
                    "ema_slow": 21,
                    "time_stop_minutes": 45,
                    "target_atr_mult": 1.5,
                    "trailing_sl": True,
                },
                "is_system_preset": True,
                "is_active": True,
            },
            {
                "name": "Institutional Micro-Scalp: VWAP Confluence, Momentum Thrust & Auto Risk Guard",
                "rule_type": BacktestRuleTypeChoices.ALGO_MICRO_SCALP,
                "market_type": RuleMarketTypeChoices.ALL,
                "description": (
                    "Engineered for high-frequency precision by a 20-year prop trader. Exploits structural momentum "
                    "breakouts aligning Session VWAP, EMA 9, and 1.4x volume surge. Features built-in automated risk control: "
                    "tight 7 pt SL, 1:2.0 RR target, instant Auto-Breakeven at 1:1.0 RR (+7 pts), and a 5-bar Time-Stop decay exit."
                ),
                "prompt_directive": (
                    "Micro-Scalp Execution Setup: 1. Confluence: Price must reject and break beyond Session VWAP and EMA 9. "
                    "2. Volume Thrust: Require volume >= 1.4x 10-period SMA volume with candle body >= 55% of range. "
                    "3. Auto Risk: Place 7.0 pt SL and 14.0 pt Target (1:2.0 RR). Move SL to Breakeven (+0.5 pt) immediately upon "
                    "reaching +7.0 pts. Hard exit after 5 bars if target unfilled. Max 3 trades per session."
                ),
                "parameters": {
                    "sl_pts": 7.0,
                    "min_risk_reward": 2.0,
                    "auto_breakeven_rr": 1.0,
                    "time_stop_bars": 5,
                    "volume_surge_multiplier": 1.4,
                    "min_body_ratio": 0.55,
                    "vwap_filter": True,
                    "ema9_filter": True,
                    "max_trades_per_day": 3,
                    "killzone_filter": True,
                },
                "is_system_preset": True,
                "is_active": True,
            },
            {
                "name": "Morning 3-Min Multi-Timeframe MACD & Option Momentum Retest",
                "rule_type": BacktestRuleTypeChoices.MORNING_MACD_RETEST,
                "market_type": RuleMarketTypeChoices.INDEX_FO,
                "description": (
                    "Aligns 3-Minute Higher Timeframe index trend momentum with 1-Minute option contract MACD "
                    "crossovers during Morning Open Killzone (09:18-10:30). Executes on sharp retests into 9 EMA "
                    "for high delta expansion (1:2.5+ RR)."
                ),
                "prompt_directive": (
                    "Verify 3-minute index trend direction. Wait for 1-minute option strike MACD bullish crossover "
                    "and pull back to 9 EMA. Enter strictly on retest confirmation with 1:2.5+ Risk to Reward."
                ),
                "parameters": {
                    "htf_tf": "3m",
                    "ltf_tf": "1m",
                    "macd_fast": 12,
                    "macd_slow": 26,
                    "macd_signal": 9,
                    "retest_ema": 9,
                    "min_risk_reward": 2.5,
                    "time_window_start": "09:18",
                    "time_window_end": "10:30",
                },
                "is_system_preset": True,
                "is_active": True,
            },
            {
                "name": "Previous Day High / Low (PDH/PDL) Sweep & Equilibrium Fade",
                "rule_type": BacktestRuleTypeChoices.PDH_PDL,
                "market_type": RuleMarketTypeChoices.ALL,
                "description": (
                    "Institutional trap detection strategy. Monitors Previous Day High (PDH) and Low (PDL) for "
                    "wick sweeps without body acceptance. Fades the false breakout back into previous day value range "
                    "equilibrium with 1:2.5+ RR."
                ),
                "prompt_directive": (
                    "Track Previous Day High and Low boundaries. When price wicks beyond PDH or PDL but closes inside, "
                    "fade the false breakout toward previous day midpoint equilibrium. Enforce tight SL beyond wick extreme."
                ),
                "parameters": {
                    "sweep_buffer_pts": 2.0,
                    "require_body_rejection": True,
                    "target_equilibrium": True,
                    "min_risk_reward": 2.5,
                },
                "is_system_preset": True,
                "is_active": True,
            },
            {
                "name": "Gamma Blast 0DTE Expiry Afternoon Surge",
                "rule_type": BacktestRuleTypeChoices.GAMMA_BLAST,
                "market_type": RuleMarketTypeChoices.INDEX_FO,
                "description": (
                    "Afternoon expiry day volatility strategy (13:00-15:15). Detects explosive Delta/Gamma momentum "
                    "surges on weekly and monthly 0DTE contracts with dynamic 15-minute trailing stops."
                ),
                "prompt_directive": (
                    "Activate strictly on 0DTE expiry sessions between 13:00 and 15:15. Detect breakout from afternoon "
                    "consolidation range. Ride gamma delta expansion with trailing stop loss."
                ),
                "parameters": {
                    "expiry_only": True,
                    "time_window_start": "13:00",
                    "time_window_end": "15:15",
                    "strike_offset": "OTM1",
                    "trailing_stop": True,
                    "min_risk_reward": 2.0,
                },
                "is_system_preset": True,
                "is_active": True,
            },
            {
                "name": "Dynamic ATR Volatility Buffer (Anti-Noise Filter)",
                "rule_type": BacktestRuleTypeChoices.ATR_NOISE_FILTER,
                "market_type": RuleMarketTypeChoices.ALL,
                "description": (
                    "Volatility-adaptive risk filter. Requires minimum 1.5x ATR expansion to avoid dead chop "
                    "and skips low-volume lunch deadzones (11:30-13:00) where bid-ask spread and theta decay erode capital."
                ),
                "prompt_directive": (
                    "Enforce 1.5x ATR minimum volatility filter. Invalidate signals during 11:30-13:00 low-liquidity deadzone. "
                    "Anchor dynamic volatility stop loss buffer."
                ),
                "parameters": {
                    "atr_multiplier": 1.5,
                    "skip_deadzone_start": "11:30",
                    "skip_deadzone_end": "13:00",
                    "noise_filter_active": True,
                },
                "is_system_preset": True,
                "is_active": True,
            }
        ]

        for r_info in rules_data:
            rule, created = BacktestRule.objects.update_or_create(
                name=r_info["name"],
                defaults=r_info
            )
            status_str = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"Successfully {status_str} system rule: {rule.name} (ID: {rule.id})"))
