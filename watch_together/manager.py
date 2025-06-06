import uuid
import asyncio
import time
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, List, Any

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Хранилище данных
rooms: Dict[str, Dict[str, Any]] = {}
room_locks: Dict[str, asyncio.Lock] = {}

class ChatMessage:
    def __init__(self, user_id: str, username: str, message: str):
        self.user_id = user_id
        self.username = username
        self.message = message
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "message": self.message,
            "timestamp": self.timestamp
        }

@app.get("/")
def index(request: Request):
    videos = ["video1.mp4", "video2.mp4", "video3.mp4"]
    return templates.TemplateResponse("index.html", {"request": request, "videos": videos})

@app.get("/create_room/{video_name}")
def create_room(video_name: str):
    room_id = str(uuid.uuid4())[:8]
    rooms[room_id] = {
        "video": video_name,
        "state": {"playing": False, "time": 0.0, "version": 0},
        "listeners": {},
        "users": {},  # Активные пользователи
        "messages": [],  # История сообщений
        "last_message_id": 0,
        "message_version": 0  # Отдельная версия для сообщений
    }
    room_locks[room_id] = asyncio.Lock()
    return RedirectResponse(f"/room/{room_id}")

@app.get("/room/{room_id}")
def get_room(request: Request, room_id: str):
    if room_id not in rooms:
        return RedirectResponse("/")
    return templates.TemplateResponse("room.html", {
        "request": request,
        "room_id": room_id,
        "video_name": rooms[room_id]["video"]
    })

@app.post("/room/{room_id}/update")
async def update_state(room_id: str, request: Request):
    if room_id not in rooms:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    
    try:
        data = await request.json()
        playing = data.get("playing")
        time_pos = data.get("time")
        user_id = data.get("user_id")
        username = data.get("username")
        
        if playing is None or time_pos is None:
            raise ValueError("Неверные данные")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Неверный формат данных")
    
    async with room_locks[room_id]:
        room = rooms[room_id]
        
        # Обновляем информацию о пользователе
        if user_id and username:
            room["users"][user_id] = {
                "username": username,
                "last_seen": time.time()
            }
        
        # Обновляем состояние видео
        room["state"] = {
            "playing": playing,
            "time": time_pos,
            "version": room["state"]["version"] + 1
        }
        
        # Уведомляем всех слушателей
        for event in room["listeners"].values():
            event.set()
        
        room["listeners"] = {}
    
    return JSONResponse({"status": "success", "version": room["state"]["version"]})

@app.post("/room/{room_id}/chat")
async def send_chat_message(room_id: str, request: Request):
    if room_id not in rooms:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    
    try:
        data = await request.json()
        message_text = data.get("message", "").strip()
        user_id = data.get("user_id")
        username = data.get("username")
        
        if not message_text or not user_id or not username:
            raise ValueError("Неверные данные")
        
        # Ограничение длины сообщения
        if len(message_text) > 500:
            raise ValueError("Сообщение слишком длинное")
            
    except Exception as e:
        raise HTTPException(status_code=400, detail="Неверный формат данных")
    
    async with room_locks[room_id]:
        room = rooms[room_id]
        
        # Создаем новое сообщение с уникальным ID
        room["last_message_id"] += 1
        message = ChatMessage(user_id, username, message_text)
        message_dict = message.to_dict()
        message_dict["id"] = room["last_message_id"]  # Добавляем уникальный ID
        
        room["messages"].append(message_dict)
        room["message_version"] += 1  # Увеличиваем версию сообщений
        
        # Ограничиваем количество сообщений в истории
        if len(room["messages"]) > 100:
            room["messages"] = room["messages"][-100:]
        
        # Обновляем информацию о пользователе
        room["users"][user_id] = {
            "username": username,
            "last_seen": time.time()
        }
        
        # Уведомляем всех слушателей о новом сообщении
        for event in room["listeners"].values():
            event.set()
        
        room["listeners"] = {}
    
    return JSONResponse({"status": "success", "message_id": room["last_message_id"]})

