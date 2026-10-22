"""Optional lifecycle management of a locally launched breeze-server."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class ServerConfig:
    executable: str = 'breeze-server'
    model: str = ''
    host: str = '127.0.0.1'
    port: int = 8080
    webui: bool = False
    cpu: bool = False
    chunk_first: int | None = None  # omitted -> upstream default 4
    chunk_max: int | None = None    # omitted -> upstream default 25
    verbose: bool = False
    voices_dir: str | None = None
    ws_port: int | None = None
    split_chars: int | None = None  # omitted -> upstream default 600
    cors: str | None = None
    no_warmup: bool = False
    startup_timeout: float = 180.0

    def command(self) -> list[str]:
        if not self.model:
            raise ValueError('A GGUF model path is required to launch breeze-server')
        cmd = [self.executable, self.model, '--host', self.host, '--port', str(self.port)]
        for key, flag in [('webui','--webui'), ('cpu','--cpu'),
                          ('verbose','--verbose'), ('no_warmup','--no-warmup')]:
            if getattr(self, key):
                cmd.append(flag)
        for key, flag in [('chunk_first','--chunk-first'), ('chunk_max','--chunk-max'),
                          ('voices_dir','--voices-dir'), ('ws_port','--ws-port'),
                          ('split_chars','--split-chars')]:
            val = getattr(self, key)
            if val is not None:
                cmd.extend([flag, str(val)])
        if self.cors is not None:
            cmd.append('--cors')
            if self.cors:
                cmd.append(self.cors)
        return cmd


class ManagedBreezeServer:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.process: subprocess.Popen | None = None
        if config.host not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Managed server must bind to localhost')

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.config.port}'

    def __enter__(self):
        # Never attach to and later terminate somebody else's server.
        try:
            requests.get(self.url + '/health', timeout=0.5)
        except requests.RequestException:
            pass
        else:
            raise RuntimeError(f'Port {self.config.port} already has an HTTP service; use external mode')
        self.process = subprocess.Popen(self.config.command())
        deadline = time.monotonic() + self.config.startup_timeout
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f'breeze-server exited with code {self.process.returncode}')
                try:
                    r = requests.get(self.url + '/health', timeout=1)
                    if r.ok and r.json().get('status') == 'ok':
                        return self
                except (requests.RequestException, ValueError):
                    pass
                time.sleep(0.4)
            raise TimeoutError('Timed out waiting for breeze-server /health')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
