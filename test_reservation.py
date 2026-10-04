import concurrent.futures
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def make_show(n=10, limit=4):
    r=client.post('/shows',json={'name':'test','seats':[f'A{i}' for i in range(1,n+1)],'price_paise':25000,'per_user_limit':limit})
    assert r.status_code == 201
    return r.json()['id']

def reserve(show,user,seat,key):
    return client.post(f'/shows/{show}/reserve',headers={'Authorization':f'Bearer {user}'},json={'seats':[seat],'idempotency_key':key})

def test_hot_seat_exactly_one_winner():
    show=make_show()
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        rs=list(ex.map(lambda i: reserve(show,f'u{i}','A1',f'k{i}'),range(20)))
    assert sum(r.status_code == 201 for r in rs) == 1
    assert sum(r.status_code == 409 for r in rs) == 19
    assert not any(r.status_code >= 500 for r in rs)

def test_same_key_replays():
    show=make_show()
    first=reserve(show,'u1','A1','same')
    second=reserve(show,'u1','A1','same')
    assert first.status_code == second.status_code == 201
    assert first.json()['reservation_id'] == second.json()['reservation_id']

def test_same_key_different_body_conflicts():
    show=make_show()
    assert reserve(show,'u1','A1','same').status_code == 201
    assert reserve(show,'u1','A2','same').status_code == 409

def test_limit_under_concurrency():
    show=make_show(n=20,limit=4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        rs=list(ex.map(lambda i: reserve(show,'same-user',f'A{i+1}',f'k{i}'),range(10)))
    assert sum(r.status_code == 201 for r in rs) == 4
    assert not any(r.status_code >= 500 for r in rs)

def test_identity_not_from_body():
    show=make_show()
    r=client.post(f'/shows/{show}/reserve',headers={'Authorization':'Bearer real-user'},json={'user_id':'attacker','seats':['A1'],'idempotency_key':'k'})
    assert r.status_code == 201
    assert r.json()['user_id'] == 'real-user'

def test_reconciliation():
    show=make_show()
    assert reserve(show,'u1','A1','k').status_code == 201
    state=client.get(f'/shows/{show}').json()
    assert sum(state['counts'].values()) == state['total_seats']
