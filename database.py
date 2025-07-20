import os
import motor.motor_asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Create an asynchronous client to connect to MongoDB
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)

# Get a reference to the database and collections
db = client.hronetask_db
product_collection = db.get_collection("products")
order_collection = db.get_collection("orders")