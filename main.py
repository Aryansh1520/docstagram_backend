from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import List, Generator
import json
from sqlalchemy.exc import SQLAlchemyError

app = FastAPI()

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        self.active_connections[user_id] = websocket
        print(f"User {user_id} connected.")

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_text(message)

    async def broadcast(self, message: str):
        for websocket in self.active_connections.values():
            await websocket.send_text(message)

            
class Database:
    def __init__(self, url):
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
		manager.disconnect(user_id)
		await manager.broadcast(f"User #{user_id} left the chat")
		
@app.get("/health")
def health_check():
    return {"status": "Server is running"}

from sqlalchemy.exc import SQLAlchemyError

@app.get("/db_health")
def db_health_check():
    try:
        # Create a connection from the engine and execute a test query
        with db.engine.connect() as connection:
            result = connection.execute("SELECT 1")
            # Optionally, you can fetch the result if needed
            # result.fetchone()
        return {"status": "Database connection is OK"}
    except SQLAlchemyError as e:
        return {"status": "Database connection failed", "error": str(e)}

manager = WebSocketManager()

# Database URL - replace with your actual database credentials
database_url = "postgresql://dev_aryansh:docstagram@localhost:5432/direct_messages_db"
db = Database(database_url)