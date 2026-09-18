"""Measure startup/load and gameplay coverage without changing game sources.

Requires Python 3.14+ (sys.monitoring). Run with the project's virtualenv.
Default: a bounded dummy-display run. --interactive records until you quit.
Coverage means observed execution, never proof that unobserved code is redundant.
Saves/preferences are copied to disposable temporary storage; play-session saves
are discarded on exit. Content editor changes are not isolated by this launcher.
"""

from __future__ import annotations

import argparse
import ast
import builtins
from collections import defaultdict
import csv
import dis
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import time
import types


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "environment_sandbox"


def inventory():
    files = {}
    for path in sorted(SOURCE.rglob("*.py")):
        if path.name.startswith("test_") or "_debug" in path.parts:
            continue
        text = path.read_text()
        tree = ast.parse(text)
        executable = set()
        functions = {}
        definitions = {
            (node.name, min([node.lineno, *[d.lineno for d in node.decorator_list]]))
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        def visit(code):
            executable.update(line for _, line in dis.findlinestarts(code) if line and line > 0)
            if (code.co_name, code.co_firstlineno) in definitions:
                functions[(code.co_qualname, code.co_firstlineno)] = code
            for value in code.co_consts:
                if isinstance(value, types.CodeType):
                    visit(value)

        visit(compile(text, str(path), "exec"))
        files[str(path)] = {
            "path": str(path.relative_to(SOURCE)),
            "source_lines": len(text.splitlines()),
            "executable": executable,
            "functions": functions,
        }
    return files


class Recorder:
    def __init__(self, files):
        self.files = files
        self.phase = "startup_load"
        self.lines = defaultdict(set)
        self.functions = defaultdict(set)
        self.tool = sys.monitoring.COVERAGE_ID

    def start(self):
        monitor = sys.monitoring
        monitor.use_tool_id(self.tool, "sim-runtime-audit")

        def entered(code, offset):
            if code.co_filename in self.files:
                self.functions[(self.phase, code.co_filename)].add(
                    (code.co_qualname, code.co_firstlineno)
                )
                monitor.set_local_events(self.tool, code, monitor.events.LINE)
            return monitor.DISABLE

        def line(code, number):
            self.lines[(self.phase, code.co_filename)].add(number)
            return monitor.DISABLE

        monitor.register_callback(self.tool, monitor.events.PY_START, entered)
        monitor.register_callback(self.tool, monitor.events.LINE, line)
        monitor.set_events(self.tool, monitor.events.PY_START)

    def begin_play(self):
        self.phase = "gameplay"
        sys.monitoring.restart_events()

    def stop(self):
        sys.monitoring.clear_tool_id(self.tool)
        sys.monitoring.free_tool_id(self.tool)

    def report(self, output, metadata):
        rows = []
        unseen = []
        for filename, entry in self.files.items():
            executable = entry["executable"]
            startup = self.lines[("startup_load", filename)] & executable
            play = self.lines[("gameplay", filename)] & executable
            called = self.functions[("startup_load", filename)] | self.functions[("gameplay", filename)]
            functions = entry["functions"]
            rows.append({
                "module": entry["path"],
                "source_lines": entry["source_lines"],
                "executable_lines": len(executable),
                "startup_load_lines": len(startup),
                "gameplay_lines": len(play),
                "observed_lines": len(startup | play),
                "observed_percent": round(100 * len(startup | play) / max(1, len(executable)), 1),
                "functions": len(functions),
                "functions_entered": len(set(functions) & called),
            })
            for (name, first_line), code in functions.items():
                if (name, first_line) not in called:
                    unseen.append({"module": entry["path"], "function": name, "line": first_line})
        totals = {key: sum(row[key] for row in rows) for key in (
            "source_lines", "executable_lines", "startup_load_lines", "gameplay_lines",
            "observed_lines", "functions", "functions_entered",
        )}
        totals["modules"] = len(rows)
        totals["modules_observed"] = sum(row["observed_lines"] > 0 for row in rows)
        totals["observed_percent"] = round(100 * totals["observed_lines"] / max(1, totals["executable_lines"]), 1)
        output.mkdir(parents=True, exist_ok=True)
        with (output / "modules.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (output / "coverage.json").write_text(json.dumps({
            "run": metadata, "totals": totals, "modules": rows,
            "unentered_functions": unseen,
            "line_hits": {
                phase: {entry["path"]: sorted(self.lines[(phase, filename)])
                        for filename, entry in self.files.items()}
                for phase in ("startup_load", "gameplay")
            },
        }, indent=2))
        summary = [
            "# Runtime usage observation", "",
            "This measures executed Python code, not the minimum code required to ship the game.",
            "Unobserved code is not established as dead or safe to delete. Imports and startup",
            "are included separately from gameplay. Executable lines are bytecode line-table",
            "locations, not a count of all physical source lines. Test files are excluded.", "",
            "```json", json.dumps(metadata, indent=2), "```", "",
            f"Observed {totals['observed_lines']:,} / {totals['executable_lines']:,} executable lines ({totals['observed_percent']}%).",
            f"Entered {totals['functions_entered']:,} / {totals['functions']:,} declared functions/methods.",
            f"Observed {totals['modules_observed']} / {totals['modules']} non-test modules.", "",
            "| Module | Source lines | Executable | Startup/load | Gameplay | Observed % |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in sorted(rows, key=lambda row: row["source_lines"], reverse=True):
            summary.append(f"| {row['module']} | {row['source_lines']} | {row['executable_lines']} | {row['startup_load_lines']} | {row['gameplay_lines']} | {row['observed_percent']} |")
        (output / "summary.md").write_text("\n".join(summary) + "\n")
        print(json.dumps(totals, indent=2))
        print(f"Reports: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, help="Save to load; defaults to newest world save")
    parser.add_argument("--interactive", action="store_true", help="Use a real window; play until quit")
    parser.add_argument("--frames", type=int, default=180)
    parser.add_argument("--speed", type=int, default=32, choices=(1, 2, 4, 8, 16, 32, 64, 128))
    parser.add_argument("--output", type=Path, default=Path("/tmp/sim-runtime-usage"))
    args = parser.parse_args()
    if sys.version_info < (3, 14):
        parser.error("Python 3.14 or later is required")
    if args.frames < 1:
        parser.error("--frames must be positive")
    save = args.save
    if save is None:
        saves = [p for p in (ROOT / "saves").glob("*.json") if p.name != "balance_prefs.json"]
        save = max(saves, key=lambda path: path.stat().st_mtime)
    save = save.resolve()
    output = args.output.resolve()
    source_data = json.loads(save.read_text())
    if "grid" not in source_data and "tutorial_checkpoint" not in source_data:
        parser.error(f"Not a world save: {save}")
    if not args.interactive:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    sys.path.insert(0, str(SOURCE))
    recorder = Recorder(inventory())
    metadata = {
        "save": str(save), "grid": source_data.get("grid"),
        "buildings": len(source_data.get("buildings", [])),
        "villagers": len(source_data.get("villagers", [])),
        "interactive": args.interactive, "requested_frames": args.frames,
        "speed": args.speed, "frames": 0, "simulation_ticks": 0,
        "status": "incomplete",
    }
    started = time.monotonic()
    original_import = builtins.__import__
    original_argv = sys.argv
    patched = False
    recorder.start()
    try:
        with tempfile.TemporaryDirectory(prefix="sim-usage-saves-") as temp:
            sandbox_saves = Path(temp)
            copied_save = sandbox_saves / save.name
            shutil.copy2(save, copied_save)
            preferences = ROOT / "saves" / "balance_prefs.json"
            if preferences.exists():
                shutil.copy2(preferences, sandbox_saves / preferences.name)

            def importing(name, globals=None, locals=None, fromlist=(), level=0):
                nonlocal patched
                module = original_import(name, globals, locals, fromlist, level)
                if name != "game" or patched or not hasattr(module, "Game"):
                    return module
                patched = True
                builtins.__import__ = original_import
                import save_load

                old_saves_dir = save_load.saves_dir
                for loaded in list(sys.modules.values()):
                    if getattr(loaded, "saves_dir", None) is old_saves_dir:
                        loaded.saves_dir = lambda: sandbox_saves
                init = module.Game.__init__
                draw = module.Game._draw
                advance = module.Game._advance_sim_ticks

                def initialise(game, *a, **kw):
                    init(game, *a, **kw)
                    save_load.load_from_path(game, copied_save)
                    game._last_save_path = copied_save
                    game._loaded_save_name = save.name
                    game._launch_menu = None
                    game._sync_time_knobs_from_clock()
                    game.sim_speed = args.speed
                    metadata["calendar_start"] = game.calendar_day
                    recorder.begin_play()

                def drawing(game, *a, **kw):
                    result = draw(game, *a, **kw)
                    metadata["frames"] += 1
                    metadata["calendar_end"] = game.calendar_day
                    if not args.interactive and metadata["frames"] >= args.frames:
                        game.running = False
                    return result

                def advancing(game, ticks, *a, **kw):
                    result = advance(game, ticks, *a, **kw)
                    if recorder.phase == "gameplay":
                        metadata["simulation_ticks"] += max(0, ticks)
                    return result

                module.Game.__init__ = initialise
                module.Game._draw = drawing
                module.Game._advance_sim_ticks = advancing
                return module

            builtins.__import__ = importing
            sys.argv = [str(SOURCE / "main.py")]
            # Execute the actual entry point, preserving content bootstrap order.
            runpy.run_path(str(SOURCE / "main.py"), run_name="__main__")
            metadata["status"] = "completed"
    finally:
        builtins.__import__ = original_import
        sys.argv = original_argv
        recorder.stop()
        metadata["elapsed_seconds"] = round(time.monotonic() - started, 2)
        recorder.report(output, metadata)


if __name__ == "__main__":
    main()