@app.get("/room/{room_id}/poll")
async def poll_state(room_id: str, last_version: int = 0, last_message_version: int = 0, user_id: str = None, username: str = None):
    if room_id not in rooms:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    
    client_id = str(uuid.uuid4())
    room = rooms[room_id]
    
    # Регистрируем пользователя
    if user_id and username:
        async with room_locks[room_id]:
            room["users"][user_id] = {
                "username": username,
                "last_seen": time.time()
            }
    
    # Очистка неактивных пользователей (не активны более 30 сек)
    current_time = time.time()
    async with room_locks[room_id]:
        inactive_users = [
            uid for uid, user_info in room["users"].items() 
            if current_time - user_info["last_seen"] > 30
        ]
        for uid in inactive_users:
            del room["users"][uid]
    
    # Получаем текущее состояние
    current_state = {
        "state": room["state"],
        "version": room["state"]["version"],
        "message_version": room["message_version"],
        "online_count": len(room["users"]),
        "messages": []
    }
    
    # Обрабатываем сообщения
    if last_message_version == 0:
        
        current_state["messages"] = room["messages"][-10:] if room["messages"] else []
    elif room["message_version"] > last_message_version:
       
        if room["messages"]:
            
            current_state["messages"] = room["messages"][-3:] if len(room["messages"]) >= 3 else room["messages"]
    
    # Проверяем, нужно ли ждать обновлений
    need_to_wait = (last_version >= room["state"]["version"] and 
                   last_message_version >= room["message_version"])
    
    if need_to_wait:
        event = asyncio.Event()
        async with room_locks[room_id]:
            room["listeners"][client_id] = event
        
        try:
            await asyncio.wait_for(event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            pass
        finally:
            async with room_locks[room_id]:
                if client_id in room["listeners"]:
                    del room["listeners"][client_id]
        
        # Получаем обновленное состояние после ожидания
        async with room_locks[room_id]:
            # Снова очищаем неактивных пользователей
            current_time = time.time()
            inactive_users = [
                uid for uid, user_info in room["users"].items() 
                if current_time - user_info["last_seen"] > 30
            ]
            for uid in inactive_users:
                del room["users"][uid]
            
            # Формируем финальный ответ
            current_state = {
                "state": room["state"],
                "version": room["state"]["version"],
                "message_version": room["message_version"],
                "online_count": len(room["users"]),
                "messages": []
            }
            
            # Отправляем новые сообщения только если версия изменилась
            if room["message_version"] > last_message_version:
                current_state["messages"] = room["messages"][-3:] if len(room["messages"]) >= 3 else room["messages"]
    
    return JSONResponse(current_state)

@app.get("/room/{room_id}/messages")
async def get_messages(room_id: str, limit: int = 50, after_id: int = 0):
    """Получить историю сообщений"""
    if room_id not in rooms:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    
    room = rooms[room_id]
    
    # Фильтруем сообщения по ID, если указан after_id
    if after_id > 0:
        messages = [msg for msg in room["messages"] if msg.get("id", 0) > after_id]
    else:
        messages = room["messages"][-limit:] if room["messages"] else []
    
    return JSONResponse({
        "messages": messages,
        "total": len(room["messages"]),
        "message_version": room["message_version"]
    })

@app.delete("/room/{room_id}")
async def delete_room(room_id: str):
    """Удалить комнату (для администрирования)"""
    if room_id in rooms:
        async with room_locks[room_id]:
            # Уведомляем всех слушателей о закрытии комнаты
            for event in rooms[room_id]["listeners"].values():
                event.set()
        
        del rooms[room_id]
        del room_locks[room_id]
        return JSONResponse({"status": "success", "message": "Комната удалена"})
    
    raise HTTPException(status_code=404, detail="Комната не найдена")

@app.get("/room/{room_id}/stats")
async def get_room_stats(room_id: str):
    """Получить статистику комнаты"""
    if room_id not in rooms:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    
    room = rooms[room_id]
    
    # Очистка неактивных пользователей
    current_time = time.time()
    async with room_locks[room_id]:
        inactive_users = [
            uid for uid, user_info in room["users"].items() 
            if current_time - user_info["last_seen"] > 30
        ]
        for uid in inactive_users:
            del room["users"][uid]
    
    return JSONResponse({
        "room_id": room_id,
        "video": room["video"],
        "online_users": len(room["users"]),
        "total_messages": len(room["messages"]),
        "video_state": room["state"],
        "message_version": room["message_version"],
        "users": [
            {
                "username": user_info["username"],
                "last_seen": user_info["last_seen"]
            }
            for user_info in room["users"].values()
        ]
    })

# Фоновая задача для очистки неактивных комнат
async def cleanup_inactive_rooms():
    """Очистка неактивных комнат каждые 5 минут"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 минут
            current_time = time.time()
            
            rooms_to_delete = []
            
            for room_id, room in rooms.items():
               
                if not room["users"]:
                    
                    rooms_to_delete.append(room_id)
                else:
                    # Очищаем неактивных пользователей
                    async with room_locks[room_id]:
                        inactive_users = [
                            uid for uid, user_info in room["users"].items() 
                            if current_time - user_info["last_seen"] > 60
                        ]
                        for uid in inactive_users:
                            del room["users"][uid]
            
            # Удаляем неактивные комнаты
            for room_id in rooms_to_delete:
                if room_id in rooms and not rooms[room_id]["users"]:
                    print(f"Удаляем неактивную комнату: {room_id}")
                    del rooms[room_id]
                    if room_id in room_locks:
                        del room_locks[room_id]
                        
        except Exception as e:
            print(f"Ошибка в cleanup_inactive_rooms: {e}")

# Запуск фоновой задачи при старте приложения
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_inactive_rooms())

@app.on_event("shutdown") 
async def shutdown_event():
    print("Завершение работы сервера...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)