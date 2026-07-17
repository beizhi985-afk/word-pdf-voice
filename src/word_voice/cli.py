from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .anki_export import export_anki_deck
from .extractor import extract_vocabulary_pdf, write_csv, write_json
from .samples import select_pronunciation_samples
from .storage import ProjectWorkspace, VocabularyStore, prepare_default_workspace
from .tts import AudioService, KokoroOnnxEngine, TtsConfig


def _workspace(value: str | None, pdf: Path) -> ProjectWorkspace:
    if value:
        return ProjectWorkspace.create(value)
    workspace, _ = prepare_default_workspace(pdf)
    return workspace


def command_extract(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    workspace = _workspace(args.workspace, pdf)
    print("正在读取 PDF...")
    document = extract_vocabulary_pdf(
        pdf,
        progress=lambda current, total: print(
            f"\r正在分析第 {current}/{total} 页", end="", flush=True
        ),
    )
    print()
    store = VocabularyStore(workspace.database_path)
    store.import_document(document)
    csv_path = write_csv(document.entries, workspace.root / "vocabulary.csv")
    json_path = write_json(document, workspace.root / "vocabulary.json")
    print(json.dumps(document.summary(), ensure_ascii=False, indent=2))
    print(f"CSV：{csv_path}")
    print(f"JSON：{json_path}")
    print(f"数据库：{workspace.database_path}")
    return 0


def _audio_service(args: argparse.Namespace, workspace: ProjectWorkspace) -> AudioService:
    config = TtsConfig(
        model_path=Path(args.model),
        voices_path=Path(args.voices),
        voice=args.voice,
        speed=args.speed,
        language=args.language,
    )
    return AudioService(
        VocabularyStore(workspace.database_path),
        workspace.audio_dir,
        KokoroOnnxEngine(config),
    )


def command_generate_samples(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    workspace = _workspace(args.workspace, pdf)
    store = VocabularyStore(workspace.database_path)
    if not store.entry_count():
        document = extract_vocabulary_pdf(pdf)
        store.import_document(document)
    entries = select_pronunciation_samples(store.list_entries(), args.count)
    service = _audio_service(args, workspace)
    completed, failed = service.generate_many(
        entries,
        progress=lambda index, total, entry, state: print(
            f"[{index}/{total}] {entry.sequence} {entry.word}: {state}"
        ),
    )
    print(f"完成 {completed}，失败 {failed}，音频目录：{workspace.audio_dir}")
    return 1 if failed else 0


def command_export_anki(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    workspace = _workspace(args.workspace, pdf)
    store = VocabularyStore(workspace.database_path)
    if not store.entry_count():
        print("尚未提取词表，请先运行 extract。", file=sys.stderr)
        return 2
    output = Path(args.output) if args.output else workspace.export_dir / "CET4-4450.apkg"
    result = export_anki_deck(
        store.list_entries(),
        store,
        output,
        ready_only=args.ready_only,
        deck_name="英语四级乱序词汇 · 已生成音频" if args.ready_only else "英语四级乱序词汇 4450",
    )
    print(f"Anki 卡组：{result.path}（{result.exported_count} 条）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="英文词汇 PDF 点读与 Anki 导出")
    subparsers = parser.add_subparsers(dest="command")

    extract_parser = subparsers.add_parser("extract", help="提取 PDF 词表")
    extract_parser.add_argument("pdf")
    extract_parser.add_argument("--workspace")
    extract_parser.set_defaults(handler=command_extract)

    sample_parser = subparsers.add_parser("generate-samples", help="生成代表性试听样本")
    sample_parser.add_argument("pdf")
    sample_parser.add_argument("--workspace")
    sample_parser.add_argument("--model", required=True)
    sample_parser.add_argument("--voices", required=True)
    sample_parser.add_argument("--voice", default="af_sarah")
    sample_parser.add_argument("--speed", type=float, default=0.9)
    sample_parser.add_argument("--language", default="en-us")
    sample_parser.add_argument("--count", type=int, default=30)
    sample_parser.set_defaults(handler=command_generate_samples)

    export_parser = subparsers.add_parser("export-anki", help="导出包含音频的 Anki 卡组")
    export_parser.add_argument("pdf")
    export_parser.add_argument("--workspace")
    export_parser.add_argument("--output")
    export_parser.add_argument("--ready-only", action="store_true", help="只导出已有音频的词条")
    export_parser.set_defaults(handler=command_export_anki)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        from .app import main as app_main

        return app_main()
    try:
        return args.handler(args)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

