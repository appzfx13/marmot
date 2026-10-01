import json
import os
import threading
import time
import redis
from django.conf import settings
from apps.common.constants import REDIS_CHANNEL
from apps.common.logger import Logger
from .models import BacktestTask

logger = Logger(section="BACKTEST", app="backtest", log_type="services")

REDIS_URL = settings.REDIS_URL
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


class BacktestControlRegistry:
    """Thread-safe in-memory controller for coordinating Pause, Resume, and Cancel signals."""
    _lock = threading.Lock()
    _controllers = {}

    @classmethod
    def register(cls, task_id: int):
        with cls._lock:
            pause_event = threading.Event()
            pause_event.set()
            cancel_event = threading.Event()
            cls._controllers[int(task_id)] = {
                "pause_event": pause_event,
                "cancel_event": cancel_event,
            }
            return cancel_event, pause_event

    @classmethod
    def get(cls, task_id: int):
        with cls._lock:
            return cls._controllers.get(int(task_id))

    @classmethod
    def pause(cls, task_id: int):
        with cls._lock:
            ctrl = cls._controllers.get(int(task_id))
            if ctrl:
                ctrl["pause_event"].clear()
                return True
            return False

    @classmethod
    def resume(cls, task_id: int):
        with cls._lock:
            ctrl = cls._controllers.get(int(task_id))
            if ctrl:
                ctrl["pause_event"].set()
                return True
            return False

    @classmethod
    def cancel(cls, task_id: int):
        with cls._lock:
            ctrl = cls._controllers.get(int(task_id))
            if ctrl:
                ctrl["cancel_event"].set()
                ctrl["pause_event"].set()
                return True
            return False

    @classmethod
    def cleanup(cls, task_id: int):
        with cls._lock:
            cls._controllers.pop(int(task_id), None)


def broadcast_backtest_progress(task_id, progress: int, status: str, net_pnl: float = 0.0, total_trades: int = 0, step_info: str = ""):
    """Broadcasts live progress update to Redis Pub/Sub and WebSocket clients."""
    try:
        payload = {
            "type": "progress",
            "task_id": str(task_id),
            "progress": int(progress),
            "status": status,
            "net_pnl": float(net_pnl),
            "total_trades": int(total_trades),
            "step_info": str(step_info),
        }
        t_qs = BacktestTask.objects.filter(id=task_id)
        curr_status = t_qs.values_list('status', flat=True).first()
        if curr_status in [BacktestTask.StatusChoices.PAUSED, BacktestTask.StatusChoices.CANCELLED] and status == BacktestTask.StatusChoices.RUNNING:
            return
        t_qs.update(progress=progress, status=status)
        pub_count = redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
        print(f"📡 [BROADCAST-PROGRESS] Task #{task_id} -> {progress}% ({status}) | Step: {step_info} | PnL: ₹{net_pnl:,.2f} | Trades: {total_trades} | Redis Pub Subscribed Clients: {pub_count}", flush=True)
    except Exception as e:
        print(f"❌ [BROADCAST-PROGRESS ERROR] Task #{task_id}: {e}", flush=True)
        logger.error("Failed to broadcast backtest progress", exc=e, extra={"task_id": task_id})


def create_and_start_backtest_task(strategy_name, index_name, start_date, end_date, initial_capital, parameters, user, backup_task=None, use_macro_assist=False, macro_timeframe='1h', macro_backup_task=None, enable_ai_lot_sizing=False, auto_risk_management=True, max_risk_per_trade_pct=2.00, max_capital_utilization_pct=60.00, max_lots_cap=10):
    """Creates a BacktestTask DB entry in CREATED status without auto-starting."""
    task = BacktestTask.objects.create(
        strategy_name=strategy_name,
        index_name=index_name,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        parameters=parameters or {},
        backup_task=backup_task,
        use_macro_assist=use_macro_assist,
        macro_timeframe=macro_timeframe or '1h',
        macro_backup_task=macro_backup_task,
        enable_ai_lot_sizing=enable_ai_lot_sizing,
        auto_risk_management=auto_risk_management,
        max_risk_per_trade_pct=max_risk_per_trade_pct,
        max_capital_utilization_pct=max_capital_utilization_pct,
        max_lots_cap=max_lots_cap,
        status=BacktestTask.StatusChoices.CREATED,
        created_by=user
    )
    return task


