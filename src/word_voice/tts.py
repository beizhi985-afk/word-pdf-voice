from __future__ import annotations

import os
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .models import VocabularyEntry
from .storage import VocabularyStore


class TtsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TtsConfig:
    model_path: Path
    voices_path: Path
    voice: str = "af_sarah"
    speed: float = 0.9
    language: str = "en-us"


def tts_profile_key(config: TtsConfig) -> str:
    """Return the cache identity for settings that change synthesized audio."""
    return f"kokoro-v1|{config.voice}|{config.speed:.2f}|{config.language}"


def is_legacy_default_profile(config: TtsConfig) -> bool:
    """v0.2.0 audio had no profile metadata and used these defaults."""
    return (
        config.voice == "af_sarah"
        and abs(config.speed - 0.9) < 0.0001
        and config.language == "en-us"
    )


def audio_filename(entry: VocabularyEntry) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", entry.word.casefold()).strip("-") or "word"
    return f"cet4_{entry.sequence:04d}_{slug[:48]}.wav"


class KokoroOnnxEngine:
    def __init__(self, config: TtsConfig):
        self.config = config
        self._kokoro = None

    @property
    def profile_key(self) -> str:
        return tts_profile_key(self.config)

    @property
    def accepts_legacy_default_cache(self) -> bool:
        return is_legacy_default_profile(self.config)

    def _load(self):
        if self._kokoro is not None:
            return self._kokoro
        if not self.config.model_path.is_file():
            raise TtsError(f"找不到语音模型：{self.config.model_path}")
        if not self.config.voices_path.is_file():
            raise TtsError(f"找不到声音文件：{self.config.voices_path}")
        try:
            from kokoro_onnx import EspeakConfig, Kokoro
        except ImportError as exc:
            raise TtsError("缺少 kokoro-onnx，请先安装项目依赖。") from exc
        espeak_config = None
        if platform.system() == "Windows":
            espeak_config = _prepare_windows_espeak_runtime(EspeakConfig)
        self._kokoro = Kokoro(
            str(self.config.model_path),
            str(self.config.voices_path),
            espeak_config=espeak_config,
        )
        return self._kokoro

    def synthesize(self, entry: VocabularyEntry, output_path: Path) -> Path:
        try:
            import soundfile as sf
        except ImportError as exc:
            raise TtsError("缺少 soundfile，请先安装项目依赖。") from exc
        text = entry.word
        if entry.pronunciation_override:
            text = f"[{entry.word}](/{entry.pronunciation_override}/)"
        kokoro = self._load()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            is_phonemes = bool(entry.pronunciation_override)
            samples, sample_rate = kokoro.create(
                text,
                voice=self.config.voice,
                speed=self.config.speed,
                lang=self.config.language,
                is_phonemes=is_phonemes,
            )
            sf.write(str(output_path), samples, sample_rate)
        except Exception as exc:  # model/runtime errors vary by platform
            raise TtsError(f"生成 {entry.word} 失败：{exc}") from exc
        return output_path


class AudioService:
    def __init__(
        self,
        store: VocabularyStore,
        audio_dir: str | Path,
        engine: KokoroOnnxEngine,
    ):
        self.store = store
        self.audio_dir = Path(audio_dir)
        self.engine = engine

    def ensure_audio(self, entry: VocabularyEntry, force: bool = False) -> Path:
        status, stored_path, _ = self.store.audio_record(entry.sequence)
        stored_profile = self.store.audio_profile(entry.sequence)
        current_profile = self.engine.profile_key
        if not force and status == "ready" and stored_path and Path(stored_path).is_file():
            if stored_profile == current_profile:
                return Path(stored_path)
            if not stored_profile and self.engine.accepts_legacy_default_cache:
                # v0.2.0 did not persist a profile. Its fixed defaults are known,
                # so keep that audio and upgrade the cache metadata in place.
                self.store.mark_audio_ready(entry.sequence, stored_path, current_profile)
                return Path(stored_path)
        target = self.audio_dir / audio_filename(entry)
        try:
            result = self.engine.synthesize(entry, target)
            self.store.mark_audio_ready(entry.sequence, result, current_profile)
            return result
        except Exception as exc:
            self.store.mark_audio_failed(entry.sequence, str(exc))
            raise

    def generate_many(
        self,
        entries: Iterable[VocabularyEntry],
        progress: Callable[[int, int, VocabularyEntry, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> tuple[int, int]:
        items = list(entries)
        completed = 0
        failed = 0
        for index, entry in enumerate(items, start=1):
            if should_stop and should_stop():
                break
            state = "ready"
            try:
                self.ensure_audio(entry)
                completed += 1
            except Exception:
                failed += 1
                state = "failed"
            if progress:
                progress(index, len(items), entry, state)
        return completed, failed


def _prepare_windows_espeak_runtime(espeak_config_class):
    """Copy eSpeak assets to an ASCII path before loading them on Windows."""
    try:
        import espeakng_loader
    except ImportError as exc:
        raise TtsError("缺少 espeakng-loader。") from exc
    source_library = Path(espeakng_loader.get_library_path())
    source_data = Path(espeakng_loader.get_data_path())
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    runtime_root = local_app_data / "WordPdfVoice" / "runtime" / "espeakng"
    runtime_data = runtime_root / "espeak-ng-data"
    runtime_library = runtime_root / source_library.name
    marker = runtime_root / ".ready"
    if not marker.is_file():
        runtime_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_library, runtime_library)
        shutil.copytree(source_data, runtime_data, dirs_exist_ok=True)
        marker.write_text("ready\n", encoding="ascii")
    return espeak_config_class(
        lib_path=str(runtime_library),
        data_path=str(runtime_data),
    )
