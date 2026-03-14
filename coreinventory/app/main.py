from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Literal
import os
import secrets
import smtplib

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, create_engine, func, or_
from sqlalchemy.orm import Mapped, Session, declarative_base, mapped_column, relationship, sessionmaker


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR.parent / "coreinventory.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

SECRET_KEY = "coreinventory-super-secret-key-change-me"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


DocumentType = Literal["receipt", "delivery", "transfer", "adjustment"]
DocumentStatus = Literal["draft", "waiting", "ready", "done", "canceled"]


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="manager")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_location_warehouse_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)

    warehouse: Mapped[Warehouse] = relationship("Warehouse")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    uom: Mapped[str] = mapped_column(String(30), nullable=False)
    reorder_level: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[int] = mapped_column(Integer, default=1)

    category: Mapped[Category | None] = relationship("Category")


class StockBalance(Base):
    __tablename__ = "stock_balances"
    __table_args__ = (UniqueConstraint("product_id", "location_id", name="uq_product_location"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    qty: Mapped[float] = mapped_column(Float, default=0)

    product: Mapped[Product] = relationship("Product")
    location: Mapped[Location] = relationship("Location")


class InventoryDocument(Base):
    __tablename__ = "inventory_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    source_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    dest_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    partner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InventoryDocumentLine(Base):
    __tablename__ = "inventory_document_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("inventory_documents.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    qty_planned: Mapped[float] = mapped_column(Float, nullable=False)
    qty_done: Mapped[float] = mapped_column(Float, nullable=False)

    product: Mapped[Product] = relationship("Product")


class StockLedger(Base):
    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    qty_delta: Mapped[float] = mapped_column(Float, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(20), index=True)
    doc_id: Mapped[int] = mapped_column(Integer, index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    product: Mapped[Product] = relationship("Product")
    location: Mapped[Location] = relationship("Location")


# ------------------ Schemas ------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SignupRequest(BaseModel):
    name: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=6)
    role: Literal["manager", "staff"] = "manager"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=6)


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1)


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1)


class LocationCreate(BaseModel):
    warehouse_id: int
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)


class ProductCreate(BaseModel):
    name: str
    sku: str
    category_id: int | None = None
    uom: str
    reorder_level: float = 0
    initial_stock: float | None = None
    initial_location_id: int | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    category_id: int | None = None
    uom: str | None = None
    reorder_level: float | None = None
    active: int | None = None


class DocumentLineInput(BaseModel):
    product_id: int
    qty_planned: float
    qty_done: float


class DocumentCreate(BaseModel):
    type: DocumentType
    status: DocumentStatus = "draft"
    source_location_id: int | None = None
    dest_location_id: int | None = None
    partner_name: str | None = None
    reference: str | None = None
    scheduled_at: datetime | None = None
    lines: list[DocumentLineInput]


# ------------------ App + Helpers ------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_defaults()
    yield


app = FastAPI(title="CoreInventory API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def get_smtp_config() -> dict[str, str | int]:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    return {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "smtp_from": smtp_from,
    }


def get_smtp_problem() -> str | None:
    config = get_smtp_config()
    smtp_host = str(config["smtp_host"])
    smtp_user = str(config["smtp_user"])
    smtp_password = str(config["smtp_password"])

    if not smtp_host:
        return "SMTP_HOST is empty in .env"
    if not smtp_user:
        return "SMTP_USER is empty in .env"
    if not smtp_password:
        return "SMTP_PASSWORD is empty in .env"
    if "your_gmail" in smtp_user:
        return "SMTP_USER still has the placeholder value"
    if "your_16char_app_password" in smtp_password:
        return "SMTP_PASSWORD still has the placeholder value"
    return None


