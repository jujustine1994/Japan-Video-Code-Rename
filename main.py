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
from datetime import datetime
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
        ttk.Button(frame_dir, text="⚙ 命名格式...",
                   command=self._open_fmt_dialog).grid(
            row=0, column=2, padx=(12, 0), sticky="e")

        self.dir_var = tk.StringVar(value=self._cfg.get("target_dir", ""))
        self.entry_dir = ttk.Entry(frame_dir, textvariable=self.dir_var, width=52)
        self.entry_dir.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(frame_dir, text="瀏覽", command=self._browse).grid(
            row=1, column=2, padx=(6, 0), pady=(6, 0))

        # 開始按鈕
        frame_btn = tk.Frame(self.root)
        frame_btn.grid(row=1, column=0, pady=6)
        self.btn_start = ttk.Button(frame_btn, text="▶  開始掃描",
                                    command=self._start, width=22)
        self.btn_start.pack(ipady=6)

        # 進度區
        frame_prog = ttk.LabelFrame(self.root, text=" 處理進度 ", padding=8)
        frame_prog.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))
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
        self.frame_action.grid(row=3, column=0, pady=(0, 12))
        self.btn_open_review = ttk.Button(
            self.frame_action, text="📋  開啟審閱清單",
            command=self._open_review_window, width=22)
        self.btn_cancel = ttk.Button(
            self.frame_action, text="✖  取消",
            command=self._cancel, width=12)

        # 資料庫管理
        frame_db = ttk.LabelFrame(self.root, text=" 資料庫 ", padding=8)
        frame_db.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 8))
        ttk.Button(frame_db, text="資料庫管理...",
                   command=self._open_db_manager, width=18).pack(anchor="w")
        ttk.Label(frame_db, text="⚠ 社群資料庫收錄番號與片名，女優名需首次查詢時自動補入",
                  foreground="#888888", font=("", 8)).pack(anchor="w", pady=(4, 0))

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

    def _open_fmt_dialog(self):
        NamingFormatDialog(
            self.root,
            self._format_order,
            on_save=lambda order: setattr(self, "_format_order", order),
        )

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

            lookup_file = str(SCRIPT_DIR / cfg["lookup_file"])
            self._put("switch_progress", len(files))
            fetcher = Fetcher(cache_file, lookup_file)
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

    def _open_db_manager(self):
        DatabaseManagerDialog(self.root, self._cfg)

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


class NamingFormatDialog:
    def __init__(self, parent: tk.Tk, current_order: list, on_save):
        self._on_save = on_save

        self.win = tk.Toplevel(parent)
        self.win.title("命名格式設定")
        self.win.resizable(False, False)
        self.win.grab_set()

        parent.update_idletasks()
        x = parent.winfo_x() + 40
        y = parent.winfo_y() + 40
        self.win.geometry(f"200x160+{x}+{y}")

        self._fmt_list = tk.Listbox(
            self.win, height=3, selectmode="single",
            width=16, font=("", 10),
        )
        for key in current_order:
            self._fmt_list.insert("end", LABELS[key])
        self._fmt_list.grid(row=0, column=0, rowspan=2,
                            padx=(14, 0), pady=14, sticky="ns")
        self._fmt_list.selection_set(0)

        ttk.Button(self.win, text="↑", width=4,
                   command=self._move_up).grid(row=0, column=1, padx=8, pady=(14, 2))
        ttk.Button(self.win, text="↓", width=4,
                   command=self._move_down).grid(row=1, column=1, padx=8, pady=(2, 0))

        btn_row = tk.Frame(self.win)
        btn_row.grid(row=2, column=0, columnspan=2, pady=(8, 12))
        ttk.Button(btn_row, text="確定", width=10,
                   command=self._ok).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="取消", width=10,
                   command=self.win.destroy).pack(side="left")

    def _move_up(self):
        sel = self._fmt_list.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        val = self._fmt_list.get(i)
        self._fmt_list.delete(i)
        self._fmt_list.insert(i - 1, val)
        self._fmt_list.selection_set(i - 1)

    def _move_down(self):
        sel = self._fmt_list.curselection()
        if not sel or sel[0] == self._fmt_list.size() - 1:
            return
        i = sel[0]
        val = self._fmt_list.get(i)
        self._fmt_list.delete(i)
        self._fmt_list.insert(i + 1, val)
        self._fmt_list.selection_set(i + 1)

    def _ok(self):
        new_order = [KEYS[self._fmt_list.get(i)]
                     for i in range(self._fmt_list.size())]
        cfg = config.load()
        cfg["format_order"] = new_order
        config.save(cfg)
        self._on_save(new_order)
        self.win.destroy()


