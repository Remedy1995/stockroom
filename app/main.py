import json
import logging
import secrets
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case, delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.db import SessionLocal, engine, get_db
from app.models import (
    ActionToken,
    Audit,
    Product,
    RateBucket,
    Session,
    User,
    Workspace,
    now,
)
from app.schemas import (
    Credentials,
    EmailVerification,
    MemberCreate,
    PasswordChange,
    PasswordReset,
    PasswordResetRequest,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    Registration,
    UserOut,
)
from app.security import (
    DUMMY_HASH,
    current_user,
    digest,
    editor,
    issue_session,
    owner,
    password_hasher,
    verify_password,
)

settings = get_settings()
logger = logging.getLogger('stockroom')
logging.basicConfig(level=logging.INFO, format='%(message)s')
app = FastAPI(title='Stockroom API', version='1.0.0', description='Workspace-scoped inventory API. Register or log in to obtain an opaque bearer token; browser sessions use an HttpOnly cookie. All amounts are integer USD cents.',
              openapi_tags=[
                  {'name': 'Authentication', 'description': 'Register, sign in, inspect the current account, and revoke sessions.'},
                  {'name': 'Product CRUD', 'description': 'Create, list, read, update, and delete products in the signed-in workspace.'},
                  {'name': 'Workspace', 'description': 'Workspace summary, activity history, and member administration.'},
                  {'name': 'Operations', 'description': 'Liveness and readiness probes.'},
              ])
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True,
                   allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Content-Type', 'Authorization'], expose_headers=['X-Request-ID'])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)


