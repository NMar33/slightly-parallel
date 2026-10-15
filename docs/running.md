# Running Slightly Parallel

You need **Python 3.11+** and **git**. On Debian or Ubuntu also
`sudo apt install python3-venv`. The UI comes built (`frontend/dist`);
**Node 20+** is needed only to rebuild it, which a production start does
whenever Node is on PATH, and for the hot-reload start. `tmux` is optional: with it, the
terminals stay open after a reload or a restart.

```bash
git clone https://github.com/nmar33/slightly-parallel.git slightly-parallel
cd slightly-parallel
./run.sh --prod       # serves everything from http://127.0.0.1:8123
```

The first start takes a minute: it makes the backend's environment (and,
with Node, installs the UI's packages and rebuilds the UI). To work on Slightly Parallel's own
code, `./run.sh` with no flag starts the backend on :8123 and a hot-reload UI
on :5173. On Windows: `sp run --prod` and `sp run`.

When a start fails (a port in use, Node not found), the last line says what to do.

## As a service

One launcher, `sp.py`, on Linux, macOS and Windows (Python 3.11+;
Node 20+ to rebuild the UI). `sp.sh` (Linux, macOS) and `sp.cmd` (Windows) run it;
`run.sh` is `sp.sh run`. In the background, a server that crashes is
restarted:

```bash
./sp.sh up            # prod mode, auto-restarting, in the background
./sp.sh up --dev      # same, with the hot-reload dev pair
./sp.sh status        # supervisor / health / terminal state
./sp.sh logs          # follow the server log
./sp.sh restart       # down, then up in the same mode
./sp.sh down          # stop everything
./sp.sh run [--prod]  # in the foreground; Ctrl+C stops it
./sp.sh terminal on   # switch the embedded terminal on (the same switch as Settings › Terminal)
./sp.sh terminal off
```

On Windows the same commands are `sp up`, `sp status`, … in the
repository folder (Command Prompt or PowerShell).

Configuration, the ports and the network: [configuration.md](configuration.md).
