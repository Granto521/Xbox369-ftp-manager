import os
import json
import time
import threading
import ftplib
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE = Path(__file__).parent
CONFIG = BASE / "config.json"
PHONE_ROOT = Path("/storage/emulated/0").resolve()

settings = {
    "host": "192.168.0.181",
    "port": 21,
    "username": "xboxftp",
    "password": "12345",
    "passive": True
}

if CONFIG.exists():
    settings.update(json.loads(CONFIG.read_text()))
else:
    CONFIG.write_text(json.dumps(settings, indent=2))

lock = threading.Lock()
stop_event = threading.Event()

job = {
    "status": "idle",
    "current": "",
    "done": 0,
    "total": 0,
    "bytes": 0,
    "total_bytes": 0,
    "speed": 0,
    "error": ""
}


def connect():
    ftp = ftplib.FTP()
    ftp.connect(
        settings["host"],
        int(settings["port"]),
        timeout=25
    )
    ftp.login(
        settings["username"],
        settings["password"]
    )
    ftp.set_pasv(settings.get("passive", True))
    return ftp


def remote_path(path):
    path = str(path).replace("\\", "/")
    parts = []

    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)

    return "/" + "/".join(parts)


def list_directory(ftp, path):
    path = remote_path(path)
    old = ftp.pwd()
    result = []

    try:
        ftp.cwd(path)
        lines = []
        ftp.retrlines("LIST", lines.append)

        for line in lines:
            parts = line.split(None, 8)

            if len(parts) < 9:
                continue

            permissions = parts[0]
            name = parts[8]

            if name in (".", ".."):
                continue

            is_folder = permissions.startswith("d")
            full_path = remote_path(path + "/" + name)

            try:
                size = int(parts[4])
            except (ValueError, IndexError):
                size = 0

            result.append({
                "name": name,
                "path": full_path,
                "type": "folder" if is_folder else "file",
                "size": size
            })

    finally:
        ftp.cwd(old)

    return sorted(
        result,
        key=lambda item: (
            item["type"] != "folder",
            item["name"].lower()
        )
    )


def phone_list(path):
    folder = Path(path).expanduser().resolve()

    if folder != PHONE_ROOT and PHONE_ROOT not in folder.parents:
        raise Exception("That folder is outside shared phone storage.")

    if not folder.is_dir():
        raise Exception("Phone folder does not exist.")

    items = []

    for item in folder.iterdir():
        try:
            is_folder = item.is_dir()
            items.append({
                "name": item.name,
                "path": str(item),
                "type": "folder" if is_folder else "file",
                "size": item.stat().st_size
            })
        except OSError:
            pass

    return sorted(
        items,
        key=lambda item: (
            item["type"] != "folder",
            item["name"].lower()
        )
    )


def ensure_remote_folder(ftp, path):
    path = remote_path(path)

    if path == "/":
        return

    current = ""

    for part in path.strip("/").split("/"):
        current += "/" + part

        try:
            ftp.cwd(current)
        except ftplib.all_errors:
            try:
                ftp.mkd(current)
            except ftplib.all_errors:
                pass
            ftp.cwd(current)



def transfer_upload(source, destination):
    ftp = None
    source = Path(source).expanduser().resolve()

    try:
        if PHONE_ROOT != source and PHONE_ROOT not in source.parents:
            raise Exception("Source must be inside shared phone storage.")

        if not source.exists():
            raise Exception("Phone file or folder does not exist.")

        destination = remote_path(destination)

        files = []

        with lock:
            job.update({
                "status": "scanning",
                "current": "Scanning phone folder...",
                "done": 0,
                "total": 0,
                "bytes": 0,
                "total_bytes": 0,
                "speed": 0,
                "error": ""
            })

        if source.is_file():
            files.append((source, source.name))
            with lock:
                job["total"] = 1
                job["total_bytes"] = source.stat().st_size
            base_folder = None
        else:
            base_folder = source

            for current, directories, names in os.walk(source):
                directories.sort()
                names.sort()

                for name in names:
                    item = Path(current) / name
                    size = item.stat().st_size
                    files.append((item, str(item.relative_to(base_folder))))

                    with lock:
                        job["total"] += 1
                        job["total_bytes"] += size
                        job["current"] = "Scanning: " + str(item.relative_to(base_folder))

        with lock:
            job["status"] = "connecting"
            job["current"] = "Folder scanned. Connecting to Xbox FTP..."

        if stop_event.is_set():
            raise Exception("Upload cancelled.")

        ftp = connect()

        with lock:
            job["status"] = "running"
            job["current"] = "Preparing Xbox folders"

        ensure_remote_folder(ftp, destination)

        if base_folder is not None:
            folder_name = source.name
            destination_root = remote_path(destination + "/" + folder_name)
            ensure_remote_folder(ftp, destination_root)
        else:
            destination_root = destination

        start = time.time()
        transferred = 0

        for item, relative in files:
            if stop_event.is_set():
                break

            remote_folder = destination_root

            if "/" in relative:
                parent = Path(relative).parent.as_posix()
                remote_folder = remote_path(destination_root + "/" + parent)
                ensure_remote_folder(ftp, remote_folder)

            target = remote_path(remote_folder + "/" + item.name)

            with lock:
                job["current"] = item.name

            def callback(block):
                nonlocal transferred
                transferred += len(block)
                elapsed = max(time.time() - start, 0.1)

                with lock:
                    job["bytes"] = transferred
                    job["speed"] = transferred / elapsed

            with item.open("rb") as file_handle:
                ftp.storbinary(
                    "STOR " + target,
                    file_handle,
                    256 * 1024,
                    callback
                )

            with lock:
                job["done"] += 1

        with lock:
            if stop_event.is_set():
                job["status"] = "stopped"
                job["current"] = "Upload stopped"
            else:
                job["status"] = "completed"
                job["current"] = "Upload completed"

    except Exception as error:
        with lock:
            job["status"] = "error"
            job["error"] = str(error)
            job["current"] = "Upload failed"

    finally:
        if ftp:
            try:
                ftp.close()
            except Exception:
                pass

        stop_event.clear()


