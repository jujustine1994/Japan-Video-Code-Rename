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

import config
from scanner import scan, extract_code
from fetcher import Fetcher
from renamer import build_filename, rename_file, write_processed_log

SCRIPT_DIR = Path(__file__).parent
LABELS = {"code": "番號", "actress": "女優名", "title": "片名"}
KEYS = {"番號": "code", "女優名": "actress", "片名": "title"}


class AVRenameApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AV Code Rename")
        self.root.resizable(False, False)

        self.msg_queue: queue.Queue = queue.Queue()
        self._pending: list = []   # (Path, str)
        self._skipped: list = []   # (str, str)

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
        frame_dir.columnconfigure(0, weight=1)
        self.dir_var = tk.StringVar(value=self._cfg.get("target_dir", ""))
        ttk.Entry(frame_dir, textvariable=self.dir_var, width=52).grid(row=0, column=0, sticky="ew")
        ttk.Button(frame_dir, text="瀏覽", command=self._browse).grid(row=0, column=1, padx=(6, 0))

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

        # 進度
        frame_prog = ttk.LabelFrame(self.root, text=" 處理進度 ", padding=8)
        frame_prog.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 6))
        self.lbl_progress = ttk.Label(frame_prog, text="等待開始...")
        self.lbl_progress.pack(anchor="w")
        self.progress_bar = ttk.Progressbar(frame_prog, mode="indeterminate", length=420)
        self.progress_bar.pack(fill="x", pady=(4, 8))
        self.log_text = scrolledtext.ScrolledText(
            frame_prog, width=62, height=16, state="disabled", font=("Consolas", 9)
        )
        self.log_text.pack(fill="x")

        # 確認/取消（初始隱藏）
        self.frame_confirm = tk.Frame(self.root)
        self.frame_confirm.grid(row=4, column=0, pady=(0, 12))
        self.btn_confirm = ttk.Button(self.frame_confirm, text="✔  確認改名",
                                      command=self._confirm, width=18)
        self.btn_cancel = ttk.Button(self.frame_confirm, text="✖  取消",
                                     command=self._cancel, width=12)

        self.root.columnconfigure(0, weight=1)

    # ── UI 互動 ──────────────────────────────────────────────

    def _browse(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_var.set(d)

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

    # ── 執行流程 ──────────────────────────────────────────────

    def _start(self):
        target_dir = self.dir_var.get().strip()
        if not os.path.isdir(target_dir):
            messagebox.showerror("錯誤", "請選擇有效的目標資料夾")
            return
        cfg = config.load()
        cfg["target_dir"] = target_dir
        cfg["format_order"] = self._format_order
        config.save(cfg)

        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.btn_confirm.pack_forget()
        self.btn_cancel.pack_forget()
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(10)
        self.lbl_progress.config(text="掃描中...")
        self.btn_start.config(state="disabled")
        self._pending = []
        self._skipped = []

        threading.Thread(target=self._worker, args=(target_dir,), daemon=True).start()

    def _worker(self, target_dir: str):
        try:
            cfg = config.load()
            log_file = str(SCRIPT_DIR / cfg["processed_log"])
            cache_file = str(SCRIPT_DIR / cfg["cache_file"])

            files = scan(target_dir, log_file)
            self._put("log", f"掃描完成，找到 {len(files)} 個待處理檔案\n")

            if not files:
                self._put("done_query", None)
                return

            self._put("switch_progress", len(files))
            fetcher = Fetcher(cache_file)
            fetcher.start()
            try:
                for i, f in enumerate(files, 1):
                    code = extract_code(f.name)
                    self._put("progress", (i, len(files), f"查詢中 {i}/{len(files)}"))
                    if not code:
                        self._skipped.append((f.name, "無法辨識番號"))
                        self._put("log", f"⚠ {f.name}\n  → 無法辨識番號\n")
                        continue
                    result = fetcher.query(code)
                    if not result:
                        self._skipped.append((f.name, "javdb 查無資料"))
                        self._put("log", f"⚠ {f.name}\n  → javdb 查無資料\n")
                        continue
                    new_name = build_filename(
                        code, result["actresses"], result["title"],
                        f.suffix, format_order=self._format_order
                    )
                    self._pending.append((f, new_name))
                    self._put("log", f"✓ {f.name}\n  → {new_name}\n")
            finally:
                fetcher.stop()
            self._put("done_query", None)
        except Exception as e:
            self._put("log", f"\n[ERROR] {e}\n")
            self._put("error", str(e))

    def _confirm(self):
        self.btn_confirm.config(state="disabled")
        self.btn_cancel.config(state="disabled")
        threading.Thread(target=self._do_rename, daemon=True).start()

    def _cancel(self):
        self.btn_confirm.pack_forget()
        self.btn_cancel.pack_forget()
        self.btn_start.config(state="normal")
        self.lbl_progress.config(text="已取消")
        self._put("log", "已取消，未執行任何改名。\n")

    def _do_rename(self):
        cfg = config.load()
        log_file = str(SCRIPT_DIR / cfg["processed_log"])
        skipped_file = str(SCRIPT_DIR / cfg["skipped_log"])
        success = fail = 0
        for src, new_name in self._pending:
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
                    n_ok, n_skip = len(self._pending), len(self._skipped)
                    self.lbl_progress.config(text=f"查詢完成 — {n_ok} 筆可改名，{n_skip} 筆跳過")
                    self._put("log", f"\n── 共 {n_ok} 筆可改名，{n_skip} 筆跳過 ──\n")
                    if n_ok > 0:
                        self.btn_confirm.pack(side="left", padx=(0, 8), ipady=4)
                    self.btn_cancel.pack(side="left", ipady=4)
                elif msg_type == "done_rename":
                    success, fail, skipped = data
                    self.lbl_progress.config(
                        text=f"完成 — 成功 {success} / 失敗 {fail} / 跳過 {skipped}")
                    self.btn_confirm.pack_forget()
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
