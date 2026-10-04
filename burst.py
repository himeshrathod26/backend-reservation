#!/usr/bin/env python3
import argparse, concurrent.futures, json, sys, time
import httpx


def reserve(client, base, show_id, user, seats, key):
    try:
        r = client.post(f"{base}/shows/{show_id}/reserve", headers={"Authorization": f"Bearer {user}"}, json={"seats": seats, "idempotency_key": key}, timeout=30)
        try: body = r.json()
        except Exception: body = {}
        return r.status_code, body
    except Exception as e:
        return 599, {"detail": str(e)}


def run_hot_seat(client, base, show_id, count, workers):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        fs=[ex.submit(reserve,client,base,show_id,f"hot-user-{i}",["A1"],f"hot-{i}") for i in range(count)]
        return [f.result() for f in fs]


def run_limit(client, base, show_id, count, workers):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        fs=[ex.submit(reserve,client,base,show_id,"limit-user",[f"A{i+1}"],f"limit-{i}") for i in range(count)]
        return [f.result() for f in fs]


def run_idempotency(client, base, show_id, count, workers):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        fs=[ex.submit(reserve,client,base,show_id,"idem-user",["A2"],"same-key") for _ in range(count)]
        return [f.result() for f in fs]


def summarize(results):
    out={}
    for status, body in results:
        reason = "confirmed" if status == 201 and body.get("status") == "confirmed" else body.get("detail", f"http_{status}")
        out[reason]=out.get(reason,0)+1
    return out


def create_show(client, base, seats, limit=4):
    r=client.post(base+"/shows", json={"name":"burst-test","seats":seats,"price_paise":25000,"per_user_limit":limit}, timeout=30)
    r.raise_for_status(); return r.json()["id"]


def main():
    p=argparse.ArgumentParser()
    p.add_argument("base_url")
    p.add_argument("--requests",type=int,default=500)
    p.add_argument("--workers",type=int,default=100)
    args=p.parse_args(); base=args.base_url.rstrip("/")
    seats=[f"A{i}" for i in range(1,max(args.requests+5,25))]
    with httpx.Client() as client:
        # Scenario 1: hot-seat storm.
        show=create_show(client,base,seats)
        start=time.perf_counter(); hot=run_hot_seat(client,base,show,args.requests,args.workers); elapsed=time.perf_counter()-start
        print("HOT-SEAT STORM")
        print(json.dumps({"requests":len(hot),"elapsed_seconds":round(elapsed,3),"distribution":summarize(hot)},indent=2))
        if sum(1 for s,b in hot if s==201) != 1 or any(s >= 500 for s,b in hot):
            print("FAIL: hot-seat correctness",file=sys.stderr); return 2

        # Scenario 2: one user races past the limit.
        limit_show=create_show(client,base,seats,limit=4)
        limited=run_limit(client,base,limit_show,10,args.workers)
        print("PER-USER LIMIT")
        print(json.dumps({"requests":len(limited),"distribution":summarize(limited)},indent=2))
        if sum(1 for s,b in limited if s==201) > 4 or any(s >= 500 for s,b in limited):
            print("FAIL: per-user limit",file=sys.stderr); return 3

        # Scenario 3: same key replay.
        idem_show=create_show(client,base,seats,limit=4)
        idem=run_idempotency(client,base,idem_show,args.requests,args.workers)
        print("IDEMPOTENCY")
        print(json.dumps({"requests":len(idem),"distribution":summarize(idem)},indent=2))
        if sum(1 for s,b in idem if s==201) != args.requests or any(s >= 500 for s,b in idem):
            print("FAIL: idempotency replay",file=sys.stderr); return 4

        state=client.get(f"{base}/shows/{show}",timeout=30); state.raise_for_status(); body=state.json(); c=body["counts"]
        reconciliation={"available":c["available"],"held":c["held"],"confirmed":c["confirmed"],"sum":sum(c.values()),"total":body["total_seats"]}
        print("RECONCILIATION")
        print(json.dumps(reconciliation,indent=2))
        if reconciliation["sum"] != reconciliation["total"]:
            print("FAIL: reconciliation invariant",file=sys.stderr); return 5
    print("PASS")
    return 0

if __name__ == "__main__": raise SystemExit(main())
