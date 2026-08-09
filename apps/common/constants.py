REDIS_CHANNEL = 'market_backup_commands'

INDEX_INSTRUMENT_MAP = {
    'NIFTY': {"security_id": "13", "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'BANKNIFTY': {"security_id": "25", "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'FINNIFTY': {"security_id": "27", "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'MIDCPNIFTY': {"security_id": "26", "exchange_segment": "IDX_I", "instrument": "INDEX"}
}

DEFAULT_INITIAL_CAPITAL = 100000.0
DEFAULT_RISK_REWARD_RATIO = 2.0
DEFAULT_STOP_LOSS_PCT = 0.5
DEFAULT_STRIKE_COUNT = 5
MAX_LOG_LINES = 200