def error(status, message, request_id, details=None, headers=None):
    return JSONResponse(status_code=status, content={'error': {'message': message, 'details': details or [], 'request_id': request_id}}, headers=headers)


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    return error(exc.status_code, str(exc.detail), getattr(request.state, 'request_id', ''), headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    details = [{'field': '.'.join(str(part) for part in e['loc']), 'message': e['msg']} for e in exc.errors()]
    return error(422, 'Please check the submitted values.', getattr(request.state, 'request_id', ''), details)


def rate_allowed(identity, limit):
    window = now() // settings.rate_window_seconds
    key = digest(f'{identity}:{window}')
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if engine.dialect.name == 'postgresql' else sqlite_insert
    with SessionLocal.begin() as db:
        stmt = insert(RateBucket).values(key=key, count=1, expires_at=(window + 2) * settings.rate_window_seconds)
        stmt = stmt.on_conflict_do_update(index_elements=['key'], set_={'count': RateBucket.count + 1}).returning(RateBucket.count)
        count = db.execute(stmt).scalar_one()
        db.execute(delete(RateBucket).where(RateBucket.expires_at < now()))
    return count <= limit


@app.middleware('http')
async def safeguards(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = None
        if request.url.path.startswith('/api/'):
            unsafe = request.method not in {'GET', 'HEAD', 'OPTIONS'}
            origin = request.headers.get('origin')
            bearer_request = request.headers.get('authorization', '').lower().startswith('bearer ')
            cookie_request = bool(request.cookies.get('stockroom_session')) and not bearer_request
            if unsafe and ((origin and origin not in settings.allowed_origins) or (cookie_request and not origin)):
                response = error(403, 'Request origin is not allowed.', request.state.request_id)
            if not response and unsafe:
                # Enforce the limit on actual bytes, including chunked requests.
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 32768:
                        response = error(413, 'Request body exceeds 32 KiB.', request.state.request_id)
                        break
                if not response:
                    request._body = bytes(body)
            if not response and request.method != 'OPTIONS':
                from starlette.concurrency import run_in_threadpool
                ip = request.client.host if request.client else 'unknown'
                auth = request.url.path in {'/api/v1/auth/login', '/api/v1/auth/register'}
                identity = f'auth:{ip}' if auth else f'api:{ip}'
                allowed = await run_in_threadpool(rate_allowed, identity, settings.auth_limit if auth else settings.api_limit)
                if not allowed:
                    response = error(429, 'Too many requests. Try again shortly.', request.state.request_id, headers={'Retry-After': str(settings.rate_window_seconds)})
        if response is None:
            response = await call_next(request)
    except Exception:
        logger.exception('Unhandled request error request_id=%s', request.state.request_id)
        response = error(500, 'An unexpected error occurred.', request.state.request_id)
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    if request.url.path == '/' or request.url.path.startswith('/static/'):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if settings.secure_cookies:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    logger.info(json.dumps({'request_id': request.state.request_id, 'method': request.method, 'path': request.url.path, 'status': response.status_code, 'duration_ms': round((time.perf_counter() - started) * 1000, 2)}))
    return response


def audit(db, user, action, target):
    db.add(Audit(workspace_id=user.workspace_id, actor_name=user.name, action=action, target=target))


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account or SKU with this value already exists.')


def profile(db, user):
    return {**UserOut.model_validate(user).model_dump(), 'workspace': db.get(Workspace, user.workspace_id).name}


def product_dict(p):
    return {k: getattr(p, k) for k in ['id', 'name', 'sku', 'category', 'description', 'quantity', 'price_cents', 'reorder_point', 'version', 'created_at', 'updated_at']} | {'status': 'out_of_stock' if p.quantity == 0 else 'low_stock' if p.quantity <= p.reorder_point else 'in_stock'}


def find_product(db, user, product_id):
    p = db.scalar(select(Product).where(Product.id == product_id, Product.workspace_id == user.workspace_id))
    if not p:
        raise HTTPException(404, 'Product not found.')
    return p


def issue_action_token(db, user, purpose):
    token = secrets.token_urlsafe(48)
    db.execute(delete(ActionToken).where(ActionToken.user_id == user.id, ActionToken.purpose == purpose))
    db.add(ActionToken(token_hash=digest(token), user_id=user.id, purpose=purpose,
                       expires_at=now() + settings.action_token_minutes * 60))
    return token


def consume_action_token(db, token, purpose):
    action = db.get(ActionToken, digest(token))
    if not action or action.purpose != purpose or action.expires_at <= now():
        raise HTTPException(400, 'This link is invalid or has expired.')
    db.delete(action)
    user = db.get(User, action.user_id)
    if not user:
        raise HTTPException(400, 'This link is invalid or has expired.')
    return user


@app.post('/api/v1/auth/register', status_code=201, tags=['Authentication'])
def register(payload: Registration, response: Response, db: DBSession = Depends(get_db)):
    workspace = Workspace(name=payload.workspace)
    db.add(workspace)
    db.flush()
    user = User(workspace_id=workspace.id, name=payload.name, email=payload.email, password_hash=password_hasher.hash(payload.password), role='owner')
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Unable to create an account with these details.')
    token = issue_session(db, user, response)
    audit(db, user, 'workspace.created', workspace.name)
    commit(db)
    return {'user': profile(db, user), 'access_token': token, 'token_type': 'bearer', 'expires_in': settings.session_hours * 3600}


@app.post('/api/v1/auth/login', tags=['Authentication'])
def login(payload: Credentials, response: Response, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    valid = verify_password(payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, 'Incorrect email or password.', headers={'WWW-Authenticate': 'Bearer'})
    token = issue_session(db, user, response)
    audit(db, user, 'session.created', 'Signed in')
    commit(db)
    return {'user': profile(db, user), 'access_token': token, 'token_type': 'bearer', 'expires_in': settings.session_hours * 3600}


@app.get('/api/v1/auth/me', tags=['Authentication'])
def me(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    return profile(db, user)


@app.post('/api/v1/auth/logout', status_code=204, tags=['Authentication'])
def logout(request: Request, response: Response, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    db.execute(delete(Session).where(Session.token_hash == request.state.session_hash))
    commit(db)
    response.delete_cookie('stockroom_session', path='/', secure=settings.secure_cookies, httponly=True, samesite='strict')


@app.post('/api/v1/auth/logout-all', status_code=204, tags=['Authentication'])
def logout_all(response: Response, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, user, 'sessions.revoked', 'All sessions')
    commit(db)
    response.delete_cookie('stockroom_session', path='/')


@app.put('/api/v1/auth/password', status_code=204, tags=['Authentication'])
def change_password(payload: PasswordChange, response: Response, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(401, 'Current password is incorrect.')
    user.password_hash = password_hasher.hash(payload.new_password)
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, user, 'password.changed', 'All sessions revoked')
    commit(db)
    response.delete_cookie('stockroom_session', path='/')


@app.post('/api/v1/auth/verification-email', status_code=202, tags=['Authentication'], summary='Request an email verification link')
def request_verification(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    token = issue_action_token(db, user, 'email_verification')
    audit(db, user, 'email.verification_requested', user.email)
    commit(db)
    logger.info(json.dumps({'event': 'verification_link_created', 'user_id': user.id, 'token_hint': token[:8]}))


@app.post('/api/v1/auth/verify-email', status_code=204, tags=['Authentication'], summary='Verify an email address')
def verify_email(payload: EmailVerification, db: DBSession = Depends(get_db)):
    user = consume_action_token(db, payload.token, 'email_verification')
    user.is_email_verified = True
    audit(db, user, 'email.verified', user.email)
    commit(db)


@app.post('/api/v1/auth/password-reset-request', status_code=202, tags=['Authentication'], summary='Request a password-reset link')
def request_password_reset(payload: PasswordResetRequest, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if user:
        token = issue_action_token(db, user, 'password_reset')
        audit(db, user, 'password.reset_requested', user.email)
        commit(db)
        logger.info(json.dumps({'event': 'password_reset_link_created', 'user_id': user.id, 'token_hint': token[:8]}))


@app.post('/api/v1/auth/password-reset', status_code=204, tags=['Authentication'], summary='Set a password with a reset link')
def reset_password(payload: PasswordReset, response: Response, db: DBSession = Depends(get_db)):
    user = consume_action_token(db, payload.token, 'password_reset')
    user.password_hash = password_hasher.hash(payload.new_password)
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, user, 'password.reset', 'All sessions revoked')
    commit(db)
    response.delete_cookie('stockroom_session', path='/')


@app.get('/api/v1/products', tags=['Product CRUD'], summary='List products')
def products(q: str = Query('', max_length=120), category: str | None = Query(None, max_length=40),
             status: Literal['in_stock', 'low_stock', 'out_of_stock'] | None = None,
             sort: Literal['updated', 'name', 'quantity', 'price'] = 'updated', page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
             user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    filters = [Product.workspace_id == user.workspace_id]
    if q:
        filters.append(or_(Product.name.icontains(q, autoescape=True), Product.sku.icontains(q, autoescape=True)))
    if category:
        filters.append(Product.category == category)
    if status == 'out_of_stock':
        filters.append(Product.quantity == 0)
    elif status == 'low_stock':
        filters.extend([Product.quantity > 0, Product.quantity <= Product.reorder_point])
    elif status == 'in_stock':
        filters.append(Product.quantity > Product.reorder_point)
    total = db.scalar(select(func.count()).select_from(Product).where(*filters))
    ordering = {'updated': Product.updated_at.desc(), 'name': Product.name.asc(), 'quantity': Product.quantity.asc(), 'price': Product.price_cents.desc()}[sort]
    rows = db.scalars(select(Product).where(*filters).order_by(ordering, Product.id).offset((page - 1) * page_size).limit(page_size))
    return {'items': [product_dict(p) for p in rows], 'total': total, 'page': page, 'page_size': page_size}


@app.post('/api/v1/products', status_code=201, response_model=ProductOut, tags=['Product CRUD'], summary='Create a product')
def create_product(payload: ProductCreate, response: Response, user: User = Depends(editor), db: DBSession = Depends(get_db)):
    p = Product(workspace_id=user.workspace_id, **payload.model_dump())
    db.add(p)
    audit(db, user, 'product.created', p.name)
    commit(db)
    response.headers['Location'] = f'/api/v1/products/{p.id}'
    return product_dict(p)


@app.get('/api/v1/products/{product_id}', response_model=ProductOut, tags=['Product CRUD'], summary='Get one product')
def get_product(product_id: uuid.UUID, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    return product_dict(find_product(db, user, str(product_id)))


@app.put('/api/v1/products/{product_id}', response_model=ProductOut, tags=['Product CRUD'], summary='Update a product')
def update_product(product_id: uuid.UUID, payload: ProductUpdate, user: User = Depends(editor), db: DBSession = Depends(get_db)):
    p = find_product(db, user, str(product_id))
    try:
        result = db.execute(update(Product).where(Product.id == p.id, Product.workspace_id == user.workspace_id, Product.version == payload.version)
                            .values(**payload.model_dump(exclude={'version'}), version=Product.version + 1, updated_at=now()))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This SKU already exists in your workspace.')
    if result.rowcount != 1:
        raise HTTPException(409, 'This product changed since you opened it. Reload and try again.')
    audit(db, user, 'product.updated', payload.name)
    commit(db)
    db.refresh(p)
    return product_dict(p)


@app.delete('/api/v1/products/{product_id}', status_code=204, tags=['Product CRUD'], summary='Delete a product')
def delete_product(product_id: uuid.UUID, version: int = Query(..., ge=1), user: User = Depends(editor), db: DBSession = Depends(get_db)):
    p = find_product(db, user, str(product_id))
    name = p.name
    result = db.execute(delete(Product).where(Product.id == p.id, Product.workspace_id == user.workspace_id, Product.version == version))
    if result.rowcount != 1:
        raise HTTPException(409, 'This product changed. Reload before deleting.')
    audit(db, user, 'product.deleted', name)
    commit(db)


@app.get('/api/v1/overview', tags=['Workspace'])
def overview(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    row = db.execute(select(func.count(Product.id), func.coalesce(func.sum(Product.quantity), 0), func.coalesce(func.sum(Product.quantity * Product.price_cents), 0), func.coalesce(func.sum(case((Product.quantity <= Product.reorder_point, 1), else_=0)), 0)).where(Product.workspace_id == user.workspace_id)).one()
    categories = db.execute(select(Product.category, func.count(Product.id)).where(Product.workspace_id == user.workspace_id).group_by(Product.category).order_by(func.count(Product.id).desc(), Product.category)).all()
    return {'products': row[0], 'units': row[1], 'value_cents': row[2], 'needs_attention': row[3], 'categories': [{'name': c, 'count': n} for c, n in categories]}


@app.get('/api/v1/activity', tags=['Workspace'])
def activity(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    query = select(Audit).where(Audit.workspace_id == user.workspace_id)
    rows = db.scalars(query.order_by(Audit.created_at.desc(), Audit.id).offset((page - 1) * page_size).limit(page_size))
    return {'items': [{k: getattr(a, k) for k in ['id', 'actor_name', 'action', 'target', 'created_at']} for a in rows], 'total': db.scalar(select(func.count()).select_from(Audit).where(Audit.workspace_id == user.workspace_id)), 'page': page, 'page_size': page_size}


@app.get('/api/v1/members', tags=['Workspace'])
def members(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    return {'items': [UserOut.model_validate(u) for u in db.scalars(select(User).where(User.workspace_id == user.workspace_id).order_by(User.created_at, User.id))]}


@app.post('/api/v1/members', status_code=201, response_model=UserOut, tags=['Workspace'])
def create_member(payload: MemberCreate, user: User = Depends(owner), db: DBSession = Depends(get_db)):
    member = User(workspace_id=user.workspace_id, name=payload.name.strip(), email=payload.email, role=payload.role, password_hash=password_hasher.hash(payload.password))
    db.add(member)
    audit(db, user, 'member.created', member.name)
    commit(db)
    return member


@app.delete('/api/v1/members/{member_id}', status_code=204, tags=['Workspace'])
def remove_member(member_id: uuid.UUID, user: User = Depends(owner), db: DBSession = Depends(get_db)):
    member = db.scalar(select(User).where(User.id == str(member_id), User.workspace_id == user.workspace_id))
    if not member:
        raise HTTPException(404, 'Member not found.')
    if member.role == 'owner':
        raise HTTPException(409, 'The workspace owner cannot be removed.')
    audit(db, user, 'member.removed', member.name)
    db.execute(delete(Session).where(Session.user_id == member.id))
    db.delete(member)
    commit(db)


@app.get('/health/live', tags=['Operations'])
def live():
    return {'status': 'ok'}


@app.get('/health/ready', tags=['Operations'])
def ready(db: DBSession = Depends(get_db)):
    try:
        db.execute(text('SELECT 1 FROM users LIMIT 1'))
        revision = db.execute(text('SELECT version_num FROM alembic_version')).scalar()
        if revision != '0002':
            raise RuntimeError('Migrations pending')
    except Exception:
        raise HTTPException(503, 'Database is not ready.')
    return {'status': 'ready', 'version': '1.0.0'}


static_dir = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=static_dir), name='static')


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(static_dir / 'index.html')
