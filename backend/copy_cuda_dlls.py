import os
import shutil
import glob
import sys
import importlib.util

def find_package_path(package_name):
    """Шукає шлях до пакета навіть якщо стандартні атрибути відсутні."""
    # Спроба через importlib (найбільш надійний метод для сучасних середовищ)
    spec = importlib.util.find_spec(package_name)
    if spec and spec.submodule_search_locations:
        return spec.submodule_search_locations[0]
    
    # Спроба через прямий імпорт
    try:
        pkg = __import__(package_name)
        # Перевірка __path__
        path = getattr(pkg, "__path__", None)
        if path:
            return path[0]
        # Перевірка __file__
        file = getattr(pkg, "__file__", None)
        if file:
            return os.path.dirname(file)
    except ImportError:
        return None
    return None

def copy_dlls():
    # Шлях до папки з моделлю
    dest_dir = os.path.abspath("./models/nllb_int8")
    
    if not os.path.exists(dest_dir):
        print(f"Створюю папку для моделі: {dest_dir}")
        os.makedirs(dest_dir, exist_ok=True)

    # Список пакетів для пошуку
    packages_to_scan = ["nvidia.cublas", "nvidia.cudnn"]
    found_files = []

    for pkg_name in packages_to_scan:
        print(f"Пошук бібліотек у {pkg_name}...")
        pkg_path = find_package_path(pkg_name)
        
        if not pkg_path:
            print(f"Попередження: Пакет {pkg_name} не знайдено. Спробуй: uv pip install {pkg_name.replace('.', '-')}")
            continue

        # Шаблони пошуку: у корені пакета та в підпапці lib/bin
        search_paths = [
            pkg_path,
            os.path.join(pkg_path, "lib"),
            os.path.join(pkg_path, "bin")
        ]

        for s_path in search_paths:
            if not os.path.exists(s_path):
                continue
                
            dlls = glob.glob(os.path.join(s_path, "*.dll"))
            for dll in dlls:
                filename = os.path.basename(dll)
                target = os.path.join(dest_dir, filename)
                
                # Копіюємо тільки якщо файлу ще немає або він іншого розміру
                try:
                    shutil.copy2(dll, target)
                    if filename not in found_files:
                        print(f"Скопійовано: {filename}")
                        found_files.append(filename)
                except Exception as e:
                    print(f"Помилка при копіюванні {filename}: {e}")

    if not found_files:
        print("\nЖодної DLL не знайдено. Переконайся, що пакети встановлені через uv.")
    else:
        print(f"\nГотово! Скопійовано файлів: {len(found_files)}")
        print(f"Шлях призначення: {dest_dir}")
        print("Тепер можеш запускати: python -m app.main")

if __name__ == "__main__":
    copy_dlls()