class Server(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def get_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path == "/":
            page = (BASE / "static" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return

        if self.path.startswith("/api/local-list"):
            try:
                query = parse_qs(urlparse(self.path).query)
                path = query.get("path", [str(PHONE_ROOT)])[0]

                self.send_json({
                    "path": str(Path(path).resolve()),
                    "items": phone_list(path)
                })
            except Exception as error:
                self.send_json({"error": str(error)}, 500)
            return

        if self.path.startswith("/api/list"):
            ftp = None
            try:
                query = parse_qs(urlparse(self.path).query)
                path = query.get("path", ["/"])[0]

                ftp = connect()
                items = list_directory(ftp, path)
                ftp.quit()

                self.send_json({
                    "path": remote_path(path),
                    "items": items
                })
            except Exception as error:
                if ftp:
                    try:
                        ftp.close()
                    except Exception:
                        pass
                self.send_json({"error": str(error)}, 500)
            return

        if self.path == "/api/status":
            with lock:
                result = dict(job)

            total_bytes = result.get("total_bytes", 0)
            transferred = result.get("bytes", 0)
            progress = (
                round(transferred / total_bytes * 100, 1)
                if total_bytes else 0
            )

            result["progress"] = progress
            result["message"] = (
                f'{result["status"].upper()} | '
                f'{result["done"]}/{result["total"]} files | '
                f'{transferred / 1073741824:.2f}/'
                f'{total_bytes / 1073741824:.2f} GB | '
                f'{progress}% | '
                f'{result["speed"] / 1048576:.2f} MB/s | '
                f'{result["current"]}'
            )

            self.send_json(result)
            return

        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        try:
            data = self.get_body()

            if self.path == "/api/config":
                settings.update(data)
                CONFIG.write_text(json.dumps(settings, indent=2))
                self.send_json({"ok": True})
                return

            if self.path == "/api/test":
                ftp = connect()
                welcome = ftp.getwelcome()
                ftp.quit()
                self.send_json({"ok": True, "welcome": welcome})
                return

            if self.path == "/api/upload":
                with lock:
                    if job["status"] in ("connecting", "running"):
                        raise Exception("A transfer is already running.")

                    job["status"] = "connecting"

                stop_event.clear()

                threading.Thread(
                    target=transfer_upload,
                    args=(data["local_path"], data["remote_path"]),
                    daemon=True
                ).start()

                self.send_json({"ok": True})
                return

            if self.path == "/api/stop":
                stop_event.set()
                self.send_json({"ok": True})
                return

            if self.path == "/api/mkdir":
                ftp = connect()
                ftp.mkd(remote_path(data["path"]))
                ftp.quit()
                self.send_json({"ok": True})
                return

            if self.path == "/api/delete":
                ftp = connect()
                path = remote_path(data["path"])

                def remove(item):
                    try:
                        children = list_directory(ftp, item)
                        for child in children:
                            remove(child["path"])
                        ftp.rmd(item)
                    except Exception:
                        ftp.delete(item)

                remove(path)
                ftp.quit()
                self.send_json({"ok": True})
                return

            self.send_json({"error": "Not found"}, 404)

        except Exception as error:
            self.send_json({"error": str(error)}, 500)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("Xbox FTP Manager: http://127.0.0.1:8765")
    print("Phone storage: " + str(PHONE_ROOT))
    print("Press Ctrl+C to stop.")

    ThreadingHTTPServer(
        ("127.0.0.1", 8765),
        Server
    ).serve_forever()