def send_otp_email(to_email: str, otp_code: str) -> tuple[bool, str]:
    """Send OTP via SMTP. Returns (success, message)."""
    config = get_smtp_config()
    smtp_host = str(config["smtp_host"])
    smtp_port = int(config["smtp_port"])
    smtp_user = str(config["smtp_user"])
    smtp_password = str(config["smtp_password"])
    smtp_from = str(config["smtp_from"])

    smtp_problem = get_smtp_problem()
    if smtp_problem:
        print(f"[CoreInventory OTP] Email={to_email} OTP={otp_code} ({smtp_problem}, showing on screen only)")
        return False, smtp_problem

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "CoreInventory – Your Password Reset OTP"
        msg["From"] = smtp_from
        msg["To"] = to_email

        html_body = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px;border:1px solid #ddd;border-radius:12px">
          <h2 style="color:#3f6ad9">CoreInventory</h2>
          <p>You requested a password reset. Use the OTP below:</p>
          <div style="font-size:36px;font-weight:bold;letter-spacing:8px;text-align:center;
                      background:#f0f4ff;padding:20px;border-radius:8px;color:#1a2a6c;margin:20px 0">
            {otp_code}
          </div>
          <p>This OTP expires in <strong>10 minutes</strong>.</p>
          <p style="color:#999;font-size:12px">If you did not request this, ignore this email.</p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())

        print(f"[CoreInventory OTP] OTP email sent to {to_email}")
        return True, "OTP email sent successfully"

    except Exception as exc:
        print(f"[CoreInventory OTP] Failed to send email to {to_email}: {exc}")
        return False, str(exc)


