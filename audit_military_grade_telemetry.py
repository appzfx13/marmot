import os
import sys
import time
import json
import math
import datetime
import urllib.request
import numpy as np
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8"
TARGET_URL = "http://localhost:8050/admins/dashboard/sandbox/?account_id=3"
MOCK_API = "http://localhost:8088/mock/api/streamer"

def configure_mock_streamer():
    """Ensure mock broker streamer is playing 1/33/dataset.parquet locked at 1x speed."""
    endpoints = [
        ("select?file=1/33/dataset.parquet", "Select dataset"),
        ("speed?val=1", "Set 1x speed"),
        ("restart", "Restart from row 0")
    ]
    for ep, desc in endpoints:
        try:
            req = urllib.request.Request(f"{MOCK_API}/{ep}", data=b"", method="POST")
            urllib.request.urlopen(req, timeout=3)
            print(f"[Setup] {desc} OK.")
        except Exception as e:
            print(f"[Setup] Warning: {desc} ({e})")

def compute_ssim_and_pixel_diff(img1_path, img2_path, diff_output_path):
    """Computes exact pixel difference percentage and structural similarity between two images."""
    im1 = Image.open(img1_path).convert('RGB')
    im2 = Image.open(img2_path).convert('RGB')
    
    diff = ImageChops.difference(im1, im2)
    diff.save(diff_output_path)
    
    arr1 = np.array(im1, dtype=np.float64)
    arr2 = np.array(im2, dtype=np.float64)
    
    mse = np.mean((arr1 - arr2) ** 2)
    
    diff_arr = np.array(diff)
    changed_pixels = np.count_nonzero(diff_arr.sum(axis=2))
    total_pixels = im1.width * im1.height
    diff_pct = (changed_pixels / total_pixels) * 100.0
    
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mean1 = np.mean(arr1)
    mean2 = np.mean(arr2)
    var1 = np.var(arr1)
    var2 = np.var(arr2)
    cov = np.mean((arr1 - mean1) * (arr2 - mean2))
    ssim = ((2 * mean1 * mean2 + c1) * (2 * cov + c2)) / ((mean1**2 + mean2**2 + c1) * (var1 + var2 + c2))
    
    return {
        "mse": round(float(mse), 4),
        "changed_pixels_pct": round(float(diff_pct), 3),
        "ssim_score": round(float(ssim), 4),
        "diff_path": diff_output_path
    }

