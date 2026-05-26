import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import math, os, json

try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class BlockSceneApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Minecraft 3D Scene Builder (Textured)")
        self.geometry("1100x700")

        os.makedirs("./blocks", exist_ok=True)
        os.makedirs("./items",  exist_ok=True)

        self.blocks       = []
        self.current_idx  = None
        self.show_player  = tk.BooleanVar(value=True)

        self.cam_yaw, self.cam_pitch, self.cam_zoom = 45.0, 25.0, 400.0
        self.drag_x = self.drag_y = 0

        self.color_cache = {}   # path → "#rrggbb"  (avg colour fallback)
        self.img_cache   = {}   # path → PIL Image | None
        self.photo       = None # keep PhotoImage alive

        self.setup_ui()
        self.add_block()

        if not HAS_PIL:
            messagebox.showwarning("Pillow Missing",
                "Install Pillow for texture rendering:\n  pip install pillow")
        elif not HAS_NUMPY:
            messagebox.showwarning("NumPy Missing",
                "Install NumPy for texture rendering:\n  pip install numpy\n"
                "Falling back to average-colour preview.")

    # ── UI ────────────────────────────────────────────────────────────────────

    def setup_ui(self):
        self.left_frame   = ttk.Frame(self, width=200, padding="10")
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.center_frame = ttk.Frame(self, padding="10")
        self.center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.right_frame  = ttk.Frame(self, width=350, padding="10")
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(self.left_frame, text="Objects in Scene:").pack(anchor=tk.W)
        self.listbox = tk.Listbox(self.left_frame, height=20, exportselection=False)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.listbox.bind('<<ListboxSelect>>', self.on_list_select)

        bf = ttk.Frame(self.left_frame); bf.pack(fill=tk.X)
        ttk.Button(bf, text="+ Add",  command=self.add_block ).pack(side=tk.LEFT,  expand=True)
        ttk.Button(bf, text="- Del",  command=self.delete_block).pack(side=tk.RIGHT, expand=True)

        ttk.Checkbutton(self.left_frame, text="Show Player",
            variable=self.show_player, command=self.render_scene
        ).pack(pady=10, anchor=tk.W)
        ttk.Button(self.left_frame, text="📦 Export Datapack",
            command=self.export_datapack).pack(fill=tk.X, pady=20)

        ttk.Label(self.center_frame, text="3D Live Preview").pack()
        self.canvas = tk.Canvas(self.center_frame, bg="#2b2b2b")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>",     self.on_mouse_drag)
        self.canvas.bind("<MouseWheel>",    self.on_mouse_scroll)
        self.canvas.bind("<Button-4>",      self.on_mouse_scroll)
        self.canvas.bind("<Button-5>",      self.on_mouse_scroll)
        self.canvas.bind("<Configure>",     lambda e: self.render_scene())

        ttk.Label(self.right_frame, text="ID (e.g. minecraft:stone or beef):").pack(anchor=tk.W)
        self.ent_id = ttk.Entry(self.right_frame)
        self.ent_id.pack(fill=tk.X, pady=(0, 10))
        self.ent_id.bind("<KeyRelease>", lambda e: self.update_block_data())

        self.pos_x   = self._slider("Pos X",   -10.0, 10.0,  0.0)
        self.pos_y   = self._slider("Pos Y",    -5.0, 15.0,  0.0)
        self.pos_z   = self._slider("Pos Z",   -10.0, 10.0,  0.0)
        self.scl_x   = self._slider("Scale X",   0.1, 10.0,  1.0)
        self.scl_y   = self._slider("Scale Y",   0.1, 10.0,  1.0)
        self.scl_z   = self._slider("Scale Z",   0.1, 10.0,  1.0)
        self.rot_yaw   = self._slider("Yaw",   -180, 180, 0)
        self.rot_pitch = self._slider("Pitch",   -90,  90, 0)

    def _slider(self, label, lo, hi, default):
        f = ttk.Frame(self.right_frame); f.pack(fill=tk.X, pady=2)
        ttk.Label(f, text=label, width=10).pack(side=tk.LEFT)
        vsld = tk.DoubleVar(value=default)
        vtxt = tk.StringVar(value=f"{default:.2f}")
        def on_sld(*_): vtxt.set(f"{vsld.get():.2f}"); self.update_block_data()
        def on_txt(*_):
            try: vsld.set(float(vtxt.get())); self.update_block_data()
            except ValueError: pass
        ttk.Scale(f, from_=lo, to=hi, variable=vsld,
                  command=on_sld).pack(side=tk.LEFT, fill=tk.X, expand=True)
        e = ttk.Entry(f, textvariable=vtxt, width=7); e.pack(side=tk.RIGHT)
        e.bind("<KeyRelease>", on_txt)
        return {"slider": vsld, "text": vtxt}

    # ── Camera / mouse ────────────────────────────────────────────────────────

    def on_mouse_down(self, e): self.drag_x, self.drag_y = e.x, e.y
    def on_mouse_drag(self, e):
        self.cam_yaw  -= (e.x - self.drag_x) * 0.5
        self.cam_pitch = max(-89.0, min(89.0, self.cam_pitch + (e.y - self.drag_y) * 0.5))
        self.drag_x, self.drag_y = e.x, e.y
        self.render_scene()
    def on_mouse_scroll(self, e):
        self.cam_zoom *= 1.15 if (e.num == 4 or getattr(e, "delta", 0) > 0) else (1/1.15)
        self.cam_zoom  = max(50.0, min(3000.0, self.cam_zoom))
        self.render_scene()

    # ── Block list ────────────────────────────────────────────────────────────

    def add_block(self):
        b = dict(name=f"Obj_{len(self.blocks)+1}", id="minecraft:stone",
                 px=0.0, py=0.0, pz=0.0, sx=1.0, sy=1.0, sz=1.0,
                 yaw=0.0, pitch=0.0)
        self.blocks.append(b)
        self.listbox.insert(tk.END, b["name"])
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(tk.END)
        self.on_list_select(None)

    def delete_block(self):
        if self.current_idx is None: return
        del self.blocks[self.current_idx]
        self.listbox.delete(self.current_idx)
        self.current_idx = None
        if self.blocks: self.listbox.selection_set(0); self.on_list_select(None)
        else: self.render_scene()

    def on_list_select(self, _):
        if not self.listbox.curselection(): return
        self.current_idx = self.listbox.curselection()[0]
        b = self.blocks[self.current_idx]
        self.ent_id.delete(0, tk.END); self.ent_id.insert(0, b["id"])
        for k in ("px","py","pz","sx","sy","sz","yaw","pitch"):
            ui = getattr(self,
                "pos_"+k[-1]  if k[0]=="p" and len(k)==2 else
                "scl_"+k[-1]  if k[0]=="s" else
                "rot_"+k)
            ui["slider"].set(b[k]); ui["text"].set(f"{b[k]:.2f}")
        self.render_scene()

    def update_block_data(self):
        if self.current_idx is None: return
        b = self.blocks[self.current_idx]
        b["id"] = self.ent_id.get()
        for k in ("px","py","pz","sx","sy","sz","yaw","pitch"):
            ui = getattr(self,
                "pos_"+k[-1]  if k[0]=="p" and len(k)==2 else
                "scl_"+k[-1]  if k[0]=="s" else
                "rot_"+k)
            b[k] = ui["slider"].get()
        self.listbox.delete(self.current_idx)
        self.listbox.insert(self.current_idx,
                            f"{b['name']} ({b['id'].split(':')[-1]})")
        self.listbox.selection_set(self.current_idx)
        self.render_scene()

    # ── Texture loading ───────────────────────────────────────────────────────

    def load_img(self, path):
        """Return cached PIL Image (RGBA) or None."""
        if not HAS_PIL: return None
        if path not in self.img_cache:
            try:    self.img_cache[path] = Image.open(path).convert("RGBA")
            except: self.img_cache[path] = None
        return self.img_cache[path]

    def avg_color(self, img_or_path):
        """Return '#rrggbb' average colour from a PIL Image or file path."""
        if not HAS_PIL: return "#909090"
        if isinstance(img_or_path, str):
            if img_or_path in self.color_cache: return self.color_cache[img_or_path]
            img = self.load_img(img_or_path)
        else:
            img = img_or_path
        if img is None: return "#909090"
        tiny = img.resize((1, 1), Image.Resampling.LANCZOS)
        col  = "#{:02x}{:02x}{:02x}".format(*tiny.getpixel((0, 0)))
        if isinstance(img_or_path, str): self.color_cache[img_or_path] = col
        return col

    def check_local_textures(self, bid):
        """Return (display_type, materials[]) where each material is
        a PIL Image (textures found) or a '#rrggbb' string (fallback)."""
        base = bid.replace("minecraft:", "")

        # ── items/ folder → item_display ──
        item_path = f"./items/{base}.png"
        if os.path.exists(item_path):
            img = self.load_img(item_path)
            mat = img if img else (self.avg_color(item_path) or "#ff00ff")
            return "item_display", [mat, mat]

        # ── blocks/ folder → block_display ──
        side_img = self.load_img(f"./blocks/{base}_side.png")
        top_img  = self.load_img(f"./blocks/{base}_top.png")
        bot_img  = self.load_img(f"./blocks/{base}_bottom.png")
        base_img = self.load_img(f"./blocks/{base}.png")

        if any([side_img, top_img, base_img]):
            side = side_img or base_img
            top  = top_img  or base_img
            bot  = bot_img  or top
            # face order: front, back, left, right, bottom, top
            return "block_display", [side, side, side, side, bot, top]

        # ── built-in colour fallbacks ──
        if "grass_block" in bid: return "block_display", ["#866043"]*4 + ["#866043","#559c3e"]
        if "log"         in bid: return "block_display", ["#8f7040"]*4 + ["#a2875b","#a2875b"]
        if any(x in bid for x in ("sword","beef","apple")):
            return "item_display", ["#ff5555","#ff5555"]
        return "block_display", ["#a0a0a0"]*6

    # ── 3-D geometry ──────────────────────────────────────────────────────────

    def rotate_3d(self, x, y, z, ax, ay):
        rx, ry = math.radians(ax), math.radians(ay)
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        y1, z1 = y*cx - z*sx, y*sx + z*cx
        return x*cy + z1*sy, y1, -x*sy + z1*cy

    def create_faces(self, b, c_type, materials):
        """Return [(depth, screen_pts, material, shade), ...]"""
        cw = max(self.canvas.winfo_width()  / 2, 250)
        ch = max(self.canvas.winfo_height() / 2, 250)

        if c_type == "item_display":
            verts  = [[-0.5,0,0],[0.5,0,0],[0.5,1,0],[-0.5,1,0]]
            faces  = [(0,1,2,3),(3,2,1,0)]
            shades = [1.0, 0.8]
        else:
            verts  = [[-0.5,0,-0.5],[0.5,0,-0.5],[0.5,1,-0.5],[-0.5,1,-0.5],
                      [-0.5,0, 0.5],[0.5,0, 0.5],[0.5,1, 0.5],[-0.5,1, 0.5]]
            faces  = [(0,1,2,3),(5,4,7,6),(4,0,3,7),(1,5,6,2),(4,5,1,0),(3,2,6,7)]
            shades = [0.8, 0.7, 0.6, 0.6, 0.4, 1.0]

        out = []
        for i, f_idx in enumerate(faces):
            tv = []
            for vi in f_idx:
                x = verts[vi][0] * b["sx"]
                y = verts[vi][1] * b["sy"]
                z = verts[vi][2] * b["sz"]
                x, y, z = self.rotate_3d(x, y - b["sy"]/2, z, b["pitch"], -b["yaw"])
                x, y, z = self.rotate_3d(x + b["px"],
                                         (y + b["sy"]/2) + b["py"],
                                         z + b["pz"],
                                         self.cam_pitch, self.cam_yaw)
                tv.append((cw + (x/(z+12))*self.cam_zoom,
                           ch - (y/(z+12))*self.cam_zoom,
                           z + 12))
            depth = sum(v[2] for v in tv) / len(tv)
            pts   = [(v[0], v[1]) for v in tv]
            out.append((depth, pts, materials[i], shades[i]))
        return out

    # ── Rendering ─────────────────────────────────────────────────────────────

    @staticmethod
    def _hex_shade(hx, shade):
        r = max(0, min(255, int(int(hx[1:3],16) * shade)))
        g = max(0, min(255, int(int(hx[3:5],16) * shade)))
        b = max(0, min(255, int(int(hx[5:7],16) * shade)))
        return (r, g, b)

    def _draw_face(self, scene, pts, material, shade):
        """Rasterise one face (textured or solid) into the H×W×3 uint8 array.
        Textures are RGBA – transparent pixels are skipped, semi-transparent
        pixels are alpha-blended against whatever is already in the scene."""
        H, W = scene.shape[:2]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        x0 = max(0, int(min(xs)));      y0 = max(0, int(min(ys)))
        x1 = min(W, int(max(xs)) + 1); y1 = min(H, int(max(ys)) + 1)
        rw, rh = x1-x0, y1-y0
        if rw <= 0 or rh <= 0: return

        # Polygon mask for this bounding-box region
        mask_pil = Image.new("L", (rw, rh), 0)
        ImageDraw.Draw(mask_pil).polygon(
            [(p[0]-x0, p[1]-y0) for p in pts], fill=255)
        poly_mask = np.array(mask_pil, dtype=bool)
        if not poly_mask.any(): return

        region = scene[y0:y1, x0:x1]

        if isinstance(material, Image.Image):
            # ── Perspective-correct texture mapping (RGBA) ───────────────────
            tex_f32 = np.array(material, dtype=np.float32)   # H×W×4
            th, tw  = tex_f32.shape[:2]

            # Shade only the RGB channels; preserve alpha as-is
            tex_rgb = np.clip(tex_f32[:,:,:3] * shade, 0, 255).astype(np.uint8)
            tex_a   = tex_f32[:,:,3].astype(np.uint8)         # 0-255 alpha

            # Map screen quad corners → texture pixel corners:
            #   pts[0]=bottom-left→(0,th-1)  pts[1]=bottom-right→(tw-1,th-1)
            #   pts[2]=top-right  →(tw-1,0)  pts[3]=top-left    →(0,   0   )
            scr = np.array(pts,                                    dtype=np.float64)
            uv  = np.array([[0,th-1],[tw-1,th-1],[tw-1,0],[0,0]], dtype=np.float64)

            # Solve 8-parameter homography:  screen (x,y) → texture (u,v)
            A  = np.zeros((8, 8)); bv = np.zeros(8)
            for k in range(4):
                sx, sy = scr[k]; u, v = uv[k]
                A[2*k]   = [sx, sy, 1,  0,  0, 0, -sx*u, -sy*u]
                A[2*k+1] = [ 0,  0, 0, sx, sy, 1, -sx*v, -sy*v]
                bv[2*k] = u; bv[2*k+1] = v
            try:
                a, b_, c, d, e, f, g, hc = np.linalg.solve(A, bv)
            except np.linalg.LinAlgError:
                return  # degenerate (edge-on face)

            gx, gy = np.meshgrid(
                np.arange(x0, x1, dtype=np.float64),
                np.arange(y0, y1, dtype=np.float64))
            den = g*gx + hc*gy + 1.0
            den = np.where(np.abs(den) < 1e-10, 1e-10, den)
            ui = np.clip((a*gx + b_*gy + c) / den, 0, tw-1).astype(np.int32)
            vi = np.clip((d*gx +  e*gy + f) / den, 0, th-1).astype(np.int32)

            # Per-pixel alpha: combine polygon mask with texture alpha
            sampled_a   = tex_a  [vi, ui]                      # (rh,rw)
            sampled_rgb = tex_rgb[vi, ui]                       # (rh,rw,3)

            # Pixels that are inside the polygon AND not fully transparent
            draw_mask = poly_mask & (sampled_a > 0)
            if not draw_mask.any(): return

            # Alpha-blend: out = src*α + dst*(1-α)
            a_f   = sampled_a[draw_mask].astype(np.float32) / 255.0   # (N,)
            src   = sampled_rgb[draw_mask].astype(np.float32)          # (N,3)
            dst   = region[draw_mask].astype(np.float32)               # (N,3)
            region[draw_mask] = (src * a_f[:,None] + dst * (1.0 - a_f[:,None])).astype(np.uint8)

        else:
            # ── Solid shaded colour (player parts, fallback) ─────────────────
            region[poly_mask] = self._hex_shade(material, shade)

    def render_scene(self):
        self.canvas.delete("all")
        W = max(self.canvas.winfo_width(),  100)
        H = max(self.canvas.winfo_height(), 100)

        # Collect all faces
        faces = []
        for b in self.blocks:
            e_type, mats = self.check_local_textures(b["id"])
            faces.extend(self.create_faces(b, e_type, mats))

        if self.show_player.get():
            # Each tuple: (px, py, pz, sx, sy, sz, col, front_col)
            # front_col is applied to the front face (index 0) of the head only;
            # None means all faces share the same col (legs, torso).
            # Face order from create_faces: front, back, left, right, bottom, top
            player_parts = [
                (0, 0.00, 0, 0.4, 0.70, 0.25, "#211570", None),    # legs
                (0, 0.70, 0, 0.4, 0.75, 0.25, "#00a8a8", None),    # torso
                (0, 1.45, 0, 0.4, 0.40, 0.40, "#e3ab88", "#5c2a10"), # head
            ]
            for px, py, pz, sx, sy, sz, col, front_col in player_parts:
                pb = dict(px=px, py=py, pz=pz, sx=sx, sy=sy, sz=sz, yaw=0, pitch=0)
                # Front face gets the darker face colour; all others use the body colour
                mats = ([front_col, col, col, col, col, col]
                        if front_col else [col] * 6)
                faces.extend(self.create_faces(pb, "block_display", mats))

        faces.sort(key=lambda f: f[0], reverse=True)   # painter's algorithm

        # ── Full-PIL+NumPy path: actual texture mapping ──────────────────────
        if HAS_PIL and HAS_NUMPY:
            scene = np.full((H, W, 3), (43, 43, 43), dtype=np.uint8)

            for _depth, pts, mat, shade in faces:
                self._draw_face(scene, pts, mat, shade)

            # Draw thin outlines over everything
            pil_img = Image.fromarray(scene)
            draw    = ImageDraw.Draw(pil_img)
            for _, pts, _, _ in faces:
                if len(pts) >= 3:
                    draw.polygon(pts, outline=(17, 17, 17))

            self.photo = ImageTk.PhotoImage(pil_img)
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

        # ── Fallback: tkinter canvas with average colours ────────────────────
        else:
            for _depth, pts, mat, shade in faces:
                if HAS_PIL and isinstance(mat, Image.Image):
                    hx = self.avg_color(mat)
                elif isinstance(mat, str):
                    hx = mat
                else:
                    hx = "#909090"
                r, g, b = self._hex_shade(hx, shade)
                self.canvas.create_polygon(
                    pts, fill=f"#{r:02x}{g:02x}{b:02x}", outline="#111", width=1)

        self.canvas.create_text(
            10, 10, anchor=tk.NW, fill="#aaa",
            text="Drag to Orbit | Scroll to Zoom | PNGs → ./blocks/ or ./items/")

    # ── Export ────────────────────────────────────────────────────────────────

    def export_datapack(self):
        if not self.blocks:
            return messagebox.showerror("Error", "No objects to export!")
        folder = filedialog.askdirectory(title="Save Datapack")
        if not folder: return

        func_dir = os.path.join(folder, "ScenePack", "data", "scene", "functions")
        os.makedirs(func_dir, exist_ok=True)

        with open(os.path.join(folder, "ScenePack", "pack.mcmeta"), "w") as f:
            json.dump({"pack": {"pack_format": 15, "description": "Custom Scene"}},
                      f, indent=4)

        cmds = ["# Generated Scene\n"]
        for b in self.blocks:
            e_type, _ = self.check_local_textures(b["id"])
            trans = (f"transformation:{{translation:[0f,0f,0f],"
                     f"scale:[{b['sx']}f,{b['sy']}f,{b['sz']}f],"
                     f"left_rotation:[0f,0f,0f,1f],"
                     f"right_rotation:[0f,0f,0f,1f]}}")
            if e_type == "item_display":
                nbt = (f'{{item:{{id:"{b["id"]}",Count:1b}},'
                       f'{trans},Rotation:[{b["yaw"]}f,{b["pitch"]}f]}}')
            else:
                nbt = (f'{{block_state:{{Name:"{b["id"]}"}},'
                       f'{trans},Rotation:[{b["yaw"]}f,{b["pitch"]}f]}}')
            cmds.append(f"summon {e_type} ~{b['px']} ~{b['py']} ~{b['pz']} {nbt}\n")

        with open(os.path.join(func_dir, "spawn.mcfunction"), "w") as f:
            f.writelines(cmds)
        self.clipboard_clear()
        self.clipboard_append("/function scene:spawn")
        messagebox.showinfo("Success",
            "Datapack exported!\nRun command copied to clipboard.")


if __name__ == "__main__":
    BlockSceneApp().mainloop()