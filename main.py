import os
from datetime import datetime
from fastapi import FastAPI, Body, HTTPException, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from bson import ObjectId
from dotenv import load_dotenv

# Import database collections from your database.py file
from database import product_collection, order_collection

# Load environment variables
load_dotenv()

app = FastAPI(
    title="HROne E-commerce API",
    description="API for the HROne Backend Intern Hiring Task."
)

# --- Pydantic Models for Data Validation ---
class Size(BaseModel):
    size: str
    quantity: int

class ProductCreate(BaseModel):
    name: str
    price: float
    sizes: List[Size]

class ProductList(BaseModel):
    id: str
    name: str
    price: float

class OrderItem(BaseModel):
    productId: str
    qty: int

class OrderCreate(BaseModel):
    userId: str
    items: List[OrderItem]

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"message": "HROne E-commerce API is running!"}

@app.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(product: ProductCreate = Body(...)):
    product_dict = product.dict()
    new_product = await product_collection.insert_one(product_dict)
    return JSONResponse(content={"id": str(new_product.inserted_id)}, status_code=status.HTTP_201_CREATED)

@app.get("/products", status_code=status.HTTP_200_OK)
async def list_products(
    name: Optional[str] = None,
    size: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    query = {}
    if name:
        query["name"] = {"$regex": name, "$options": "i"}
    if size:
        query["sizes.size"] = size

    products_cursor = product_collection.find(query, {"sizes": 0}).skip(offset).limit(limit)
    products = await products_cursor.to_list(length=limit)
    
    formatted_products = [ProductList(id=str(p["_id"]), name=p["name"], price=p["price"]).dict() for p in products]

    next_offset = offset + len(formatted_products)
    prev_offset = offset - limit

    return JSONResponse(content={
        "data": formatted_products,
        "page": {
            "limit": len(formatted_products),
            "next": str(next_offset),
            "previous": str(prev_offset if prev_offset >= 0 else -1)
        }
    })

@app.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_order(order: OrderCreate = Body(...)):
    order_dict = order.dict()
    product_ids_str = [item["productId"] for item in order_dict["items"]]
    
    if not all(ObjectId.is_valid(pid) for pid in product_ids_str):
        raise HTTPException(status_code=400, detail="One or more product IDs are invalid.")

    product_ids = [ObjectId(pid) for pid in product_ids_str]
    
    products = await product_collection.find({"_id": {"$in": product_ids}}).to_list(length=len(product_ids))
    price_map = {str(p["_id"]): p["price"] for p in products}

    if len(products) != len(product_ids_str):
        raise HTTPException(status_code=404, detail="One or more products not found.")

    total_amount = sum(price_map.get(item["productId"], 0) * item["qty"] for item in order_dict["items"])
    
    for item in order_dict["items"]:
        item["productId"] = ObjectId(item["productId"])

    order_dict["total"] = total_amount
    order_dict["created_at"] = datetime.utcnow()

    new_order = await order_collection.insert_one(order_dict)
    return JSONResponse(content={"id": str(new_order.inserted_id)}, status_code=status.HTTP_201_CREATED)

@app.get("/orders/{user_id}", status_code=status.HTTP_200_OK)
async def get_list_of_orders(
    user_id: str,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    pipeline = [
        {"$match": {"userId": user_id}},
        {"$sort": {"created_at": -1}},
        {"$skip": offset},
        {"$limit": limit},
        {"$unwind": "$items"},
        {
            "$lookup": {
                "from": "products",
                "localField": "items.productId",
                "foreignField": "_id",
                "as": "productInfo"
            }
        },
        {"$unwind": "$productInfo"},
        {
            "$group": {
                "_id": "$_id",
                "total": {"$first": "$total"},
                "items": {
                    "$push": {
                        "qty": "$items.qty",
                        "productDetails": {
                            "id": {"$toString": "$productInfo._id"},
                            "name": "$productInfo.name"
                        }
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "id": {"$toString": "$_id"},
                "total": 1,
                "items": 1
            }
        }
    ]
    orders = await order_collection.aggregate(pipeline).to_list(length=limit)
    
    next_offset = offset + len(orders)
    prev_offset = offset - limit

    return JSONResponse(content={
        "data": orders,
        "page": {
            "limit": len(orders),
            "next": str(next_offset),
            "previous": str(prev_offset if prev_offset >= 0 else -1)
        }
    })