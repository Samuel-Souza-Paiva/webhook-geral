import os
import sys
import time
import signal
import subprocess
import threading
import webbrowser
from urllib.request import urlopen
from typing import List

ROOT = os.path.dirname(os.path.abspath(__file__))

# Commands to start backend and frontend; adjust as needed
BACKEND_CMD = ["python", "-m", "http.server", "666"]
FRONTEND_CMD = ["python", "-m", "http.server", "8080"]

procs: List[subprocess.Popen] = []


def stream(name: str, p: subprocess.Popen) -> None:
	"""Read process stdout and print labeled lines."""
	if p.stdout is None:
		return
	for raw in iter(p.stdout.readline, b""):
		try:
			line = raw.decode(errors="replace").rstrip()
		except Exception:
			line = str(raw)
		print(f"[{name}] {line}")


def start(cmd, name):
	p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	t = threading.Thread(target=stream, args=(name, p), daemon=True)
	t.start()
	procs.append(p)
	return p


def wait_http(url: str, timeout: int = 45) -> bool:
	end = time.time() + timeout
	while time.time() < end:
		try:
			with urlopen(url, timeout=2):
				return True
		except Exception:
			time.sleep(0.3)
	return False


def shutdown(*_):
	print("Encerrando...")
	for p in procs:
		if p.poll() is None:
			p.terminate()
	time.sleep(1.2)
	for p in procs:
		if p.poll() is None:
			p.kill()
	sys.exit(0)


if __name__ == "__main__":
	signal.signal(signal.SIGINT, shutdown)
	try:
		signal.signal(signal.SIGTERM, shutdown)
	except Exception:
		pass

	print("Iniciando backend (666) e frontend (8080)...")
	start(BACKEND_CMD, "backend")
	start(FRONTEND_CMD, "frontend")

	# Abre o navegador quando o frontend responder
	url = "http://127.0.0.1:8080/"
	if wait_http(url, 45):
		try:
			if sys.platform.startswith("win"):
				os.startfile(url)  # melhor no Windows
			else:
				webbrowser.open_new_tab(url)
		except Exception:
			webbrowser.open_new_tab(url)
	else:
		print("Aviso: frontend não respondeu a tempo; acesse manualmente:", url)

	# Mantém vivo enquanto os processos estiverem rodando
	while any(p.poll() is None for p in procs):
		time.sleep(0.5)