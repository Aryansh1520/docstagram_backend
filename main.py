from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import Dict, List, Generator
import json
from sqlalchemy.exc import SQLAlchemyError

app = FastAPI()

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        self.active_connections[user_id] = websocket
        print(f"User {user_id} connected.")

    async def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            print(f"User {user_id} disconnected.")

    async def send_personal_message(self, message: str, user_id: str):
        websocket = self.active_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_text(message)
            except Exception as e:
                print(f"Error sending message to {user_id}: {e}")

    async def broadcast(self, message: str):
        for user_id, websocket in list(self.active_connections.items()):
            try:
                await websocket.send_text(message)
            except Exception as e:
                print(f"Error broadcasting message to {user_id}: {e}")
                await self.disconnect(user_id)


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
            message = await websocket.receive_text()
            data = json.loads(message)
            print(f"Message: {message}")

            if 'recipient_id' in data:
                recipient_id = data['recipient_id']
                await manager.send_personal_message(message, recipient_id)
            else:
                await manager.broadcast(f"User #{user_id} says: {data.get('message', 'No message provided')}")
    except WebSocketDisconnect:
        await manager.disconnect(user_id)
        await manager.broadcast(f"User #{user_id} left the chat")
    except Exception as e:
        print(f"Error: {e}")
        await manager.disconnect(user_id)
        await manager.broadcast(f"User #{user_id} disconnected due to an error")

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
database_url = "postgresql://dev_aryansh:docstagram@localhost:5432/direct_messages_db"
db = Database(database_url)
