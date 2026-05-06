import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pathlib import Path

from collections import Counter

import config
from scanner import scan, extract_code
from fetcher import Fetcher
from renamer import build_filename, rename_file, write_processed_log

SCRIPT_DIR = Path(__file__).parent
LABELS = {"code": "番號", "actress": "女優名", "title": "片名"}
KEYS = {"番號": "code", "女優名": "actress", "片名": "title"}
CHECK_ON  = "☑"
CHECK_OFF = "☐"


class AVRenameApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AV Code Rename")
        self.root.resizable(True, True)

        self.msg_queue: queue.Queue = queue.Queue()
        self._pending: list = []
        self._skipped: list = []
        self._item_map: dict = {}
        self._mode = tk.StringVar(value="folder")
        self._selected_files: list = []
        self._review_win = None

        self._cfg = config.load()
        self._format_order: list = self._cfg.get("format_order", ["code", "actress", "title"])

        self._build_ui()
        self._poll_queue()

    # ── UI 建立 ──────────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}

        # 目標資料夾
        frame_dir = ttk.LabelFrame(self.root, text=" 目標資料夾 ", padding=8)
        frame_dir.grid(row=0, column=0, sticky="ew", **pad)
        frame_dir.columnconfigure(1, weight=1)

        ttk.Radiobutton(frame_dir, text="整個資料夾", variable=self._mode,
                        value="folder", command=self._on_mode_change).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Radiobutton(frame_dir, text="選擇檔案", variable=self._mode,
                        value="files", command=self._on_mode_change).grid(
            row=0, column=1, sticky="w")

        self.dir_var = tk.StringVar(value=self._cfg.get("target_dir", ""))
        self.entry_dir = ttk.Entry(frame_dir, textvariable=self.dir_var, width=52)
        self.entry_dir.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(frame_dir, text="瀏覽", command=self._browse).grid(
            row=1, column=2, padx=(6, 0), pady=(6, 0))

        # 命名格式
        frame_fmt = ttk.LabelFrame(self.root, text=" 命名格式順序 ", padding=8)
        frame_fmt.grid(row=1, column=0, sticky="ew", **pad)
        self.fmt_list = tk.Listbox(frame_fmt, height=3, selectmode="single",
                                   width=16, font=("", 10))
        for key in self._format_order:
            self.fmt_list.insert("end", LABELS[key])
        self.fmt_list.grid(row=0, column=0, rowspan=2, sticky="ns")
        self.fmt_list.selection_set(0)
        ttk.Button(frame_fmt, text="↑", width=4, command=self._move_up).grid(
            row=0, column=1, padx=8, pady=(4, 2))
        ttk.Button(frame_fmt, text="↓", width=4, command=self._move_down).grid(
            row=1, column=1, padx=8, pady=(2, 4))

        # 開始按鈕
        frame_btn = tk.Frame(self.root)
        frame_btn.grid(row=2, column=0, pady=6)
        self.btn_start = ttk.Button(frame_btn, text="▶  開始掃描",
                                    command=self._start, width=22)
        self.btn_start.pack(ipady=6)

        # 進度區
        frame_prog = ttk.LabelFrame(self.root, text=" 處理進度 ", padding=8)
        frame_prog.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.lbl_progress = ttk.Label(frame_prog, text="等待開始...")
        self.lbl_progress.pack(anchor="w")
        self.progress_bar = ttk.Progressbar(frame_prog, mode="indeterminate", length=420)
        self.progress_bar.pack(fill="x", pady=(4, 6))
        self.log_text = scrolledtext.ScrolledText(
            frame_prog, width=62, height=6, state="disabled", font=("Consolas", 9)
        )
        self.log_text.pack(fill="x")

        # 查詢完畢後的動作列（初始隱藏）
        self.frame_action = tk.Frame(self.root)
        self.frame_action.grid(row=4, column=0, pady=(0, 12))
        self.btn_open_review = ttk.Button(
            self.frame_action, text="📋  開啟審閱清單",
            command=self._open_review_window, width=22)
        self.btn_cancel = ttk.Button(
            self.frame_action, text="✖  取消",
            command=self._cancel, width=12)

        self.root.columnconfigure(0, weight=1)

    # ── UI 互動 ──────────────────────────────────────────────

    def _on_mode_change(self):
        if self._mode.get() == "folder":
            self.entry_dir.config(state="normal")
            self.dir_var.set(self._cfg.get("target_dir", ""))
            self._selected_files = []
        else:
            self.entry_dir.config(state="readonly")
            self.dir_var.set("（尚未選擇檔案）")
            self._selected_files = []

    def _browse(self):
        if self._mode.get() == "folder":
            d = filedialog.askdirectory()
            if d:
                self.dir_var.set(d)
        else:
            FILETYPES = [("影片檔案", "*.mp4 *.webm *.srt"), ("所有檔案", "*.*")]
            paths = filedialog.askopenfilenames(filetypes=FILETYPES)
            if paths:
                self._selected_files = [Path(p) for p in paths]
                self.entry_dir.config(state="normal")
                self.dir_var.set(f"已選擇 {len(self._selected_files)} 個檔案")
                self.entry_dir.config(state="readonly")

    def _move_up(self):
        sel = self.fmt_list.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        val = self.fmt_list.get(i)
        self.fmt_list.delete(i)
        self.fmt_list.insert(i - 1, val)
        self.fmt_list.selection_set(i - 1)
        self._save_fmt()

    def _move_down(self):
        sel = self.fmt_list.curselection()
        if not sel or sel[0] == self.fmt_list.size() - 1:
            return
        i = sel[0]
        val = self.fmt_list.get(i)
        self.fmt_list.delete(i)
        self.fmt_list.insert(i + 1, val)
        self.fmt_list.selection_set(i + 1)
        self._save_fmt()

    def _save_fmt(self):
        self._format_order = [KEYS[self.fmt_list.get(i)]
                               for i in range(self.fmt_list.size())]
        cfg = config.load()
        cfg["format_order"] = self._format_order
        config.save(cfg)

    # ── 審閱清單視窗 ──────────────────────────────────────────

    def _open_review_window(self):
        if self._review_win and self._review_win.winfo_exists():
            self._review_win.lift()
            return

        win = tk.Toplevel(self.root)
        win.title(f"審閱清單 — {len(self._pending)} 筆可改名")
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", self._close_review)
        self._review_win = win

        # 定位到主視窗右側
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() + 10
        y = self.root.winfo_y()
        win.geometry(f"720x540+{x}+{y}")

        # 重複番號警告條（若有）
        dup_count = sum(1 for _, _, is_dup in self._pending if is_dup)
        if dup_count > 0:
            warn_frame = tk.Frame(win, bg="#FFF3CD", pady=4)
            warn_frame.pack(fill="x", padx=8, pady=(8, 0))
            tk.Label(
                warn_frame,
                text=f"⚠  發現 {dup_count} 個重複番號，已自動加編號（可雙擊新檔名欄修改）",
                bg="#FFF3CD", fg="#856404", padx=8,
            ).pack(anchor="w")

        # Treeview
        tree_frame = tk.Frame(win)
        tree_frame.pack(fill="both", expand=True, padx=8,
                        pady=(4 if dup_count > 0 else 8, 0))

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("check", "old", "new"),
            show="headings",
            selectmode="none",
            height=20,
        )
        self.tree.heading("check", text="✔")
        self.tree.heading("old",   text="原始檔名")
        self.tree.heading("new",   text="新檔名")
        self.tree.column("check", width=32,  stretch=False, anchor="center")
        self.tree.column("old",   width=300, stretch=True)
        self.tree.column("new",   width=360, stretch=True)
        self.tree.tag_configure("duplicate", background="#FFF3CD")
        self.tree.bind("<Button-1>", self._toggle_check)
        self.tree.bind("<Double-1>", self._start_edit)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 填入資料
        self._item_map = {}
        for src, new_name, is_dup in self._pending:
            tags = ("duplicate",) if is_dup else ()
            iid  = self.tree.insert("", "end", values=(CHECK_ON, src.name, new_name), tags=tags)
            self._item_map[iid] = (src, new_name)

        # 全選/全不選
        btn_row = tk.Frame(win)
        btn_row.pack(anchor="w", padx=8, pady=(6, 0))
        ttk.Button(btn_row, text="全選",   command=self._select_all,   width=8).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="全不選", command=self._deselect_all, width=8).pack(side="left")
        self.lbl_checked = ttk.Label(btn_row, text="")
        self.lbl_checked.pack(side="left", padx=12)
        self._update_checked_label()

        # 確認/關閉
        btn_bottom = tk.Frame(win)
        btn_bottom.pack(pady=(8, 12))
        self.btn_confirm = ttk.Button(btn_bottom, text="✔  確認改名",
                                      command=self._confirm, width=18)
        self.btn_confirm.pack(side="left", padx=(0, 8), ipady=4)
        ttk.Button(btn_bottom, text="✖  關閉",
                   command=self._close_review, width=12).pack(side="left", ipady=4)

    def _close_review(self):
        if self._review_win and self._review_win.winfo_exists():
            self._review_win.destroy()
        self._review_win = None

    # ── 審閱清單操作 ─────────────────────────────────────────

    def _toggle_check(self, event):
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or col != "#1":
            return
        current = self.tree.set(iid, "check")
        self.tree.set(iid, "check", CHECK_OFF if current == CHECK_ON else CHECK_ON)
        self._update_checked_label()

    def _start_edit(self, event):
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or col != "#3":
            return
        bbox = self.tree.bbox(iid, "new")
        if not bbox:
            return
        x, y, w, h = bbox
        val = self.tree.set(iid, "new")
        var = tk.StringVar(value=val)
        entry = ttk.Entry(self.tree, textvariable=var, font=("Consolas", 9))
        entry.place(x=x, y=y, width=w, height=h)
        entry.select_range(0, "end")
        entry.focus_set()

        def confirm(e=None):
            new_val = var.get().strip()
            if new_val:
                self.tree.set(iid, "new", new_val)
            entry.destroy()

        entry.bind("<Return>",   confirm)
        entry.bind("<Escape>",   lambda e: entry.destroy())
        entry.bind("<FocusOut>", confirm)

    def _select_all(self):
        for iid in self.tree.get_children():
            self.tree.set(iid, "check", CHECK_ON)
        self._update_checked_label()

    def _deselect_all(self):
        for iid in self.tree.get_children():
            self.tree.set(iid, "check", CHECK_OFF)
        self._update_checked_label()

    def _update_checked_label(self):
        total   = len(self.tree.get_children())
        checked = sum(1 for iid in self.tree.get_children()
                      if self.tree.set(iid, "check") == CHECK_ON)
        self.lbl_checked.config(text=f"已勾選 {checked} / {total} 筆")

    # ── 執行流程 ──────────────────────────────────────────────

    def _start(self):
        if self._mode.get() == "folder":
            target_dir = self.dir_var.get().strip()
            if not os.path.isdir(target_dir):
                messagebox.showerror("錯誤", "請選擇有效的目標資料夾")
                return
            cfg = config.load()
            cfg["target_dir"] = target_dir
            cfg["format_order"] = self._format_order
            config.save(cfg)
        else:
            if not self._selected_files:
                messagebox.showerror("錯誤", "請先選擇要處理的檔案")
                return

        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self._close_review()
        self.btn_open_review.pack_forget()
        self.btn_cancel.pack_forget()
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(10)
        self.lbl_progress.config(text="掃描中...")
        self.btn_start.config(state="disabled")
        self._pending = []
        self._skipped = []

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            cfg = config.load()
            log_file   = str(SCRIPT_DIR / cfg["processed_log"])
            cache_file = str(SCRIPT_DIR / cfg["cache_file"])

            if self._mode.get() == "folder":
                target_dir = self.dir_var.get().strip()
                files = scan(target_dir, log_file)
            else:
                from scanner import load_processed_log, SUPPORTED_EXTS
                processed = load_processed_log(log_file)
                files = [f for f in self._selected_files
                         if f.suffix.lower() in SUPPORTED_EXTS and f.name not in processed]

            self._put("log", f"掃描完成，找到 {len(files)} 個待處理檔案\n")

            if not files:
                self._put("done_query", None)
                return

            self._put("switch_progress", len(files))
            fetcher = Fetcher(cache_file)
            fetcher.start()

            # Phase 1: 查詢所有番號，收集 (Path, base_new_name)
            fetched = []
            try:
                for i, f in enumerate(files, 1):
                    code = extract_code(f.name)
                    self._put("progress", (i, len(files), f"查詢中 {i}/{len(files)}"))
                    if not code:
                        self._skipped.append((f.name, "無法辨識番號"))
                        self._put("log", f"⚠ {f.name} → 無法辨識番號\n")
                        continue
                    result = fetcher.query(code)
                    if not result:
                        self._skipped.append((f.name, "javdb 查無資料"))
                        self._put("log", f"⚠ {f.name} → javdb 查無資料\n")
                        continue
                    base_name = build_filename(
                        code, result["actresses"], result["title"],
                        f.suffix, format_order=self._format_order
                    )
                    fetched.append((f, base_name))
            finally:
                fetcher.stop()

            # Phase 2: 偵測重複，重複者全部補 (1)(2)(3)...
            dup_set    = {name for name, cnt in Counter(n for _, n in fetched).items() if cnt > 1}
            name_index: dict = {}
            for f, base_name in fetched:
                is_dup = base_name in dup_set
                if is_dup:
                    name_index[base_name] = name_index.get(base_name, 0) + 1
                    n    = name_index[base_name]
                    stem = Path(base_name).stem
                    ext  = Path(base_name).suffix
                    new_name = f"{stem}({n}){ext}"
                else:
                    new_name = base_name
                self._pending.append((f, new_name, is_dup))

            self._put("done_query", None)
        except Exception as e:
            self._put("log", f"\n[ERROR] {e}\n")
            self._put("error", str(e))

    def _confirm(self):
        to_rename = [
            (self._item_map[iid][0], self.tree.set(iid, "new"))
            for iid in self.tree.get_children()
            if self.tree.set(iid, "check") == CHECK_ON
        ]
        if not to_rename:
            messagebox.showwarning("提示", "沒有勾選任何檔案")
            return
        self.btn_confirm.config(state="disabled")
        threading.Thread(target=self._do_rename, args=(to_rename,), daemon=True).start()

    def _cancel(self):
        self._close_review()
        self.btn_open_review.pack_forget()
        self.btn_cancel.pack_forget()
        self.btn_start.config(state="normal")
        self.lbl_progress.config(text="已取消")
        self._put("log", "已取消，未執行任何改名。\n")

    def _do_rename(self, to_rename: list):
        cfg = config.load()
        log_file     = str(SCRIPT_DIR / cfg["processed_log"])
        skipped_file = str(SCRIPT_DIR / cfg["skipped_log"])
        success = fail = 0
        for src, new_name in to_rename:
            if rename_file(src, new_name):
                write_processed_log(log_file, src.name, new_name)
                success += 1
            else:
                fail += 1
                self._put("log", f"✗ 改名失敗: {src.name}\n")
        if self._skipped:
            sk_path = Path(skipped_file)
            existing = {}
            if sk_path.exists():
                with open(sk_path, encoding="utf-8") as f:
                    existing = json.load(f)
            for fname, reason in self._skipped:
                existing[fname] = reason
            with open(sk_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        self._put("done_rename", (success, fail, len(self._skipped)))

    # ── 執行緒安全 UI 更新 ────────────────────────────────────

    def _put(self, msg_type: str, data):
        self.msg_queue.put((msg_type, data))

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "log":
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", data)
                    self.log_text.see("end")
                    self.log_text.config(state="disabled")
                elif msg_type == "progress":
                    cur, total, label = data
                    self.progress_bar["value"] = cur
                    self.lbl_progress.config(text=label)
                elif msg_type == "switch_progress":
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate", maximum=data, value=0)
                elif msg_type == "done_query":
                    self.progress_bar.stop()
                    n_ok   = len(self._pending)
                    n_skip = len(self._skipped)
                    self.lbl_progress.config(
                        text=f"查詢完成 — {n_ok} 筆可改名，{n_skip} 筆查無資料")
                    if n_ok > 0:
                        self.btn_open_review.config(
                            text=f"📋  開啟審閱清單（{n_ok} 筆）")
                        self.btn_open_review.pack(side="left", padx=(0, 8), ipady=4)
                    self.btn_cancel.pack(side="left", ipady=4)
                elif msg_type == "done_rename":
                    success, fail, skipped = data
                    self.lbl_progress.config(
                        text=f"完成 — 成功 {success} / 失敗 {fail} / 跳過 {skipped}")
                    self._close_review()
                    self.btn_open_review.pack_forget()
                    self.btn_cancel.pack_forget()
                    self.btn_start.config(state="normal")
                elif msg_type == "error":
                    self.progress_bar.stop()
                    self.lbl_progress.config(text="發生錯誤，請查看上方記錄")
                    self.btn_start.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main():
    root = tk.Tk()
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    AVRenameApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
