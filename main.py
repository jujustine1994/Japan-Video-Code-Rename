import sys
import os
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

import config
import scanner
import renamer
from fetcher import Fetcher

console = Console()


def show_cth_banner():
    b = "\033[90m"
    c = "\033[96m"
    y = "\033[93m"
    r = "\033[0m"
    print(f"{b}/*  ================================  *\\{r}")
    print(f"{b} *                                    *{r}")
    print(f"{b} *    {c}██████╗████████╗██╗  ██╗{b}        *{r}")
    print(f"{b} *   {c}██╔════╝   ██║   ██║  ██║{b}        *{r}")
    print(f"{b} *   {c}██║        ██║   ███████║{b}        *{r}")
    print(f"{b} *   {c}██║        ██║   ██╔══██║{b}        *{r}")
    print(f"{b} *   {c}╚██████╗   ██║   ██║  ██║{b}        *{r}")
    print(f"{b} *    {c}╚═════╝   ╚═╝   ╚═╝  ╚═╝{b}        *{r}")
    print(f"{b} *                                    *{r}")
    print(f"{b} *          {y}created by CTH{b}            *{r}")
    print(f"{b}\\*  ================================  */{r}")
    print()


def ensure_target_dir(cfg: dict) -> dict:
    while not cfg["target_dir"] or not Path(cfg["target_dir"]).is_dir():
        if cfg["target_dir"]:
            console.print(f"[red]路徑不存在：{cfg['target_dir']}[/red]")
        console.print("[cyan]請輸入目標資料夾路徑：[/cyan]", end=" ")
        path = input().strip().strip('"')
        if Path(path).is_dir():
            cfg["target_dir"] = path
            config.save(cfg)
            console.print(f"[green]已儲存路徑：{path}[/green]\n")
        else:
            console.print("[red]路徑不存在，請重新輸入。[/red]")
    return cfg


def phase1_scan(cfg: dict) -> list:
    console.print("[bold cyan]Phase 1 — 掃描資料夾...[/bold cyan]")
    files = scanner.scan(cfg["target_dir"], cfg["processed_log"])
    console.print(f"  找到 [bold]{len(files)}[/bold] 個待處理檔案\n")
    return files