def seed_defaults() -> None:
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, email: str, role: str) -> str:
    expire = utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(status_code=401, detail="Invalid authentication credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise credentials_exception

    user = db.get(User, user_id)
    if not user:
        raise credentials_exception
    return user


def require_manager(user: User) -> None:
    if user.role != "manager":
        raise HTTPException(status_code=403, detail="Manager access required")


def get_or_create_balance(db: Session, product_id: int, location_id: int) -> StockBalance:
    bal = db.query(StockBalance).filter(
        StockBalance.product_id == product_id,
        StockBalance.location_id == location_id,
    ).first()
    if not bal:
        bal = StockBalance(product_id=product_id, location_id=location_id, qty=0)
        db.add(bal)
        db.flush()
    return bal


def apply_stock_movement(
    db: Session,
    product_id: int,
    location_id: int,
    qty_delta: float,
    doc_type: str,
    doc_id: int,
    reason: str,
    user_id: int,
) -> None:
    bal = get_or_create_balance(db, product_id, location_id)
    new_qty = bal.qty + qty_delta
    if new_qty < 0:
        raise HTTPException(status_code=400, detail=f"Insufficient stock for product {product_id} at location {location_id}")
    bal.qty = new_qty
    db.add(
        StockLedger(
            product_id=product_id,
            location_id=location_id,
            qty_delta=qty_delta,
            doc_type=doc_type,
            doc_id=doc_id,
            reason=reason,
            created_by=user_id,
        )
    )


def validate_document_logic(db: Session, doc: InventoryDocument, user: User) -> None:
    if doc.status in ("done", "canceled"):
        raise HTTPException(status_code=400, detail=f"Cannot validate document with status {doc.status}")

    lines = db.query(InventoryDocumentLine).filter(InventoryDocumentLine.document_id == doc.id).all()
    if not lines:
        raise HTTPException(status_code=400, detail="Document has no lines")

    if doc.type == "receipt":
        if not doc.dest_location_id:
            raise HTTPException(status_code=400, detail="Receipt requires destination location")
        for line in lines:
            apply_stock_movement(
                db,
                line.product_id,
                doc.dest_location_id,
                line.qty_done,
                doc.type,
                doc.id,
                "Receipt validated",
                user.id,
            )

    elif doc.type == "delivery":
        if not doc.source_location_id:
            raise HTTPException(status_code=400, detail="Delivery requires source location")
        if doc.status != "ready":
            raise HTTPException(status_code=400, detail="Delivery must be packed and marked ready before validation")
        for line in lines:
            apply_stock_movement(
                db,
                line.product_id,
                doc.source_location_id,
                -abs(line.qty_done),
                doc.type,
                doc.id,
                "Delivery validated",
                user.id,
            )

    elif doc.type == "transfer":
        if not doc.source_location_id or not doc.dest_location_id:
            raise HTTPException(status_code=400, detail="Transfer requires source and destination locations")
        if doc.source_location_id == doc.dest_location_id:
            raise HTTPException(status_code=400, detail="Source and destination locations must differ")
        for line in lines:
            qty = abs(line.qty_done)
            apply_stock_movement(
                db,
                line.product_id,
                doc.source_location_id,
                -qty,
                doc.type,
                doc.id,
                "Internal transfer - source",
                user.id,
            )
            apply_stock_movement(
                db,
                line.product_id,
                doc.dest_location_id,
                qty,
                doc.type,
                doc.id,
                "Internal transfer - destination",
                user.id,
            )

    elif doc.type == "adjustment":
        if not doc.source_location_id:
            raise HTTPException(status_code=400, detail="Adjustment requires location in source_location_id")
        for line in lines:
            bal = get_or_create_balance(db, line.product_id, doc.source_location_id)
            counted_qty = line.qty_done
            diff = counted_qty - bal.qty
            if diff != 0:
                apply_stock_movement(
                    db,
                    line.product_id,
                    doc.source_location_id,
                    diff,
                    doc.type,
                    doc.id,
                    "Stock adjustment",
                    user.id,
                )

    doc.status = "done"
    db.add(doc)


def transition_delivery_document(doc: InventoryDocument, target_status: str) -> None:
    if doc.type != "delivery":
        raise HTTPException(status_code=400, detail="Only delivery documents support pick/pack workflow")
    if doc.status == "canceled":
        raise HTTPException(status_code=400, detail="Canceled documents cannot be updated")
    if doc.status == "done":
        raise HTTPException(status_code=400, detail="Validated deliveries cannot be updated")

    allowed_transitions = {
        "draft": "waiting",
        "waiting": "ready",
    }
    expected = allowed_transitions.get(doc.status)
    if expected != target_status:
        raise HTTPException(status_code=400, detail=f"Cannot move delivery from {doc.status} to {target_status}")

    doc.status = target_status


# ------------------ Static entry ------------------


@app.get("/")
def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


# ------------------ Auth ------------------


@app.post("/api/auth/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=payload.name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email, user.role)
    return TokenResponse(access_token=token)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id, user.email, user.role)
    return TokenResponse(access_token=token)


@app.post("/api/auth/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if not user:
        return {"message": "If this email exists, OTP has been sent."}

    code = str(secrets.randbelow(900000) + 100000)
    expiry = utcnow() + timedelta(minutes=10)

    otp = PasswordResetOTP(user_id=user.id, code=code, expires_at=expiry, used=0)
    db.add(otp)
    db.commit()

    email_sent, delivery_message = send_otp_email(user.email, code)
    
    response: dict = {"expires_in_minutes": 10}
    if email_sent:
        response["message"] = f"OTP sent to {user.email}. Check your inbox."
        response["delivery_message"] = delivery_message
    else:
        response["message"] = "OTP email was not sent. See delivery_message for the reason."
        response["delivery_message"] = delivery_message
        response["demo_otp"] = code

    return response


@app.post("/api/auth/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or OTP")

    otp = db.query(PasswordResetOTP).filter(
        PasswordResetOTP.user_id == user.id,
        PasswordResetOTP.code == payload.otp,
        PasswordResetOTP.used == 0,
    ).order_by(PasswordResetOTP.id.desc()).first()

    if not otp or otp.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    user.password_hash = hash_password(payload.new_password)
    otp.used = 1
    db.add(user)
    db.add(otp)
    db.commit()

    return {"message": "Password reset successful"}


@app.get("/api/auth/me")
def me(current: User = Depends(get_current_user)):
    return {"id": current.id, "name": current.name, "email": current.email, "role": current.role}


# ------------------ Master Data ------------------


@app.get("/api/categories")
def list_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    categories = db.query(Category).order_by(Category.name.asc()).all()
    return [{"id": c.id, "name": c.name} for c in categories]


@app.post("/api/categories")
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_manager(current)
    exists = db.query(Category).filter(func.lower(Category.name) == payload.name.lower()).first()
    if exists:
        raise HTTPException(status_code=400, detail="Category already exists")

    item = Category(name=payload.name.strip())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "name": item.name}


@app.get("/api/warehouses")
def list_warehouses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(Warehouse).order_by(Warehouse.name.asc()).all()
    return [{"id": w.id, "name": w.name} for w in rows]


@app.post("/api/warehouses")
def create_warehouse(payload: WarehouseCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_manager(current)
    exists = db.query(Warehouse).filter(func.lower(Warehouse.name) == payload.name.lower()).first()
    if exists:
        raise HTTPException(status_code=400, detail="Warehouse already exists")

    w = Warehouse(name=payload.name.strip())
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"id": w.id, "name": w.name}


@app.get("/api/locations")
def list_locations(
    warehouse_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Location)
    if warehouse_id:
        q = q.filter(Location.warehouse_id == warehouse_id)
    rows = q.order_by(Location.name.asc()).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "code": row.code,
            "warehouse_id": row.warehouse_id,
            "warehouse_name": row.warehouse.name if row.warehouse else None,
        }
        for row in rows
    ]


