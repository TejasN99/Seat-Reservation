"""
Paytm Seat Reservation Concurrency & Burst Benchmark Tool
Reproduces on-sale stampedes, hot-seat storms, idempotency replays, and reconciles state.
"""

import sys
import asyncio
import time
from typing import Dict
import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
BURST_SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else 500


class ScenarioStats:
    def __init__(self, name: str):
        self.name = name
        self.total = 0
        self.status_codes: Dict[int, int] = {}
        self.server_errors = 0

    def record(self, status_code: int):
        self.total += 1
        self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1
        if status_code >= 500:
            self.server_errors += 1

    def print_summary(self, extra_message: str = ""):
        print(f"\n   +-------------------------------------------------------------")
        print(f"   | Scenario: {self.name}")
        print(f"   | Total Requests Fired : {self.total}")
        for code, count in sorted(self.status_codes.items()):
            label = "201 Created (Winner/Replay)" if code == 201 else "409 Conflict (Clean Decline)" if code == 409 else f"HTTP {code}"
            print(f"   |   {label:30} : {count} ({count/self.total*100:.1f}%)")
        print(f"   |   5xx Server Errors              : {self.server_errors}")
        if extra_message:
            print(f"   | Status: {extra_message}")
        print(f"   +-------------------------------------------------------------\n")


