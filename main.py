from urllib.parse import urlencode
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, HTTPException, Depends, Body
from sqlalchemy import create_engine, Column, String, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Dict, List, Generator
import json
from sqlalchemy.exc import SQLAlchemyError
import logging
import firebase_admin
from firebase_admin import messaging
from pydantic import BaseModel

# Initialize Firebase
def initialize_firebase_app(credentials_path):
    cred = firebase_admin.credentials.Certificate(credentials_path)
    firebase_admin.initialize_app(cred)

# Logging configuration
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('./server.log'),
                              logging.StreamHandler()])

# FastAPI app instance
app = FastAPI()

# Initialize Firebase app
initialize_firebase_app("./docstagram-notif-9a2a2975ecdd.json")

# SQLAlchemy setup
Base = declarative_base()

class FcmToken(Base):
    __tablename__ = 'fcm_tokens'

    user_id = Column(String, primary_key=True, index=True)
    fcm_token = Column(String, nullable=False)

# Database class
class Database:
    def __init__(self, url: str):
        self.engine = create_engine(url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_db(self) -> Generator:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

# Create tables
database_url = "postgresql://aryan:aryan1520@localhost:5432/fcm_token"
db = Database(database_url)
Base.metadata.create_all(bind=db.engine)


def get_fcm_tokens(user_id: str, db: Session) -> List[str]:
    query = text("SELECT fcm_token FROM fcm_tokens WHERE user_id = :user_id")
    result = db.execute(query, {"user_id": user_id}).fetchall()
    fcm_tokens = [row[0] for row in result]
    return fcm_tokens

# WebSocket Manager
class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.offline_messages: Dict[str, List[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        self.active_connections[user_id] = websocket
        logging.info(f"User {user_id} connected.")
        print(f"User {user_id} connected.")
        # Send stored messages
        if user_id in self.offline_messages:
            for message in self.offline_messages[user_id]:
                await self.send_personal_message(message, user_id)
            del self.offline_messages[user_id]

    async def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logging.info(f"User {user_id} disconnected.")
            print(f"User {user_id} disconnected.")

    async def send_personal_message(self, message: str, user_id: str):
        websocket = self.active_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logging.error(f"Error sending message to {user_id}: {e}")
                print(f"Error sending message to {user_id}: {e}")
        else:
            # Store message for offline users
            if user_id not in self.offline_messages:
                self.offline_messages[user_id] = []
            self.offline_messages[user_id].append(message)
            await self.send_offline_notification(user_id, message)

    async def send_offline_notification(self, user_id: str, message: dict):
        fcm_tokens = get_fcm_tokens(user_id, db.SessionLocal())
        message = json.loads(message)
        for fcm_token in fcm_tokens:
            await send_notification(fcm_token, message)
            print(f"Notification sent to {fcm_token}")

# Initialize the WebSocketManager
manager = WebSocketManager()

# Firebase notification function
async def send_notification(fcm_token, message_body: dict):
    try:

        # Debugging: Check the structure of message_body
        print("Received message_body:", message_body)
        
        first_name = message_body["message"]["author"]["firstName"]
        last_name = message_body["message"]["author"]["lastName"]
        text = message_body["message"]["text"]

        # Construct title and body
        title = f"{first_name} {last_name}"
        body = text
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            token=fcm_token
        )
        # Send the message
        response = messaging.send(message)
        print("Successfully sent message:", response)

    except KeyError as e:
        print(f"KeyError: {e}")
        return
    except Exception as e:
        print(f"Unexpected error: {e}")

# WebSocket endpoint
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                #print(f"Message: {data}")
                #logging.info(f"Message: {data}")

                if 'recipient_id' in message:
                    logging.info(f"Sending personal message to {message['recipient_id']}")
                    recipient_id = message['recipient_id']
                    await manager.send_personal_message(data, recipient_id)
            except json.JSONDecodeError as e:
                logging.error(f"JSON decoding error for user {user_id}: {e}")
                # Consider sending an error message back to the user
                # await websocket.send_text("Invalid JSON format.")
    except WebSocketDisconnect:
        await manager.disconnect(user_id)
    except Exception as e:
        logging.error(f"Unexpected error for user {user_id}: {e}")
        await manager.disconnect(user_id)

# Health check endpoints
@app.get("/health")
def health_check():
    return {"status": "Server is running"}

@app.get("/say_hello")
def say_hello():
    return {"message": "Hello, Aryan"}

@app.get("/db_health")
def db_health_check():
    try:
        with db.engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
        return {"status": "Database connection is OK"}
    except SQLAlchemyError as e:
        return {"status": "Database connection failed", "error": str(e)}

# Token storage endpoint

class TokenRequest(BaseModel):
    user_id: str
    fcm_token: str

@app.post("/store_token")
async def store_token(
    token_request: TokenRequest,
    db: Session = Depends(db.get_db)
):
    try:
        query = text("INSERT INTO fcm_tokens (user_id, fcm_token) VALUES (:user_id, :fcm_token)")
        db.execute(query, {"user_id": token_request.user_id, "fcm_token": token_request.fcm_token})
        db.commit()
        return {"message": "Token stored successfully"}
    except SQLAlchemyError as e:
        db.rollback()
        # Handle the exception (e.g., log the error)
        return {"error": str(e)}  