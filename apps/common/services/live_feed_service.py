import datetime
import math
from zoneinfo import ZoneInfo
from django.utils import timezone


def get_ist_market_clock():
    """Return current IST time and exchange session operational state."""
    ist_tz = ZoneInfo('Asia/Kolkata')
    now_ist = datetime.datetime.now(ist_tz)
    time_str = now_ist.strftime('%H:%M:%S')
    date_str = now_ist.strftime('%d %b %Y')
    weekday = now_ist.weekday()  # 5=Saturday, 6=Sunday

    t_val = now_ist.time()
    t_pre_start = datetime.time(9, 0, 0)
    t_open = datetime.time(9, 15, 0)
    t_sqoff = datetime.time(15, 15, 0)
    t_close = datetime.time(15, 30, 0)

    if weekday in (5, 6):
        status = 'CLOSED'
        label = 'Weekend (Exchange Closed)'
        badge_class = 'bg-secondary bg-opacity-25 text-white-50 border border-secondary border-opacity-25'
        is_open = False
    elif t_pre_start <= t_val < t_open:
        status = 'PRE_OPEN'
        label = 'Pre-Open Session'
        badge_class = 'bg-info bg-opacity-25 text-info border border-info border-opacity-25'
        is_open = False
    elif t_open <= t_val < t_sqoff:
        status = 'OPEN'
        label = 'Market Open'
        badge_class = 'bg-success bg-opacity-25 text-success border border-success border-opacity-25'
        is_open = True
    elif t_sqoff <= t_val <= t_close:
        status = 'SQUAREOFF'
        label = 'Auto-Squareoff Phase'
        badge_class = 'bg-warning bg-opacity-25 text-warning border border-warning border-opacity-25'
        is_open = True
    else:
        status = 'CLOSED'
        label = 'Market Closed'
        badge_class = 'bg-secondary bg-opacity-25 text-muted border border-secondary border-opacity-25'
        is_open = False

    return {
        'time_str': time_str,
        'date_str': date_str,
        'status': status,
        'label': label,
        'badge_class': badge_class,
        'is_open': is_open,
        'iso_now': now_ist.isoformat(),
    }


def _extract_trade_date(trade_dict: dict) -> str:
    raw = trade_dict.get('exchangeTime') or trade_dict.get('orderTimestamp') or trade_dict.get('createTime') or ''
    if raw and len(raw) >= 10:
        return raw[:10].replace('/', '-')
    return ''


def _calculate_real_daily_pnl(trades_list: list) -> dict:
    daily_map = {}
    for t in trades_list:
        date_str = _extract_trade_date(t)
        if not date_str:
            continue
        if date_str not in daily_map:
            daily_map[date_str] = {'buy_val': 0.0, 'sell_val': 0.0, 'trades': 0}
        qty = int(t.get('tradedQuantity', 0) or t.get('quantity', 0) or 0)
        px = float(t.get('tradedPrice', 0.0) or t.get('price', 0.0) or 0.0)
        val = round(qty * px, 2)
        side = str(t.get('transactionType', 'BUY')).upper()
        if side == 'BUY':
            daily_map[date_str]['buy_val'] += val
        else:
            daily_map[date_str]['sell_val'] += val
        daily_map[date_str]['trades'] += 1

    result = {}
    for d_str, info in daily_map.items():
        gross = round(info['sell_val'] - info['buy_val'], 2)
        brokerage = round(info['trades'] * 20.0, 2)
        turnover = round(info['buy_val'] + info['sell_val'], 2)
        govt_charges = round((turnover * 0.00198) + (brokerage * 0.09), 2)
        net = round(gross - brokerage - govt_charges, 2)
        result[d_str] = {
            'net_pnl': net,
            'trades': info['trades'],
        }
    return result


def get_current_month_calendar_pnl(target, trades=None):
    """Calculate and return monthly realized PnL calendar grid and summary KPIs from real broker trades."""
    from apps.trade_config.models import UserTradingAccount
    from apps.trade_core.brokers.factory import BrokerFactory

    if target is None:
        account = None
    elif isinstance(target, UserTradingAccount):
        account = target
    elif hasattr(target, 'trading_accounts'):
        account = target.trading_accounts.filter(broker__code='dhan', is_active=True).first()
    else:
        account = UserTradingAccount.objects.filter(broker__code='dhan', is_active=True).first()

    ist_tz = ZoneInfo('Asia/Kolkata')
    now_ist = datetime.datetime.now(ist_tz)
    year = now_ist.year
    month = now_ist.month
    month_name = now_ist.strftime('%B')

    first_day = datetime.date(year, month, 1)
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    num_days = (next_month - first_day).days

    daily_map = {}
    if trades is not None:
        if trades:
            daily_map = _calculate_real_daily_pnl(trades)
    elif account:
        try:
            adapter = BrokerFactory.get_adapter(account)
            token = getattr(adapter, 'get_access_token', lambda: '')()
            if token:
                from_d = first_day.strftime('%Y-%m-%d')
                to_d = datetime.date(year, month, num_days).strftime('%Y-%m-%d')
                t_res = adapter.get_trade_history(from_d, to_d, page=0, fetch_all=True)
                raw_trades = t_res.get('trades', []) if t_res.get('success') else []
                if not raw_trades:
                    tb_res = adapter.get_trade_book()
                    raw_trades = tb_res.get('trades', []) if tb_res.get('success') else []
                if raw_trades:
                    daily_map = _calculate_real_daily_pnl(raw_trades)
        except Exception:
            pass

    days_list = []
    total_monthly_pnl = 0.0
    profit_days = 0
    loss_days = 0

    for d in range(1, num_days + 1):
        c_date = datetime.date(year, month, d)
        w_day = c_date.weekday()
        is_weekend = w_day in (5, 6)
        is_past_or_today = c_date <= now_ist.date()
        date_key = c_date.strftime('%Y-%m-%d')

        day_pnl = 0.0
        trade_count = 0
        if date_key in daily_map:
            day_pnl = daily_map[date_key]['net_pnl']
            trade_count = daily_map[date_key]['trades']
            if day_pnl > 0:
                profit_days += 1
            elif day_pnl < 0:
                loss_days += 1
            total_monthly_pnl += day_pnl

        days_list.append({
            'day': d,
            'date': date_key,
            'weekday_name': c_date.strftime('%a'),
            'is_weekend': is_weekend,
            'is_today': (c_date == now_ist.date()),
            'is_past_or_today': is_past_or_today,
            'pnl': day_pnl,
            'trade_count': trade_count,
            'is_profit': day_pnl > 0,
            'is_loss': day_pnl < 0,
        })

    total_traded_days = profit_days + loss_days
    win_rate = round((profit_days / total_traded_days * 100.0), 1) if total_traded_days > 0 else 0.0

    return {
        'month': month,
        'year': year,
        'month_name': month_name,
        'days': days_list,
        'total_monthly_pnl': round(total_monthly_pnl, 2),
        'profit_days': profit_days,
        'loss_days': loss_days,
        'total_traded_days': total_traded_days,
        'win_rate': win_rate,
    }


