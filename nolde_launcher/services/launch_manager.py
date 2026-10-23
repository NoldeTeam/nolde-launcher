"""Start installed builds. Uses an argument list and never a shell.

Launching never elevates privileges and never runs anything that the user has
not explicitly asked to start. Only one instance per project is tracked.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..storage.paths import logs_dir
from .install_manager import InstallError, resolve_inside


class LaunchError(RuntimeError):
    pass


class AlreadyRunningError(LaunchError):
    pass


@dataclass(frozen=True)
class LaunchRequest:
    project_id: str
    install_folder: str          # relative to the library directory
    main_executable: str         # relative to the install folder
    launch_args: tuple[str, ...] = ()


def resolve_executable(library_dir: Path, request: LaunchRequest) -> tuple[Path, Path]:
    """Return (executable, working_dir), validating that both are inside the library."""
    install_dir = resolve_inside(library_dir, request.install_folder)
    if not install_dir.is_dir():
        raise LaunchError("the installation folder is missing")
    try:
        exe = resolve_inside(install_dir, request.main_executable)
    except InstallError as exc:
        raise LaunchError("the configured executable path is not allowed") from exc
    if not exe.is_file():
        raise LaunchError("the configured executable was not found; it may have been moved or deleted")
    if sys.platform == "win32" and exe.suffix.lower() != ".exe":
        raise LaunchError("the configured file is not a Windows executable")
    if sys.platform != "win32" and not os.access(exe, os.X_OK):
        raise LaunchError("the configured file is not marked executable")
    return exe, exe.parent


class LaunchManager:
    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen] = {}
        self._started: dict[str, float] = {}
        self._finished: list[tuple[str, float]] = []

    def is_running(self, project_id: str) -> bool:
        proc = self._processes.get(project_id)
        if proc is None:
            return False
        if proc.poll() is None:
            return True
        del self._processes[project_id]
        started = self._started.pop(project_id, None)
        if started is not None:
            self._finished.append((project_id, time.monotonic() - started))
        return False

    def pop_finished_playtime(self) -> list[tuple[str, float]]:
        """Seconds each game ran since the last call. Used to update the library."""
        self.running_ids()  # make sure exited processes have been noticed
        done, self._finished = self._finished, []
        return done

    def running_ids(self) -> list[str]:
        return [pid for pid in list(self._processes) if self.is_running(pid)]

    def launch(self, library_dir: Path, request: LaunchRequest) -> subprocess.Popen:
        if self.is_running(request.project_id):
            raise AlreadyRunningError("this game is already running")
        exe, cwd = resolve_executable(library_dir, request)
        args = [str(exe), *request.launch_args]
        log_path = logs_dir() / f"game-{request.project_id}.log"
        log = open(log_path, "ab")
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                shell=False,
                close_fds=True,
            )
        except OSError as exc:
            raise LaunchError(f"could not start the game: {exc.strerror or exc.__class__.__name__}") from exc
        finally:
            log.close()
        self._processes[request.project_id] = proc
        self._started[request.project_id] = time.monotonic()
        return proc
