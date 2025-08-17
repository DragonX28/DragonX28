import tkinter as tk
from tkinter import messagebox, ttk
from pytubefix import YouTube
from github import Github
import subprocess
import os
import json
import threading
import urllib.parse

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def compress_webm(input_file, output_file, target_size_mb=20, log_func=None):
    if log_func:
        log_func(f"Определяем длительность видео: {input_file}...")
    target_size_bytes = target_size_mb * 1024 * 1024
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', 
         '-show_entries', 'format=duration', 
         '-of', 'default=noprint_wrappers=1:nokey=1', input_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    duration = float(result.stdout)
    if log_func:
        log_func(f"Длительность видео: {duration:.2f} секунд")
    target_bitrate = (target_size_bytes * 8) / duration
    target_bitrate_kbps = int(target_bitrate / 1024)
    if log_func:
        log_func(f"Расчёт битрейта: {target_bitrate_kbps} кбит/с")
        log_func("Начинаем сжатие с использованием ffmpeg (ultrafast)...")
    threads = os.cpu_count() or 1
    command = [
        'ffmpeg', '-i', input_file,
        '-c:v', 'libvpx-vp9',
        '-preset', 'ultrafast',
        '-threads', str(threads),
        '-b:v', f'{target_bitrate_kbps}k',
        '-c:a', 'libopus',
        '-y',
        output_file
    ]
    subprocess.run(command, check=True)
    if log_func:
        log_func("Сжатие завершено")

def convert_mp4_to_webm(input_file, output_file, log_func=None):
    if log_func:
        log_func("Начинаем конвертацию mp4 в webm (ultrafast)...")
    threads = os.cpu_count() or 1
    command = [
        'ffmpeg', '-i', input_file,
        '-c:v', 'libvpx-vp9',
        '-preset', 'ultrafast',
        '-threads', str(threads),
        '-c:a', 'libopus',
        '-y',
        output_file
    ]
    subprocess.run(command, check=True)
    if log_func:
        log_func("Конвертация завершена")

class YouTubeDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube WebM Downloader with GitHub Upload")

        frame_url = tk.Frame(root)
        frame_url.pack(pady=5, padx=10, fill='x')
        tk.Label(frame_url, text="Введите ссылку YouTube:").pack(side=tk.LEFT)
        self.url_entry = tk.Entry(frame_url, width=45)
        self.url_entry.pack(side=tk.LEFT, padx=5)
        btn_paste_url = tk.Button(frame_url, text="Вставить", command=lambda: self.paste_from_clipboard(self.url_entry))
        btn_paste_url.pack(side=tk.LEFT)

        frame_token = tk.Frame(root)
        frame_token.pack(pady=5, padx=10, fill='x')
        tk.Label(frame_token, text="GitHub Token:").pack(side=tk.LEFT)
        self.token_entry = tk.Entry(frame_token, width=45, show='*')
        self.token_entry.pack(side=tk.LEFT, padx=5)
        btn_paste_token = tk.Button(frame_token, text="Вставить", command=lambda: self.paste_from_clipboard(self.token_entry))
        btn_paste_token.pack(side=tk.LEFT)

        frame_repo = tk.Frame(root)
        frame_repo.pack(pady=5, padx=10, fill='x')
        tk.Label(frame_repo, text="Репозиторий (user/repo):").pack(side=tk.LEFT)
        self.repo_entry = tk.Entry(frame_repo, width=45)
        self.repo_entry.pack(side=tk.LEFT, padx=5)
        btn_paste_repo = tk.Button(frame_repo, text="Вставить", command=lambda: self.paste_from_clipboard(self.repo_entry))
        btn_paste_repo.pack(side=tk.LEFT)

        frame_path = tk.Frame(root)
        frame_path.pack(pady=5, padx=10, fill='x')
        tk.Label(frame_path, text="Путь в репозитории для файла:").pack(side=tk.LEFT)
        self.path_entry = tk.Entry(frame_path, width=45)
        self.path_entry.insert(0, "videos/")
        self.path_entry.pack(side=tk.LEFT, padx=5)
        btn_paste_path = tk.Button(frame_path, text="Вставить", command=lambda: self.paste_from_clipboard(self.path_entry))
        btn_paste_path.pack(side=tk.LEFT)

        self.start_button = tk.Button(root, text="Скачать и загрузить", command=self.start_thread)
        self.start_button.pack(pady=10)

        self.progress = ttk.Progressbar(root, mode='indeterminate', length=400)
        self.progress.pack(pady=10)
        self.progress.stop()
        self.progress['value'] = 0

        self.status_text = tk.Text(root, height=12, width=75)
        self.status_text.pack(padx=10, pady=10)
        self.status_text.config(state=tk.DISABLED)

        self.raw_url_label = tk.Label(root, text="", fg="blue", cursor="hand2")
        self.raw_url_label.pack(pady=5)
        self.raw_url_label.bind("<Button-1>", self.on_empty_click)  # Клик не нужен

        self.copy_url_button = tk.Button(root, text="Копировать URL", command=self.copy_url)
        self.copy_url_button.pack(pady=5)
        self.copy_url_button.config(state=tk.DISABLED)

        # Создаём подпись с кликабельным IP:PORT
        signature_frame = tk.Frame(root)
        signature_frame.pack(side=tk.BOTTOM, pady=5)

        label_prefix = tk.Label(signature_frame, text="Скрипт by Seigu спецально для сервера Уютный Сандбокс ")
        label_prefix.pack(side=tk.LEFT)

        self.ip_port = "212.22.80.35:27015"
        self.ip_label = tk.Label(signature_frame, text=self.ip_port, fg="blue", cursor="hand2", font=("Arial", 9, "underline"))
        self.ip_label.pack(side=tk.LEFT)
        self.ip_label.bind("<Button-1>", self.on_ip_click)

        self.uploaded_file_url = ""

        config = load_config()
        self.token_entry.insert(0, config.get("token", ""))
        self.repo_entry.insert(0, config.get("repo_name", ""))
        self.path_entry.delete(0, tk.END)
        self.path_entry.insert(0, config.get("repo_path", "videos/"))

    def paste_from_clipboard(self, widget):
        try:
            clipboard = self.root.clipboard_get()
            widget.delete(0, tk.END)
            widget.insert(0, clipboard)
        except tk.TclError:
            self.log("Буфер обмена пуст или недоступен")

    def log(self, message):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update()

    def copy_url(self):
        if self.uploaded_file_url:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.uploaded_file_url)
            self.log("Raw URL скопирован в буфер обмена!")

    def start_thread(self):
        threading.Thread(target=self.start_process, daemon=True).start()

    def start_process(self):
        url = self.url_entry.get().strip()
        token = self.token_entry.get().strip()
        repo_name = self.repo_entry.get().strip()
        repo_path = self.path_entry.get().strip()

        if not url or not token or not repo_name:
            messagebox.showerror("Ошибка", "Заполните все поля!")
            return

        save_config({
            "token": token,
            "repo_name": repo_name,
            "repo_path": repo_path
        })

        self.start_button.config(state=tk.DISABLED)
        self.progress.start()
        self.log("Начинаем процесс...")

        try:
            yt = YouTube(url)
            safe_title = "".join(c for c in yt.title if c.isalnum() or c in " -_.()").rstrip()
            webm_filename = f"{safe_title}.webm"
            file_exists = os.path.exists(webm_filename)

            if file_exists:
                self.log(f"Файл {webm_filename} уже существует, загружаем на GitHub...")
                output_file = webm_filename
            else:
                self.log("Файл webm не найден, начинаем скачивание...")
                stream = yt.streams.filter(file_extension='webm', progressive=True).first()
                if not stream:
                    self.log("Формат webm не найден, скачиваем mp4 и конвертируем в webm...")
                    stream = yt.streams.filter(file_extension='mp4', progressive=True).order_by('resolution').desc().first()
                    if not stream:
                        raise Exception("Невозможно найти поток с видео в webm или mp4 формате.")
                    mp4_file = stream.download()
                    self.log(f"Видео mp4 скачано: {mp4_file}")
                    convert_mp4_to_webm(mp4_file, webm_filename, log_func=self.log)
                    os.remove(mp4_file)
                    output_file = webm_filename
                else:
                    output_file = stream.download(filename=webm_filename)
                    self.log(f"Видео webm скачано: {output_file}")

            filesize_mb = os.path.getsize(output_file) / (1024 * 1024)
            self.log(f"Размер файла: {filesize_mb:.2f} МБ")

            if filesize_mb > 25:
                self.log("Файл больше 25МБ, сжимаем до 20МБ...")
                compressed_file = "compressed_" + os.path.basename(output_file)
                compress_webm(output_file, compressed_file, target_size_mb=20, log_func=self.log)
                os.remove(output_file)
                output_file = compressed_file
                filesize_mb = os.path.getsize(output_file) / (1024 * 1024)
                self.log(f"Новый размер: {filesize_mb:.2f} МБ")

            g = Github(token)
            repo = g.get_repo(repo_name)

            with open(output_file, 'rb') as file:
                content = file.read()

            filename_github = os.path.join(repo_path, os.path.basename(output_file)).replace("\\", "/")

            try:
                file_content = repo.get_contents(filename_github)
                repo.update_file(file_content.path, f"Обновление видео {os.path.basename(output_file)}", content, file_content.sha)
                self.log(f"Файл обновлен в репозитории: {filename_github}")
            except:
                repo.create_file(filename_github, f"Добавлено видео {os.path.basename(output_file)}", content)
                self.log(f"Файл создан в репозитории: {filename_github}")

            user_repo = repo_name.split("/")
            if len(user_repo) == 2:
                user, repo_name_only = user_repo
                encoded_path = urllib.parse.quote(filename_github)
                raw_url = f"https://github.com/{user}/{repo_name_only}/raw/refs/heads/main/{encoded_path}"
                self.uploaded_file_url = raw_url
                self.raw_url_label.config(text=raw_url)
                self.copy_url_button.config(state=tk.NORMAL)
                self.log("Ссылка на raw файл отображена и готова к копированию.")
            else:
                self.uploaded_file_url = ""
                self.raw_url_label.config(text="")
                self.copy_url_button.config(state=tk.DISABLED)

            self.log("Загрузка завершена!")

        except Exception as e:
            self.uploaded_file_url = ""
            self.raw_url_label.config(text="")
            self.copy_url_button.config(state=tk.DISABLED)
            self.log(f"Ошибка: {str(e)}")
            messagebox.showerror("Ошибка", str(e))

        finally:
            self.start_button.config(state=tk.NORMAL)
            self.progress.stop()
            self.progress['value'] = 0

    def on_ip_click(self, event):
        ip_port = self.ip_port
        connect_cmd = f"connect {ip_port}"
        self.root.clipboard_clear()
        self.root.clipboard_append(connect_cmd)
        messagebox.showinfo(
            "О!",
            "Ты решил поиграть на сервере? Войк мне не заплатил за рекламу, "
            "но сервер и правда хороший, в твой буфер обмена скопирована команда для подключения, "
            "так что просто запусти Garry's Mod и введи её в консоль. 🙂"
        )

    def on_empty_click(self, event):
        # Можно по ссылке raw ничего не делать или добавить открытие браузера
        pass

if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()