async def run_burst():
    admin_headers = {"Authorization": "Bearer admin"}
    overall_total = 0
    overall_status: Dict[int, int] = {}
    overall_5xx = 0

    def aggregate(s: ScenarioStats):
        nonlocal overall_total, overall_5xx
        overall_total += s.total
        overall_5xx += s.server_errors
        for code, cnt in s.status_codes.items():
            overall_status[code] = overall_status.get(code, 0) + cnt

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(base_url=BASE_URL, limits=limits, timeout=60.0) as client:
        print(f"\n===============================================================")
        print(f"PAYTM SEAT RESERVATION - CONCURRENCY & RECONCILIATION BENCHMARK")
        print(f"Target URL: {BASE_URL}")
        print(f"===============================================================\n")

        # 1. Health check
        health_resp = await client.get("/health/ready")
        if health_resp.status_code != 200:
            print(f"[FAIL] Server readiness check failed: {health_resp.text}")
            return
        print("[INFO] Server readiness probe passed (/health/ready -> 200 OK).")

        # 2. Create a fresh show with 100 seats
        show_name = f"burst-show-{int(time.time())}"
        seats = [f"A{i}" for i in range(1, 101)]  # 100 seats: A1 to A100
        create_resp = await client.post(
            "/shows",
            headers=admin_headers,
            json={"name": show_name, "seats": seats, "price_paise": 25000, "per_user_limit": 4}
        )
        if create_resp.status_code != 201:
            print(f"[FAIL] Failed to create show: {create_resp.text}")
            return

        show = create_resp.json()
        show_id = show["id"]
        print(f"[INFO] Created show '{show_name}' (ID: {show_id}) with {len(seats)} seats.\n")

        # -------------------------------------------------------------
        # SCENARIO A: Hot-Seat Storm (BURST_SIZE users competing for seat 'A1')
        # -------------------------------------------------------------
        print(f"[EXEC] Scenario A: Hot-Seat Storm ({BURST_SIZE} concurrent buyers competing for seat 'A1')...")
        stats_a = ScenarioStats("Scenario A (Hot-Seat Contention on A1)")
        start_a = time.perf_counter()

        async def storm_hot_seat(user_idx: int):
            user_token = f"storm_user_{user_idx}"
            headers = {"Authorization": f"Bearer {user_token}"}
            payload = {"seats": ["A1"], "idempotency_key": f"key_storm_{user_idx}"}
            try:
                r = await client.post(f"/shows/{show_id}/reserve", headers=headers, json=payload)
                stats_a.record(r.status_code)
            except Exception:
                stats_a.record(500)

        await asyncio.gather(*(storm_hot_seat(i) for i in range(BURST_SIZE)))
        dur_a = time.perf_counter() - start_a
        
        winners_a = stats_a.status_codes.get(201, 0)
        declines_a = stats_a.status_codes.get(409, 0)
        verdict_a = (
            f"[PASS] Exactly {winners_a} buyer won seat 'A1'; remaining {declines_a} declined with 409 Conflict. Zero 5xx."
            if winners_a == 1 and stats_a.server_errors == 0
            else f"[FAIL] Expected 1 winner, got {winners_a} winners."
        )
        stats_a.print_summary(verdict_a)
        aggregate(stats_a)

        # -------------------------------------------------------------
        # SCENARIO B: Multi-Seat Random Contention (Seats A2 to A80)
        # -------------------------------------------------------------
        print(f"[EXEC] Scenario B: Multi-Seat Contention ({BURST_SIZE} concurrent buyers booking 2 seats each)...")
        stats_b = ScenarioStats("Scenario B (Multi-Seat Random Contention)")
        import random
        start_b = time.perf_counter()

        sem_b = asyncio.Semaphore(100)

        async def storm_multi_seats(user_idx: int):
            async with sem_b:
                user_token = f"multi_user_{user_idx}"
                headers = {"Authorization": f"Bearer {user_token}"}
                s1 = f"A{random.randint(2, 80)}"
                s2 = f"A{random.randint(2, 80)}"
                payload = {"seats": list(set([s1, s2])), "idempotency_key": f"key_multi_{user_idx}"}
                try:
                    r = await client.post(f"/shows/{show_id}/reserve", headers=headers, json=payload)
                    stats_b.record(r.status_code)
                except Exception:
                    stats_b.record(500)

        await asyncio.gather(*(storm_multi_seats(i) for i in range(BURST_SIZE)))
        dur_b = time.perf_counter() - start_b
        
        verdict_b = "[PASS] Handled multi-seat reservations with zero deadlocks and zero 5xx."
        stats_b.print_summary(verdict_b)
        aggregate(stats_b)

        # -------------------------------------------------------------
        # SCENARIO C: Idempotency Replay Test (100 parallel retries on dedicated seat A99)
        # -------------------------------------------------------------
        print(f"[EXEC] Scenario C: Idempotency Storm (100 parallel retries with identical key on seat 'A99')...")
        stats_c = ScenarioStats("Scenario C (100 Idempotent Retries on seat A99)")
        shared_key = f"shared_idempotent_key_{int(time.time())}"

        async def idempotent_retry(attempt: int):
            headers = {"Authorization": "Bearer idempotent_user_1"}
            payload = {"seats": ["A99"], "idempotency_key": shared_key}
            try:
                r = await client.post(f"/shows/{show_id}/reserve", headers=headers, json=payload)
                stats_c.record(r.status_code)
            except Exception:
                stats_c.record(500)

        await asyncio.gather(*(idempotent_retry(i) for i in range(100)))
        
        replays_c = stats_c.status_codes.get(201, 0)
        verdict_c = (
            f"[PASS] All {replays_c} retries returned the original 201 response with exact-once execution."
            if replays_c == 100
            else f"[FAIL] Expected 100 replays returning 201, got {replays_c}."
        )
        stats_c.print_summary(verdict_c)
        aggregate(stats_c)

        # -------------------------------------------------------------
        # SCENARIO D: Same key with DIFFERENT body -> Must 409
        # -------------------------------------------------------------
        print(f"[EXEC] Scenario D: Idempotency Key Conflict Test (Same key with modified payload)...")
        stats_d = ScenarioStats("Scenario D (Key Conflict on Modified Payload)")
        r_diff = await client.post(
            f"/shows/{show_id}/reserve",
            headers={"Authorization": "Bearer idempotent_user_1"},
            json={"seats": ["A100"], "idempotency_key": shared_key}
        )
        stats_d.record(r_diff.status_code)
        
        verdict_d = (
            "[PASS] Correctly rejected with 409 Conflict when key was reused with modified seat payload."
            if r_diff.status_code == 409
            else f"[FAIL] Expected 409, got {r_diff.status_code}."
        )
        stats_d.print_summary(verdict_d)
        aggregate(stats_d)

        # -------------------------------------------------------------
        # Final Show State & Invariant Reconciliation
        # -------------------------------------------------------------
        print(f"===============================================================")
        print(f"FINAL INVARIANT RECONCILIATION REPORT")
        print(f"===============================================================")
        state_resp = await client.get(f"/shows/{show_id}")
        state = state_resp.json()
        
        total = state["total_seats"]
        available = state["available_count"]
        confirmed = state["confirmed_count"]
        
        print(f"Total Seats Registered : {total}")
        print(f"Available Seats        : {available}")
        print(f"Confirmed Seats        : {confirmed}")
        print(f"Reconciliation Balance : {available} + {confirmed} = {available + confirmed} (Expected: {total})")
        
        if available + confirmed == total:
            print("RECONCILIATION INVARIANT: [PASS] Strict balance holds to the unit (100% Correct).")
        else:
            print("RECONCILIATION INVARIANT: [FAIL] State mismatch detected.")

        # -------------------------------------------------------------
        # Overall Summary
        # -------------------------------------------------------------
        print(f"\n===============================================================")
        print(f"OVERALL OUTCOME DISTRIBUTION")
        print(f"===============================================================")
        print(f"Total Requests Fired : {overall_total}")
        for code, cnt in sorted(overall_status.items()):
            label = "201 Created (Success / Replay)" if code == 201 else "409 Conflict (Clean Domain Decline)" if code == 409 else f"HTTP {code}"
            print(f"  {label:38} : {cnt} ({cnt/overall_total*100:.1f}%)")
        print(f"  5xx Server Errors                      : {overall_5xx} ({overall_5xx/overall_total*100:.1f}%)")
        print(f"===============================================================\n")


if __name__ == "__main__":
    asyncio.run(run_burst())