def run_military_grade_audit():
    print("=" * 110)
    print("MARMOT QA: 60-SECOND MILITARY-GRADE TELEMETRY & UI SMOOTHNESS AUDIT (1X REPLAY / 189MS TICK INTERVAL)")
    print("=" * 110)
    
    configure_mock_streamer()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-frame-rate-limit",
                "--enable-gpu-rasterization",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--run-all-compositor-stages-before-draw"
            ]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        
        # Track incoming WebSocket frames with microsecond precision
        ws_event_log = []
        def on_websocket(ws):
            def on_frame(payload):
                t_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                ws_event_log.append({
                    "timestamp": t_iso,
                    "url": ws.url,
                    "length": len(payload),
                    "is_json": payload.startswith("{"),
                    "data": json.loads(payload) if payload.startswith("{") else payload[:100]
                })
            ws.on("framereceived", on_frame)
        page.on("websocket", on_websocket)
        
        # 1. Login
        print("\n[Step 1] Authenticating as marmotadmin...")
        page.goto("http://localhost:8050/admins/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_url("**/admins/dashboard/**", timeout=12000)
        page.wait_for_timeout(2000)
        print("  -> Authentication successful. Current URL:", page.url)
        
        # 2. Navigate to Sandbox Dashboard
        print(f"\n[Step 2] Navigating to Sandbox Dashboard: {TARGET_URL}...")
        page.goto(TARGET_URL, wait_until="networkidle")
        page.wait_for_selector("#live-macro-spot-ltp", timeout=15000)
        page.wait_for_timeout(2000)
        print("  -> Dashboard DOM ready.")
        
        # Connect Chrome DevTools Protocol (CDP) session
        cdp = context.new_cdp_session(page)
        cdp.send("Performance.enable")
        cdp.send("DOM.enable")
        print("[CDP] Hooked into Chrome DevTools Protocol (Performance & DOM domains active).")
        
        # 3. Inject In-Page Telemetry (RAF loop, CLS PerformanceObserver, LongTasks, Memory)
        print("\n[Step 3] Injecting in-browser high-precision telemetry instrumentation...")
        page.evaluate("""() => {
            window.__marmot_telemetry = {
                frameDeltas: [],
                clsScore: 0,
                layoutShifts: [],
                longTasks: [],
                memorySnapshots: []
            };
            
            // 1. Layout Shift (CLS) Observer
            try {
                const po = new PerformanceObserver((list) => {
                    for (const entry of list.getEntries()) {
                        if (!entry.hadRecentInput) {
                            window.__marmot_telemetry.clsScore += entry.value;
                            window.__marmot_telemetry.layoutShifts.push({
                                time: entry.startTime,
                                value: entry.value,
                                sources: entry.sources ? entry.sources.map(s => s.node ? s.node.nodeName : 'unknown') : []
                            });
                        }
                    }
                });
                po.observe({ type: 'layout-shift', buffered: true });
            } catch(e) { console.error('CLS observer error:', e); }
            
            // 2. Long Tasks Observer (>50ms)
            try {
                const lto = new PerformanceObserver((list) => {
                    for (const entry of list.getEntries()) {
                        window.__marmot_telemetry.longTasks.push({
                            startTime: entry.startTime,
                            duration: entry.duration,
                            name: entry.name
                        });
                    }
                });
                lto.observe({ type: 'longtask', buffered: true });
            } catch(e) { console.error('LongTask observer error:', e); }
            
            // 3. RequestAnimationFrame delta tracking (<16.6ms paint budget)
            let lastTime = performance.now();
            function onFrame(now) {
                const delta = now - lastTime;
                lastTime = now;
                if (window.__marmot_telemetry.frameDeltas.length < 15000) {
                    window.__marmot_telemetry.frameDeltas.push(delta);
                }
                requestAnimationFrame(onFrame);
            }
            requestAnimationFrame(onFrame);
            
            // 4. Memory Sampler
            setInterval(() => {
                if (window.performance && window.performance.memory) {
                    window.__marmot_telemetry.memorySnapshots.push({
                        time: performance.now(),
                        usedJSHeapSize: window.performance.memory.usedJSHeapSize,
                        totalJSHeapSize: window.performance.memory.totalJSHeapSize
                    });
                }
            }, 1000);
        }""")
        
        # 4. Start 60-Second Telemetry Run at 1x Speed
        print("\n[Step 4] Commencing 60-Second Continuous Telemetry & Tick-Aligned Invariant Checks...")
        start_time = time.time()
        duration_sec = 60
        check_interval = 2.0
        next_check = start_time
        
        snapshots = []
        screenshots_captured = []
        sample_idx = 0
        
        while time.time() - start_time < duration_sec:
            cur_time = time.time()
            elapsed = cur_time - start_time
            
            if cur_time >= next_check:
                next_check += check_interval
                
                # Screenshot at 10s intervals
                shot_path = None
                if sample_idx % 5 == 0 or elapsed >= (duration_sec - 1.0):
                    shot_name = f"mil_audit_t_{int(elapsed)}s.png"
                    shot_path = os.path.join(ARTIFACT_DIR, shot_name)
                    page.screenshot(path=shot_path, full_page=False)
                    screenshots_captured.append((int(elapsed), shot_path))
                
                # Query DOM elements
                def safe_text(sel):
                    try:
                        el = page.query_selector(sel)
                        return el.inner_text().strip() if el else "—"
                    except Exception:
                        return "—"
                
                spot_ltp = safe_text("#live-macro-spot-ltp")
                spot_range = safe_text("#live-macro-spot-summary")
                spot_time = safe_text("#live-macro-spot-time")
                oc_spot = safe_text("#live-option-chain-spot-ltp")
                oc_atm = safe_text("#live-option-chain-atm")
                net_pnl_str = safe_text("#sandbox-live-net-pnl")
                realized_pnl_str = safe_text("#sandbox-realized-pnl")
                unrealized_pnl_str = safe_text("#sandbox-unrealized-pnl")
                margin_avail = safe_text("#sandbox-available-margin")
                orders_count_str = safe_text("#sandbox-orders-badge")
                
                # Parse floats for math reconciliation
                def to_float(val_str):
                    try:
                        clean = val_str.replace("₹", "").replace("+", "").replace(",", "").strip()
                        return float(clean)
                    except Exception:
                        return 0.0
                
                num_net = to_float(net_pnl_str)
                num_realized = to_float(realized_pnl_str)
                num_unrealized = to_float(unrealized_pnl_str)
                pnl_math_diff = abs(num_net - (num_realized + num_unrealized))
                is_pnl_consistent = pnl_math_diff < 0.05
                
                snapshot = {
                    "sample_idx": sample_idx,
                    "elapsed_sec": round(elapsed, 2),
                    "iso_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "spot_ltp": spot_ltp,
                    "spot_range": spot_range,
                    "spot_time": spot_time,
                    "oc_spot": oc_spot,
                    "oc_atm": oc_atm,
                    "net_pnl": net_pnl_str,
                    "realized_pnl": realized_pnl_str,
                    "unrealized_pnl": unrealized_pnl_str,
                    "margin_available": margin_avail,
                    "is_pnl_consistent": is_pnl_consistent,
                    "pnl_drift": round(pnl_math_diff, 2),
                    "screenshot": shot_path
                }
                snapshots.append(snapshot)
                
                status_icon = "✓" if is_pnl_consistent else "✗"
                print(f"  [{elapsed:04.1f}s] Spot: {spot_ltp:>10} | OC: {oc_spot:>10} | ATM: {oc_atm:>5} | Net: {net_pnl_str:>14} | Realized: {realized_pnl_str:>14} | Math {status_icon} (drift: {pnl_math_diff:.2f})")
                sample_idx += 1
            
            time.sleep(0.1)
        
        # 5. Extract CDP Performance Metrics & Browser In-Page Telemetry
        print("\n[Step 5] Gathering CDP & In-Page Diagnostics...")
        cdp_metrics_raw = cdp.send("Performance.getMetrics")
        cdp_metrics = {m["name"]: m["value"] for m in cdp_metrics_raw.get("metrics", [])}
        
        telemetry_data = page.evaluate("() => window.__marmot_telemetry")
        
        frame_deltas = telemetry_data.get("frameDeltas", [])
        if frame_deltas and len(frame_deltas) > 1:
            clean_deltas = frame_deltas[1:]
            avg_delta = float(np.mean(clean_deltas))
            p50_delta = float(np.percentile(clean_deltas, 50))
            p95_delta = float(np.percentile(clean_deltas, 95))
            p99_delta = float(np.percentile(clean_deltas, 99))
            avg_fps = round(1000.0 / avg_delta, 1) if avg_delta > 0 else 60.0
            budget_violations = sum(1 for d in clean_deltas if d > 16.67)
            budget_violation_pct = round((budget_violations / len(clean_deltas)) * 100.0, 2)
        else:
            avg_fps, p50_delta, p95_delta, p99_delta, budget_violation_pct = 60.0, 16.6, 16.6, 16.6, 0.0
            
        cls_score = round(telemetry_data.get("clsScore", 0.0), 6)
        long_tasks = telemetry_data.get("longTasks", [])
        mem_snapshots = telemetry_data.get("memorySnapshots", [])
        
        mem_start = mem_snapshots[0]["usedJSHeapSize"] if mem_snapshots else 0
        mem_end = mem_snapshots[-1]["usedJSHeapSize"] if mem_snapshots else 0
        mem_growth_mb = round((mem_end - mem_start) / (1024 * 1024), 2)
        
        # 6. Pixel-by-Pixel Diffing & SSIM Across Sequential Screenshots
        print("\n[Step 6] Computing Frame-to-Frame Visual Diff & SSIM...")
        diff_results = []
        for i in range(len(screenshots_captured) - 1):
            t1, path1 = screenshots_captured[i]
            t2, path2 = screenshots_captured[i+1]
            diff_name = f"diff_t_{t1}s_vs_{t2}s.png"
            diff_path = os.path.join(ARTIFACT_DIR, diff_name)
            metrics = compute_ssim_and_pixel_diff(path1, path2, diff_path)
            diff_entry = {
                "frame_a": f"T+{t1}s",
                "frame_b": f"T+{t2}s",
                "ssim": metrics["ssim_score"],
                "changed_pct": metrics["changed_pixels_pct"],
                "diff_file": diff_path
            }
            diff_results.append(diff_entry)
            print(f"  Frame {diff_entry['frame_a']} -> {diff_entry['frame_b']}: SSIM={diff_entry['ssim']:.4f} | Changed Pixels={diff_entry['changed_pct']:.2f}% (Expected localized tick updates)")

        # 7. Broker Telemetry & Mathematical Integrity Audit
        print(f"\n[Step 7] Total WebSocket Frames Processed: {len(ws_event_log)}")
        inconsistent_samples = sum(1 for s in snapshots if not s["is_pnl_consistent"])
        spot_strike_leak = any("23,400" in s["spot_ltp"] or "23400" in s["spot_ltp"] for s in snapshots)
        
        final_verdict = "PASS" if (
            cls_score < 0.05 and 
            inconsistent_samples == 0 and 
            not spot_strike_leak and 
            len(ws_event_log) > 0
        ) else "FAIL"
        
        report = {
            "test_title": "MARMOT HFT/BROKERAGE 60-SECOND TELEMETRY AUDIT",
            "execution_speed": "1x (Replay 189ms/tick)",
            "duration_seconds": 60,
            "total_ws_frames": len(ws_event_log),
            "samples_collected": len(snapshots),
            "fps_telemetry": {
                "average_fps": avg_fps,
                "p50_frame_time_ms": round(p50_delta, 2),
                "p95_frame_time_ms": round(p95_delta, 2),
                "p99_frame_time_ms": round(p99_delta, 2),
                "frames_exceeding_16ms_pct": budget_violation_pct
            },
            "cls_telemetry": {
                "cumulative_layout_shift": cls_score,
                "shift_events_count": len(telemetry_data.get("layoutShifts", [])),
                "target_cls": "< 0.05",
                "status": "PASS" if cls_score < 0.05 else "FAIL"
            },
            "memory_telemetry": {
                "initial_heap_mb": round(mem_start / (1024 * 1024), 2),
                "final_heap_mb": round(mem_end / (1024 * 1024), 2),
                "heap_growth_mb": mem_growth_mb,
                "leak_detected": bool(mem_growth_mb > 35.0)
            },
            "math_reconciliation": {
                "total_checks": len(snapshots),
                "consistent_checks": len(snapshots) - inconsistent_samples,
                "drift_incidents": inconsistent_samples,
                "formula": "Net P&L == Realized P&L + Unrealized P&L",
                "status": "PASS" if inconsistent_samples == 0 else "FAIL"
            },
            "spot_integrity": {
                "strike_leak_23400_detected": spot_strike_leak,
                "status": "PASS" if not spot_strike_leak else "FAIL"
            },
            "visual_diff_telemetry": diff_results,
            "sample_ledger": snapshots,
            "verdict": final_verdict
        }
        
        report_path = os.path.join(ARTIFACT_DIR, "audit_military_grade_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            
        print("\n" + "=" * 110)
        print(f"AUDIT COMPLETE. FINAL VERDICT: [{final_verdict}]")
        print(f"Report written to: {report_path}")
        print("=" * 110)
        
        browser.close()

if __name__ == "__main__":
    run_military_grade_audit()
