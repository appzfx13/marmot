import csv
import io
import json
import logging
import os
import re
import time
import urllib.request
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class DhanScripResolver:
    """Resolves human-readable symbols and option contracts to Dhan numeric security IDs and scrips."""

    _cache = None
    _cache_file = '/app/backup/dhan_scrip_cache.json'

    @classmethod
    def load(cls) -> dict:
        """Loads scrip mapping from cached JSON or downloads Dhan Scrip Master CSV."""
        if cls._cache:
            return cls._cache
        if os.path.exists(cls._cache_file):
            try:
                with open(cls._cache_file, 'r', encoding='utf-8') as f:
                    cls._cache = json.load(f)
                    return cls._cache
            except Exception as e:
                logger.warning("Could not read dhan_scrip_cache.json: %s", e)

        equities = {}
        options = []
        try:
            url = 'https://images.dhan.co/api-data/api-scrip-master.csv'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                reader = csv.reader(io.TextIOWrapper(resp, encoding='utf-8', errors='ignore'))
                next(reader, None)
                for r in reader:
                    if len(r) > 10 and r[0] == 'NSE':
                        sec_id = r[2]
                        lot = int(float(r[6])) if r[6] else 1
                        expiry = r[8]
                        strike = float(r[9]) if r[9] else 0.0
                        opt_type = r[10]
                        sym = r[5].upper()
                        cust = r[7].upper() if len(r) > 7 else ''

                        if r[1] == 'E':
                            equities[sym] = {'sec_id': sec_id, 'lot': lot, 'sym': sym, 'seg': 'NSE_EQ'}
                            if cust:
                                equities[cust] = equities[sym]
                        elif r[1] == 'D' and opt_type in ('CE', 'PE'):
                            idx = next((cand for cand in ['BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTY'] if cand in sym), '')
                            if idx:
                                options.append({
                                    'sec_id': sec_id,
                                    'sym': sym,
                                    'cust': cust,
                                    'lot': lot,
                                    'expiry': expiry,
                                    'strike': strike,
                                    'type': opt_type,
                                    'idx': idx,
                                    'seg': 'NSE_FNO'
                                })
            cls._cache = {'equities': equities, 'options': options, 'created_at': time.time()}
            os.makedirs(os.path.dirname(cls._cache_file), exist_ok=True)
            with open(cls._cache_file, 'w', encoding='utf-8') as f:
                json.dump(cls._cache, f)
        except Exception as err:
            logger.error("Failed to download or cache Dhan scrip master: %s", err)
            cls._cache = {'equities': {}, 'options': [], 'created_at': time.time()}

        return cls._cache

    @classmethod
    def resolve(cls, symbol: str, security_id: Optional[str] = None) -> Tuple[str, str, int, str]:
        """Resolves symbol to (numeric_security_id, trading_symbol, lot_units, exchange_segment)."""
        data = cls.load()
        from apps.common.constants import get_historical_lot_size

        if security_id and str(security_id).strip().isdigit():
            sec_str = str(security_id).strip()
            for o in data.get('options', []):
                if o['sec_id'] == sec_str:
                    return sec_str, o['sym'], o['lot'], o['seg']
            return sec_str, str(symbol)[:25], get_historical_lot_size(symbol), 'NSE_FNO'

        clean = str(symbol).strip().upper()
        if clean.isdigit():
            for o in data.get('options', []):
                if o['sec_id'] == clean:
                    return clean, o['sym'], o['lot'], o['seg']
            return clean, clean, get_historical_lot_size(symbol), 'NSE_FNO'

        # 1. Direct equity match
        sym_clean = re.sub(r'^(NSE:|BSE:)', '', clean).split('-')[0].strip()
        if sym_clean in data.get('equities', {}):
            eq = data['equities'][sym_clean]
            return eq['sec_id'], eq['sym'], eq['lot'], eq['seg']

        # 2. Option contract parsing
        clean_spaceless = clean.replace(' ', '').replace('-', '').replace('_', '')
        idx = next((cand for cand in ['BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTY'] if cand in clean_spaceless), None)
        m = re.search(r'(\d{5})\s*(CE|PE|CALL|PUT)', clean) or re.search(r'(\d{4,6})\s*(CE|PE|CALL|PUT)', clean)
        if idx and m:
            strike = float(m.group(1))
            opt_type = 'CE' if m.group(2) in ('CE', 'CALL') else 'PE'
            matches = [
                o for o in data.get('options', [])
                if o['idx'] == idx and o['type'] == opt_type and abs(o['strike'] - strike) < 0.1
            ]
            if matches:
                matches.sort(key=lambda x: x['expiry'])
                match = matches[0]
                return match['sec_id'], match['sym'], match['lot'], match['seg']

        fb_lot = get_historical_lot_size(symbol)
        clean_sec_id = re.sub(r'[^0-9]', '', clean)
        if clean_sec_id:
            return clean_sec_id, clean[:25], fb_lot, 'NSE_FNO'

        return '1333', clean[:25], fb_lot, 'NSE_FNO'
