#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import List, Optional, Dict

import yaml  # python3 -m pip install pyyaml

DEFAULT_CONFIG_FILE = 'bruniceps.yaml'
DEFAULT_ARIA2C_CMD = "aria2c"
DEFAULT_FFMPEG_CMD = "ffmpeg"
DEFAULT_TMP_DIR = Path(tempfile.gettempdir()) / "bruniceps"
DEFAULT_ENCODING_PROFILES = {
    "default": "-map 0 -c:v libsvtav1 -crf 32 -c:a aac -ac 2 -c:s copy",  # av1
    "original": None
}
CONFIG_ENV_VAR = "BRUNICEPS_CONFIG"
# splitter to multiple config files
CONFIG_PATH_SPLITTER = ","

print = partial(print, flush=True)


@dataclass
class Episode:
    key: str
    source: str
    encoding: str = 'default'
    format: Optional[str] = None
    dir: Optional[Path] = None  # episode.dir overrides series.dir and the default {catalog.dir}/{series.title}


@dataclass
class Series:
    key: str
    title: str
    catalog: str
    dir: Optional[Path]  # series.dir overrides the default {catalog.dir}/{series.title}
    episodes: List[Episode]


@dataclass
class Catalog:
    key: str
    dir: Path


@dataclass
class MetaConfig:
    tmp_dir: Path
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
        k: Catalog(key=k, dir=Path(v['dir']))
        for k, v in catalogs_raw.items()
    }

    encoding_profiles = DEFAULT_ENCODING_PROFILES.copy()
    for item in meta_raw.get('encoding_profiles', []):
        encoding_profiles.update(item)

    tmp_dir = Path(meta_raw.get('tmp_dir') or DEFAULT_TMP_DIR)

    meta = MetaConfig(
        tmp_dir=tmp_dir,
        aria2c_cmd=meta_raw.get('aria2c_cmd', DEFAULT_ARIA2C_CMD),
        ffmpeg_cmd=meta_raw.get('ffmpeg_cmd', DEFAULT_FFMPEG_CMD),
        encoding_profiles=encoding_profiles,
        catalogs=catalogs
    )

    series_list = []
    for key, val in raw.get('series', {}).items():
        episodes_raw = val.get('episodes') or []

        series_dir = val.get('dir', None)
        if series_dir is not None:
            series_dir = Path(series_dir)

        episodes = [Episode(**ep) for ep in episodes_raw]

        def ensure_episode_dir(ep: Episode) -> Episode:
            if ep.dir is not None:
                ep.dir = Path(ep.dir)
            return ep

        episodes = list(map(ensure_episode_dir, episodes))

        series_list.append(Series(
            key=key,
            title=val['title'],
            catalog=val['catalog'],
            dir=series_dir,
            episodes=episodes))

    return Config(meta=meta, series=series_list)


def load_config(paths: str) -> Config:
    """
    load_config read YAML files in paths.
    Multiple config supported by paths str split by comma, files will be merged
    in the order (later is prior).

    :arg paths: a str of "path/to/config-file-0.yaml,path/to/config-file-1.yaml,..."
    """
    raw = {}
    for config_path in paths.split(CONFIG_PATH_SPLITTER):
        config_path = config_path.strip()
        # tolerant towards tailing "," and ",," typo
        # should be friendly to `-c "$(find config -type f -name '*.yaml' | tr '\n' ',')"` and `-c "$(ls -xm *.yaml)"`.
        if not config_path:
            continue
        with open(config_path, 'r') as f:
            part = yaml.safe_load(f)
            raw.update(part)

    return parse_config(raw)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def file_exists_with_basename(directory: Path, base_name: str) -> bool:
    return any(f.stem == base_name for f in directory.iterdir() if f.is_file())


def download_source(source_url, output_dir: Path, aria2c_cmd: str) -> Path:
    subprocess.run(aria2c_cmd.split() + [
        '--dir=' + str(output_dir),
        '--auto-file-renaming=false',
        '--allow-overwrite=true',
        # '--summary-interval=0',
        # '--show-console-readout=false',
        source_url
    ], check=True)

    files = list(output_dir.iterdir())
    if not files:
        raise FileNotFoundError("No files downloaded")

    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    return latest_file


def encode_video(input_path: Path, output_path: Path, encoding_args: Optional[str], ffmpeg_cmd: str):
    if not encoding_args:
        shutil.copy(input_path, output_path)
    else:
        subprocess.run(ffmpeg_cmd.split() + ['-i', str(input_path)] + encoding_args.split() + [str(output_path)],
                       check=True)


def clear_task_dir(task_dir: Path):
    try:
        shutil.rmtree(task_dir)
    except Exception as e:
        print(f"Warning: Failed to clean temp dir {task_dir}: {e}")


def process_episode(ep: Episode, series: Series, catalog: Catalog, meta: MetaConfig):
    task_id = f"{series.key}-{ep.key}"

    # 0. Check if already exists. 

    base_filename = f"{series.title} {ep.key}"

    target_dir = Path(catalog.dir) / series.title
    if series.dir:
        target_dir = Path(series.dir)
    if ep.dir:
        target_dir = Path(ep.dir)

    ensure_dir(target_dir)

    if file_exists_with_basename(target_dir, base_filename):
        print(f"[{task_id}] Skipping, target ({base_filename}) already exists in {target_dir}.")
        return

    # 1. Download it

    task_dir = Path(meta.tmp_dir) / task_id

    downloaded_dir = task_dir / "downloaded"
    ensure_dir(downloaded_dir)

    print(f"[{task_id}] Downloading to {downloaded_dir} from {ep.source} by {meta.aria2c_cmd}")
    downloaded_file = download_source(ep.source, downloaded_dir, meta.aria2c_cmd)

    # 2. Encode it

    encoded_dir = task_dir / "encoded"
    ensure_dir(encoded_dir)

    ext = ep.format if ep.format else downloaded_file.suffix.lstrip('.')
    encoded_file = encoded_dir / f"{downloaded_file.stem}_encoded.{ext}"

    encoding_args = meta.encoding_profiles.get(ep.encoding)

    print(f"[{task_id}] Encoding {downloaded_file} to {encoded_file} by {meta.ffmpeg_cmd}")
    encode_video(downloaded_file, encoded_file, encoding_args, meta.ffmpeg_cmd)

    # 3. Move it to the target

    target_file = target_dir / f"{base_filename}.{ext}"

    print(f"[{task_id}] Moving {encoded_file} to {target_file}")
    shutil.copy(str(encoded_file), str(target_file))

    print(f"[{task_id}] Done: {target_file}")

    # 4. Clear the tmp dir

    print(f"[{task_id}] Clearing temp task working dir: {task_dir}")
    clear_task_dir(task_dir)


def sync(config: Config):
    for series in config.series:
        catalog = config.meta.catalogs[series.catalog]
        for ep in series.episodes:
            process_episode(ep, series, catalog, config.meta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["sync"], help="Command to run")
    parser.add_argument("-c", "--config", help="Path to config file, "
                                               "multiple files (split by comma) are supported (later is prior, e.g. -c \"base.yaml,override.yaml\"), "
                                               "defaults to \"bruniceps.yaml\"")
    args = parser.parse_args()

    config_paths = args.config or os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_FILE
    config = load_config(config_paths)

    if args.command == "sync":
        sync(config)


if __name__ == '__main__':
    main()
