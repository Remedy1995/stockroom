from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.main import app, issue_action_token
from app.models import User

client = TestClient(app, base_url='http://127.0.0.1:8000')


def setup_function():
    client.cookies.clear()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def register(email, name='Jordan Doe', workspace='North Star'):
    response = client.post('/api/v1/auth/register', headers={'Origin': 'http://127.0.0.1:8000'}, json={
        'name': name, 'workspace': workspace, 'email': email, 'password': 'a-secure-password-123',
    })
    assert response.status_code == 201, response.text
    return response.json()


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def product_payload(**overrides):
    payload = {
        'name': 'Field notebook', 'sku': 'note-a5-cream', 'category': 'Stationery',
        'description': 'Grid paper', 'quantity': 16, 'price_cents': 1299, 'reorder_point': 6,
    }
    payload.update(overrides)
    return payload


def test_full_product_lifecycle_with_audit_and_optimistic_locking():
    account = register('jordan@example.com')
    headers = auth(account['access_token'])
    created = client.post('/api/v1/products', json=product_payload(), headers=headers)
    assert created.status_code == 201, created.text
    product = created.json()
    assert product['sku'] == 'NOTE-A5-CREAM'
    assert product['status'] == 'in_stock'
    listed = client.get('/api/v1/products?q=note', headers=headers).json()
    assert listed['total'] == 1
    update = product_payload(quantity=4, sku=product['sku'], version=product['version'])
    changed = client.put(f"/api/v1/products/{product['id']}", json=update, headers=headers)
    assert changed.status_code == 200, changed.text
    assert changed.json()['status'] == 'low_stock'
    assert changed.json()['version'] == 2
    stale = client.put(f"/api/v1/products/{product['id']}", json=update, headers=headers)
    assert stale.status_code == 409
    activity = client.get('/api/v1/activity', headers=headers).json()['items']
    assert {item['action'] for item in activity} >= {'workspace.created', 'product.created', 'product.updated'}
    deleted = client.delete(f"/api/v1/products/{product['id']}?version=2", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/products/{product['id']}", headers=headers).status_code == 404


def test_workspace_isolation_and_viewer_permissions():
    first = register('owner@example.com', workspace='First workspace')
    first_headers = auth(first['access_token'])
    product = client.post('/api/v1/products', json=product_payload(), headers=first_headers).json()
    second = register('other@example.com', name='Other Owner', workspace='Second workspace')
    assert client.get(f"/api/v1/products/{product['id']}", headers=auth(second['access_token'])).status_code == 404
    member = client.post('/api/v1/members', headers=first_headers, json={
        'name': 'Viewer User', 'email': 'viewer@example.com', 'password': 'a-secure-password-456', 'role': 'viewer',
    })
    assert member.status_code == 201, member.text
    login = client.post('/api/v1/auth/login', headers={'Origin': 'http://127.0.0.1:8000'}, json={
        'email': 'viewer@example.com', 'password': 'a-secure-password-456',
    })
    viewer_headers = auth(login.json()['access_token'])
    assert client.get('/api/v1/products', headers=viewer_headers).status_code == 200
    assert client.post('/api/v1/products', headers=viewer_headers, json=product_payload(sku='VIEWER-1')).status_code == 403


def test_validation_and_logout_revoke_access():
    account = register('security@example.com')
    headers = auth(account['access_token'])
    invalid = client.post('/api/v1/products', headers=headers, json=product_payload(quantity=-1))
    assert invalid.status_code == 422
    assert 'details' in invalid.json()['error']
    assert client.post('/api/v1/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/v1/auth/me', headers=headers).status_code == 401


def test_health_contract_and_security_headers():
    assert client.get('/health/live').json() == {'status': 'ok'}
    homepage = client.get('/')
    assert homepage.status_code == 200
    assert homepage.headers['x-frame-options'] == 'DENY'
    assert 'default-src' in homepage.headers['content-security-policy']


def test_openapi_lists_all_product_crud_operations():
    schema = client.get('/openapi.json').json()
    assert schema['paths']['/api/v1/products']['get']['summary'] == 'List products'
    assert schema['paths']['/api/v1/products']['post']['summary'] == 'Create a product'
    assert schema['paths']['/api/v1/products/{product_id}']['get']['summary'] == 'Get one product'
    assert schema['paths']['/api/v1/products/{product_id}']['put']['summary'] == 'Update a product'
    assert schema['paths']['/api/v1/products/{product_id}']['delete']['summary'] == 'Delete a product'


def test_password_reset_is_single_use_and_revokes_existing_sessions():
    account = register('recovery@example.com')
    headers = auth(account['access_token'])
    client.cookies.clear()
    assert client.post('/api/v1/auth/password-reset-request', json={'email': 'recovery@example.com'}).status_code == 202
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == 'recovery@example.com'))
        token = issue_action_token(db, user, 'password_reset')
    response = client.post('/api/v1/auth/password-reset', json={'token': token, 'new_password': 'new-secure-password-456'})
    assert response.status_code == 204
    assert client.get('/api/v1/auth/me', headers=headers).status_code == 401
    assert client.post('/api/v1/auth/password-reset', json={'token': token, 'new_password': 'another-secure-password'}).status_code == 400
    assert client.post('/api/v1/auth/login', json={'email': 'recovery@example.com', 'password': 'new-secure-password-456'}).status_code == 200
