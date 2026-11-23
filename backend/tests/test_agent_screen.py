import signal
from pathlib import Path
from types import SimpleNamespace


def test_pty_close_escalates_without_a_blocking_wait(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import screen

    monkeypatch.setattr(screen, "WINDOWS", False)
    instance = screen.Screen.__new__(screen.Screen)
    instance.pid, instance.fd = 82, 12
    signals = []
    closed = []
    def waitpid(pid, flags):
        assert flags == 1
        return (pid, 0) if len(signals) == 2 else (0, 0)

    ticks = iter([0, 30, 30])
    monkeypatch.setattr(screen, "os", SimpleNamespace(kill=lambda pid, sig: signals.append((pid, sig)),
                                                     close=closed.append, waitpid=waitpid, WNOHANG=1))
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(screen, "time", type("Clock", (), {"monotonic": staticmethod(lambda: next(ticks))}))

    instance.close()

    assert signals == [(82, signal.SIGTERM), (82, signal.SIGKILL)]
    assert closed == [12]
