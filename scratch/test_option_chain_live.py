import urllib.request
import json
import time

def test_chain():
    req_sel = urllib.request.Request('http://localhost:8088/mock/api/streamer/select?file=1/20/dataset.parquet', data=b'', method='POST')
    try:
        with urllib.request.urlopen(req_sel) as resp:
            print("Select response:", resp.read().decode()[:80])
    except Exception as e:
        print("Select error:", e)

    # Let it stream
    for step in range(5):
        time.sleep(2)
        try:
            with urllib.request.urlopen('http://localhost:8088/mock/v2/optionchain?index=NIFTY') as resp:
                data = json.loads(resp.read().decode())
                print("\n--- STEP %d: Time=%s Spot=%s ATM=%s Expiry=%s Live=%s ---" % (
                    step + 1,
                    str(data.get('lastUpdated')),
                    str(data.get('spotLTP')),
                    str(data.get('atmStrike')),
                    str(data.get('expiryDate')),
                    str(data.get('isLive')),
                ))
                strikes = data.get('strikes', [])
                print("%-8s | %-10s | %-10s | %-10s | %-10s" % ('Strike', 'CE LTP', 'CE OI', 'PE LTP', 'PE OI'))
                print('-'*55)
                for s in strikes[8:24]:
                    print("%-8s | %-10s | %-10s | %-10s | %-10s" % (
                        str(s.get('strike')),
                        str(s.get('ce_ltp')),
                        str(s.get('ce_oi')),
                        str(s.get('pe_ltp')),
                        str(s.get('pe_oi')),
                    ))
        except Exception as e:
            print('Optionchain error:', e)

if __name__ == '__main__':
    test_chain()
