import tkinter as tk
from tkinter import messagebox, ttk
from pytubefix import YouTube
from github import Github
import subprocess
import os
import json
import threading
import urllib.parse
import shutil

CONFIG_FILE = "config.json"
LOCAL_REPO_DIR = "local_repo"  # Папка для локального клона репо через git lfs

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

def git_lfs_initialize(repo_path, log_func=None):
    if log_func:
        log_func("Инициализация git lfs в локальном репозитории...")
    subprocess.run(["git", "lfs", "install"], cwd=repo_path, check=True)
    if log_func:
        log_func("Git LFS инициализирован")

def git_lfs_push(repo_path, file_path, commit_message, log_func=None):
    try:
        if log_func:
            log_func(f"Добавляем файл {file_path} в git...")
        subprocess.run(["git", "add", file_path], cwd=repo_path, check=True)

        if log_func:
            log_func("Коммитим изменения...")
        subprocess.run(["git", "commit", "-m", commit_message], cwd=repo_path, check=True)

        if log_func:
            log_func("Отправляем изменения в удалённый репозиторий...")
        subprocess.run(["git", "push"], cwd=repo_path, check=True)

        if log_func:
            log_func("Загрузка через Git LFS завершена успешно")
        return True
    except subprocess.CalledProcessError as e:
        if log_func:
            log_func(f"Ошибка при git lfs push: {e}")
        return False

def ensure_ssh_folder(log_func=None):
    ssh_dir = os.path.expanduser("~/.ssh")
    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir)
        if log_func:
            log_func(f"Папка {ssh_dir} создана.")
    else:
        if log_func:
            log_func(f"Папка {ssh_dir} уже существует.")

def generate_ssh_key(email, log_func=None):
    ssh_key_path = os.path.expanduser("~/.ssh/id_rsa")
    if os.path.exists(ssh_key_path):
        if log_func:
            log_func(f"SSH ключ уже существует по пути {ssh_key_path}")
        return ssh_key_path

    cmd = f'ssh-keygen -t rsa -b 4096 -C "{email}" -f "{ssh_key_path}" -N ""'
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        if log_func:
            log_func(f"Ошибка генерации SSH ключа: {result.stderr}")
        return None
    else:
        if log_func:
            log_func(f"SSH ключ создан: {ssh_key_path}")
        return ssh_key_path

