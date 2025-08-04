#!/usr/bin/env python3

import subprocess
import os
import shutil
import yaml  # python3 -m pip install pyyaml
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict

CONFIG_FILE = 'bruniceps.yaml'

ARIA2C = "aria2c -s16 -x16 -k1M --seed-time=0 --file-allocation=none"
FFMPEG = "ffmpeg -hide_banner"

ENCODING_PROFILES = {
    'av1': ['-map', '0', '-c:v', 'libsvtav1', '-crf', '32', '-c:a', 'aac', '-ac', '2', '-c:s', 'copy'],
    'original': None
}

@dataclass
class Episode:
    suffix: str
    source: str
    encoding: str = 'av1'
    format: Optional[str] = None

@dataclass
class MediaEntry:
    key: str
    full_name: str
    episodes: List[Episode]

def parse_config(config: Dict) -> List[MediaEntry]:
    entries = []

    for media_type in ('tv', 'movie'):
        for key, val in config.get(media_type, {}).items():
            episodes_raw = val.get('Episodes') or []
            episodes = [Episode(**ep) for ep in episodes_raw]
            entries.append(MediaEntry(key=key, full_name=val['FullName'], episodes=episodes))

    return entries

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def file_exists_with_basename(directory: Path, base_name: str) -> bool:
    return any(f.stem == base_name for f in directory.iterdir() if f.is_file())

def download_source(source_url, base_download_dir, task_id):
    task_dir = Path(base_download_dir) / task_id
    ensure_dir(task_dir)
    print(f"Downloading: {source_url} to {task_dir}")

    subprocess.run(ARIA2C.split() + [
        '--dir=' + str(task_dir),
        '--auto-file-renaming=false',
        '--allow-overwrite=true',
        #'--summary-interval=0',
        #'--show-console-readout=false',
        source_url
    ], check=True)

    files = list(task_dir.iterdir())
    if not files:
        raise FileNotFoundError("No files downloaded")

    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    return latest_file

def encode_video(input_path: str, output_path: str, profile: str, task_id: str):
    print(f"[{task_id}] Encoding: {input_path} -> {output_path} with profile {profile}")
    encoding_args = ENCODING_PROFILES.get(profile)
    if not encoding_args:
        shutil.copy(input_path, output_path)
    else:
        subprocess.run(FFMPEG.split() + ['-i', input_path] + encoding_args + [output_path], check=True)

def process_episode(entry: MediaEntry, ep: Episode, target_dir: Path, downloaded_dir: Path, encoded_dir: Path):
    task_id = f"{entry.key}_{ep.suffix}"
    base_filename = f"{entry.full_name} {ep.suffix}"

    if file_exists_with_basename(target_dir, base_filename):
        print(f"[{task_id}] Skipping {base_filename}, already exists in {target_dir}.")
        return

    print(f"[{task_id}] Downloading episode {base_filename} to: {downloaded_dir}")
    input_file = download_source(ep.source, downloaded_dir, task_id)

    output_ext = ep.format if ep.format else input_file.suffix.lstrip('.')
    output_encoded = encoded_dir / f"{input_file.stem}_encoded.{output_ext}"
    final_output_path = target_dir / f"{base_filename}.{output_ext}"

    encode_video(str(input_file), str(output_encoded), profile=ep.encoding, task_id=task_id)

    ensure_dir(target_dir)
    shutil.move(str(output_encoded), str(final_output_path))
    print(f"[{task_id}] Moved to {final_output_path}")

    input_file.unlink()
    try:
        input_file.parent.rmdir()
    except Exception:
        pass

def process_all_entries(entries: List[MediaEntry], tv_dir: Path, movie_dir: Path, downloaded_dir: Path, encoded_dir: Path):
    for entry in entries:
        target_root = tv_dir if entry.key in config.get('tv', {}) else movie_dir
        target_dir = target_root / entry.full_name
        ensure_dir(target_dir)

        for ep in entry.episodes:
            process_episode(entry, ep, target_dir, downloaded_dir, encoded_dir)

def clean_tmp_dirs(*dirs):
    for d in dirs:
        print(f"Cleaning {d}")
        shutil.rmtree(d, ignore_errors=True)

def sync():
    global config
    config = load_config()
    entries = parse_config(config)

    tmp_dir = Path(config['tmpDir'])
    tv_dir = Path(config['tvDir'])
    movie_dir = Path(config['movieDir'])
    downloaded_dir = tmp_dir / 'downloaded'
    encoded_dir = tmp_dir / 'encoded'

    ensure_dir(downloaded_dir)
    ensure_dir(encoded_dir)

    process_all_entries(entries, tv_dir, movie_dir, downloaded_dir, encoded_dir)

    clean_tmp_dirs(encoded_dir)

def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'sync':
        sync()
    else:
        print("Usage: bruniceps sync")

if __name__ == '__main__':
    main()

