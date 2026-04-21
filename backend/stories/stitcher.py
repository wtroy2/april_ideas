"""
ffmpeg-based stitcher. Concatenates each scene's chosen Generation video into
one long video, honoring per-scene transitions, then applies the project-level
audio mix (original volume/fade + overlay music) to the final.

Implementation details:
  - Scenes joined with the `xfade` + `acrossfade` filters for crossfades
  - 'cut' = no crossfade (direct concat via concat filter)
  - 'fade_black' = xfade fadeblack + acrossfade
  - Final audio mix reuses assets.audio_mix.apply_audio_mix on the joined video

Requires ffmpeg on PATH. In dev: `brew install ffmpeg`.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger('stories')


# How long the xfade overlap lasts; must be < each clip's duration.
CROSSFADE_DURATION = 0.5


def stitch_scenes(
    *,
    scene_clips: List[Tuple[bytes, int, str]],
    # Each tuple: (video_bytes, scene_duration_seconds, transition_out)
    #   transition_out is the transition going INTO the NEXT scene:
    #   'cut' | 'crossfade' | 'fade_black' (last scene's transition is ignored)
) -> bytes:
    """Return concatenated video bytes (pre-audio-mix)."""
    if not scene_clips:
        raise ValueError('No scene clips to stitch')

    if not shutil.which('ffmpeg'):
        logger.warning('ffmpeg not on PATH — returning first clip only (stitching skipped)')
        return scene_clips[0][0]

    workdir = Path(tempfile.mkdtemp(prefix='critter_stitch_'))
    try:
        # 1) Write each scene to a file
        scene_paths = []
        for i, (video_bytes, _dur, _trans) in enumerate(scene_clips):
            p = workdir / f'scene_{i:02d}.mp4'
            p.write_bytes(video_bytes)
            scene_paths.append(p)

        # 2) All-cuts fast path: ffmpeg concat demuxer (no re-encode for video)
        all_cuts = all(
            scene_clips[i][2] == 'cut' for i in range(len(scene_clips) - 1)
        )
        out_path = workdir / 'stitched.mp4'

        if all_cuts or len(scene_clips) == 1:
            list_file = workdir / 'concat.txt'
            list_file.write_text(
                '\n'.join(f"file '{p.resolve()}'" for p in scene_paths) + '\n'
            )
            cmd = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', str(list_file),
                '-c:v', 'libx264', '-c:a', 'aac',
                '-preset', 'fast', '-crf', '23',
                str(out_path),
            ]
        else:
            # Crossfade path: use xfade + acrossfade between each pair
            cmd = ['ffmpeg', '-y']
            for p in scene_paths:
                cmd += ['-i', str(p)]
            cmd += ['-filter_complex', _build_xfade_filter(scene_clips)]
            cmd += ['-map', '[v]', '-map', '[a]']
            cmd += ['-c:v', 'libx264', '-c:a', 'aac', '-preset', 'fast', '-crf', '23']
            cmd += [str(out_path)]

        logger.info(f'Stitching {len(scene_clips)} scenes with ffmpeg')
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f'ffmpeg stitch failed (rc={result.returncode}): {result.stderr[-1500:]}')
            raise RuntimeError(f'ffmpeg failed: {result.stderr[-400:]}')

        return out_path.read_bytes()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _build_xfade_filter(scene_clips) -> str:
    """
    Construct a filter_complex string that chains xfade transitions.

    Example for 3 clips with crossfades (each 8s):
      [0:v]...[0v]; [1:v]...[1v]; [2:v]...[2v];
      [0:a]...[0a]; [1:a]...[1a]; [2:a]...[2a];
      [0v][1v]xfade=transition=fade:duration=0.5:offset=7.5[v01];
      [0a][1a]acrossfade=d=0.5[a01];
      [v01][2v]xfade=transition=fade:duration=0.5:offset=15.0[v];
      [a01][2a]acrossfade=d=0.5[a]
    """
    parts = []

    # Normalize each input video + audio stream
    for i in range(len(scene_clips)):
        parts.append(f'[{i}:v]setpts=PTS-STARTPTS[{i}v]')
        parts.append(f'[{i}:a]asetpts=PTS-STARTPTS[{i}a]')

    # Chain transitions. running_offset is cumulative play time of stitched clips
    # minus the xfade overlap (since each xfade eats CROSSFADE_DURATION of overlap).
    prev_v = '[0v]'
    prev_a = '[0a]'
    running_offset = scene_clips[0][1]  # duration of scene 0

    for i in range(1, len(scene_clips)):
        trans = scene_clips[i - 1][2]  # transition going OUT of scene i-1
        kind = {'fade_black': 'fadeblack', 'crossfade': 'fade', 'cut': 'fade'}.get(trans, 'fade')
        # For 'cut' we fall back to an instant xfade (d=0.01) so the timeline stays consistent
        duration = 0.01 if trans == 'cut' else CROSSFADE_DURATION

        v_out = f'[v{i:02d}]' if i < len(scene_clips) - 1 else '[v]'
        a_out = f'[a{i:02d}]' if i < len(scene_clips) - 1 else '[a]'
        xfade_offset = max(0.0, running_offset - duration)

        parts.append(
            f'{prev_v}[{i}v]xfade=transition={kind}:duration={duration}:offset={xfade_offset:.3f}{v_out}'
        )
        parts.append(
            f'{prev_a}[{i}a]acrossfade=d={duration}{a_out}'
        )

        prev_v, prev_a = v_out, a_out
        running_offset += scene_clips[i][1] - duration

    return ';'.join(parts)