def phase2_query(files: list, cfg: dict) -> tuple:
    can_rename = []
    uncertain = []

    videos = [f for f in files if f.suffix.lower() in {".mp4", ".webm"}]
    srts   = [f for f in files if f.suffix.lower() == ".srt"]

    groups = scanner.group_by_code([f.name for f in videos])
    multipart_codes = {code for code, names in groups.items() if len(names) > 1}

    fetcher = Fetcher(cfg["cache_file"])
    fetcher.start()

    try:
        with Progress(
            SpinnerColumn(),
            BarColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("查詢 javdb 中...", total=len(videos))

            for f in videos:
                code = scanner.extract_code(f.name)
                progress.update(task, description=f"查詢 {code or f.name[:30]}...")

                if not code:
                    uncertain.append({"file": f, "reason": "找不到番號"})
                    progress.advance(task)
                    continue

                data = fetcher.query(code)
                if not data:
                    uncertain.append({"file": f, "reason": "javdb 查無資料"})
                    progress.advance(task)
                    continue

                part = None
                if code in multipart_codes:
                    parts_list = sorted(groups[code])
                    part = parts_list.index(f.name) + 1

                new_name = renamer.build_filename(
                    code, data["actresses"], data["title"], f.suffix, part
                )
                can_rename.append({
                    "file": f, "code": code,
                    "new_name": new_name, "part": part,
                    "data": data,
                })
                progress.advance(task)

        _process_srts(srts, can_rename, uncertain, fetcher)

    finally:
        fetcher.stop()

    return can_rename, uncertain


def _process_srts(srts, can_rename, uncertain, fetcher):
    mp4_codes = {item["code"]: item["new_name"] for item in can_rename}

    for srt in srts:
        code = scanner.extract_code(srt.name)
        if not code:
            uncertain.append({"file": srt, "reason": "找不到番號"})
            continue
        if code in mp4_codes:
            base = Path(mp4_codes[code]).stem
            can_rename.append({
                "file": srt, "code": code,
                "new_name": base + ".srt", "part": None, "data": {},
            })
        else:
            data = fetcher.query(code)
            if data:
                new_name = renamer.build_filename(
                    code, data["actresses"], data["title"], ".srt"
                )
                can_rename.append({
                    "file": srt, "code": code,
                    "new_name": new_name, "part": None, "data": data,
                })
            else:
                uncertain.append({"file": srt, "reason": "javdb 查無資料"})


def phase3_review(can_rename: list, uncertain: list) -> bool:
    console.print()
    console.rule("[bold]審閱清單[/bold]")
    console.print(
        f"  [green]可更名：{len(can_rename)} 筆[/green]  "
        f"[yellow]不確定：{len(uncertain)} 筆[/yellow]  "
        f"共 {len(can_rename) + len(uncertain)} 筆\n"
    )

    if can_rename:
        console.print("[green]── 可更名 ──[/green]")
        for i, item in enumerate(can_rename, 1):
            console.print(f"  [dim]{i:03d}[/dim]  {item['file'].name}")
            console.print(f"       [green]→ {item['new_name']}[/green]")
        console.print()

    if uncertain:
        console.print("[yellow]── 不確定（維持原狀）──[/yellow]")
        for i, item in enumerate(uncertain, 1):
            idx = len(can_rename) + i
            console.print(
                f"  [dim]{idx:03d}[/dim]  {item['file'].name}  "
                f"[dim]({item['reason']})[/dim]"
            )
        console.print()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    preview_path = Path(f"preview_{ts}.txt")
    _write_preview(preview_path, can_rename, uncertain)
    console.print(f"[dim]審閱清單已儲存至 {preview_path}[/dim]\n")

    console.rule()
    console.print(
        f"按 [bold green]Enter[/bold green] 確認更名 {len(can_rename)} 個檔案  "
        "[dim]|[/dim]  [bold red]Ctrl+C[/bold red] 取消"
    )
    try:
        input()
        return True
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消。[/yellow]")
        return False


def _write_preview(path: Path, can_rename: list, uncertain: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("AV Code Rename — 審閱清單\n")
        f.write(f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"可更名：{len(can_rename)} 筆  不確定：{len(uncertain)} 筆\n\n")
        f.write("── 可更名 ──\n")
        for i, item in enumerate(can_rename, 1):
            f.write(f"{i:03d}  {item['file'].name}\n")
            f.write(f"     → {item['new_name']}\n")
        f.write("\n── 不確定（維持原狀）──\n")
        for i, item in enumerate(uncertain, 1):
            f.write(f"{len(can_rename)+i:03d}  {item['file'].name}  ({item['reason']})\n")


def phase4_execute(can_rename: list, uncertain: list, cfg: dict) -> None:
    console.print("\n[bold cyan]執行更名中...[/bold cyan]")
    success = 0
    failed = []

    with Progress(BarColumn(), TextColumn("{task.completed}/{task.total}"),
                  console=console) as progress:
        task = progress.add_task("", total=len(can_rename))
        for item in can_rename:
            ok = renamer.rename_file(item["file"], item["new_name"])
            if ok:
                renamer.write_processed_log(
                    cfg["processed_log"], item["file"].name, item["new_name"]
                )
                success += 1
            else:
                failed.append(item["file"].name)
            progress.advance(task)

    if uncertain:
        skipped_entries = [
            {
                "filename": item["file"].name,
                "reason": item["reason"],
                "skipped_at": datetime.now().isoformat(),
            }
            for item in uncertain
        ]
        renamer.write_skipped_log(cfg["skipped_log"], skipped_entries)

    console.print()
    console.print(f"  [green]✓ 成功更名：{success} 個[/green]")
    if failed:
        console.print(f"  [red]✗ 失敗：{len(failed)} 個[/red]")
        for name in failed:
            console.print(f"      {name}")
    console.print(f"  [dim]─ 不確定，維持原狀：{len(uncertain)} 個[/dim]")
    if uncertain:
        console.print(f"  [dim]  （已記錄至 {cfg['skipped_log']}）[/dim]")
    console.print()


def main():
    os.system("cls")
    show_cth_banner()

    cfg = config.load()

    console.print(f"[dim]目標資料夾：{cfg['target_dir'] or '（未設定）'}[/dim]")
    if cfg["target_dir"]:
        console.print("按 [bold]Enter[/bold] 開始掃描  [dim]|[/dim]  輸入 [bold]C[/bold] 更改資料夾")
        ans = input().strip().upper()
        if ans == "C":
            cfg["target_dir"] = ""
    cfg = ensure_target_dir(cfg)

    files = phase1_scan(cfg)
    if not files:
        console.print("[green]沒有待處理的檔案，全部已處理完畢。[/green]")
        input("\n按 Enter 關閉")
        return

    can_rename, uncertain = phase2_query(files, cfg)

    confirmed = phase3_review(can_rename, uncertain)
    if not confirmed:
        return

    phase4_execute(can_rename, uncertain, cfg)
    input("按 Enter 關閉")


if __name__ == "__main__":
    main()
