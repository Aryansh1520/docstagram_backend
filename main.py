from urllib.parse import urlencode
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import Dict, List, Generator
import json
from sqlalchemy.exc import SQLAlchemyError
import logging
import firebase_admin
from firebase_admin import messaging

def initialize_firebase_app(credentials_path):
    cred = firebase_admin.credentials.Certificate(credentials_path)
    firebase_admin.initialize_app(cred)

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('./server.log'),
                              logging.StreamHandler()])
app = FastAPI()

initialize_firebase_app("./docstagram-notif-d8ba5bb32bc4.json")



async def send_notification(fcm_token):
    """Sends a notification to the specified FCM token."""

    message = messaging.Message(
        notification=messaging.Notification(
            title="Dummy Title",
            body="Dummy Body"
        ),
        token=fcm_token
    )

    # Send the message
    response = messaging.send(message)
    print('Successfully sent message:', response)





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

    async def send_offline_notification(self, user_id: str, message: str):
            await send_notification("dAtFUaguQIaEvlah6EU67W:APA91bG8PY42hHnh3OLge1a2O4Ar76aje2yMDZJcZ-EAt3veSdxsJ0mmwmksKTAAXebDB6-ukvFneF7JXItJpJ9F8yqbymF_N2Nu9s2QW2NfBN_J81iC2Z15gp67d-SwJTNspymehsF0")


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

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                print(f"Message: {data}")
                logging.info(f"Message: {data}")

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



# Initialize the WebSocketManager and Database

manager = WebSocketManager()
database_url = "postgresql://aryan:aryan1520@localhost:5432/fcm_token"
db = Database(database_url)