class DatabaseManagerDialog:
    _STATE_PATH   = SCRIPT_DIR / "data" / "enrich_state.json"
    _SESSION_FILE = SCRIPT_DIR / "data" / "javdb_session.txt"

    def __init__(self, parent: tk.Tk, cfg: dict):
        self._cfg         = cfg
        self._running     = False
        self._pause_event = threading.Event()
        self._abort_event = threading.Event()

        self.win = tk.Toplevel(parent)
        self.win.title("資料庫管理")
        self.win.resizable(False, False)
        self.win.grab_set()

        # 定位到主視窗旁
        parent.update_idletasks()
        x = parent.winfo_x() + parent.winfo_width() + 10
        y = parent.winfo_y()
        self.win.geometry(f"480x720+{x}+{y}")

        self._build_ui()
        self._refresh_stats()
        self._refresh_community_stats()

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}

        # 統計列
        stats_frame = ttk.LabelFrame(self.win, text=" 資料庫狀態 ", padding=8)
        stats_frame.pack(fill="x", **pad)
        self.lbl_count = ttk.Label(stats_frame, text="載入中...")
        self.lbl_count.pack(anchor="w")
        lp_row = tk.Frame(stats_frame)
        lp_row.pack(anchor="w", pady=(4, 0))
        ttk.Label(lp_row, text="上次停在第").pack(side="left")
        self.last_page_var = tk.StringVar(value="0")
        ttk.Spinbox(lp_row, from_=0, to=99999, increment=1,
                    textvariable=self.last_page_var, width=7).pack(side="left", padx=(4, 4))
        ttk.Label(lp_row, text="頁（可手動修改）").pack(side="left")
        ttk.Button(lp_row, text="儲存", width=6,
                   command=self._save_last_page).pack(side="left", padx=(8, 0))

        # 操作區
        action_frame = ttk.LabelFrame(self.win, text=" 操作 ", padding=8)
        action_frame.pack(fill="x", padx=14, pady=(0, 6))

        # 追新
        row1 = tk.Frame(action_frame)
        row1.pack(fill="x", pady=(0, 6))
        self.btn_update = ttk.Button(row1, text="追新", command=self._run_update, width=14)
        self.btn_update.pack(side="left")
        ttk.Button(row1, text="ℹ", width=3,
                   command=lambda: messagebox.showinfo(
                       "追新說明",
                       "從最新番號開始掃描，遇到連續已知番號自動停止。\n"
                       "同時補回之前查無資料的番號。\n\n"
                       "沒有頁數上限，久未執行時可能需要較長時間。"
                   )).pack(side="left", padx=(4, 0))

        # 全量建置
        row2 = tk.Frame(action_frame)
        row2.pack(fill="x", pady=(0, 4))
        self.btn_build = ttk.Button(row2, text="全量建置", command=self._run_build, width=14)
        self.btn_build.pack(side="left")
        ttk.Button(row2, text="ℹ", width=3,
                   command=lambda: messagebox.showinfo(
                       "全量建置說明",
                       "從指定頁碼爬取，適合初次建庫或補充特定區間。\n"
                       "連續 2 頁無新增時自動暫停（可能是 session 失效）。\n"
                       "下次執行會從上次停止頁碼接續。"
                   )).pack(side="left", padx=(4, 0))

        # 頁碼設定（全量建置用）
        row3 = tk.Frame(action_frame)
        row3.pack(fill="x", pady=(0, 6))
        ttk.Label(row3, text="從第").pack(side="left")
        self.start_page_var = tk.StringVar(value="1")
        ttk.Spinbox(row3, from_=1, to=99999, increment=1,
                    textvariable=self.start_page_var, width=7).pack(side="left", padx=(4, 8))
        ttk.Label(row3, text="頁，爬").pack(side="left")
        self.pages_var = tk.StringVar(value="100")
        ttk.Spinbox(row3, from_=10, to=5000, increment=100,
                    textvariable=self.pages_var, width=6).pack(side="left", padx=(4, 4))
        ttk.Label(row3, text="頁").pack(side="left")

        # 暫停 / 中止按鈕
        row4 = tk.Frame(action_frame)
        row4.pack(fill="x")
        self.btn_pause = ttk.Button(row4, text="⏸ 暫停", command=self._on_pause,
                                    width=14, state="disabled")
        self.btn_pause.pack(side="left", padx=(0, 6))
        self.btn_abort = ttk.Button(row4, text="✖ 中止", command=self._on_abort,
                                    width=14, state="disabled")
        self.btn_abort.pack(side="left")

        # Session Cookie
        cookie_frame = ttk.LabelFrame(self.win, text=" JavDB Session Cookie ", padding=8)
        cookie_frame.pack(fill="x", padx=14, pady=(0, 6))
        self.lbl_session = ttk.Label(cookie_frame, text="")
        self.lbl_session.pack(anchor="w")
        ttk.Button(cookie_frame, text="設定 Cookie...", command=self._open_cookie_dialog,
                   width=18).pack(anchor="w", pady=(4, 0))
        self._refresh_session_status()

        # 社群同步
        sync_frame = ttk.LabelFrame(self.win, text=" 社群同步 ", padding=8)
        sync_frame.pack(fill="x", padx=14, pady=(0, 6))

        self.lbl_community_count = ttk.Label(sync_frame, text="社群資料庫：載入中...")
        self.lbl_community_count.pack(anchor="w")
        self.lbl_contribute_count = ttk.Label(sync_frame, text="可貢獻：計算中...")
        self.lbl_contribute_count.pack(anchor="w", pady=(2, 6))

        sync_btn_row = tk.Frame(sync_frame)
        sync_btn_row.pack(anchor="w")
        self.btn_download = ttk.Button(sync_btn_row, text="⬇ 下載最新",
                                       command=self._run_download, width=16)
        self.btn_download.pack(side="left", padx=(0, 8))
        self.btn_contribute = ttk.Button(sync_btn_row, text="⬆ 貢獻我的資料",
                                         command=self._run_contribute, width=16)
        self.btn_contribute.pack(side="left")

        # Log
        log_frame = ttk.LabelFrame(self.win, text=" 進度 ", padding=8)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.log_text = scrolledtext.ScrolledText(
            log_frame, width=56, height=10, state="disabled", font=("Consolas", 9)
        )
        self.log_text.pack(fill="both", expand=True)

        # 關閉
        self.btn_close = ttk.Button(self.win, text="關閉", command=self.win.destroy, width=12)
        self.btn_close.pack(pady=(0, 10))

    def _refresh_session_status(self):
        if self._SESSION_FILE.exists():
            val = self._SESSION_FILE.read_text(encoding="utf-8").strip()
            status = f"已設定（{len(val)} 字元）" if val else "檔案存在但內容空白"
        else:
            status = "未設定"
        self.lbl_session.config(text=f"狀態：{status}　← 貼上新 cookie 後點儲存")

    def _open_cookie_dialog(self):
        from urllib.parse import unquote
        dialog = tk.Toplevel(self.win)
        dialog.title("設定 JavDB Session Cookie")
        dialog.resizable(True, False)
        dialog.grab_set()
        self.win.update_idletasks()
        dialog.geometry(f"560x340+{self.win.winfo_x() + 20}+{self.win.winfo_y() + 20}")

        ttk.Label(dialog, text="目前儲存的 Cookie（唯讀）：").pack(
            anchor="w", padx=12, pady=(10, 2))
        cur_frame = tk.Frame(dialog, padx=12)
        cur_frame.pack(fill="x")
        cur_text = tk.Text(cur_frame, height=3, font=("Consolas", 8),
                           wrap="char", state="disabled", bg="#f0f0f0")
        cur_text.pack(fill="x")
        cur_val = (self._SESSION_FILE.read_text(encoding="utf-8").strip()
                   if self._SESSION_FILE.exists() else "（尚未設定）")
        cur_text.config(state="normal")
        cur_text.insert("1.0", cur_val)
        cur_text.config(state="disabled")

        ttk.Label(dialog, text="貼上新的 Cookie 值：").pack(
            anchor="w", padx=12, pady=(10, 2))
        new_frame = tk.Frame(dialog, padx=12)
        new_frame.pack(fill="x")
        new_text = tk.Text(new_frame, height=3, font=("Consolas", 8), wrap="char")
        new_text.pack(fill="x")
        new_text.focus_set()

        def do_save():
            raw = new_text.get("1.0", "end").strip()
            if not raw:
                messagebox.showwarning("空白", "請先貼上 cookie 值", parent=dialog)
                return
            decoded = unquote(raw)
            self._SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._SESSION_FILE.write_text(decoded, encoding="utf-8")
            self._refresh_session_status()
            dialog.destroy()

        btn_row = tk.Frame(dialog)
        btn_row.pack(pady=10)
        ttk.Button(btn_row, text="儲存", width=10, command=do_save).pack(
            side="left", padx=(0, 8))
        ttk.Button(btn_row, text="取消", width=10,
                   command=dialog.destroy).pack(side="left")

    def _refresh_stats(self):
        lookup_path = SCRIPT_DIR / self._cfg.get("lookup_file", "data/javdb_lookup.json")
        count = 0
        if lookup_path.exists():
            data = json.loads(lookup_path.read_text(encoding="utf-8"))
            count = len(data)

        lp = 0
        last_updated = "尚未建置"
        if self._STATE_PATH.exists():
            state = json.loads(self._STATE_PATH.read_text(encoding="utf-8"))
            lp = state.get("last_page") or 0
            last_updated = state.get("last_updated", "未知")

        self.lbl_count.config(text=f"共 {count:,} 筆 · 上次更新：{last_updated}")
        self.last_page_var.set(str(lp))
        self.start_page_var.set(str(lp + 1))

    def _refresh_community_stats(self):
        from community_sync import CommunitySync
        lookup_path = SCRIPT_DIR / self._cfg.get("lookup_file", "data/javdb_lookup.json")
        sync = CommunitySync(lookup_path)

        def worker():
            stats = sync.get_community_stats()
            count_str = (f"社群資料庫：{stats['count']:,} 筆"
                         f"（更新：{stats['last_updated'][:10]}）")
            contrib = sync.get_contribute_count()
            contrib_str = f"可貢獻新番號：{contrib:,} 筆"
            self.win.after(0, lambda: self.lbl_community_count.config(text=count_str))
            self.win.after(0, lambda: self.lbl_contribute_count.config(text=contrib_str))

        threading.Thread(target=worker, daemon=True).start()

    def _run_download(self):
        if self._running:
            return
        self._set_running(True)
        self._pause_event.clear()
        self._abort_event.clear()

        from community_sync import CommunitySync
        lookup_path = SCRIPT_DIR / self._cfg.get("lookup_file", "data/javdb_lookup.json")
        backup_dir  = SCRIPT_DIR / "data" / "backups"
        sync = CommunitySync(lookup_path)

        def worker():
            try:
                sync.download(backup_dir, progress_cb=lambda m: self.win.after(
                    0, lambda msg=m: self._log(msg + "\n")))
                self.win.after(0, self._refresh_stats)
                self.win.after(0, self._refresh_community_stats)
            finally:
                self.win.after(0, lambda: self._set_running(False))

        threading.Thread(target=worker, daemon=True).start()

    def _run_contribute(self):
        if self._running:
            return
        contrib_text = self.lbl_contribute_count.cget("text")
        if not messagebox.askyesno(
            "確認貢獻",
            f"將把本機的新番號送出到社群資料庫。\n{contrib_text}\n\n確定送出？",
            parent=self.win,
        ):
            return

        self._set_running(True)
        from community_sync import CommunitySync
        lookup_path = SCRIPT_DIR / self._cfg.get("lookup_file", "data/javdb_lookup.json")
        sync = CommunitySync(lookup_path)

        def worker():
            try:
                sync.contribute(progress_cb=lambda m: self.win.after(
                    0, lambda msg=m: self._log(msg + "\n")))
            finally:
                self.win.after(0, lambda: self._set_running(False))

        threading.Thread(target=worker, daemon=True).start()

    def _save_last_page(self):
        try:
            lp = int(self.last_page_var.get())
        except ValueError:
            messagebox.showerror("錯誤", "頁碼必須為整數")
            return
        state = {}
        if self._STATE_PATH.exists():
            state = json.loads(self._STATE_PATH.read_text(encoding="utf-8"))
        state["last_page"] = lp
        self._STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        self.start_page_var.set(str(lp + 1))

    def _log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _set_running(self, running: bool):
        self._running = running
        state = "disabled" if running else "normal"
        self.btn_update.config(state=state)
        self.btn_build.config(state=state)
        self.btn_close.config(state=state)
        self.btn_download.config(state=state)
        self.btn_contribute.config(state=state)
        self.btn_pause.config(state="normal" if running else "disabled", text="⏸ 暫停")
        self.btn_abort.config(state="normal" if running else "disabled", text="✖ 中止")

    def _on_pause(self):
        self._pause_event.set()
        self.btn_pause.config(state="disabled", text="⏸ 暫停中...")
        self.btn_abort.config(state="disabled")

    def _on_abort(self):
        self._abort_event.set()
        self._pause_event.set()
        self.btn_pause.config(state="disabled")
        self.btn_abort.config(state="disabled", text="✖ 中止中...")

    def _save_state(self, updates: dict):
        state = {}
        if self._STATE_PATH.exists():
            state = json.loads(self._STATE_PATH.read_text(encoding="utf-8"))
        state.update(updates)
        state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _run_update(self):
        self._set_running(True)
        self._pause_event.clear()
        self._abort_event.clear()
        self.btn_update.config(text="追新中...")
        self.win.after(0, self._log, "開始追新...\n")

        lookup_file = str(SCRIPT_DIR / self._cfg.get("lookup_file", "data/javdb_lookup.json"))
        cache_file  = str(SCRIPT_DIR / self._cfg.get("cache_file",  "cache/javdb_cache.json"))

        def run():
            from fetcher import Fetcher
            from enricher import LookupEnricher
            fetcher  = Fetcher(cache_file, lookup_file)
            enricher = LookupEnricher(lookup_file, cache_file)
            fetcher.start()
            logged_in, login_msg = fetcher.check_login_status()
            self.win.after(0, self._log, f"{'✅' if logged_in else '❌'} {login_msg}\n")
            try:
                new = enricher.scrape_new_releases(
                    fetcher, stop_after_known=50, max_pages=9999,
                    progress_cb=lambda msg: self.win.after(0, self._log, msg + "\n"),
                    pause_event=self._pause_event,
                )
                if self._abort_event.is_set():
                    self.win.after(0, self._log, f"✖ 已中止：追新 +{new} 筆\n")
                elif not self._pause_event.is_set():
                    recovered = enricher.retry_no_data(
                        fetcher, max_retries=50,
                        progress_cb=lambda msg: self.win.after(0, self._log, msg + "\n"),
                    )
                    self._save_state({})
                    self.win.after(0, self._log, f"完成：追新 +{new} 筆，補回 +{recovered} 筆\n")
                else:
                    self.win.after(0, self._log, f"⏸ 已暫停：追新 +{new} 筆\n")
            except Exception as e:
                self.win.after(0, self._log, f"失敗：{e}\n")
            finally:
                fetcher.stop()
                self.win.after(0, self._finish, self.btn_update, "追新")

        threading.Thread(target=run, daemon=True).start()

    def _run_build(self):
        self._set_running(True)
        self._pause_event.clear()
        self._abort_event.clear()
        self.btn_build.config(text="建置中...")
        max_pages  = int(self.pages_var.get() or 100)
        start_page = int(self.start_page_var.get() or 1)

        lookup_file = str(SCRIPT_DIR / self._cfg.get("lookup_file", "data/javdb_lookup.json"))
        cache_file  = str(SCRIPT_DIR / self._cfg.get("cache_file",  "cache/javdb_cache.json"))

        def run():
            from fetcher import Fetcher
            from enricher import LookupEnricher
            state = json.loads(self._STATE_PATH.read_text(encoding="utf-8")) \
                    if self._STATE_PATH.exists() else {}
            prev_last = state.get("last_page", 0)
            self.win.after(0, self._log, f"從第 {start_page} 頁開始，最多 {max_pages} 頁\n")

            fetcher  = Fetcher(cache_file, lookup_file)
            enricher = LookupEnricher(lookup_file, cache_file)
            fetcher.start()
            logged_in, login_msg = fetcher.check_login_status()
            self.win.after(0, self._log, f"{'✅' if logged_in else '❌'} {login_msg}\n")
            try:
                new_count, last_page = enricher.scrape_listing_pages(
                    fetcher, start_page=start_page, max_pages=max_pages,
                    progress_cb=lambda msg: self.win.after(0, self._log, msg + "\n"),
                    pause_event=self._pause_event,
                    prev_last_page=prev_last,
                )
                if self._abort_event.is_set():
                    self.win.after(0, lambda: self.start_page_var.set(str(start_page)))
                    self.win.after(0, self._log,
                        f"✖ 已中止：本次 +{new_count} 筆，進度未儲存，"
                        f"下次仍從第 {start_page} 頁開始\n")
                elif new_count > 0:
                    total = state.get("total_imported", 0) + new_count
                    self._save_state({"last_page": last_page, "total_imported": total})
                    self.win.after(0, lambda: self.start_page_var.set(str(last_page + 1)))
                    if self._pause_event.is_set():
                        self.win.after(0, self._log,
                            f"⏸ 已暫停：本次 +{new_count} 筆，停在第 {last_page} 頁\n"
                            f"（再按「全量建置」從第 {last_page + 1} 頁繼續）\n")
                    else:
                        total = state.get("total_imported", 0) + new_count
                        self.win.after(0, self._log,
                            f"完成：本次 +{new_count} 筆，累計 {total} 筆，停在第 {last_page} 頁\n")
                elif start_page > prev_last:
                    self.win.after(0, self._log,
                        "⚠ 在未爬過的範圍卻無新增，可能是 session 失效。last_page 未更新。\n")
                else:
                    self.win.after(0, self._log, "完成：本次 +0 筆（頁碼範圍為已知內容）\n")
            except Exception as e:
                self.win.after(0, self._log, f"失敗：{e}\n")
            finally:
                fetcher.stop()
                self.win.after(0, self._finish, self.btn_build, "全量建置")

        threading.Thread(target=run, daemon=True).start()

    def _finish(self, btn: ttk.Button, label: str):
        btn.config(text=label)
        self._set_running(False)
        self._refresh_stats()


def main():
    root = tk.Tk()
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    AVRenameApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