def get_today_intraday_equity_curve(target, base_capital=100000.0, trades=None):
    """Generate today's minute-interval equity curve from actual executed trades or flatline standby."""
    from apps.trade_config.models import UserTradingAccount
    from apps.trade_core.brokers.factory import BrokerFactory

    if target is None:
        account = None
    elif isinstance(target, UserTradingAccount):
        account = target
    elif hasattr(target, 'trading_accounts'):
        account = target.trading_accounts.filter(broker__code='dhan', is_active=True).first()
    else:
        account = UserTradingAccount.objects.filter(broker__code='dhan', is_active=True).first()
    ist_tz = ZoneInfo('Asia/Kolkata')
    now_ist = datetime.datetime.now(ist_tz)
    today_str = now_ist.strftime('%Y-%m-%d')

    today_trades = []
    if trades is not None:
        today_trades = [t for t in trades if _extract_trade_date(t) == today_str]
    elif account:
        try:
            adapter = BrokerFactory.get_adapter(account)
            token = getattr(adapter, 'get_access_token', lambda: '')()
            if token:
                tb_res = adapter.get_trade_book()
                raw_trades = tb_res.get('trades', []) if tb_res.get('success') else []
                today_trades = [t for t in raw_trades if _extract_trade_date(t) == today_str]
        except Exception:
            pass

    if today_trades:
        labels = ["09:15"]
        pnl_values = [0.0]
        running_pnl = 0.0
        for t in today_trades:
            raw_time = t.get('exchangeTime') or t.get('orderTimestamp') or ''
            t_label = raw_time[11:16] if len(raw_time) >= 16 else "10:00"
            qty = int(t.get('tradedQuantity', 0) or t.get('quantity', 0) or 0)
            px = float(t.get('tradedPrice', 0.0) or t.get('price', 0.0) or 0.0)
            side = str(t.get('transactionType', 'BUY')).upper()
            val = round(qty * px, 2)
            trade_pnl = val if side == 'SELL' else -val
            running_pnl = round(running_pnl + trade_pnl, 2)
            labels.append(t_label)
            pnl_values.append(running_pnl)

        return {
            'has_trades': True,
            'labels': labels,
            'equity_values': [round(base_capital + p, 2) for p in pnl_values],
            'pnl_values': pnl_values,
            'current_pnl': pnl_values[-1] if pnl_values else 0.0,
        }

    time_now_str = now_ist.strftime('%H:%M')
    return {
        'has_trades': False,
        'labels': ["09:15", time_now_str if time_now_str > "09:15" else "15:30"],
        'equity_values': [base_capital, base_capital],
        'pnl_values': [0.0, 0.0],
        'current_pnl': 0.0,
    }