@app.post("/api/locations")
def create_location(payload: LocationCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_manager(current)
    wh = db.get(Warehouse, payload.warehouse_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    exists = db.query(Location).filter(
        Location.warehouse_id == payload.warehouse_id,
        func.lower(Location.code) == payload.code.lower(),
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="Location code already exists in warehouse")

    row = Location(warehouse_id=payload.warehouse_id, name=payload.name.strip(), code=payload.code.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "warehouse_id": row.warehouse_id,
        "warehouse_name": wh.name,
    }


@app.get("/api/products")
def list_products(
    search: str | None = None,
    category_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Product)
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))

    rows = q.order_by(Product.name.asc()).all()

    product_ids = [r.id for r in rows]
    qty_map: dict[int, float] = {}
    if product_ids:
        sums = db.query(StockBalance.product_id, func.coalesce(func.sum(StockBalance.qty), 0)).filter(
            StockBalance.product_id.in_(product_ids)
        ).group_by(StockBalance.product_id).all()
        qty_map = {pid: float(total) for pid, total in sums}

    return [
        {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "category_id": p.category_id,
            "category_name": p.category.name if p.category else None,
            "uom": p.uom,
            "reorder_level": p.reorder_level,
            "active": p.active,
            "total_qty": qty_map.get(p.id, 0),
        }
        for p in rows
    ]


