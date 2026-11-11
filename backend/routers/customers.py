"""Customer CRUD, search, and pagination endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.dependencies import get_db
from backend.models import Customer
from backend.schemas import CustomerCreate, CustomerOut, CustomerUpdate
from backend.services.domain import create_customer, customer_dict, paginate

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("", response_model=CustomerOut, status_code=201, name="create_customer")
def create(payload: CustomerCreate, db: Session = Depends(get_db)):
    return create_customer(db, payload.model_dump())


@router.get("", name="list_customers")
def list_customers(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = None, db: Session = Depends(get_db)):
    query = select(Customer)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Customer.first_name.ilike(pattern), Customer.last_name.ilike(pattern), Customer.email.ilike(pattern), Customer.company_name.ilike(pattern)))
    result = paginate(db, query, page, page_size)
    return {**result, "items": [customer_dict(x) for x in result["items"]]}


@router.get("/{customer_id}", response_model=CustomerOut, name="get_customer")
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None: raise HTTPException(404, "Customer not found.")
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut, name="update_customer")
def update_customer(customer_id: str, payload: CustomerUpdate, db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None: raise HTTPException(404, "Customer not found.")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(customer, key, value)
    db.commit(); db.refresh(customer)
    return customer
