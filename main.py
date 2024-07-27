from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import Dict, List, Generator
import json
from sqlalchemy.exc import SQLAlchemyError
import logging

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('./server.log'),
                              logging.StreamHandler()])
app = FastAPI()

class WebSocketManager:
    def __init__(self, server_key_path: str):
        with open(server_key_path) as f:
            server_key_data = json.load(f)
        self.firebase_server_key = server_key_data['private_key']  # Adjust based on actual key name
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
        """Sends a notification to an offline user using Firebase Cloud Messaging (FCM).

        Args:
            user_id (str): The ID of the user to send the notification to.
            message (str): The message content to be displayed in the notification.

        Returns:
            dict (optional): The FCM response dictionary on successful delivery,
                            or None on errors.
        """
        access = "25459060c9377cf0fc066f7453325aa7333af385"  # Replace with your actual access token
        logging.info(f"User {user_id} is offline. Sending notification.")
        print(f"User {user_id} is offline. Sending notification.")

        fcm_url = "https://fcm.googleapis.com/fcm/send"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access}",  # Replace with your access token
        }
        payload = {
            "to": f"/topics/{user_id}",  # Assuming each user is subscribed to a topic named with their user_id
            "notification": {
                "title": "New Message",
                "body": message,
            },
            "data": {
                "user_id": user_id,
                "message": message,
            },
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(fcm_url, headers=headers, json=payload)
                response.raise_for_status()  # Raise an exception for non-200 status codes
                return response.json()  # Return FCM response on success
            except (httpx.HTTPStatusError, Exception) as e:
                logging.error(f"Error sending notification to user {user_id}: {e}")
                return None  # Indicate failure


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
server_key_path = "./docstagram-notif-25459060c937.json"  # Path to your server_key.json file

manager = WebSocketManager(server_key_path)
database_url = "postgresql://dev_aryansh:docstagram@localhost:5432/direct_messages_db"
db = Database(database_url)