def send_backtest_control_command(task_id, command):
    """Sends START_BACKTEST, PAUSE, RESUME, or CANCEL command to Go Engine or Python RL worker."""
    task = BacktestTask.objects.get(id=task_id)
    cmd = command.upper()

    if cmd in ['START', 'START_BACKTEST', 'RERUN', 'RESTART']:
        if task.results and isinstance(task.results, dict) and task.metrics:
            from .models import BacktestRunLog
            run_num = task.run_logs.count() + 1
            BacktestRunLog.objects.create(
                task=task,
                run_number=run_num,
                status=task.status,
                metrics=task.metrics,
                applied_rules=[r.name for r in task.rules.all()],
                notes=f"Snapshot of run #{run_num} before re-run execution.",
                created_by=task.created_by
            )
        # Sync task.parameters['rules'] from current M2M so Go always receives
        # the latest attached rules, not the stale snapshot from task creation.
        current_params = dict(task.parameters or {})
        current_params['use_macro_assist'] = bool(task.use_macro_assist)
        current_params['rules'] = [
            {
                'id': r.id,
                'name': r.name,
                'rule_type': r.rule_type,
                'prompt_directive': r.prompt_directive or '',
                'parameters': r.parameters or {},
            }
            for r in task.rules.filter(is_active=True)
        ]
        task.parameters = current_params
        task.status = BacktestTask.StatusChoices.RUNNING
        task.progress = 5
        task.error_logs = ""
        task.results = {}
        task.metrics = {}

        # Cleanly purge stale trade result file on disk from previous runs
        user_id = str(task.created_by_id or '1')
        candidate_files = [
            task.result_file_path,
            f"/app/go-app/data/users/{user_id}/backtests/backtest_{task.id}.json",
            f"/app/data/users/{user_id}/backtests/backtest_{task.id}.json",
            os.path.join(settings.BASE_DIR, 'go-app', 'data', 'users', user_id, 'backtests', f'backtest_{task.id}.json'),
            os.path.join(settings.BASE_DIR, 'data', 'users', user_id, 'backtests', f'backtest_{task.id}.json'),
        ]
        for c_file in candidate_files:
            if c_file and os.path.exists(c_file):
                try:
                    os.remove(c_file)
                except Exception:
                    pass
        task.result_file_path = ""

        task.save(update_fields=['status', 'progress', 'error_logs', 'results', 'metrics', 'parameters', 'result_file_path'])
        broadcast_backtest_progress(task.id, 5, BacktestTask.StatusChoices.RUNNING, step_info="Starting Go Quantitative Rule Engine backtest execution...")
    elif cmd == 'RESUME':
        BacktestControlRegistry.resume(task.id)
        task.status = BacktestTask.StatusChoices.RUNNING
        task.save(update_fields=['status'])
        broadcast_backtest_progress(task.id, task.progress or 10, BacktestTask.StatusChoices.RUNNING, step_info="Resuming backtest execution...")
    elif cmd == 'PAUSE':
        task.status = BacktestTask.StatusChoices.PAUSED
        task.save(update_fields=['status'])
        BacktestControlRegistry.pause(task.id)
        broadcast_backtest_progress(task.id, task.progress or 0, BacktestTask.StatusChoices.PAUSED, step_info="Backtest paused by user.")
    elif cmd in ['CANCEL', 'STOP']:
        task.status = BacktestTask.StatusChoices.CANCELLED
        task.save(update_fields=['status'])
        BacktestControlRegistry.cancel(task.id)
        broadcast_backtest_progress(task.id, task.progress or 0, BacktestTask.StatusChoices.CANCELLED, step_info="Backtest cancelled by user.")

    # Also notify Redis for Go service or external subscribers
    payload = {
        "task_id": str(task.id),
        "command": cmd,
        "params": {
            "strategy_name": task.strategy_name,
            "index_name": task.index_name,
            "start_date": task.start_date.isoformat(),
            "end_date": task.end_date.isoformat(),
            "initial_capital": task.initial_capital,
            "user_id": str(task.created_by.id if getattr(task, 'created_by', None) else 1),
            "backup_task_id": str(task.backup_task.id) if task.backup_task else "",
            "params": task.parameters or {}
        }
    }
    try:
        redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
    except Exception as e:
        logger.warning(f"Redis publish warning: {e}")

    return task