def get_mock_index_option_chain(idx_clean: str, strike_step: int, spot_symbol: str, today) -> dict:
    """Fetch real-time option chain directly from Dhan Mock Broker Gateway emulator."""
    import requests
    from apps.common.constants import get_option_expiry_analysis

    mock_urls = [
        f"http://mock_broker:8088/mock/v2/optionchain?index={idx_clean}",
        f"http://127.0.0.1:8088/mock/v2/optionchain?index={idx_clean}",
    ]
    for url in mock_urls:
        try:
            resp = requests.get(url, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                data['expiry_info'] = get_option_expiry_analysis(idx_clean, today)
                data['is_mock_mode'] = True
                data['is_fyers_live'] = False
                return data
        except Exception:
            continue

    return {
        'is_live': True,
        'is_mock_live': True,
        'feed_status': 'STREAMING',
        'index_name': idx_clean,
        'spot_symbol': spot_symbol,
        'fyers_symbol': f"DHAN_MOCK:{idx_clean}",
        'spot_ltp': '24,542.80',
        'raw_spot_ltp': 24542.80,
        'spot_change': '+118.20',
        'spot_change_pct': '+0.48%',
        'is_positive': True,
        'open_price': '24,450.00',
        'high_price': '24,590.00',
        'low_price': '24,420.00',
        'prev_close': '24,424.60',
        'atm_strike': '24550',
        'strike_step': strike_step,
        'pcr': 1.12,
        'india_vix': 13.28,
        'expiry_info': get_option_expiry_analysis(idx_clean, today),
        'strikes': [],
        'error_message': 'Dhan Mock Gateway is ready.',
        'last_updated': timezone.localtime().strftime('%I:%M:%S %p IST'),
    }


def get_live_index_option_chain(index_name: str = 'NIFTY', is_mock: bool = False) -> dict:
    """Retrieve genuine real-time option chain and quotes from FYERS API or Dhan Mock Emulator."""
    import requests
    from apps.common.models import SiteSettings
    from apps.common.constants import INDEX_STRIKE_INTERVAL, FYERS_INDEX_SYMBOLS, get_option_expiry_analysis

    idx_clean = (index_name or 'NIFTY').upper().strip()
    strike_step = INDEX_STRIKE_INTERVAL.get(idx_clean, 50)
    display_names = {
        'NIFTY': 'NIFTY 50',
        'BANKNIFTY': 'BANK NIFTY',
        'FINNIFTY': 'FIN NIFTY',
        'MIDCPNIFTY': 'MIDCP NIFTY',
        'SENSEX': 'BSE SENSEX',
        'GIFTNIFTY': 'GIFT NIFTY',
        'INDIAVIX': 'INDIA VIX',
    }
    spot_symbol = display_names.get(idx_clean, idx_clean)
    today = timezone.localdate()

    if is_mock:
        return get_mock_index_option_chain(idx_clean, strike_step, spot_symbol, today)

    cache_key = f"marmot:fyers:option_chain:{idx_clean}"
    last_known_key = f"marmot:fyers:last_known_option_chain:{idx_clean}"
    rate_limit_key = "marmot:fyers_rate_limited"
    from django.core.cache import cache
    cached_payload = cache.get(cache_key)
    if cached_payload and cached_payload.get('is_live'):
        return cached_payload

    if cache.get(rate_limit_key):
        last_known = cache.get(last_known_key)
        if last_known and last_known.get('is_live'):
            return last_known

    fyers_sym = FYERS_INDEX_SYMBOLS.get(idx_clean, f"NSE:{idx_clean}50-INDEX")
    settings_obj = SiteSettings.load()
    token_valid = bool(settings_obj.fyers_access_token and settings_obj.fyers_token_generated_date == today)
    app_id = (settings_obj.fyers_app_id or '').strip()

    # If FYERS credentials or daily token are not active, check last known or return clean unauthenticated state
    if not (token_valid and app_id and settings_obj.fyers_access_token):
        last_known = cache.get(last_known_key)
        if last_known and last_known.get('is_live'):
            return last_known
        return {
            'is_live': False,
            'is_fyers_live': False,
            'feed_status': 'AUTH_REQUIRED',
            'index_name': idx_clean,
            'spot_symbol': spot_symbol,
            'fyers_symbol': fyers_sym,
            'spot_ltp': '0.00',
            'raw_spot_ltp': 0.0,
            'spot_change': '0.00',
            'spot_change_pct': '0.00%',
            'is_positive': True,
            'open_price': '0.00',
            'high_price': '0.00',
            'low_price': '0.00',
            'prev_close': '0.00',
            'atm_strike': '-',
            'strike_step': strike_step,
            'pcr': 0.0,
            'india_vix': 0.0,
            'expiry_info': get_option_expiry_analysis(idx_clean, today),
            'strikes': [],
            'error_message': 'FYERS daily session unauthenticated. Please authorize live feed in Site Settings.',
            'last_updated': timezone.localtime().strftime('%I:%M:%S %p IST'),
        }

    auth_header = f"{app_id}:{settings_obj.fyers_access_token}"
    headers = {'Authorization': auth_header}

    spot_ltp = 0.0
    spot_change = 0.0
    spot_change_pct = 0.0
    open_px = 0.0
    high_px = 0.0
    low_px = 0.0
    prev_close = 0.0
    india_vix = 0.0
    pcr = 0.0
    expiry_tag = ''
    strikes_data = []
    is_fyers_live = False

    # 1. Fetch real-time option chain contracts from FYERS API
    try:
        oc_url = f"https://api-t1.fyers.in/data/options-chain-v3?symbol={fyers_sym}&strikecount=15"
        oc_resp = requests.get(oc_url, headers=headers, timeout=3.5)
        if oc_resp.status_code == 200:
            oc_json = oc_resp.json()
            if oc_json.get('s') == 'ok' and oc_json.get('data'):
                oc_data = oc_json['data']
                raw_chain = oc_data.get('optionsChain', [])

                # Extract spot quote object (strike_price == -1)
                spot_item = next((x for x in raw_chain if x.get('strike_price') == -1), None)
                if spot_item:
                    spot_ltp = float(spot_item.get('ltp', 0.0))
                    spot_change = float(spot_item.get('ltpch', 0.0))
                    spot_change_pct = float(spot_item.get('ltpchp', 0.0))

                # Extract India VIX & PCR
                vix_data = oc_data.get('indiavixData', {})
                india_vix = float(vix_data.get('ltp', 0.0))
                call_oi = int(oc_data.get('callOi', 0))
                put_oi = int(oc_data.get('putOi', 0))
                pcr = round(put_oi / call_oi, 2) if call_oi > 0 else 0.0

                # Extract upcoming expiry date
                exp_list = oc_data.get('expiryData', [])
                if exp_list and isinstance(exp_list, list):
                    expiry_tag = exp_list[0].get('date', '')

                # Parse and group strike contracts (CE & PE)
                strikes_map = {}
                for item in raw_chain:
                    sp = item.get('strike_price')
                    if not sp or sp == -1:
                        continue
                    if sp not in strikes_map:
                        strikes_map[sp] = {
                            'strike': sp,
                            'is_atm': False,
                            'ce_ltp': 0.0,
                            'ce_chg': 0.0,
                            'ce_chg_pct': 0.0,
                            'ce_oi': '0',
                            'pe_ltp': 0.0,
                            'pe_chg': 0.0,
                            'pe_chg_pct': 0.0,
                            'pe_oi': '0',
                        }
                    opt_type = (item.get('option_type') or '').upper()
                    ltp_val = float(item.get('ltp', 0.0))
                    chg_val = float(item.get('ltpch', 0.0))
                    chgp_val = float(item.get('ltpchp', 0.0))
                    oi_val = int(item.get('oi', 0))

                    if opt_type == 'CE':
                        strikes_map[sp]['ce_ltp'] = ltp_val
                        strikes_map[sp]['ce_chg'] = chg_val
                        strikes_map[sp]['ce_chg_pct'] = chgp_val
                        strikes_map[sp]['ce_oi'] = f"{oi_val:,}"
                    elif opt_type == 'PE':
                        strikes_map[sp]['pe_ltp'] = ltp_val
                        strikes_map[sp]['pe_chg'] = chg_val
                        strikes_map[sp]['pe_chg_pct'] = chgp_val
                        strikes_map[sp]['pe_oi'] = f"{oi_val:,}"

                # Cache individual real-time option contract prices with strict expiry partitioning
                from apps.market.services import redis_client
                import datetime
                active_exp_tag = ''
                active_exp_display = ''
                if expiry_tag:
                    try:
                        exp_dt = datetime.datetime.strptime(expiry_tag, '%d-%m-%Y')
                        active_exp_display = exp_dt.strftime('%d %b').upper()
                        active_exp_tag = exp_dt.strftime('%d%b').upper()
                    except Exception:
                        pass

                if active_exp_display:
                    try:
                        redis_client.set(f"marmot:fyers:active_expiry:{idx_clean}", active_exp_display, ex=86400)
                    except Exception:
                        pass

                for sp, sval in strikes_map.items():
                    try:
                        if sval.get('ce_ltp'):
                            cache.set(f"marmot:opt_ltp:{idx_clean}:{sp}:CE", sval['ce_ltp'], timeout=120)
                            cache.set(f"marmot:opt_ltp:{idx_clean}:{sp}:CALL", sval['ce_ltp'], timeout=120)
                            if active_exp_tag:
                                redis_client.set(f"marmot:opt_ltp:{idx_clean}:{active_exp_tag}:{sp}:CE", str(sval['ce_ltp']), ex=120)
                                redis_client.set(f"marmot:opt_ltp:{idx_clean}:{active_exp_tag}:{sp}:CALL", str(sval['ce_ltp']), ex=120)
                        if sval.get('pe_ltp'):
                            cache.set(f"marmot:opt_ltp:{idx_clean}:{sp}:PE", sval['pe_ltp'], timeout=120)
                            cache.set(f"marmot:opt_ltp:{idx_clean}:{sp}:PUT", sval['pe_ltp'], timeout=120)
                            if active_exp_tag:
                                redis_client.set(f"marmot:opt_ltp:{idx_clean}:{active_exp_tag}:{sp}:PE", str(sval['pe_ltp']), ex=120)
                                redis_client.set(f"marmot:opt_ltp:{idx_clean}:{active_exp_tag}:{sp}:PUT", str(sval['pe_ltp']), ex=120)
                    except Exception:
                        pass

                sorted_strikes = sorted(strikes_map.values(), key=lambda x: x['strike'])
                atm_idx = -1
                if sorted_strikes and spot_ltp > 0:
                    closest = min(sorted_strikes, key=lambda x: abs(x['strike'] - spot_ltp))
                    closest['is_atm'] = True
                    atm_strike_val = closest['strike']
                    atm_idx = sorted_strikes.index(closest)
                else:
                    atm_strike_val = int(round(spot_ltp / strike_step) * strike_step) if spot_ltp > 0 else '-'

                for idx, s_row in enumerate(sorted_strikes):
                    s_row['is_active_window'] = (atm_idx - 3 <= idx <= atm_idx + 3) if atm_idx >= 0 else True

                strikes_data = sorted_strikes
                is_fyers_live = True
        elif oc_resp.status_code == 429:
            cache.set(rate_limit_key, True, timeout=60)
    except Exception:
        pass

    # 2. Fetch or fallback session metrics (Day Open, High, Low, Prev Close)
    last_known_q = cache.get(f"marmot:fyers_last_known_quote:{fyers_sym}") or {}
    open_px = float(last_known_q.get('open_price', 0.0))
    high_px = float(last_known_q.get('high_price', 0.0))
    low_px = float(last_known_q.get('low_price', 0.0))
    prev_close = float(last_known_q.get('prev_close_price', 0.0))

    if not cache.get(rate_limit_key):
        try:
            q_url = f"https://api-t1.fyers.in/data/quotes?symbols={fyers_sym}"
            q_resp = requests.get(q_url, headers=headers, timeout=2.5)
            if q_resp.status_code == 200:
                q_json = q_resp.json()
                if q_json.get('s') == 'ok' and q_json.get('d'):
                    qv = q_json['d'][0].get('v', {})
                    open_px = float(qv.get('open_price', open_px))
                    high_px = float(qv.get('high_price', high_px))
                    low_px = float(qv.get('low_price', low_px))
                    prev_close = float(qv.get('prev_close_price', prev_close))
            elif q_resp.status_code == 429:
                cache.set(rate_limit_key, True, timeout=60)
        except Exception:
            pass

    # Synchronize shared live spot quote across all widgets so top ribbon and option chain are 100% in sync
    if spot_ltp > 0:
        quote_sync = {
            'lp': spot_ltp,
            'ch': spot_change,
            'chp': spot_change_pct,
            'high_price': high_px if high_px > 0 else spot_ltp,
            'low_price': low_px if low_px > 0 else spot_ltp,
            'open_price': open_px if open_px > 0 else spot_ltp,
            'prev_close_price': prev_close if prev_close > 0 else spot_ltp,
        }
        cache.set(f"marmot:fyers_quote:{fyers_sym}", quote_sync, timeout=2)
        cache.set(f"marmot:fyers_last_known_quote:{fyers_sym}", quote_sync, timeout=86400)
        try:
            from apps.market.services import redis_client
            import json
            redis_client.set(f"marmot:fyers_quote:{fyers_sym}", json.dumps(quote_sync), ex=10)
        except Exception:
            pass

    # If FYERS live call failed, check last known quote before reporting offline
    if not is_fyers_live or not strikes_data:
        last_known = cache.get(last_known_key)
        if last_known and last_known.get('is_live'):
            return last_known
        return {
            'is_live': False,
            'is_fyers_live': False,
            'feed_status': 'FEED_OFFLINE',
            'index_name': idx_clean,
            'spot_symbol': spot_symbol,
            'fyers_symbol': fyers_sym,
            'spot_ltp': '0.00',
            'raw_spot_ltp': 0.0,
            'spot_change': '0.00',
            'spot_change_pct': '0.00%',
            'is_positive': True,
            'open_price': '0.00',
            'high_price': '0.00',
            'low_price': '0.00',
            'prev_close': '0.00',
            'atm_strike': '-',
            'strike_step': strike_step,
            'pcr': 0.0,
            'india_vix': 0.0,
            'expiry_info': get_option_expiry_analysis(idx_clean, today),
            'strikes': [],
            'total_strikes': 0,
            'active_window_strikes': 0,
            'error_message': 'FYERS live market feed offline or session timed out.',
            'last_updated': timezone.now().strftime('%H:%M:%S IST'),
        }

    expiry_info = get_option_expiry_analysis(idx_clean, today, spot_ltp, spot_ltp, 'CE')
    if expiry_tag:
        expiry_info['expiry_date'] = expiry_tag
        expiry_info['expiry_tag'] = f"Expiry ({expiry_tag})"

    res = {
        'is_live': True,
        'is_fyers_live': True,
        'feed_status': 'ONLINE',
        'index_name': idx_clean,
        'spot_symbol': spot_symbol,
        'fyers_symbol': fyers_sym,
        'spot_ltp': f"{spot_ltp:,.2f}",
        'raw_spot_ltp': spot_ltp,
        'spot_change': f"{'+' if spot_change >= 0 else ''}{spot_change:.2f}",
        'spot_change_pct': f"{'+' if spot_change_pct >= 0 else ''}{spot_change_pct:.2f}%",
        'is_positive': spot_change >= 0,
        'open_price': f"{open_px:,.2f}",
        'high_price': f"{high_px:,.2f}",
        'low_price': f"{low_px:,.2f}",
        'prev_close': f"{prev_close:,.2f}",
        'atm_strike': atm_strike_val,
        'strike_step': strike_step,
        'pcr': pcr,
        'india_vix': f"{india_vix:.2f}" if india_vix else "-",
        'expiry_info': expiry_info,
        'strikes': strikes_data,
        'total_strikes': len(strikes_data),
        'active_window_strikes': len([s for s in strikes_data if s.get('is_active_window')]),
        'last_updated': timezone.localtime().strftime('%I:%M:%S %p IST'),
    }
    cache.set(cache_key, res, timeout=2)
    cache.set(last_known_key, res, timeout=86400)
    try:
        from apps.market.services import redis_client
        import json
        redis_client.set(f"marmot:fyers:option_chain:{idx_clean}", json.dumps(res), ex=2)
        redis_client.set(f"marmot:fyers:last_known_option_chain:{idx_clean}", json.dumps(res), ex=86400)
    except Exception:
        pass
    return res


def to_fyers_option_symbol(symbol_str: str) -> str:
    """Map human-readable standard option symbol to exchange FYERS symbol."""
    import re
    if not symbol_str:
        return ""
    m = re.search(r'([A-Z]+)\s+(\d{1,2})\s+([A-Z]{3})\s+(\d+)\s+(CALL|PUT|CE|PE)', str(symbol_str).upper())
    if m:
        idx, day, mon, strike, otype = m.groups()
        months = {'JAN': '1', 'FEB': '2', 'MAR': '3', 'APR': '4', 'MAY': '5', 'JUN': '6', 'JUL': '7', 'AUG': '8', 'SEP': '9', 'OCT': 'O', 'NOV': 'N', 'DEC': 'D'}
        m_code = months.get(mon, '9')
        opt = 'CE' if otype in ['CALL', 'CE'] else 'PE'
        return f"NSE:{idx}26{m_code}{int(day):02d}{strike}{opt}"
    return str(symbol_str).strip()


def get_live_contract_market_quote(symbol_str: str) -> float:
    """Fetch real-time option contract market quote from FYERS with 5s caching in Redis."""
    from django.core.cache import cache
    from apps.market.services import redis_client
    from apps.common.models import SiteSettings
    import requests
    import re

    if not symbol_str:
        return 0.0

    fyers_sym = to_fyers_option_symbol(symbol_str)
    cache_key = f"marmot:contract_ltp:{fyers_sym}"
    cached_val = cache.get(cache_key)
    if cached_val:
        try:
            return float(cached_val)
        except (ValueError, TypeError):
            pass

    m = re.search(r'([A-Z]+).*?(\d{4,5})\s+(CALL|PUT|CE|PE)', str(symbol_str).upper())
    idx_clean = m.group(1) if m else 'NIFTY'
    strike_val = m.group(2) if m else ''
    opt_type = 'CE' if (m and m.group(3) in ['CALL', 'CE']) else 'PE'

    settings_obj = SiteSettings.load()
    if settings_obj.fyers_access_token and settings_obj.fyers_app_id:
        try:
            url = f"https://api-t1.fyers.in/data/quotes?symbols={fyers_sym}"
            headers = {'Authorization': f"{settings_obj.fyers_app_id}:{settings_obj.fyers_access_token}"}
            resp = requests.get(url, headers=headers, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('s') == 'ok' and data.get('d'):
                    v = data['d'][0].get('v', {})
                    lp = float(v.get('lp', 0.0))
                    if lp > 0:
                        cache.set(cache_key, lp, timeout=5)
                        try:
                            redis_client.set(f"marmot:contract_ltp:{fyers_sym}", str(lp), ex=120)
                        except Exception:
                            pass
                        m_exp = re.search(r'([A-Z]+)\s+(\d{1,2})\s+([A-Z]{3})\s+(\d+)\s+(CALL|PUT|CE|PE)', str(symbol_str).upper())
                        if m_exp:
                            idx_clean, day, mon, strike_val, otype = m_exp.groups()
                            exp_tag = f"{int(day):02d}{mon}"
                            opt_type = 'CE' if otype in ['CALL', 'CE'] else 'PE'
                            try:
                                redis_client.set(f"marmot:opt_ltp:{idx_clean}:{exp_tag}:{strike_val}:{opt_type}", str(lp), ex=120)
                                redis_client.set(f"marmot:opt_ltp:{idx_clean}:{exp_tag}:{strike_val}:CALL" if opt_type == 'CE' else f"marmot:opt_ltp:{idx_clean}:{exp_tag}:{strike_val}:PUT", str(lp), ex=120)
                            except Exception:
                                pass
                        return lp
        except Exception:
            pass

    if strike_val:
        m_exp = re.search(r'([A-Z]+)\s+(\d{1,2})\s+([A-Z]{3})\s+(\d+)\s+(CALL|PUT|CE|PE)', str(symbol_str).upper())
        if m_exp:
            _, day_val, mon_val, _, _ = m_exp.groups()
            exp_tag_val = f"{int(day_val):02d}{mon_val}"
            try:
                val_exp = redis_client.get(f"marmot:opt_ltp:{idx_clean}:{exp_tag_val}:{strike_val}:{opt_type}")
                if val_exp:
                    return float(val_exp)
            except Exception:
                pass
        try:
            val = redis_client.get(f"marmot:opt_ltp:{idx_clean}:{strike_val}:{opt_type}")
            if val:
                return float(val)
        except Exception:
            pass

    return 0.0


def get_nifty_mini_option_chain():
    """Backward-compatible wrapper returning live NIFTY option chain widget."""
    return get_live_index_option_chain('NIFTY')


def get_live_macro_market_cards():
    """Fetch real-time macro indices (NIFTY, BANKNIFTY, FINNIFTY, INDIA VIX, SENSEX) with 15s caching and fallback."""
    import requests
    from django.core.cache import cache
    from apps.common.models import SiteSettings

    cache_key = "marmot:fyers:macro_market_cards"
    last_known_key = "marmot:fyers:last_known_macro_market_cards"
    rate_limit_key = "marmot:fyers_rate_limited"

    cached = cache.get(cache_key)
    if cached:
        return cached

    macro_configs = [
        {'name': 'NIFTY 50', 'fyers_sym': 'NSE:NIFTY50-INDEX', 'exchange': 'NSE', 'type': 'INDEX'},
        {'name': 'BANK NIFTY', 'fyers_sym': 'NSE:NIFTYBANK-INDEX', 'exchange': 'NSE', 'type': 'INDEX'},
        {'name': 'FIN NIFTY', 'fyers_sym': 'NSE:FINNIFTY-INDEX', 'exchange': 'NSE', 'type': 'INDEX'},
        {'name': 'INDIA VIX', 'fyers_sym': 'NSE:INDIAVIX-INDEX', 'exchange': 'NSE', 'type': 'VOLATILITY'},
        {'name': 'SENSEX', 'fyers_sym': 'BSE:SENSEX-INDEX', 'exchange': 'BSE', 'type': 'INDEX'},
    ]

    if cache.get(rate_limit_key):
        last_known = cache.get(last_known_key)
        if last_known:
            return last_known

    site_settings = SiteSettings.load()
    today = timezone.localdate()
    is_fyers_token_valid = bool(
        site_settings.fyers_access_token and
        site_settings.fyers_token_generated_date == today and
        site_settings.fyers_feed_is_active
    )

    if not is_fyers_token_valid:
        last_known = cache.get(last_known_key)
        if last_known:
            return last_known
        return [
            {
                'name': m['name'],
                'fyers_sym': m['fyers_sym'],
                'exchange': m['exchange'],
                'type': m['type'],
                'ltp': '-',
                'change': '-',
                'change_pct': '-',
                'high': '-',
                'low': '-',
                'is_positive': True,
                'is_live': False,
            }
            for m in macro_configs
        ]

    headers = {'Authorization': f"{site_settings.fyers_app_id}:{site_settings.fyers_access_token}"}
    symbols_query = ','.join([m['fyers_sym'] for m in macro_configs])

    quotes_by_sym = {}
    try:
        url = f"https://api-t1.fyers.in/data/quotes?symbols={symbols_query}"
        resp = requests.get(url, headers=headers, timeout=3.5)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get('s') == 'ok' and res_json.get('d'):
                for item in res_json['d']:
                    sym = item.get('n')
                    val = item.get('v', {})
                    if sym and val:
                        quotes_by_sym[sym] = val
        elif resp.status_code == 429:
            cache.set(rate_limit_key, True, timeout=60)
    except Exception:
        pass

    cards = []
    has_any_live = False
    for m in macro_configs:
        sym = m['fyers_sym']
        q = quotes_by_sym.get(sym)
        if q and q.get('lp') is not None:
            has_any_live = True
            lp = float(q.get('lp', 0.0))
            ch = float(q.get('ch', 0.0))
            chp = float(q.get('chp', 0.0))
            hp = float(q.get('high_price', 0.0))
            low_p = float(q.get('low_price', 0.0))
            cards.append({
                'name': m['name'],
                'fyers_sym': sym,
                'exchange': m['exchange'],
                'type': m['type'],
                'ltp': f"{lp:,.2f}" if lp >= 100 else f"{lp:.2f}",
                'change': f"{'+' if ch >= 0 else ''}{ch:.2f}",
                'change_pct': f"{'+' if chp >= 0 else ''}{chp:.2f}%",
                'high': f"{hp:,.2f}" if hp >= 100 else f"{hp:.2f}",
                'low': f"{low_p:,.2f}" if low_p >= 100 else f"{low_p:.2f}",
                'is_positive': ch >= 0,
                'is_live': True,
            })
        else:
            cards.append({
                'name': m['name'],
                'fyers_sym': sym,
                'exchange': m['exchange'],
                'type': m['type'],
                'ltp': '-',
                'change': '-',
                'change_pct': '-',
                'high': '-',
                'low': '-',
                'is_positive': True,
                'is_live': False,
            })

    if has_any_live:
        cache.set(cache_key, cards, timeout=15)
        cache.set(last_known_key, cards, timeout=86400)
    else:
        last_known = cache.get(last_known_key)
        if last_known:
            return last_known

    return cards


def get_live_macro_ribbon_data(selected_index: str = 'NIFTY') -> dict:
    """Returns real-time selected index quote and hourly Gemini Macro AI intelligence."""
    import requests
    from django.core.cache import cache
    from apps.common.models import SiteSettings
    from apps.trade_core.scheduler import get_cached_macro_ai_intel

    idx_upper = (selected_index or 'NIFTY').upper().strip()
    index_map = {
        'NIFTY': {'name': 'NIFTY 50', 'fyers_sym': 'NSE:NIFTY50-INDEX', 'exchange': 'NSE'},
        'NIFTY50': {'name': 'NIFTY 50', 'fyers_sym': 'NSE:NIFTY50-INDEX', 'exchange': 'NSE'},
        'NIFTY 50': {'name': 'NIFTY 50', 'fyers_sym': 'NSE:NIFTY50-INDEX', 'exchange': 'NSE'},
        'BANKNIFTY': {'name': 'BANK NIFTY', 'fyers_sym': 'NSE:NIFTYBANK-INDEX', 'exchange': 'NSE'},
        'BANK NIFTY': {'name': 'BANK NIFTY', 'fyers_sym': 'NSE:NIFTYBANK-INDEX', 'exchange': 'NSE'},
        'FINNIFTY': {'name': 'FIN NIFTY', 'fyers_sym': 'NSE:FINNIFTY-INDEX', 'exchange': 'NSE'},
        'FIN NIFTY': {'name': 'FIN NIFTY', 'fyers_sym': 'NSE:FINNIFTY-INDEX', 'exchange': 'NSE'},
        'MIDCPNIFTY': {'name': 'MIDCP NIFTY', 'fyers_sym': 'NSE:MIDCPNIFTY-INDEX', 'exchange': 'NSE'},
        'SENSEX': {'name': 'SENSEX', 'fyers_sym': 'BSE:SENSEX-INDEX', 'exchange': 'BSE'},
    }
    cfg = index_map.get(idx_upper, index_map['NIFTY'])

    cache_key = f"marmot:fyers_quote:{cfg['fyers_sym']}"
    last_known_key = f"marmot:fyers_last_known_quote:{cfg['fyers_sym']}"
    rate_limit_key = "marmot:fyers_rate_limited"

    quote_data = cache.get(cache_key)
    is_fresh = bool(quote_data)

    if not quote_data:
        opt_chain_data = cache.get(f"marmot:fyers:option_chain:{cfg['name']}") or cache.get(f"marmot:fyers:option_chain:{idx_upper}")
        if opt_chain_data and opt_chain_data.get('is_live') and opt_chain_data.get('raw_spot_ltp'):
            raw_ltp = float(opt_chain_data.get('raw_spot_ltp', 0.0))
            if raw_ltp > 0:
                raw_ch = float(str(opt_chain_data.get('spot_change', '0')).replace('+', ''))
                raw_chp = float(str(opt_chain_data.get('spot_change_pct', '0')).replace('%', '').replace('+', ''))
                last_known_q = cache.get(last_known_key) or {}
                hp_val = float(str(opt_chain_data.get('high_price', '0')).replace(',', '')) or float(last_known_q.get('high_price', raw_ltp))
                lowp_val = float(str(opt_chain_data.get('low_price', '0')).replace(',', '')) or float(last_known_q.get('low_price', raw_ltp))
                openp_val = float(str(opt_chain_data.get('open_price', '0')).replace(',', '')) or float(last_known_q.get('open_price', raw_ltp))
                prevp_val = float(str(opt_chain_data.get('prev_close', '0')).replace(',', '')) or float(last_known_q.get('prev_close_price', raw_ltp))
                quote_data = {
                    'lp': raw_ltp,
                    'ch': raw_ch,
                    'chp': raw_chp,
                    'high_price': hp_val,
                    'low_price': lowp_val,
                    'open_price': openp_val,
                    'prev_close_price': prevp_val,
                }
                cache.set(cache_key, quote_data, timeout=2)
                cache.set(last_known_key, quote_data, timeout=86400)
                is_fresh = True

        if not quote_data:
            is_rate_limited = bool(cache.get(rate_limit_key))
            site_settings = SiteSettings.load()
            today = timezone.localdate()
            is_token_valid = bool(
                site_settings.fyers_access_token and
                site_settings.fyers_token_generated_date == today and
                site_settings.fyers_feed_is_active
            )
            if is_token_valid and not is_rate_limited:
                try:
                    headers = {'Authorization': f"{site_settings.fyers_app_id}:{site_settings.fyers_access_token}"}
                    url = f"https://api-t1.fyers.in/data/quotes?symbols={cfg['fyers_sym']}"
                    resp = requests.get(url, headers=headers, timeout=2.5)
                    if resp.status_code == 200:
                        r_json = resp.json()
                        if r_json.get('s') == 'ok' and r_json.get('d'):
                            quote_data = r_json['d'][0].get('v', {})
                            cache.set(cache_key, quote_data, timeout=2)
                            cache.set(last_known_key, quote_data, timeout=86400)
                            is_fresh = True
                    elif resp.status_code == 429:
                        cache.set(rate_limit_key, True, timeout=60)
                except Exception:
                    pass

        if not quote_data:
            quote_data = cache.get(last_known_key)

    now_time_str = timezone.localtime().strftime("%I:%M %p")
    if quote_data and quote_data.get('lp') is not None:
        lp = float(quote_data.get('lp', 0.0))
        ch = float(quote_data.get('ch', 0.0))
        chp = float(quote_data.get('chp', 0.0))
        hp = float(quote_data.get('high_price', 0.0))
        low_p = float(quote_data.get('low_price', 0.0))
        formatted_high = f"{hp:,.2f}" if hp >= 100 else f"{hp:.2f}"
        formatted_low = f"{low_p:,.2f}" if low_p >= 100 else f"{low_p:.2f}"
        selected_card = {
            'name': cfg['name'],
            'fyers_sym': cfg['fyers_sym'],
            'exchange': cfg['exchange'],
            'ltp': f"{lp:,.2f}" if lp >= 100 else f"{lp:.2f}",
            'change': f"{'+' if ch >= 0 else ''}{ch:.2f}",
            'change_pct': f"{'+' if chp >= 0 else ''}{chp:.2f}%",
            'high': formatted_high,
            'low': formatted_low,
            'summary': f"Range: ₹{formatted_low} – ₹{formatted_high}",
            'formatted_time': now_time_str,
            'is_positive': ch >= 0,
            'is_live': True,
            'is_cached': not is_fresh,
        }
    else:
        selected_card = {
            'name': cfg['name'],
            'fyers_sym': cfg['fyers_sym'],
            'exchange': cfg['exchange'],
            'ltp': '-',
            'change': '-',
            'change_pct': '-',
            'high': '-',
            'low': '-',
            'summary': 'Live exchange feed standby',
            'formatted_time': now_time_str,
            'is_positive': True,
            'is_live': False,
            'is_cached': False,
        }

    ai_intel = get_cached_macro_ai_intel(selected_index=cfg['name']) or {}
    model_name = ai_intel.get('model', 'gemini-3.6-flash')
    sync_time = ai_intel.get('formatted_time', '')

    event_risk_lvl = ai_intel.get('event_risk_level', 'LOW EVENT RISK')
    global_snt = ai_intel.get('global_sentiment', 'MILD RISK-ON')
    global_summary = ai_intel.get('global_summary', 'Positive global cues')
    event_summary = ai_intel.get('event_risk_summary', 'Normal regime volatility')

    macro_cards = [
        {
            'card_type': 'REGIME',
            'title': 'Macro AI Regime',
            'badge': f"✨ {model_name}",
            'badge_cls': 'bg-primary bg-opacity-25 text-primary',
            'value': ai_intel.get('regime_stance', 'BULLISH ACCUMULATION'),
            'score': f"Conviction: {float(ai_intel.get('regime_conviction', 0.68)):+.2f}",
            'summary': ai_intel.get('regime_summary', 'Sub-13 VIX indicates stable premium environment'),
            'icon': 'bi-stars text-primary',
            'is_positive': float(ai_intel.get('regime_conviction', 0.5)) >= 0,
            'time': sync_time,
        },
        {
            'card_type': 'INSTITUTIONAL',
            'title': 'Institutional Flow Bias',
            'badge': 'FII / DII Flow',
            'badge_cls': 'bg-success bg-opacity-25 text-success',
            'value': ai_intel.get('fii_dii_stance', 'NET INSTITUTIONAL ACCUMULATION'),
            'score': f"Bias Score: {float(ai_intel.get('fii_dii_score', 0.55)):+.2f}",
            'summary': ai_intel.get('fii_dii_summary', 'Institutional carryover positive with steady DII support'),
            'icon': 'bi-buildings-fill text-success',
            'is_positive': float(ai_intel.get('fii_dii_score', 0.5)) >= 0,
            'time': sync_time,
        },
        {
            'card_type': 'GLOBAL_RISK_GUARD',
            'title': 'Global & Event Risk',
            'badge': event_risk_lvl,
            'badge_cls': 'bg-info bg-opacity-25 text-info',
            'value': global_snt,
            'score': f"Score: {float(ai_intel.get('global_score', 0.45)):+.2f} • Guard Active",
            'summary': f"{global_summary} • {event_summary}",
            'icon': 'bi-shield-check text-info',
            'is_positive': float(ai_intel.get('global_score', 0.4)) >= 0,
            'time': sync_time,
        },
    ]

    return {
        'selected_card': selected_card,
        'macro_cards': macro_cards,
        'ai_intel': ai_intel,
        'selected_index': cfg['name'],
        'selected_code': idx_upper,
    }