@app.post("/api/products")
def create_product(payload: ProductCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_manager(user)
    exists = db.query(Product).filter(func.lower(Product.sku) == payload.sku.lower()).first()
    if exists:
        raise HTTPException(status_code=400, detail="SKU already exists")

    if payload.category_id:
        category = db.get(Category, payload.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

    product = Product(
        name=payload.name.strip(),
        sku=payload.sku.strip(),
        category_id=payload.category_id,
        uom=payload.uom.strip(),
        reorder_level=payload.reorder_level,
        active=1,
    )
    db.add(product)
    db.flush()

    if payload.initial_stock is not None and payload.initial_stock > 0:
        if not payload.initial_location_id:
            raise HTTPException(status_code=400, detail="initial_location_id required when initial_stock is provided")

        location = db.get(Location, payload.initial_location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Initial location not found")

        apply_stock_movement(
            db,
            product.id,
            location.id,
            payload.initial_stock,
            "adjustment",
            0,
            "Initial stock",
            user.id,
        )

    db.commit()
    db.refresh(product)

    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "category_id": product.category_id,
        "uom": product.uom,
        "reorder_level": product.reorder_level,
    }


@app.put("/api/products/{product_id}")
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_manager(current)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.sku and payload.sku.lower() != product.sku.lower():
        exists = db.query(Product).filter(func.lower(Product.sku) == payload.sku.lower(), Product.id != product.id).first()
        if exists:
            raise HTTPException(status_code=400, detail="SKU already exists")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(product, key, value)

    db.add(product)
    db.commit()
    db.refresh(product)
    return {"message": "Product updated"}


@app.get("/api/products/{product_id}/availability")
def product_availability(product_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    rows = db.query(StockBalance).filter(StockBalance.product_id == product_id).all()
    return [
        {
            "location_id": r.location_id,
            "location_name": r.location.name if r.location else None,
            "warehouse_id": r.location.warehouse_id if r.location else None,
            "warehouse_name": r.location.warehouse.name if (r.location and r.location.warehouse) else None,
            "qty": r.qty,
        }
        for r in rows
    ]


# ------------------ Inventory Operations ------------------


@app.post("/api/operations/documents")
def create_document(payload: DocumentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.lines:
        raise HTTPException(status_code=400, detail="At least one line is required")

    if payload.type == "receipt" and not payload.dest_location_id:
        raise HTTPException(status_code=400, detail="Receipt requires destination location")
    if payload.type == "delivery" and not payload.source_location_id:
        raise HTTPException(status_code=400, detail="Delivery requires source location")
    if payload.type == "transfer" and (not payload.source_location_id or not payload.dest_location_id):
        raise HTTPException(status_code=400, detail="Transfer requires source and destination")
    if payload.type == "adjustment" and not payload.source_location_id:
        raise HTTPException(status_code=400, detail="Adjustment requires location in source_location_id")

    doc = InventoryDocument(
        type=payload.type,
        status=payload.status,
        source_location_id=payload.source_location_id,
        dest_location_id=payload.dest_location_id,
        partner_name=payload.partner_name,
        reference=payload.reference,
        scheduled_at=payload.scheduled_at,
        created_by=user.id,
    )
    db.add(doc)
    db.flush()

    for line in payload.lines:
        product = db.get(Product, line.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {line.product_id} not found")

        db.add(
            InventoryDocumentLine(
                document_id=doc.id,
                product_id=line.product_id,
                qty_planned=line.qty_planned,
                qty_done=line.qty_done,
            )
        )

    db.commit()
    db.refresh(doc)
    return {"id": doc.id, "status": doc.status, "type": doc.type}


@app.get("/api/operations/documents")
def list_documents(
    doc_type: DocumentType | None = None,
    status_value: DocumentStatus | None = Query(default=None, alias="status"),
    warehouse_id: int | None = None,
    category_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(InventoryDocument)

    if doc_type:
        q = q.filter(InventoryDocument.type == doc_type)
    if status_value:
        q = q.filter(InventoryDocument.status == status_value)

    docs = q.order_by(InventoryDocument.id.desc()).all()

    filtered = []
    for d in docs:
        source = db.get(Location, d.source_location_id) if d.source_location_id else None
        dest = db.get(Location, d.dest_location_id) if d.dest_location_id else None

        if warehouse_id:
            source_wh_id = source.warehouse_id if source else None
            dest_wh_id = dest.warehouse_id if dest else None
            if warehouse_id not in [source_wh_id, dest_wh_id]:
                continue

        lines = db.query(InventoryDocumentLine).filter(InventoryDocumentLine.document_id == d.id).all()
        if category_id:
            keep = False
            for ln in lines:
                p = db.get(Product, ln.product_id)
                if p and p.category_id == category_id:
                    keep = True
                    break
            if not keep:
                continue

        filtered.append(
            {
                "id": d.id,
                "type": d.type,
                "status": d.status,
                "source_location_id": d.source_location_id,
                "source_location_name": source.name if source else None,
                "dest_location_id": d.dest_location_id,
                "dest_location_name": dest.name if dest else None,
                "partner_name": d.partner_name,
                "reference": d.reference,
                "scheduled_at": d.scheduled_at,
                "created_at": d.created_at,
                "line_count": len(lines),
            }
        )

    return filtered


@app.get("/api/operations/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.get(InventoryDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    lines = db.query(InventoryDocumentLine).filter(InventoryDocumentLine.document_id == doc.id).all()
    return {
        "id": doc.id,
        "type": doc.type,
        "status": doc.status,
        "source_location_id": doc.source_location_id,
        "dest_location_id": doc.dest_location_id,
        "partner_name": doc.partner_name,
        "reference": doc.reference,
        "scheduled_at": doc.scheduled_at,
        "lines": [
            {
                "id": l.id,
                "product_id": l.product_id,
                "product_name": l.product.name if l.product else None,
                "qty_planned": l.qty_planned,
                "qty_done": l.qty_done,
            }
            for l in lines
        ],
    }


@app.post("/api/operations/documents/{doc_id}/validate")
def validate_document(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.get(InventoryDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    validate_document_logic(db, doc, user)
    db.commit()
    return {"message": "Document validated", "document_id": doc.id, "status": doc.status}


@app.post("/api/operations/documents/{doc_id}/pick")
def pick_delivery(doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.get(InventoryDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    transition_delivery_document(doc, "waiting")
    db.add(doc)
    db.commit()
    return {"message": "Delivery items picked", "document_id": doc.id, "status": doc.status}


@app.post("/api/operations/documents/{doc_id}/pack")
def pack_delivery(doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.get(InventoryDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    transition_delivery_document(doc, "ready")
    db.add(doc)
    db.commit()
    return {"message": "Delivery items packed", "document_id": doc.id, "status": doc.status}


@app.post("/api/operations/documents/{doc_id}/cancel")
def cancel_document(doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.get(InventoryDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status == "done":
        raise HTTPException(status_code=400, detail="Cannot cancel a validated document")

    doc.status = "canceled"
    db.add(doc)
    db.commit()
    return {"message": "Document canceled"}


# ------------------ Ledger + Dashboard ------------------


@app.get("/api/ledger")
def list_ledger(
    product_id: int | None = None,
    location_id: int | None = None,
    doc_type: DocumentType | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(StockLedger)
    if product_id:
        q = q.filter(StockLedger.product_id == product_id)
    if location_id:
        q = q.filter(StockLedger.location_id == location_id)
    if doc_type:
        q = q.filter(StockLedger.doc_type == doc_type)

    rows = q.order_by(StockLedger.id.desc()).limit(500).all()
    return [
        {
            "id": r.id,
            "product_id": r.product_id,
            "product_name": r.product.name if r.product else None,
            "location_id": r.location_id,
            "location_name": r.location.name if r.location else None,
            "qty_delta": r.qty_delta,
            "doc_type": r.doc_type,
            "doc_id": r.doc_id,
            "reason": r.reason,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@app.get("/api/dashboard/kpis")
def dashboard_kpis(
    doc_type: DocumentType | None = None,
    status_value: DocumentStatus | None = Query(default=None, alias="status"),
    warehouse_id: int | None = None,
    category_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    product_q = db.query(Product)
    if category_id:
        product_q = product_q.filter(Product.category_id == category_id)
    products = product_q.all()

    product_ids = [p.id for p in products]
    totals: dict[int, float] = {p.id: 0 for p in products}

    if product_ids:
        stock_q = db.query(StockBalance.product_id, func.coalesce(func.sum(StockBalance.qty), 0).label("qty"))
        stock_q = stock_q.filter(StockBalance.product_id.in_(product_ids))

        if warehouse_id:
            location_ids = [
                l.id for l in db.query(Location).filter(Location.warehouse_id == warehouse_id).all()
            ]
            if location_ids:
                stock_q = stock_q.filter(StockBalance.location_id.in_(location_ids))
            else:
                stock_q = stock_q.filter(StockBalance.location_id == -1)

        stock_q = stock_q.group_by(StockBalance.product_id)
        for pid, qty in stock_q.all():
            totals[pid] = float(qty)

    total_products_in_stock = sum(1 for p in products if totals.get(p.id, 0) > 0)
    low_stock = sum(1 for p in products if 0 < totals.get(p.id, 0) <= (p.reorder_level or 0))
    out_of_stock = sum(1 for p in products if totals.get(p.id, 0) <= 0)

    doc_q = db.query(InventoryDocument)
    if doc_type:
        doc_q = doc_q.filter(InventoryDocument.type == doc_type)
    if status_value:
        doc_q = doc_q.filter(InventoryDocument.status == status_value)

    docs = doc_q.all()

    def is_in_warehouse(d: InventoryDocument) -> bool:
        if not warehouse_id:
            return True
        src = db.get(Location, d.source_location_id) if d.source_location_id else None
        dst = db.get(Location, d.dest_location_id) if d.dest_location_id else None
        ids = [src.warehouse_id if src else None, dst.warehouse_id if dst else None]
        return warehouse_id in ids

    docs = [d for d in docs if is_in_warehouse(d)]

    pending_statuses = {"draft", "waiting", "ready"}
    pending_receipts = sum(1 for d in docs if d.type == "receipt" and d.status in pending_statuses)
    pending_deliveries = sum(1 for d in docs if d.type == "delivery" and d.status in pending_statuses)
    scheduled_transfers = sum(1 for d in docs if d.type == "transfer" and d.status in pending_statuses)

    return {
        "total_products_in_stock": total_products_in_stock,
        "low_stock_items": low_stock,
        "out_of_stock_items": out_of_stock,
        "pending_receipts": pending_receipts,
        "pending_deliveries": pending_deliveries,
        "internal_transfers_scheduled": scheduled_transfers,
    }


@app.get("/api/dashboard/recent-movements")
def recent_movements(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(StockLedger).order_by(StockLedger.id.desc()).limit(12).all()
    return [
        {
            "id": r.id,
            "product": r.product.name if r.product else None,
            "location": r.location.name if r.location else None,
            "qty_delta": r.qty_delta,
            "doc_type": r.doc_type,
            "doc_id": r.doc_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@app.get("/api/dashboard/filter-options")
def dashboard_filter_options(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {
        "doc_types": ["receipt", "delivery", "transfer", "adjustment"],
        "statuses": ["draft", "waiting", "ready", "done", "canceled"],
        "warehouses": [{"id": w.id, "name": w.name} for w in db.query(Warehouse).order_by(Warehouse.name).all()],
        "categories": [{"id": c.id, "name": c.name} for c in db.query(Category).order_by(Category.name).all()],
    }


@app.get("/api/alerts/low-stock")
def low_stock_alerts(
    warehouse_id: int | None = None,
    category_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    product_q = db.query(Product)
    if category_id:
        product_q = product_q.filter(Product.category_id == category_id)
    products = product_q.order_by(Product.name.asc()).all()

    product_ids = [p.id for p in products]
    totals: dict[int, float] = {p.id: 0 for p in products}
    if product_ids:
        stock_q = db.query(StockBalance.product_id, func.coalesce(func.sum(StockBalance.qty), 0).label("qty"))
        stock_q = stock_q.filter(StockBalance.product_id.in_(product_ids))
        if warehouse_id:
            location_ids = [l.id for l in db.query(Location).filter(Location.warehouse_id == warehouse_id).all()]
            if location_ids:
                stock_q = stock_q.filter(StockBalance.location_id.in_(location_ids))
            else:
                stock_q = stock_q.filter(StockBalance.location_id == -1)
        stock_q = stock_q.group_by(StockBalance.product_id)
        for pid, qty in stock_q.all():
            totals[pid] = float(qty)

    alerts = []
    for p in products:
        qty = totals.get(p.id, 0)
        reorder = p.reorder_level or 0
        if qty <= reorder:
            alerts.append(
                {
                    "product_id": p.id,
                    "product_name": p.name,
                    "sku": p.sku,
                    "category_name": p.category.name if p.category else None,
                    "total_qty": qty,
                    "reorder_level": reorder,
                    "severity": "out_of_stock" if qty <= 0 else "low_stock",
                }
            )

    return {"count": len(alerts), "items": alerts}


if __name__ == "__main__":
    import os
    import sys
    import uvicorn

    # Ensure working directory is the project root (parent of this file's folder)
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
