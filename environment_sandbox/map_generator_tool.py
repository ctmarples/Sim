#!/usr/bin/env python3
"""Interactive random map generator. Run: ``python map_generator_tool.py``."""

from __future__ import annotations

import random
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from random_map_generator import CLIMATES, COMPOSITIONS, TERRAINS, MapOptions, generate_map


COLOURS = {
    "water": "#367f9c", "grass": "#75994d", "meadow": "#91b85b",
    "soil": "#876647", "forest": "#365f37", "rock": "#77746e",
    "riparian": "#4c845b",
}


class MapGeneratorTool:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Sim — Random Map Generator")
        root.minsize(900, 650)
        self.generated = None
        self.vars = {
            "width": tk.IntVar(value=96), "height": tk.IntVar(value=72),
            "seed": tk.IntVar(value=random.randrange(1, 999999)),
            "composition": tk.StringVar(value="valley"),
            "climate": tk.StringVar(value="temperate"),
            "temperature": tk.DoubleVar(value=.5), "rainfall": tk.DoubleVar(value=.55),
            "roughness": tk.DoubleVar(value=.5),
        }
        defaults = MapOptions().terrain_mix
        self.mix = {name: tk.DoubleVar(value=defaults[name] * 100) for name in TERRAINS}
        self._build()
        self.generate()

    def _build(self) -> None:
        controls = ttk.Frame(self.root, padding=12)
        controls.pack(side="left", fill="y")
        preview = ttk.Frame(self.root, padding=(0, 12, 12, 12))
        preview.pack(side="right", fill="both", expand=True)
        ttk.Label(controls, text="Random map", font=("TkDefaultFont", 16, "bold")).pack(anchor="w", pady=(0, 10))
        grid = ttk.Frame(controls); grid.pack(fill="x")
        for row, key in enumerate(("width", "height", "seed")):
            ttk.Label(grid, text=key.title()).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(grid, textvariable=self.vars[key], width=12).grid(row=row, column=1, sticky="ew", padx=(8, 0))
        for label, key, values in (("Composition", "composition", COMPOSITIONS), ("Climate", "climate", CLIMATES)):
            ttk.Label(controls, text=label).pack(anchor="w", pady=(10, 2))
            ttk.Combobox(controls, textvariable=self.vars[key], values=values, state="readonly", width=20).pack(fill="x")
        ttk.Label(controls, text="Climate controls", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(14, 4))
        for key in ("temperature", "rainfall", "roughness"):
            ttk.Label(controls, text=key.title()).pack(anchor="w")
            ttk.Scale(controls, from_=0, to=1, variable=self.vars[key]).pack(fill="x")
        ttk.Label(controls, text="Terrain mix (%)", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(14, 4))
        for name in TERRAINS:
            row = ttk.Frame(controls); row.pack(fill="x")
            ttk.Label(row, text=name.title(), width=9).pack(side="left")
            ttk.Scale(row, from_=0, to=60, variable=self.mix[name]).pack(side="left", fill="x", expand=True)
            ttk.Label(row, textvariable=self.mix[name], width=5).pack(side="right")
        buttons = ttk.Frame(controls); buttons.pack(fill="x", pady=(16, 0))
        ttk.Button(buttons, text="Generate", command=self.generate).pack(side="left", expand=True, fill="x")
        ttk.Button(buttons, text="New seed", command=self.new_seed).pack(side="left", expand=True, fill="x", padx=5)
        ttk.Button(buttons, text="Export JSON", command=self.export).pack(side="left", expand=True, fill="x")
        self.summary = ttk.Label(preview, text=""); self.summary.pack(anchor="w", pady=(0, 6))
        self.canvas = tk.Canvas(preview, background="#20252a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw())

    def options(self) -> MapOptions:
        return MapOptions(
            width=self.vars["width"].get(), height=self.vars["height"].get(), seed=self.vars["seed"].get(),
            composition=self.vars["composition"].get(), climate=self.vars["climate"].get(),
            temperature=self.vars["temperature"].get(), rainfall=self.vars["rainfall"].get(),
            roughness=self.vars["roughness"].get(),
            terrain_mix={name: self.mix[name].get() for name in TERRAINS},
        )

    def generate(self) -> None:
        try:
            self.generated = generate_map(self.options())
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Cannot generate map", str(exc)); return
        counts = self.generated.counts(); total = sum(counts.values())
        self.summary.configure(text="  ".join(f"{name.title()} {counts[name]/total:.0%}" for name in TERRAINS))
        self.draw()

    def new_seed(self) -> None:
        self.vars["seed"].set(random.randrange(1, 999999999)); self.generate()

    def draw(self) -> None:
        if not self.generated: return
        self.canvas.delete("all")
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        cols, rows = self.generated.options.width, self.generated.options.height
        scale = min(cw / cols, ch / rows); ox = (cw-cols*scale)/2; oy = (ch-rows*scale)/2
        for y, row in enumerate(self.generated.terrain):
            for x, terrain in enumerate(row):
                self.canvas.create_rectangle(ox+x*scale, oy+y*scale, ox+(x+1)*scale+1, oy+(y+1)*scale+1,
                                             fill=COLOURS[terrain], outline="")

    def export(self) -> None:
        if not self.generated: return
        default = f"map_{self.generated.options.seed}.json"
        export_dir = Path(__file__).resolve().parent / "generated_maps"
        export_dir.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(initialdir=export_dir,
                                            initialfile=default, defaultextension=".json",
                                            filetypes=(("Map JSON", "*.json"),))
        if path:
            self.generated.save(path); messagebox.showinfo("Map exported", f"Saved {path}")


def main() -> None:
    root = tk.Tk(); MapGeneratorTool(root); root.mainloop()


if __name__ == "__main__":
    main()