GO_STRATEGY_PRESETS = [
    {
        'rule_type': 'gamma_blast',
        'name': 'Expiry Gamma Blast 1:3.5 (Hero or Zero)',
        'market_type': 'INDEX_FO',
        'description': 'Afternoon 14:15-15:15 IST gamma explosion micro-scalper for expiry days. Tight 8pt SL, 1:3.5 RR.',
        'parameters': {
            'entry_window_from': 14 * 60 + 15,
            'entry_window_to': 15 * 60 + 15,
            'sl_pts': 8.0,
            'rr_ratio': 3.5,
            'require_expiry_day': True,
            'min_displacement': 0.70,
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'momentum_scalp',
        'name': 'Momentum Scalp 1:2.5 (EMA 9/21 + ORB)',
        'market_type': 'ALL',
        'description': 'EMA 9/21 momentum crossover with ORB midpoint filter. 1:2.5 RR, trailing breakeven at 1.2R.',
        'parameters': {
            'ema_fast': 9,
            'ema_slow': 21,
            'entry_window_from': 9 * 60 + 20,
            'entry_window_to': 15 * 60,
            'sl_pts': 12.0,
            'rr_ratio': 2.5,
            'use_orb_filter': True,
            'min_displacement': 0.50,
            'trail_breakeven': True,
            'breakeven_at_r': 1.2,
            'cooldown_seconds': 120,
            'order_type': 'LIMIT',
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'algo_micro_scalp',
        'name': 'Institutional Micro-Scalp 1:3 (EMA 5/13)',
        'market_type': 'ALL',
        'description': 'EMA 5/13 fast scalp with tight 8pt SL and 1:3 RR. Trailing BE at 1R. No ORB filter.',
        'parameters': {
            'ema_fast': 5,
            'ema_slow': 13,
            'entry_window_from': 9 * 60 + 20,
            'entry_window_to': 14 * 60 + 30,
            'sl_pts': 8.0,
            'rr_ratio': 3.0,
            'use_orb_filter': False,
            'min_displacement': 0.55,
            'trail_breakeven': True,
            'breakeven_at_r': 1.0,
            'cooldown_seconds': 180,
            'order_type': 'MARKET',
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'hft_scalp',
        'name': 'High-Frequency Micro-Scalp (HFT 1:2.0)',
        'market_type': 'ALL',
        'description': 'Ultra-fast EMA 3/8 institutional micro-scalp with tight 8pt SL, 1:2.0 RR, and aggressive 0.8R trailing breakeven.',
        'parameters': {
            'ema_fast': 3,
            'ema_slow': 8,
            'entry_window_from': 9 * 60 + 20,
            'entry_window_to': 15 * 60,
            'sl_pts': 8.0,
            'rr_ratio': 2.0,
            'use_orb_filter': False,
            'min_displacement': 0.50,
            'trail_breakeven': True,
            'breakeven_at_r': 0.8,
            'cooldown_seconds': 60,
            'order_type': 'MARKET',
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'ict_smc_matrix',
        'name': 'ICT Smart Money 1:2 (Limit Retest)',
        'market_type': 'ALL',
        'description': 'ICT displacement 65%+ with limit retest entry. 1:2 RR, trail at 1.5R.',
        'parameters': {
            'entry_window_from': 9 * 60 + 20,
            'entry_window_to': 15 * 60,
            'sl_pts': 15.0,
            'rr_ratio': 2.0,
            'order_type': 'LIMIT',
            'min_displacement': 0.65,
            'trail_breakeven': True,
            'breakeven_at_r': 1.5,
            'cooldown_seconds': 240,
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'orb_breakout',
        'name': 'ORB Breakout 1:2 (Morning Session)',
        'market_type': 'INDEX_FO',
        'description': 'ORB breakout only before noon. Wider SL with confirmed displacement above 60%.',
        'parameters': {
            'entry_window_from': 9 * 60 + 30,
            'entry_window_to': 12 * 60,
            'sl_pts': 20.0,
            'rr_ratio': 2.0,
            'use_orb_filter': True,
            'min_displacement': 0.60,
            'trail_breakeven': True,
            'breakeven_at_r': 1.0,
            'cooldown_seconds': 300,
            'order_type': 'MARKET',
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'intraday',
        'name': 'Intraday Momentum 1:2.5 (Auto Square-off)',
        'market_type': 'ALL',
        'description': 'Standard intraday momentum scalp. Square-off before 14:45.',
        'parameters': {
            'entry_window_from': 9 * 60 + 20,
            'entry_window_to': 14 * 60 + 45,
            'sl_pts': 12.0,
            'rr_ratio': 2.5,
            'use_orb_filter': True,
            'min_displacement': 0.50,
            'trail_breakeven': True,
            'breakeven_at_r': 1.0,
            'cooldown_seconds': 180,
            'order_type': 'MARKET',
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'morning_trend',
        'name': 'Morning Trend 1:2 (First Hour)',
        'market_type': 'ALL',
        'description': 'First-hour momentum capture only. Tight SL 10pts, 1:2 RR.',
        'parameters': {
            'entry_window_from': 9 * 60 + 20,
            'entry_window_to': 11 * 60,
            'sl_pts': 10.0,
            'rr_ratio': 2.0,
            'use_orb_filter': True,
            'min_displacement': 0.50,
            'trail_breakeven': True,
            'breakeven_at_r': 1.0,
            'cooldown_seconds': 120,
            'order_type': 'MARKET',
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'momentum_guardrail',
        'name': 'Professional Momentum Guardrail 1:2.5',
        'market_type': 'ALL',
        'description': 'Guardrail version: wider displacement threshold, later window close, trail at 1.5R.',
        'parameters': {
            'entry_window_from': 9 * 60 + 30,
            'entry_window_to': 14 * 60 + 30,
            'sl_pts': 15.0,
            'rr_ratio': 2.5,
            'min_displacement': 0.60,
            'use_orb_filter': True,
            'trail_breakeven': True,
            'breakeven_at_r': 1.5,
            'cooldown_seconds': 240,
            'order_type': 'MARKET',
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'macd_crossover',
        'name': 'Simple MACD Crossover (12/26 EMA)',
        'market_type': 'ALL',
        'description': 'Basic 12/26 EMA crossover mimicking MACD baseline. Used for Go Engine verification.',
        'parameters': {
            'ema_fast': 12,
            'ema_slow': 26,
            'entry_window_from': 9 * 60 + 15,
            'entry_window_to': 15 * 60,
            'sl_pts': 15.0,
            'rr_ratio': 2.0,
            'use_orb_filter': False,
            'min_displacement': 0.50,
            'trail_breakeven': True,
            'breakeven_at_r': 1.0,
            'cooldown_seconds': 300,
            'order_type': 'MARKET',
        },
        'is_system_preset': True,
        'is_active': True,
    },
    {
        'rule_type': 'macd_ict_hybrid',
        'name': 'Advanced HTF MACD + ICT Hybrid (1:2.0 High Winrate)',
        'market_type': 'ALL',
        'description': '15m HTF MACD & 200 EMA momentum gatekeeper with 1m Liquidity Sweep, MSS, and FVG Consequent Encroachment (50% CE) entry.',
        'parameters': {
            'ema_fast': 12,
            'ema_slow': 26,
            'entry_window_from': 9 * 60 + 20,
            'entry_window_to': 14 * 60 + 45,
            'sl_pts': 15.0,
            'rr_ratio': 2.0,
            'use_orb_filter': True,
            'min_displacement': 0.65,
            'trail_breakeven': True,
            'breakeven_at_r': 1.2,
            'cooldown_seconds': 300,
            'order_type': 'LIMIT',
        },
        'is_system_preset': True,
        'is_active': True,
    },
]


def ensure_strategy_presets_exist() -> int:
    """Checks and seeds Go strategy presets in BacktestRule table if not existing."""
    from apps.backtest.models import BacktestRule
    created_count = 0
    for item in GO_STRATEGY_PRESETS:
        rule_type = item['rule_type']
        if not BacktestRule.objects.filter(rule_type=rule_type).exists():
            BacktestRule.objects.create(
                rule_type=rule_type,
                name=item['name'],
                market_type=item['market_type'],
                description=item['description'],
                parameters=item['parameters'],
                is_system_preset=item['is_system_preset'],
                is_active=item['is_active'],
            )
            created_count += 1
    return created_count
