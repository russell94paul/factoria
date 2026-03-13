import socket
import time


def wait_for_gateway(host: str = "openclaw", port: int = 18789, delay: float = 2.0):
	while True:
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
			sock.settimeout(2)
			try:
				sock.connect((host, port))
			except OSError:
				print("Waiting for OpenClaw...", flush=True)
				time.sleep(delay)
			else:
				print("OpenClaw gateway is up.")
				return

if __name__ == "__main__":
    wait_for_gateway()