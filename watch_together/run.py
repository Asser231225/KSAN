#!/usr/bin/env python3


import uvicorn
import os
import sys

def main():
    print("🎬 Запуск CineSync...")
    print("=" * 50)
    
    # Проверяем, существуют ли необходимые директории
    required_dirs = ['static', 'templates']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            print(f"❌ Директория '{dir_name}' не найдена!")
            print(f"Создайте директорию '{dir_name}' и поместите в неё соответствующие файлы.")
            return
    
    # Проверяем наличие видеофайлов
    static_files = os.listdir('static') if os.path.exists('static') else []
    video_files = [f for f in static_files if f.endswith('.mp4')]
    
    if not video_files:
        print("⚠️  В директории 'static' не найдены видеофайлы (.mp4)")
        print("Поместите ваши видеофайлы в директорию 'static' для тестирования.")
    else:
        print(f"✅ Найдено видеофайлов: {len(video_files)}")
        for video in video_files:
            print(f"   - {video}")
    
    print("\n🚀 Запуск сервера...")
    print("📍 Откройте браузер и перейдите по адресу: http://127.0.0.1:8000")
    print("⏹️  Для остановки сервера нажмите Ctrl+C")
    print("=" * 50)
    
    try:
        uvicorn.run(
            "manager:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен. До свидания!")
    except Exception as e:
        print(f"\n❌ Ошибка запуска сервера: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()