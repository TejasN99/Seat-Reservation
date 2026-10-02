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


class BurstStats:
    def __init__(self):
        self.total = 0
        self.status_codes: Dict[int, int] = {}
        self.reasons: Dict[str, int] = {}
        self.server_errors = 0

    def record(self, status_code: int, detail: str = ""):
        self.total += 1
        self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1
        if status_code >= 500:
            self.server_errors += 1
        if detail:
            self.reasons[detail] = self.reasons.get(detail, 0) + 1


async def run_burst():
    stats = BurstStats()
    admin_headers = {"Authorization": "Bearer admin"}
    
    limits = httpx.Limits(max_keepalive_connections=100, max_connections=200)
    async with httpx.AsyncClient(base_url=BASE_URL, limits=limits, timeout=30.0) as client:
        print(f"\n=======================================================")
        print(f"🔥 Starting On-Sale Concurrency Burst against {BASE_URL}")
        print(f"=======================================================\n")

        # 1. Health check
        health_resp = await client.get("/health/ready")
        if health_resp.status_code != 200:
            print(f"❌ Server readiness check failed: {health_resp.text}")
            return
        print("✅ Server readiness probe passed.")

        # 2. Create a fresh show
        show_name = f"burst-show-{int(time.time())}"
        seats = [f"A{i}" for i in range(1, 51)]  # 50 seats: A1 to A50
        create_resp = await client.post(
            "/shows",
            headers=admin_headers,
            json={"name": show_name, "seats": seats, "price_paise": 25000, "per_user_limit": 4}
        )
        if create_resp.status_code != 201:
            print(f"❌ Failed to create show: {create_resp.text}")
            return

        show = create_resp.json()
        show_id = show["id"]
        print(f"✅ Created show '{show_name}' (ID: {show_id}) with {len(seats)} seats.")

        # 3. SCENARIO A: Hot-Seat Storm (BURST_SIZE users competing for seat 'A1')
        print(f"\n⚡ [Scenario A] Hot-Seat Storm: {BURST_SIZE} concurrent buyers stampeding seat 'A1'...")
        start_a = time.perf_counter()

        async def storm_hot_seat(user_idx: int):
            user_token = f"storm_user_{user_idx}"
            headers = {"Authorization": f"Bearer {user_token}"}
            payload = {"seats": ["A1"], "idempotency_key": f"key_storm_{user_idx}"}
            try:
                r = await client.post(f"/shows/{show_id}/reserve", headers=headers, json=payload)
                stats.record(r.status_code, "Seat taken" if r.status_code == 409 else "")
            except Exception as e:
                stats.record(500, str(e))

        await asyncio.gather(*(storm_hot_seat(i) for i in range(BURST_SIZE)))
        dur_a = time.perf_counter() - start_a
        print(f"   Completed {BURST_SIZE} requests in {dur_a:.2f}s ({BURST_SIZE/dur_a:.0f} req/s).")

        # 4. SCENARIO B: Multi-Seat Random Contention (BURST_SIZE users requesting 2 random seats)
        print(f"\n⚡ [Scenario B] Multi-Seat Contention: {BURST_SIZE} concurrent buyers requesting 2 seats each...")
        import random
        start_b = time.perf_counter()

        async def storm_multi_seats(user_idx: int):
            user_token = f"multi_user_{user_idx}"
            headers = {"Authorization": f"Bearer {user_token}"}
            s1 = f"A{random.randint(1, 50)}"
            s2 = f"A{random.randint(1, 50)}"
            payload = {"seats": list(set([s1, s2])), "idempotency_key": f"key_multi_{user_idx}"}
            try:
                r = await client.post(f"/shows/{show_id}/reserve", headers=headers, json=payload)
                stats.record(r.status_code)
            except Exception as e:
                stats.record(500, str(e))

        await asyncio.gather(*(storm_multi_seats(i) for i in range(BURST_SIZE)))
        dur_b = time.perf_counter() - start_b
        print(f"   Completed {BURST_SIZE} requests in {dur_b:.2f}s ({BURST_SIZE/dur_b:.0f} req/s).")

        # 5. SCENARIO C: Idempotency Replay Test (100 parallel retries with SAME key)
        print(f"\n⚡ [Scenario C] Idempotency Storm: 100 parallel retries with the SAME key...")
        shared_key = f"shared_idempotent_key_{int(time.time())}"

        async def idempotent_retry(attempt: int):
            headers = {"Authorization": "Bearer idempotent_user_1"}
            payload = {"seats": ["A50"], "idempotency_key": shared_key}
            try:
                r = await client.post(f"/shows/{show_id}/reserve", headers=headers, json=payload)
                stats.record(r.status_code)
            except Exception as e:
                stats.record(500, str(e))

        await asyncio.gather(*(idempotent_retry(i) for i in range(100)))

        # 6. SCENARIO D: Same key with DIFFERENT body -> Must 409
        print(f"\n⚡ [Scenario D] Idempotency Key Conflict Test (Same key, different seats)...")
        r_diff = await client.post(
            f"/shows/{show_id}/reserve",
            headers={"Authorization": "Bearer idempotent_user_1"},
            json={"seats": ["A49"], "idempotency_key": shared_key}
        )
        if r_diff.status_code == 409:
            print("   ✅ Correctly returned 409 Conflict for modified payload.")
            stats.record(409, "Idempotency key conflict")
        else:
            print(f"   ❌ Expected 409, got {r_diff.status_code}")
            stats.record(r_diff.status_code)

        # 7. Final Show State & Invariant Reconciliation
        print(f"\n=======================================================")
        print(f"📊 Final Invariant Reconciliation Check")
        print(f"=======================================================")
        state_resp = await client.get(f"/shows/{show_id}")
        state = state_resp.json()
        
        total = state["total_seats"]
        available = state["available_count"]
        confirmed = state["confirmed_count"]
        
        print(f"Total Seats:     {total}")
        print(f"Available Seats: {available}")
        print(f"Confirmed Seats: {confirmed}")
        print(f"Reconciliation:  {available} + {confirmed} = {available + confirmed} (Expected: {total})")
        
        if available + confirmed == total:
            print("🏆 RECONCILIATION INVARIANT: PERFECT MATCH (100% Correct)")
        else:
            print("❌ RECONCILIATION INVARIANT VIOLATED!")

        # 8. Output Distribution Summary
        print(f"\n=======================================================")
        print(f"📈 Outcome Distribution Summary")
        print(f"=======================================================")
        print(f"Total Requests Fired: {stats.total}")
        for code, cnt in sorted(stats.status_codes.items()):
            label = "201 Created (Success)" if code == 201 else "409 Conflict (Clean Domain Decline)" if code == 409 else f"HTTP {code}"
            print(f"  {label:38} : {cnt} ({cnt/stats.total*100:.1f}%)")
        print(f"  5xx Server Errors                      : {stats.server_errors} ({stats.server_errors/stats.total*100:.1f}%)")
        print(f"=======================================================\n")


if __name__ == "__main__":
    asyncio.run(run_burst())
