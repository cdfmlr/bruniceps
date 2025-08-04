#!/usr/bin/env python3

import subprocess
import os
import shutil
import yaml  # python3 -m pip install pyyaml
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict
import uuid
import sys
import os

DEFAULT_CONFIG_FILE = 'bruniceps.yaml'

@dataclass
class Episode:
    key: str
    source: str
    encoding: str = 'av1'
    format: Optional[str] = None

@dataclass
class Series:
    key: str
    title: str
    catalog: str
    episodes: List[Episode]

@dataclass
class Catalog:
    key: str
    base_dir: str

@dataclass
class MetaConfig:
    tmp_dir: str
    aria2c_cmd: str
    ffmpeg_cmd: str
    encoding_profiles: Dict[str, Optional[str]]
    catalogs: Dict[str, Catalog]

@dataclass
class Config:
    meta: MetaConfig
    series: List[Series]

def parse_config(raw: Dict) -> Config:
    meta_raw = raw.get('meta', {})
    catalogs_raw = meta_raw.get('catalogs', {})
    catalogs = {
        k: Catalog(key=k, base_dir=v['base_dir'])
        for k, v in catalogs_raw.items()
    }

    encoding_profiles = {}
    for item in meta_raw.get('encoding_profiles', []):
        encoding_profiles.update(item)

    meta = MetaConfig(
        tmp_dir=meta_raw['tmp_dir'],
        aria2c_cmd=meta_raw['aria2c_cmd'],
        ffmpeg_cmd=meta_raw['ffmpeg_cmd'],
        encoding_profiles=encoding_profiles,
        catalogs=catalogs
    )

    series_list = []
    for key, val in raw.get('series', {}).items():
        episodes_raw = val.get('episodes') or []
        episodes = [Episode(**ep) for ep in episodes_raw]
        series_list.append(Series(key=key, title=val['title'], catalog=val['catalog'], episodes=episodes))

    return Config(meta=meta, series=series_list)

def load_config(path=None) -> Config:
    config_path = path or os.environ.get("BRUNICEPS_CONFIG", DEFAULT_CONFIG_FILE)
    with open(config_path, 'r') as f:
        raw = yaml.safe_load(f)
    return parse_config(raw)

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def file_exists_with_basename(directory: Path, base_name: str) -> bool:
    return any(f.stem == base_name for f in directory.iterdir() if f.is_file())

def download_source(source_url, task_dir: Path, aria2c_cmd: str):
    ensure_dir(task_dir)
    print(f"Downloading: {source_url} to {task_dir}")

    subprocess.run(aria2c_cmd.split() + [
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

def encode_video(input_path: str, output_path: str, profile: str, task_id: str, ffmpeg_cmd: str, encoding_profiles: Dict[str, Optional[str]]):
    print(f"[{task_id}] Encoding: {input_path} -> {output_path} with profile {profile}")
    encoding_args = encoding_profiles.get(profile)
    if not encoding_args:
        shutil.copy(input_path, output_path)
    else:
        subprocess.run(ffmpeg_cmd.split() + ['-i', input_path] + encoding_args.split() + [output_path], check=True)

def process_episode(series: Series, ep: Episode, catalog: Catalog, meta: MetaConfig):
    task_id = f"{series.key}_{ep.key}"
    base_filename = f"{series.title} {ep.key}"

    target_dir = Path(catalog.base_dir) / series.title
    ensure_dir(target_dir)

    if file_exists_with_basename(target_dir, base_filename):
        print(f"[{task_id}] Skipping {base_filename}, already exists in {target_dir}.")
        return

    task_dir = Path(meta.tmp_dir) / task_id
    downloaded_dir = task_dir / "downloaded"
    encoded_dir = task_dir / "encoded"
    ensure_dir(downloaded_dir)
    ensure_dir(encoded_dir)

    input_file = download_source(ep.source, downloaded_dir, meta.aria2c_cmd)
    output_ext = ep.format if ep.format else input_file.suffix.lstrip('.')
    output_encoded = encoded_dir / f"{input_file.stem}_encoded.{output_ext}"
    final_output_path = target_dir / f"{base_filename}.{output_ext}"

    encode_video(str(input_file), str(output_encoded), ep.encoding, task_id, meta.ffmpeg_cmd, meta.encoding_profiles)

    shutil.move(str(output_encoded), str(final_output_path))
    print(f"[{task_id}] Moved to {final_output_path}")

    input_file.unlink()
    try:
        input_file.parent.rmdir()
    except Exception:
        pass

def sync(config: Config):
    for series in config.series:
        catalog = config.meta.catalogs[series.catalog]
        for ep in series.episodes:
            process_episode(series, ep, catalog, config.meta)

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["sync"], help="Command to run")
    parser.add_argument("-c", "--config", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.command == "sync":
        sync(config)

if __name__ == '__main__':
    main()

