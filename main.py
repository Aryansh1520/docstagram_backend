from fastapi import FastAPI, Depends, HTTPException , UploadFile , File
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import json
import shutil
from shutil import copyfileobj
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import base64
import os

class Database:
    def __init__(self, url):
        self.engine = create_engine(url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_db(self):
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    async def disconnect(self, user_id: str):
        del self.active_connections[user_id]

    async def send_message(self, message: str, recipient_id: str):
        recipient_websocket = self.active_connections.get(str(recipient_id))
        if recipient_websocket:
            try:
                await recipient_websocket.send_text(message)
            except RuntimeError as e:
                if str(e) == "Unexpected ASGI message 'websocket.send', after sending 'websocket.close'.":
                    print(f"Connection with recipient {recipient_id} closed before the message could be sent.")
                else:
                    raise
        else:
            print(self.active_connections)
            print(f"The recipient {recipient_id} is offline.")


class App:
    def __init__(self, database_url):
        self.app = FastAPI()
        self.db = Database(database_url)
        self.manager = ConnectionManager()

        # Check database connection during initialization
        try:
            with self.db.engine.connect() as connection:
                result = connection.execute("SELECT 1")
                result.fetchall()  # Attempt to fetch results to verify connection
                print("Connected to database successfully!")
        except Exception as e:
            print(f"Database connection failed: {e}")


        def get_file(file_path):
            with open(file_path, "rb") as file:
                    contents = file.read()
                    base64_encoded = base64.b64encode(contents).decode("utf-8")

                # Determine the file extension
            extension = os.path.splitext(file_path)[1].lower().strip('.')

            # Define signatures for image and video
            image_signature = 'IMAGE:'
            video_signature = 'VIDEO:'

            # Add signature based on the file type
            if extension in ['jpg', 'jpeg', 'png', 'gif']:
                # It's an image
                base64_encoded = image_signature + base64_encoded
            elif extension in ['mp4', 'avi', 'mov', 'webm']:
                # It's a video
                base64_encoded = video_signature + base64_encoded

            return base64_encoded
        @self.app.get("/conversations/{user_id}")
        def get_conversations(user_id: int, db: Session = Depends(self.db.get_db)):
            result_proxy = db.execute(text("""
                SELECT 
                    DirectMessages.message,
                    DirectMessages.datetime_sent,
                    DirectMessages.is_seen,
                    CASE
                        WHEN DirectMessages.sender_id = :user_id THEN Users2.username
                        ELSE Users.username
                    END AS other_user,
                    CASE
                        WHEN DirectMessages.sender_id = :user_id THEN DirectMessages.receiver_id
                        ELSE DirectMessages.sender_id
                    END AS other_user_id
                FROM 
                    DirectMessages
                JOIN 
                    Users ON Users.user_id = DirectMessages.sender_id
                LEFT JOIN 
                    Users AS Users2 ON Users2.user_id = DirectMessages.receiver_id
                WHERE 
                    (DirectMessages.sender_id = :user_id OR DirectMessages.receiver_id = :user_id)
                    AND DirectMessages.datetime_sent = (
                        SELECT MAX(DM.datetime_sent)
                        FROM DirectMessages AS DM
                        WHERE (DM.sender_id = DirectMessages.sender_id AND DM.receiver_id = DirectMessages.receiver_id)
                            OR (DM.sender_id = DirectMessages.receiver_id AND DM.receiver_id = DirectMessages.sender_id)
                    )
                ORDER BY 
                    DirectMessages.datetime_sent DESC
                LIMIT 20
                    """), {"user_id": user_id})

            # Convert result into a list of dictionaries
            result = [{column: value for column, value in zip(result_proxy.keys(), row)} for row in result_proxy]

            if not result:
                raise HTTPException(status_code=404, detail="Conversations not found")
            return result

        @self.app.get('/chat/{user_id1},{user_id2}')

        def get_chat(user_id1:int, user_id2:int):
            with engine.connect() as connection:
                result_proxy = connection.execute(text("""
                    SELECT sender_id, receiver_id, message, datetime_sent, parent_message_id, is_seen , attachment_path
                    FROM DirectMessages
                    WHERE (sender_id = :userid1 AND receiver_id = :userid2) OR (sender_id = :userid2 AND receiver_id = :userid1)
                    ORDER BY datetime_sent DESC
                """), {"userid1": user_id1, "userid2": user_id2})

                data =  {"chat": []}
                for row in result_proxy:
                    row_data = {column: value for column, value in row._mapping.items()}
                    if row_data['attachment_path'] is not None:
                        row_data['attachment'] = get_file(row_data['attachment_path'])
                    data['chat'].append(row_data)

                return data
                
        @self.app.get('/testcloudserver')
        def test_server():
                return "Hello Aryansh"


        @self.app.websocket("/ws/{user_id}")
        async def websocket_endpoint(websocket: WebSocket, user_id: str, db: Session = Depends(self.db.get_db)):
            await manager.connect(websocket, user_id)
            try:
                while True:
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    print(f"Message: {message}")
                    print(f"Sender ID: {data.get('sender_id', 'Not provided')}")
                    print(f"Recipient ID: {data.get('recipient_id', 'Not provided')}")
                    print(f"Parent ID: {data.get('parent_id', 'Not provided')}")
                    print(f"Attachments: {data.get('attachments_path', 'Not provided')}")
                    db.execute(
                        text("""
                        INSERT INTO directmessages (sender_id, receiver_id, message, is_seen, attachment_path)
                        VALUES (:sender_id, :receiver_id, :message, :is_seen, :attachment_path)
                        """),
                        {
                            "sender_id": data.get('sender_id'),
                            "receiver_id": data.get('recipient_id'),
                            "message": data.get('message'),
                            "is_seen": False,
                            "attachment_path": data.get('attachments_path')
                        }
                    )
                    db.commit()
                    await manager.send_message(message, data['recipient_id'])

            except WebSocketDisconnect:
                manager.disconnect(user_id)

        @self.app.post("/uploadfile/")
        async def upload_file_endpoint(file: UploadFile = File(...)):
            try:
                file_location = f"/home/ubuntu/media_storage/images/{file.filename}"
                with open(file_location, "wb+") as file_object:
                    shutil.copyfileobj(file.file, file_object)
                print(f"File {file.filename} stored at {file_location}")
            except Exception as e:
                print(f"An error occurred while saving the file: {str(e)}")
                return {"error": str(e)}

            return {"info": f"File {file.filename} stored at {file_location}"}


database_url = "postgresql://dev_aryansh:docstagram@localhost:5432/direct_messages_db"
engine = create_engine(database_url)
manager = ConnectionManager()
app = App(database_url).app