def start_ssh_agent(log_func=None):
    agent = subprocess.Popen(["ssh-agent", "-s"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = agent.communicate()
    if agent.returncode != 0:
        if log_func:
            log_func(f"Ошибка запуска ssh-agent: {err.strip()}")
        return False
    for line in out.splitlines():
        if "SSH_AUTH_SOCK" in line or "SSH_AGENT_PID" in line:
            key, rest = line.split('=', 1)
            value = rest.split(';',1)[0]
            os.environ[key] = value
    if log_func:
        log_func("ssh-agent запущен")
    return True

def setup_ssh_agent_add_key(key_path, log_func=None):
    if not start_ssh_agent(log_func):
        return
    result = subprocess.run(["ssh-add", key_path], text=True, capture_output=True)
    if result.returncode != 0:
        if log_func:
            log_func(f"Ошибка добавления ssh ключа в агент: {result.stderr.strip()}")
    else:
        if log_func:
            log_func("SSH ключ добавлен в ssh-agent успешно.")

class YouTubeDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube WebM Downloader with GitHub Upload")

        frame_email = tk.Frame(root)
        frame_email.pack(pady=5, padx=10, fill='x')
        tk.Label(frame_email, text="Email для SSH ключа:").pack(side=tk.LEFT)
        self.email_entry = tk.Entry(frame_email, width=30)
        self.email_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(frame_email, text="Username для Git:").pack(side=tk.LEFT, padx=(20,5))
        self.username_entry = tk.Entry(frame_email, width=20)
        self.username_entry.pack(side=tk.LEFT, padx=5)
        config = load_config()
        self.email_entry.insert(0, config.get("ssh_email", ""))
        self.username_entry.insert(0, config.get("git_username", ""))

        btn_ssh_init = tk.Button(root, text="Инициализировать SSH и Git User", command=self.init_ssh)
        btn_ssh_init.pack(pady=5)

        btn_git_lfs_init = tk.Button(root, text="Инициализировать Git LFS", command=self.init_git_lfs)
        btn_git_lfs_init.pack(pady=5)

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

        self.copy_url_button = tk.Button(root, text="Копировать URL", command=self.copy_url)
        self.copy_url_button.pack(pady=5)
        self.copy_url_button.config(state=tk.DISABLED)

        # Подпись с сервером внизу
        self.signature_frame = tk.Frame(root)
        self.signature_frame.pack(side=tk.BOTTOM, pady=5)
        label_prefix = tk.Label(self.signature_frame, text="Код by Seigu специально для сервера Уютный Сандбокс ")
        label_prefix.pack(side=tk.LEFT)
        self.ip_port = "212.22.80.35:27015"
        self.ip_label = tk.Label(self.signature_frame, text=self.ip_port, fg="blue", cursor="hand2", font=("Arial", 9, "underline"))
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
            "repo_path": repo_path,
            "ssh_email": self.email_entry.get().strip(),
            "git_username": self.username_entry.get().strip()
        })
        self.start_button.config(state=tk.DISABLED)
        self.progress.start()
        self.log("Начинаем процесс...")
        try:
            yt = YouTube(url)
            safe_title = "".join(c for c in yt.title if c.isalnum() or c in " -_ .()").rstrip()
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
                        raise Exception("Невозможно найти поток с видео в webm формате.")
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
            MAX_API_UPLOAD_MB = 24
            if filesize_mb > MAX_API_UPLOAD_MB:
                self.log(f"Файл слишком большой ({filesize_mb:.2f} МБ) для API GitHub, загружаем через Git LFS...")
                self.upload_with_git_lfs(output_file, repo_name, repo_path)
            else:
                if filesize_mb > 25:
                    self.log("Файл больше 25МБ, сжимаем...")
                    compressed_file = "compressed_" + os.path.basename(output_file)
                    compress_webm(output_file, compressed_file, target_size_mb=20, log_func=self.log)
                    os.remove(output_file)
                    output_file = compressed_file
                    filesize_mb = os.path.getsize(output_file) / (1024 * 1024)
                    self.log(f"Новый размер: {filesize_mb:.2f} МБ")
                self.upload_standard_api(output_file, token, repo_name, repo_path)
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

    def upload_standard_api(self, output_file, token, repo_name, repo_path):
        self.log("Загружаем файл на GitHub через API...")
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
        self.make_raw_link(repo_name, filename_github)

    def upload_with_git_lfs(self, output_file, repo_name, repo_path):
        self.log("Работаем с Git LFS...")
        if not os.path.exists(LOCAL_REPO_DIR):
            self.log("Клонируем репозиторий локально...")
            try:
                subprocess.run(["git", "clone", f"https://github.com/{repo_name}.git", LOCAL_REPO_DIR], check=True)
            except subprocess.CalledProcessError as e:
                self.log(f"Ошибка клонирования: {e}")
                messagebox.showerror("Ошибка", f"Не удалось клонировать репозиторий: {e}")
                return
        git_lfs_initialize(LOCAL_REPO_DIR, log_func=self.log)
        dest_dir = os.path.join(LOCAL_REPO_DIR, repo_path)
        os.makedirs(dest_dir, exist_ok=True)
        dest_file_path = os.path.join(dest_dir, os.path.basename(output_file))
        shutil.copy2(output_file, dest_file_path)
        self.log(f"Файл скопирован в локальный репозиторий: {dest_file_path}")
        rel_file_path = os.path.relpath(dest_file_path, LOCAL_REPO_DIR).replace("\\", "/")
        commit_message = f"Добавлено видео LFS: {os.path.basename(output_file)}"
        success = git_lfs_push(LOCAL_REPO_DIR, rel_file_path, commit_message, log_func=self.log)
        if success:
            filename_github = os.path.join(repo_path, os.path.basename(output_file)).replace("\\", "/")
            self.make_raw_link(repo_name, filename_github)
        else:
            messagebox.showerror("Ошибка", "Не удалось загрузить файл через Git LFS.")

    def make_raw_link(self, repo_name, filename_github):
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

    def init_ssh(self):
        email = self.email_entry.get().strip()
        username = self.username_entry.get().strip()
        if not email or not username:
            messagebox.showerror("Ошибка", "Введите email и имя пользователя для Git")
            return
        self.log("Настраиваем глобальные параметры git user.email и user.name...")
        try:
            subprocess.run(['git', 'config', '--global', 'user.email', email], check=True)
            subprocess.run(['git', 'config', '--global', 'user.name', username], check=True)
            self.log(f"Git user.email установлен: {email}")
            self.log(f"Git user.name установлен: {username}")
        except subprocess.CalledProcessError as e:
            self.log(f"Ошибка настройки git config: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось настроить git user: {str(e)}")
            return
        self.log("Создаем папку .ssh (если нужно)...")
        ensure_ssh_folder(log_func=self.log)
        self.log(f"Генерируем SSH ключ для email: {email}...")
        key_path = generate_ssh_key(email, log_func=self.log)
        if key_path:
            self.log("Запускаем ssh-agent и добавляем ключ...")
            setup_ssh_agent_add_key(key_path, log_func=self.log)
            self.log("SSH инициализация завершена.")
        else:
            self.log("Ошибка при генерации SSH ключа.")
        config = load_config()
        config["ssh_email"] = email
        config["git_username"] = username
        save_config(config)

    def init_git_lfs(self):
        repo_path = LOCAL_REPO_DIR
        if not os.path.exists(repo_path):
            messagebox.showerror("Ошибка", f"Локальная папка репозитория не найдена: {repo_path}")
            return
        self.log(f"Инициализация Git LFS в {repo_path}...")
        try:
            git_lfs_initialize(repo_path, log_func=self.log)
        except Exception as e:
            self.log(f"Ошибка инициализации Git LFS: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось инициализировать Git LFS: {str(e)}")
        else:
            self.log("Git LFS успешно инициализирован.")

    def on_ip_click(self, event):
        connect_cmd = f"connect {self.ip_port}"
        self.root.clipboard_clear()
        self.root.clipboard_append(connect_cmd)
        messagebox.showinfo(
            "О!",
            "Йо! Захотел поиграть? Сервер классный, реклама за которую мне не заплатили, "
            "так что в твой буфер кинул адрес, просто запусти Garry's Mod и вставь в консоль, чтобы попасть на сервер 🙂"
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()
