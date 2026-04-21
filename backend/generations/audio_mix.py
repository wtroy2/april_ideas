"""
ffmpeg-based audio mixer for generated videos.

Composes:
  - The original Veo-generated audio (volume + fade in/out)
  - An optional uploaded music track (start offset, volume + fade in/out)

The video stream is copied through unchanged — we only re-encode audio. That
keeps things fast (no GPU needed) and avoids re-compressing the visual.

Requires ffmpeg installed on the host (`brew install ffmpeg` locally,
`apt-get install ffmpeg` in the Dockerfile).
"""

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger('generations')


@dataclass
class AudioMixSettings:
    """All the knobs the user can turn for one video's audio mix."""
    duration_seconds: float

    # Veo's native audio (scene sounds it generated)
    original_volume: float = 0.7              # 0.0 (mute) → 1.0 (full)
    original_fade_in_seconds: float = 0.0
    original_fade_out_seconds: float = 0.5

    # Uploaded music track (optional)
    music_path: Optional[str] = None          # local file path
    music_start_offset_seconds: float = 0.0   # where in the track to begin
    music_volume: float = 0.5                 # 0.0 (mute) → 1.0 (full)
    music_fade_in_seconds: float = 0.5
    music_fade_out_seconds: float = 1.0


def ffmpeg_available() -> bool:
    return shutil.which('ffmpeg') is not None


def apply_audio_mix(video_bytes: bytes, settings: AudioMixSettings) -> bytes:
    """
    Run ffmpeg with the given mix and return the resulting MP4 bytes.

    Pure function over bytes → bytes; the caller handles GCS upload/download.
    Falls back to returning the original bytes (with a warning) if ffmpeg
    isn't installed, so the pipeline never hard-fails on a missing binary.
    """
    if not ffmpeg_available():
        logger.warning('ffmpeg not on PATH — skipping audio mix, returning raw video')
        return video_bytes

    duration = max(0.1, float(settings.duration_seconds))

    # Write inputs to temp files; ffmpeg can't read from stdin reliably for muxed inputs
    workdir = tempfile.mkdtemp(prefix='critter_mix_')
    try:
        in_video = Path(workdir) / 'in.mp4'
        in_video.write_bytes(video_bytes)

        out_video = Path(workdir) / 'out.mp4'

        cmd = ['ffmpeg', '-y', '-i', str(in_video)]
        if settings.music_path:
            cmd += ['-i', settings.music_path]

        filter_chains, audio_label = _build_filter_complex(settings, duration)
        cmd += ['-filter_complex', filter_chains]
        cmd += ['-map', '0:v', '-map', f'[{audio_label}]']
        cmd += ['-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k']
        # Trim final output to original video duration
        cmd += ['-t', f'{duration}']
        cmd += [str(out_video)]

        logger.info(f'Running ffmpeg: {" ".join(cmd)}')
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f'ffmpeg failed (rc={result.returncode}): {result.stderr[-1000:]}')
            return video_bytes

        return out_video.read_bytes()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _build_filter_complex(s: AudioMixSettings, duration: float) -> tuple[str, str]:
    """
    Build the -filter_complex string for ffmpeg.

    Branches:
      A) Music + original audio  → mix the two
      B) Music only (original muted)
      C) Original only (no music)
      D) Both muted → silent audio track
    """
    has_music = bool(s.music_path)
    orig_muted = s.original_volume <= 0.0
    music_muted = s.music_volume <= 0.0

    chains = []

    # --- original audio chain ---
    if not orig_muted:
        orig_fade_out_start = max(0.0, duration - s.original_fade_out_seconds)
        orig_chain = (
            f'[0:a]'
            f'volume={s.original_volume:.4f},'
            f'afade=t=in:d={s.original_fade_in_seconds:.3f},'
            f'afade=t=out:st={orig_fade_out_start:.3f}:d={s.original_fade_out_seconds:.3f}'
            f'[orig]'
        )
        chains.append(orig_chain)

    # --- music chain ---
    if has_music and not music_muted:
        music_fade_out_start = max(0.0, duration - s.music_fade_out_seconds)
        music_chain = (
            f'[1:a]'
            f'atrim=start={s.music_start_offset_seconds:.3f}:duration={duration:.3f},'
            f'asetpts=PTS-STARTPTS,'
            f'volume={s.music_volume:.4f},'
            f'afade=t=in:d={s.music_fade_in_seconds:.3f},'
            f'afade=t=out:st={music_fade_out_start:.3f}:d={s.music_fade_out_seconds:.3f}'
            f'[music]'
        )
        chains.append(music_chain)

    # --- combine ---
    have_orig = not orig_muted
    have_music = has_music and not music_muted

    if have_orig and have_music:
        chains.append('[orig][music]amix=inputs=2:duration=first:dropout_transition=0[a]')
        return ';'.join(chains), 'a'
    if have_orig:
        # Just rename the orig stream to the final label
        chains.append('[orig]anull[a]')
        return ';'.join(chains), 'a'
    if have_music:
        chains.append('[music]anull[a]')
        return ';'.join(chains), 'a'

    # Both muted — emit a silent audio track at the right duration
    silent = (
        f'aevalsrc=0:d={duration:.3f}:s=44100,aformat=channel_layouts=stereo[a]'
    )
    return silent, 'a'
